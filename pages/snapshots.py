"""
Página Snapshots — Registro de posições projetadas e comparativo realizado vs previsto.

Fluxo:
  1. Sexta-feira (ou quando necessário): tirar um snapshot → salva posição + FC projetado
  2. Semana seguinte: abrir comparativo → ver o que foi projetado vs o que o sistema mostra agora
     para o mesmo período (lançamentos que se realizaram, atrasaram ou mudaram de valor)
"""

import json
import streamlit as st
import pandas as pd
from datetime import date, timedelta
from collections import defaultdict
import sys, os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import db
import auth


# ─────────────────────────────────────────────────────────────────────────────
# CAPTURA DO SNAPSHOT
# ─────────────────────────────────────────────────────────────────────────────
def _capturar_dados(hoje: date, inc_alta: bool, inc_media: bool,
                    inc_fci: bool, inc_fcf: bool, erp_corte: bool,
                    horizonte_dias: int) -> dict:
    """
    Coleta todos os dados relevantes do momento atual e retorna um dict
    pronto para ser serializado como JSON no banco.
    """
    posicao = db.get_posicao_consolidada()

    # FC diário para os próximos N dias úteis (horizonte)
    dt_fim_fc = str(hoje + timedelta(days=horizonte_dias + 14))  # margem para feriados
    fc_bruto  = db.fc_diario(str(hoje), dt_fim_fc,
                             inc_alta, inc_media,
                             erp_corte_status=erp_corte,
                             inc_fci=inc_fci, inc_fcf=inc_fcf)

    # Agrega por data (vencimento)
    por_data: dict = defaultdict(lambda: {"entradas": 0.0, "saidas": 0.0, "itens": []})
    for r in fc_bruto:
        dt  = str(r.get("vencimento") or "")[:10]
        vf  = r.get("valor_final") or 0
        if vf > 0:
            por_data[dt]["entradas"] += vf
        else:
            por_data[dt]["saidas"]   += vf
        por_data[dt]["itens"].append({
            "origem":       r.get("origem"),
            "operacao":     r.get("operacao"),
            "razao_social": r.get("razao_social"),
            "descricao":    r.get("descricao"),
            "valor_final":  vf,
        })

    fc_por_data = []
    saldo_acc   = posicao["total"]
    for dt in sorted(por_data.keys()):
        e = por_data[dt]["entradas"]
        s = por_data[dt]["saidas"]
        saldo_acc += e + s
        fc_por_data.append({
            "data":            dt,
            "entradas":        round(e, 2),
            "saidas":          round(s, 2),
            "saldo_dia":       round(e + s, 2),
            "saldo_acumulado": round(saldo_acc, 2),
            "itens":           por_data[dt]["itens"],
        })

    # Posições projetadas (30/60/90 dias)
    def _proj(dias):
        dt_f  = str(hoje + timedelta(days=dias))
        dados = db.fc_diario(str(hoje), dt_f, inc_alta, inc_media,
                             erp_corte_status=erp_corte, inc_fci=inc_fci, inc_fcf=inc_fcf)
        return posicao["total"] + sum(r["valor_final"] or 0 for r in dados)

    # FUP
    dt_fim_ano = str(date(hoje.year, 12, 31))
    fup_a  = db.listar_fup(dt_ini=str(hoje), dt_fim=dt_fim_ano, prob="ALTA")
    fup_m  = db.listar_fup(dt_ini=str(hoje), dt_fim=dt_fim_ano, prob="MEDIA")
    fup_b  = db.listar_fup(dt_ini=str(hoje), dt_fim=dt_fim_ano, prob="BAIXA")

    def _sv(lst):
        return sum(r.get("valor_brl") or r.get("valor") or 0 for r in lst)

    return {
        "data_ref":   str(hoje),
        "parametros": {
            "inc_alta":  inc_alta,
            "inc_media": inc_media,
            "inc_fci":   inc_fci,
            "inc_fcf":   inc_fcf,
            "erp_corte": erp_corte,
            "horizonte_dias": horizonte_dias,
        },
        "posicao_consolidada": {
            "total_bancos":      round(posicao["total_bancos"], 2),
            "total_cambios_brl": round(posicao["total_cambios_brl"], 2),
            "total":             round(posicao["total"], 2),
        },
        "projecao": {
            "30d": round(_proj(30), 2),
            "60d": round(_proj(60), 2),
            "90d": round(_proj(90), 2),
        },
        "saldos_bancarios": [
            {"banco": r["banco"], "tipo": r.get("tipo"), "saldo": r["saldo"], "data": r["data"]}
            for r in db.listar_saldos_recentes()
        ],
        "cambios_disponiveis": [
            {"descricao": c.get("descricao"), "moeda": c["moeda"],
             "valor_me": c["valor_me"], "data_entrada": c.get("data_entrada")}
            for c in db.listar_cambios(status="DISPONIVEL")
        ],
        "fup": {
            "alta":  round(_sv(fup_a), 2),
            "media": round(_sv(fup_m), 2),
            "baixa": round(_sv(fup_b), 2),
        },
        "fc_projetado": fc_por_data,
    }


# ─────────────────────────────────────────────────────────────────────────────
# COMPARATIVO: projetado (snapshot) vs atual (re-consulta do banco)
# ─────────────────────────────────────────────────────────────────────────────
def _comparativo(snap: dict) -> pd.DataFrame:
    """
    Para cada data que estava no snapshot, re-consulta o FC atual
    e calcula a variação (realizado - projetado).
    """
    dados   = snap["dados"]
    params  = dados.get("parametros", {})
    data_ref = date.fromisoformat(dados["data_ref"])

    fc_proj = dados.get("fc_projetado", [])
    if not fc_proj:
        return pd.DataFrame()

    datas_proj = sorted({r["data"] for r in fc_proj})
    dt_ini_q   = datas_proj[0]
    dt_fim_q   = datas_proj[-1]

    # Re-consulta do banco para o mesmo período
    fc_atual_bruto = db.fc_diario(
        dt_ini_q, dt_fim_q,
        params.get("inc_alta",  True),
        params.get("inc_media", False),
        erp_corte_status=params.get("erp_corte", True),
        inc_fci=params.get("inc_fci", True),
        inc_fcf=params.get("inc_fcf", True),
    )

    por_data_atual: dict = defaultdict(lambda: {"entradas": 0.0, "saidas": 0.0})
    for r in fc_atual_bruto:
        dt = str(r.get("vencimento") or "")[:10]
        vf = r.get("valor_final") or 0
        if vf > 0:
            por_data_atual[dt]["entradas"] += vf
        else:
            por_data_atual[dt]["saidas"]   += vf

    # Monta o projetado por data
    proj_map = {r["data"]: r for r in fc_proj}

    rows = []
    saldo_proj_acc  = dados["posicao_consolidada"]["total"]
    posicao_atual   = db.get_posicao_consolidada()
    saldo_atual_acc = posicao_atual["total"]

    for dt in sorted(set(list(proj_map.keys()) + list(por_data_atual.keys()))):
        p = proj_map.get(dt, {"entradas": 0, "saidas": 0, "saldo_dia": 0})
        a = por_data_atual.get(dt, {"entradas": 0.0, "saidas": 0.0})

        e_proj = p.get("entradas", 0) or 0
        s_proj = p.get("saidas",   0) or 0
        e_atu  = a["entradas"]
        s_atu  = a["saidas"]

        saldo_proj_acc  += e_proj + s_proj
        saldo_atual_acc += e_atu  + s_atu

        rows.append({
            "Data":             dt,
            "Entradas Proj.":   e_proj,
            "Entradas Atual":   e_atu,
            "Δ Entradas":       e_atu - e_proj,
            "Saídas Proj.":     abs(s_proj),
            "Saídas Atual":     abs(s_atu),
            "Δ Saídas":         abs(s_atu) - abs(s_proj),
            "Saldo Proj. Acum.":  saldo_proj_acc,
            "Saldo Atual Acum.":  saldo_atual_acc,
            "Δ Posição":          saldo_atual_acc - saldo_proj_acc,
        })

    return pd.DataFrame(rows)


# ─────────────────────────────────────────────────────────────────────────────
# RENDER
# ─────────────────────────────────────────────────────────────────────────────
def render():
    st.title("📸 Snapshots — Previsto vs Realizado")
    st.markdown(
        "Registre a posição projetada em um momento (ex: sexta-feira) e "
        "compare na semana seguinte o que foi previsto com o que de fato ocorreu."
    )

    can_edit = st.session_state.get("can_edit", True)
    usuario  = auth.get_display_name() or "Sistema"
    hoje     = date.today()

    tab_tirar, tab_hist, tab_comp = st.tabs([
        "📸 Tirar Snapshot", "📋 Histórico", "🔍 Comparativo Previsto vs Realizado"
    ])

    # ─── ABA: TIRAR SNAPSHOT ─────────────────────────────────────────────
    with tab_tirar:
        st.subheader("Registrar posição atual como snapshot")
        st.info(
            "O snapshot captura: posição consolidada, projeção 30/60/90 dias, "
            "saldos bancários, câmbios disponíveis, FUP Vendas e o FC diário projetado "
            "para o horizonte escolhido. Use os mesmos parâmetros da análise semanal."
        )

        if not can_edit:
            st.warning("Apenas administradores podem tirar snapshots.")
            return

        with st.form("form_snapshot"):
            col1, col2 = st.columns(2)
            with col1:
                data_ref    = st.date_input("Data de referência", value=hoje)
                descricao   = st.text_input(
                    "Descrição", value=f"Fechamento {hoje.strftime('%d/%m/%Y')}",
                    placeholder="Ex: Fechamento semana 16/04"
                )
                horizonte   = st.number_input(
                    "Horizonte de projeção (dias corridos)", min_value=7, max_value=120,
                    value=45, step=7,
                    help="Quantos dias de FC serão capturados no snapshot."
                )
            with col2:
                inc_alta  = st.checkbox("Incluir ALTA",  value=True)
                inc_media = st.checkbox("Incluir MEDIA", value=False)
                inc_fci   = st.checkbox("Incluir FCI",   value=True)
                inc_fcf   = st.checkbox("Incluir FCF",   value=True)
                erp_corte = st.checkbox(
                    "Excluir PENDENTES anteriores à data base", value=True
                )

            submitted = st.form_submit_button("📸 Tirar Snapshot", type="primary")

        if submitted:
            with st.spinner("Capturando dados..."):
                try:
                    dados = _capturar_dados(
                        data_ref, inc_alta, inc_media, inc_fci, inc_fcf,
                        erp_corte, int(horizonte)
                    )
                    snap_id = db.salvar_snapshot(
                        str(data_ref), descricao, usuario, dados
                    )
                    st.success(f"✅ Snapshot #{snap_id} salvo — **{descricao}**")

                    pos = dados["posicao_consolidada"]
                    c1, c2, c3, c4, c5 = st.columns(5)
                    c1.metric("Posição Consolidada", f"R$ {pos['total']:,.2f}")
                    c2.metric("Projeção 30d",        f"R$ {dados['projecao']['30d']:,.2f}")
                    c3.metric("Projeção 60d",        f"R$ {dados['projecao']['60d']:,.2f}")
                    c4.metric("FUP ALTA",            f"R$ {dados['fup']['alta']:,.2f}")
                    c5.metric("Dias capturados",     str(len(dados["fc_projetado"])))
                except Exception as e:
                    st.error(f"Erro ao tirar snapshot: {e}")
                    import traceback; st.code(traceback.format_exc())

    # ─── ABA: HISTÓRICO ───────────────────────────────────────────────────
    with tab_hist:
        st.subheader("Snapshots registrados")
        snaps = db.listar_snapshots()

        if not snaps:
            st.info("Nenhum snapshot registrado ainda.")
        else:
            df_snaps = pd.DataFrame(snaps)
            df_snaps.columns = ["ID", "Data Ref.", "Descrição", "Usuário", "Criado em"]
            st.dataframe(df_snaps, use_container_width=True, hide_index=True)

            if can_edit:
                st.markdown("---")
                st.markdown("**Excluir snapshot**")
                ids_disp = {f"#{s['id']} — {s['descricao']} ({s['data_ref']})": s["id"]
                            for s in snaps}
                sel_del = st.selectbox("Selecione", list(ids_disp.keys()),
                                       key="sel_del_snap")
                if st.button("🗑️ Excluir", type="secondary", key="btn_del_snap"):
                    db.excluir_snapshot(ids_disp[sel_del])
                    st.success("Snapshot excluído.")
                    st.rerun()

    # ─── ABA: COMPARATIVO ────────────────────────────────────────────────
    with tab_comp:
        st.subheader("Comparativo — Previsto vs Realizado")
        snaps = db.listar_snapshots()

        if not snaps:
            st.info("Nenhum snapshot disponível. Tire um snapshot primeiro.")
            return

        ids_disp = {f"#{s['id']} — {s['descricao']} ({s['data_ref']})": s["id"]
                    for s in snaps}
        sel = st.selectbox("Snapshot base (projetado)", list(ids_disp.keys()),
                           key="sel_comp_snap")
        snap = db.obter_snapshot(ids_disp[sel])

        if not snap:
            st.error("Snapshot não encontrado.")
            return

        dados    = snap["dados"]
        data_ref = dados.get("data_ref", "—")
        pos_snap = dados.get("posicao_consolidada", {})
        proj_    = dados.get("projecao", {})
        fup_snap = dados.get("fup", {})
        params   = dados.get("parametros", {})

        st.caption(
            f"Snapshot de **{data_ref}** · "
            f"Horizonte: {params.get('horizonte_dias', '?')} dias · "
            f"Parâmetros: ALTA={'✅' if params.get('inc_alta') else '❌'} "
            f"MEDIA={'✅' if params.get('inc_media') else '❌'} "
            f"FCI={'✅' if params.get('inc_fci') else '❌'} "
            f"FCF={'✅' if params.get('inc_fcf') else '❌'}"
        )

        # ── KPIs snapshot vs atual ────────────────────────────────────────
        st.markdown("#### Posição Consolidada")
        posicao_atual = db.get_posicao_consolidada()

        col_a, col_b, col_c = st.columns(3)
        delta_pos = posicao_atual["total"] - pos_snap.get("total", 0)
        col_a.metric("Prevista (snapshot)",  f"R$ {pos_snap.get('total', 0):,.2f}")
        col_b.metric("Atual",                f"R$ {posicao_atual['total']:,.2f}",
                     delta=f"R$ {delta_pos:,.2f}",
                     delta_color="normal")
        col_c.metric("Variação",             f"R$ {delta_pos:,.2f}",
                     delta=f"{'▲' if delta_pos >= 0 else '▼'} {abs(delta_pos/pos_snap['total']*100):.1f}%" if pos_snap.get("total") else "—",
                     delta_color="normal")

        st.markdown("#### Projeções")
        col_p1, col_p2, col_p3 = st.columns(3)
        for col, label, key in [(col_p1, "30 dias", "30d"),
                                 (col_p2, "60 dias", "60d"),
                                 (col_p3, "90 dias", "90d")]:
            def _proj_atual(dias):
                dt_f  = str(hoje + timedelta(days=dias))
                dados_fc = db.fc_diario(str(hoje), dt_f,
                                        params.get("inc_alta", True),
                                        params.get("inc_media", False),
                                        erp_corte_status=params.get("erp_corte", True),
                                        inc_fci=params.get("inc_fci", True),
                                        inc_fcf=params.get("inc_fcf", True))
                return posicao_atual["total"] + sum(r["valor_final"] or 0 for r in dados_fc)

            dias_map = {"30d": 30, "60d": 60, "90d": 90}
            p_snap   = proj_.get(key, 0)
            p_atual  = _proj_atual(dias_map[key])
            col.metric(f"Projeção {label}",
                       f"R$ {p_atual:,.2f}",
                       delta=f"R$ {p_atual - p_snap:,.2f} vs previsto",
                       delta_color="normal")

        st.markdown("#### FUP Vendas")
        col_f1, col_f2, col_f3 = st.columns(3)
        dt_fim_ano = str(date(hoje.year, 12, 31))
        fup_a_atu = sum(r.get("valor_brl") or r.get("valor") or 0
                        for r in db.listar_fup(dt_ini=str(hoje), dt_fim=dt_fim_ano, prob="ALTA"))
        fup_m_atu = sum(r.get("valor_brl") or r.get("valor") or 0
                        for r in db.listar_fup(dt_ini=str(hoje), dt_fim=dt_fim_ano, prob="MEDIA"))
        fup_b_atu = sum(r.get("valor_brl") or r.get("valor") or 0
                        for r in db.listar_fup(dt_ini=str(hoje), dt_fim=dt_fim_ano, prob="BAIXA"))
        for col, label, key, atual in [
            (col_f1, "ALTA",  "alta",  fup_a_atu),
            (col_f2, "MEDIA", "media", fup_m_atu),
            (col_f3, "BAIXA", "baixa", fup_b_atu),
        ]:
            prev = fup_snap.get(key, 0)
            col.metric(f"FUP {label}",
                       f"R$ {atual:,.2f}",
                       delta=f"R$ {atual - prev:,.2f} vs previsto",
                       delta_color="normal")

        st.markdown("---")

        # ── Tabela de FC diário: previsto vs atual ────────────────────────
        st.markdown("#### Fluxo de Caixa Diário — Previsto vs Realizado")
        st.caption(
            "**Previsto**: FC capturado no snapshot.  "
            "**Atual**: o que o sistema mostra AGORA para o mesmo período. "
            "Itens que foram pagos/recebidos e baixados do ERP não aparecem no Atual."
        )

        with st.spinner("Calculando comparativo..."):
            try:
                df_comp = _comparativo(snap)
            except Exception as e:
                st.error(f"Erro ao calcular comparativo: {e}")
                import traceback; st.code(traceback.format_exc())
                df_comp = pd.DataFrame()

        if df_comp.empty:
            st.info("Sem dados de FC projetado neste snapshot.")
        else:
            # Formatação para exibição
            def _fmt(v):
                if v > 0:  return f"🟢 R$ {v:,.2f}"
                if v < 0:  return f"🔴 R$ {abs(v):,.2f}"
                return "R$ 0,00"
            def _fmt_delta(v):
                if v > 0:  return f"▲ R$ {v:,.2f}"
                if v < 0:  return f"▼ R$ {abs(v):,.2f}"
                return "—"

            df_show = df_comp.copy()
            df_show["Entradas Proj."]    = df_show["Entradas Proj."].map(lambda x: f"R$ {x:,.2f}")
            df_show["Entradas Atual"]    = df_show["Entradas Atual"].map(lambda x: f"R$ {x:,.2f}")
            df_show["Δ Entradas"]        = df_show["Δ Entradas"].map(_fmt_delta)
            df_show["Saídas Proj."]      = df_show["Saídas Proj."].map(lambda x: f"R$ {x:,.2f}")
            df_show["Saídas Atual"]      = df_show["Saídas Atual"].map(lambda x: f"R$ {x:,.2f}")
            df_show["Δ Saídas"]          = df_show["Δ Saídas"].map(_fmt_delta)
            df_show["Saldo Proj. Acum."] = df_show["Saldo Proj. Acum."].map(lambda x: _fmt(x))
            df_show["Saldo Atual Acum."] = df_show["Saldo Atual Acum."].map(lambda x: _fmt(x))
            df_show["Δ Posição"]         = df_show["Δ Posição"].map(_fmt_delta)

            st.dataframe(df_show, use_container_width=True, hide_index=True)

            # Gráfico de saldo acumulado
            st.markdown("#### Evolução do Saldo Acumulado")
            df_graf = df_comp[["Data", "Saldo Proj. Acum.", "Saldo Atual Acum."]].copy()
            df_graf = df_graf.set_index("Data")
            df_graf.columns = ["Previsto", "Atual"]
            st.line_chart(df_graf, height=280)

            # Export CSV
            csv = df_comp.to_csv(index=False).encode("utf-8")
            st.download_button(
                "⬇️ Exportar CSV",
                data=csv,
                file_name=f"comparativo_snap{snap['id']}_{hoje.strftime('%Y%m%d')}.csv",
                mime="text/csv",
            )
