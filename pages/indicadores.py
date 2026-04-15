"""
Página Indicadores — KPIs e posição de caixa projetada.
"""

import streamlit as st
import pandas as pd
from datetime import date, timedelta
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import db


def render():
    st.title("📈 Indicadores")
    st.markdown("KPIs de caixa, recebíveis, obrigações e projeção futura.")

    # ─── SALDOS BANCÁRIOS ─────────────────────────────────────────────────
    st.subheader("💳 Saldos Bancários")
    col_sb1, col_sb2 = st.columns([2, 1])

    with col_sb2:
        with st.expander("➕ Atualizar saldo"):
            with st.form("form_saldo"):
                banco = st.text_input("Banco / Conta")
                saldo = st.number_input("Saldo atual (R$)", step=0.01, format="%.2f")
                data_saldo = st.date_input("Data do saldo", value=date.today())
                if st.form_submit_button("💾 Salvar"):
                    db.salvar_saldo(banco, saldo, str(data_saldo))
                    st.success("Saldo salvo!")
                    st.rerun()

    saldos = db.listar_saldos_recentes()
    total_bancos = sum(r["saldo"] or 0 for r in saldos)

    with col_sb1:
        if saldos:
            cols_banco = st.columns(min(len(saldos), 4))
            for i, r in enumerate(saldos):
                cols_banco[i % 4].metric(
                    r["banco"],
                    f"R$ {r['saldo']:,.2f}",
                    f"em {r['data']}"
                )
        else:
            st.info("Nenhum saldo cadastrado. Use o painel ao lado para adicionar.")

    st.markdown(f"**Total em caixa:** `R$ {total_bancos:,.2f}`")
    st.markdown("---")

    hoje = date.today()
    cfg_corte = st.session_state.get("cfg_corte_status", True)

    # ─── PROJEÇÃO 2 SEMANAS (10 DIAS ÚTEIS) ──────────────────────────────
    st.subheader("📆 Projeção — Próximos 10 Dias Úteis")

    # ── Feriados nacionais brasileiros ────────────────────────────────────
    def _easter(year: int) -> date:
        a = year % 19; b = year // 100; c = year % 100
        d = b // 4;    e = b % 4;       f = (b + 8) // 25
        g = (b - f + 1) // 3
        h = (19 * a + b - d - g + 15) % 30
        i = c // 4;    k = c % 4
        l = (32 + 2 * e + 2 * i - h - k) % 7
        m = (a + 11 * h + 22 * l) // 451
        month = (h + l - 7 * m + 114) // 31
        day   = ((h + l - 7 * m + 114) % 31) + 1
        return date(year, month, day)

    def _feriados(anos):
        f = set()
        for ano in anos:
            f.update([
                date(ano, 1,  1),  date(ano, 4,  21), date(ano, 5,  1),
                date(ano, 9,  7),  date(ano, 10, 12), date(ano, 11, 2),
                date(ano, 11, 15), date(ano, 11, 20), date(ano, 12, 25),
            ])
            p = _easter(ano)
            f.update([
                p - timedelta(days=48),  # Carnaval 2a
                p - timedelta(days=47),  # Carnaval 3a
                p - timedelta(days=2),   # Sexta-feira Santa
                p + timedelta(days=60),  # Corpus Christi
            ])
        return f

    def _prox_util(d: date, fer: set) -> date:
        while d.weekday() >= 5 or d in fer:
            d += timedelta(days=1)
        return d

    def _ult_util_antes(d: date, fer: set) -> date:
        while d.weekday() >= 5 or d in fer:
            d -= timedelta(days=1)
        return d

    def _dt_efetiva(d: date, is_imposto: bool, fer: set) -> date:
        if d.weekday() < 5 and d not in fer:
            return d
        return _ult_util_antes(d, fer) if is_imposto else _prox_util(d, fer)

    # ── Base date e geração dos 10 dias úteis (sem feriados) ─────────────
    if saldos:
        try:
            default_base = date.fromisoformat(saldos[0]["data"])
        except Exception:
            default_base = hoje
    else:
        default_base = hoje

    base_date = st.date_input(
        "📅 Data base da projeção",
        value=default_base,
        key="proj2s_base_date",
        help="Os 10 dias úteis serão contados a partir desta data.",
    )

    # Calcula feriados para os anos necessários
    _anos_ref = {base_date.year, base_date.year + 1}
    fer_set = _feriados(_anos_ref)

    def _proximos_uteis(start: date, n: int, fer: set):
        dias, d = [], start
        while len(dias) < n:
            d += timedelta(days=1)
            if d.weekday() < 5 and d not in fer:
                dias.append(d)
        return dias

    DIAS_PT = ["Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"]

    inc_alta_2s  = st.checkbox("Incluir ALTA",  value=st.session_state.get("cfg_inc_alta",  True), key="proj2s_alta")
    inc_media_2s = st.checkbox("Incluir MEDIA", value=st.session_state.get("cfg_inc_media", False), key="proj2s_media")
    inc_fci_2s   = st.checkbox("Incluir FCI",   value=True, key="proj2s_fci")
    inc_fcf_2s   = st.checkbox("Incluir FCF",   value=True, key="proj2s_fcf")

    dias_uteis  = _proximos_uteis(base_date, 10, fer_set)
    dias_uteis_set = set(dias_uteis)

    # ── Busca range amplo e agrupa por data útil efetiva ─────────────────
    # +7 dias de margem para impostos em feriados/fim de semana após o último dia
    dt_busca_ini = base_date + timedelta(days=1)
    dt_busca_fim = dias_uteis[-1] + timedelta(days=7)

    todas_linhas = db.fc_diario(
        str(dt_busca_ini), str(dt_busca_fim),
        inc_alta_2s, inc_media_2s,
        erp_corte_status=cfg_corte,
        inc_fci=inc_fci_2s,
        inc_fcf=inc_fcf_2s,
    )

    from collections import defaultdict
    dia_map = defaultdict(lambda: {"entradas": 0.0, "saidas": 0.0})

    for linha in todas_linhas:
        try:
            dt_orig = date.fromisoformat(str(linha["vencimento"])[:10])
        except Exception:
            continue
        is_imp = (linha.get("imposto") or "").upper() == "SIM"
        dt_ef  = _dt_efetiva(dt_orig, is_imp, fer_set)
        if dt_ef not in dias_uteis_set:
            continue
        vf = linha.get("valor_final") or 0
        if vf > 0:
            dia_map[dt_ef]["entradas"] += vf
        else:
            dia_map[dt_ef]["saidas"]   += vf

    rows_proj = []
    saldo_acc = total_bancos
    for d in dias_uteis:
        info      = dia_map[d]
        entradas  = info["entradas"]
        saidas    = info["saidas"]
        saldo_dia = entradas + saidas
        saldo_acc += saldo_dia
        feriado_note = " 🎉" if d in fer_set else ""
        rows_proj.append({
            "Data":            d.strftime("%d/%m/%Y") + feriado_note,
            "Dia":             DIAS_PT[d.weekday()],
            "Entradas":        entradas,
            "Saídas":          abs(saidas),
            "Saldo do Dia":    saldo_dia,
            "Saldo Acumulado": saldo_acc,
        })

    df_proj = pd.DataFrame(rows_proj)

    def _fmt(v, color=True):
        if color:
            if v > 0:   return f"🟢 R$ {v:,.2f}"
            elif v < 0: return f"🔴 R$ {abs(v):,.2f}"
            else:       return "R$ 0,00"
        return f"R$ {v:,.2f}"

    df_show_proj = df_proj.copy()
    df_show_proj["Entradas"]        = df_show_proj["Entradas"].apply(lambda x: f"R$ {x:,.2f}")
    df_show_proj["Saídas"]          = df_show_proj["Saídas"].apply(lambda x: f"R$ {x:,.2f}")
    df_show_proj["Saldo do Dia"]    = df_show_proj["Saldo do Dia"].apply(_fmt)
    df_show_proj["Saldo Acumulado"] = df_show_proj["Saldo Acumulado"].apply(lambda x: _fmt(x, color=True))

    st.caption(f"Base: {base_date.strftime('%d/%m/%Y')} — saldo bancário R$ {total_bancos:,.2f}")
    st.dataframe(df_show_proj, use_container_width=True, hide_index=True)

    st.markdown("---")

    # ─── POSIÇÃO PROJETADA ─────────────────────────────────────────────────
    st.subheader("📅 Posição de Caixa Projetada")

    col_p1, col_p2, col_p3 = st.columns(3)
    inc_alta  = st.checkbox("Incluir ALTA no cálculo",  value=st.session_state.get("cfg_inc_alta",  True))
    inc_media = st.checkbox("Incluir MEDIA no cálculo", value=st.session_state.get("cfg_inc_media", False))
    inc_fci   = st.checkbox("Incluir FCI nas Provisões", value=True, key="ind_fci")
    inc_fcf   = st.checkbox("Incluir FCF nas Provisões", value=True, key="ind_fcf")

    for label, dias in [("30 dias", 30), ("60 dias", 60), ("90 dias", 90)]:
        dt_fim = str(hoje + timedelta(days=dias))
        dados = db.fc_diario(str(hoje), dt_fim, inc_alta, inc_media, erp_corte_status=cfg_corte,
                             inc_fci=inc_fci, inc_fcf=inc_fcf)
        fluxo = sum(r["valor_final"] or 0 for r in dados)
        posicao = total_bancos + fluxo

        col = [col_p1, col_p2, col_p3][["30 dias","60 dias","90 dias"].index(label)]
        col.metric(
            f"Posição em {label}",
            f"R$ {posicao:,.2f}",
            delta=f"R$ {fluxo:,.2f} de fluxo",
            delta_color="normal"
        )

    st.markdown("---")

    # ─── RECEBÍVEIS E OBRIGAÇÕES ─────────────────────────────────────────
    st.subheader("📋 Recebíveis e Obrigações")
    dt_fim_ano = str(date(hoje.year, 12, 31))
    dados_all = db.fc_diario(str(hoje), dt_fim_ano, True, False, erp_corte_status=cfg_corte,
                             inc_fci=inc_fci, inc_fcf=inc_fcf)

    if dados_all:
        total_recebiveis  = sum(r["valor_final"] for r in dados_all if (r["valor_final"] or 0) > 0)
        total_obrigacoes  = sum(r["valor_final"] for r in dados_all if (r["valor_final"] or 0) < 0)
        total_impostos    = sum(r["valor_final"] for r in dados_all
                                if r.get("imposto") == "SIM" and (r["valor_final"] or 0) < 0)

        col_k1, col_k2, col_k3, col_k4 = st.columns(4)
        col_k1.metric("Recebíveis Totais",  f"R$ {total_recebiveis:,.2f}")
        col_k2.metric("Obrigações Totais",  f"R$ {abs(total_obrigacoes):,.2f}")
        col_k3.metric("Saldo Projetado",
                       f"R$ {total_recebiveis + total_obrigacoes:,.2f}")
        col_k4.metric("Impostos a pagar",   f"R$ {abs(total_impostos):,.2f}")
    else:
        st.info("Sem dados de fluxo para o período.")

    st.markdown("---")

    # ─── DISTRIBUIÇÃO POR ORIGEM ──────────────────────────────────────────
    st.subheader("📊 Distribuição do fluxo por origem")
    if dados_all:
        df = pd.DataFrame(dados_all)
        by_orig = df.groupby("origem")["valor_final"].agg(["sum","count"]).reset_index()
        by_orig.columns = ["Origem", "Saldo", "Qtd Lançamentos"]
        by_orig["Saldo"] = by_orig["Saldo"].apply(
            lambda x: f"R$ {x:,.2f}" if x >= 0 else f"(R$ {abs(x):,.2f})"
        )
        st.dataframe(by_orig, use_container_width=True, hide_index=True)

    # ─── PRÓXIMOS VENCIMENTOS ─────────────────────────────────────────────
    st.subheader("🔔 Próximos vencimentos (15 dias)")
    dt_15 = str(hoje + timedelta(days=15))
    proximos = db.fc_diario(str(hoje), dt_15, True, False, erp_corte_status=cfg_corte,
                            inc_fci=inc_fci, inc_fcf=inc_fcf)
    if proximos:
        df_prox = pd.DataFrame(proximos)
        df_prox["vencimento"] = pd.to_datetime(df_prox["vencimento"]).dt.strftime("%d/%m/%Y")
        df_prox["valor_final"] = df_prox["valor_final"].apply(
            lambda x: f"🟢 R$ {x:,.2f}" if (x or 0) >= 0 else f"🔴 R$ {abs(x or 0):,.2f}"
        )
        cols_show = ["origem", "operacao", "razao_social", "descricao", "vencimento", "valor_final"]
        cols_show = [c for c in cols_show if c in df_prox.columns]
        st.dataframe(df_prox[cols_show], use_container_width=True)
    else:
        st.success("Nenhum vencimento nos próximos 15 dias.")
