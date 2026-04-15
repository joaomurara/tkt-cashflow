"""
Página FUP Vendas — Sincronização Pipedrive e configuração de negócios.
"""

import streamlit as st
import pandas as pd
import json
from datetime import date, datetime
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import db
import pipedrive_core as pc


# ── Editor reutilizável de parcelas livres ────────────────────────────────────
def _editor_parcelas(key_prefix: str, parcelas_json: str, valor_ref: float = 0.0,
                     titulo: str = "Parcelas", op: str = "CREDITO") -> list:
    """
    Renderiza um editor dinâmico de parcelas (crédito ou débito).
    Retorna a lista atual de parcelas como dicts.
    key_prefix  — prefixo único para as keys do Streamlit
    parcelas_json — JSON salvo (string)
    valor_ref   — valor do negócio em BRL (para mostrar R$ equivalente)
    op          — "CREDITO" ou "DEBITO" (só afeta labels)
    """
    sk = f"_parc_{key_prefix}"
    # Inicializa session_state com o que está salvo
    if sk not in st.session_state:
        try:
            st.session_state[sk] = json.loads(parcelas_json or "[]")
        except Exception:
            st.session_state[sk] = []

    parcelas = st.session_state[sk]

    # Botões de ação
    col_add, col_clr, _ = st.columns([1, 1, 4])
    with col_add:
        if st.button(f"➕ Adicionar linha", key=f"{key_prefix}_add"):
            parcelas.append({"desc": "", "tipo_val": "pct", "valor": 0.0, "dias": 0,
                              "ref": "fechamento"})
            st.session_state[sk] = parcelas
            st.rerun()
    with col_clr:
        if st.button(f"🗑 Limpar tudo", key=f"{key_prefix}_clr"):
            st.session_state[sk] = []
            st.rerun()

    if not parcelas:
        st.caption("Nenhuma linha configurada. Clique em **➕ Adicionar linha**.")
        return []

    total_pct = sum(p["valor"] for p in parcelas if p.get("tipo_val") == "pct")
    total_fix = sum(p["valor"] for p in parcelas if p.get("tipo_val") == "fixo")
    total_brl = (valor_ref * total_pct / 100 + total_fix) if valor_ref else total_fix
    lbl_total = f"**Total configurado:** {total_pct:.1f}% + R$ {total_fix:,.2f} = R$ {total_brl:,.2f}"
    if abs(total_pct + (total_fix / valor_ref * 100 if valor_ref else 0) - 100) > 0.1 and valor_ref:
        st.warning(f"⚠️ {lbl_total} — percentuais não somam 100% do valor")
    else:
        st.caption(lbl_total)

    to_delete = None
    for i, p in enumerate(parcelas):
        cols = st.columns([3, 2, 2, 2, 2, 1])
        with cols[0]:
            p["desc"] = st.text_input("Descrição", value=p.get("desc",""),
                                       key=f"{key_prefix}_desc_{i}", label_visibility="collapsed",
                                       placeholder=f"Ex.: Entrada / Parcela {i+1}")
        with cols[1]:
            p["tipo_val"] = st.selectbox("Tipo", ["pct", "fixo"],
                                          index=0 if p.get("tipo_val","pct")=="pct" else 1,
                                          format_func=lambda x: "% do valor" if x=="pct" else "R$ fixo",
                                          key=f"{key_prefix}_tv_{i}", label_visibility="collapsed")
        with cols[2]:
            p["valor"] = st.number_input(
                "Valor", min_value=0.0,
                value=float(p.get("valor", 0)),
                step=1.0 if p["tipo_val"]=="pct" else 100.0,
                format="%.2f",
                key=f"{key_prefix}_val_{i}", label_visibility="collapsed")
        with cols[3]:
            p["ref"] = st.selectbox(
                "Ref.",
                ["fechamento", "faturamento"],
                index=0 if p.get("ref", "fechamento") == "fechamento" else 1,
                format_func=lambda x: "📅 Fecham." if x == "fechamento" else "🏭 Fatura.",
                key=f"{key_prefix}_ref_{i}",
                label_visibility="collapsed",
            )
        with cols[4]:
            p["dias"] = st.number_input("+ Dias", min_value=0,
                                         value=int(p.get("dias", 0)),
                                         key=f"{key_prefix}_dias_{i}", label_visibility="collapsed",
                                         help="Dias após a data de referência")
        with cols[5]:
            if st.button("✕", key=f"{key_prefix}_del_{i}"):
                to_delete = i

    if to_delete is not None:
        parcelas.pop(to_delete)
        st.session_state[sk] = parcelas
        st.rerun()

    st.session_state[sk] = parcelas
    return parcelas


def render():
    st.title("📡 FUP Vendas — Pipedrive")
    st.markdown("Gerencie as projeções de venda sincronizadas com o Pipedrive.")

    tab_sync, tab_diag, tab_config, tab_fluxo = st.tabs([
        "🔄 Sincronizar", "🔍 Diagnóstico", "⚙️ Configurar Negócios", "📋 Fluxo Gerado"
    ])

    # ─── ABA SINCRONIZAR ───────────────────────────────────────────────────
    with tab_sync:
        st.subheader("Sincronização com Pipedrive")
        st.markdown("""
        A sincronização:
        1. Busca deals ativos com a etiqueta **financas** nos funis configurados
        2. Atualiza o câmbio em tempo real
        3. Adiciona novos deals à configuração (preservando dados já preenchidos)
        4. Remove deals que perderam a etiqueta
        5. Gera as linhas de fluxo de caixa com base nas configurações de cada negócio
        """)

        if st.button("🔄 Sincronizar agora", type="primary"):
            log_msgs = []

            def log_fn(msg):
                log_msgs.append(msg)

            with st.spinner("Sincronizando com Pipedrive..."):
                stats = pc.sincronizar_pipedrive(log_fn=log_fn)

            with st.expander("📋 Log da sincronização", expanded=True):
                for msg in log_msgs:
                    st.text(msg)

            if stats["erros"]:
                st.warning(f"⚠️ {len(stats['erros'])} erro(s):")
                for e in stats["erros"]:
                    st.text(f"  • {e}")

            col1, col2, col3, col4 = st.columns(4)
            col1.metric("Novos deals", stats["novos"])
            col2.metric("Atualizados", stats["atualizados"])
            col3.metric("Removidos",   stats["removidos"])
            col4.metric("Linhas geradas", stats["linhas"])

            if stats["linhas"] > 0:
                st.success("✅ Sincronização concluída!")
            else:
                st.warning("Nenhuma linha gerada. Use a aba **Diagnóstico** para identificar o problema.")

    # ─── ABA DIAGNÓSTICO ───────────────────────────────────────────────────
    with tab_diag:
        st.subheader("🔍 Diagnóstico da conexão Pipedrive")
        st.markdown("""
        Executa uma verificação completa: lista todos os pipelines, estágios, etiquetas
        e deals encontrados, mostrando exatamente onde o filtro está bloqueando os resultados.
        """)

        st.markdown("**Filtros atualmente configurados no código:**")
        col_cfg1, col_cfg2 = st.columns(2)
        with col_cfg1:
            st.markdown("**Funis e Estágios:**")
            for funil, estagios in pc.FILTROS.items():
                st.markdown(f"- `{funil}`: {', '.join(f'`{e}`' for e in estagios)}")
        with col_cfg2:
            st.markdown(f"**Etiqueta obrigatória:** `{pc.ETIQUETA_OBRIGATORIA}` (id={pc.ETIQUETA_OBRIGATORIA_ID})")

        if st.button("🔍 Executar diagnóstico", type="primary"):
            log_msgs = []
            def log_diag(msg):
                log_msgs.append(msg)

            with st.spinner("Consultando Pipedrive..."):
                try:
                    resultado = pc.diagnosticar_pipedrive(log_fn=log_diag)
                except Exception as e:
                    st.error(f"Erro: {e}")
                    resultado = None

            if resultado:
                with st.expander("📋 Log completo", expanded=False):
                    for msg in log_msgs:
                        st.text(msg)

                # Pipelines
                st.markdown("### Pipelines encontrados")
                if resultado["pipelines"]:
                    df_pip = pd.DataFrame(resultado["pipelines"])
                    st.dataframe(df_pip, use_container_width=True, hide_index=True)

                    funis_encontrados = [p["nome"] for p in resultado["pipelines"]]
                    funis_config = list(pc.FILTROS.keys())
                    for f in funis_config:
                        if f in funis_encontrados:
                            st.success(f"✅ Funil '{f}' encontrado no Pipedrive")
                        else:
                            st.error(f"❌ Funil '{f}' NÃO encontrado. Nomes disponíveis: {funis_encontrados}")
                else:
                    st.warning("Nenhum pipeline retornado pela API.")

                # Estágios
                st.markdown("### Estágios encontrados")
                if resultado["stages"]:
                    df_st = pd.DataFrame(resultado["stages"])
                    st.dataframe(df_st, use_container_width=True, hide_index=True)

                    for funil, estagios in pc.FILTROS.items():
                        estagios_do_funil = [
                            s["nome"] for s in resultado["stages"]
                            if s["pipeline_nome"] == funil
                        ]
                        for est in estagios:
                            if est in estagios_do_funil:
                                st.success(f"✅ Estágio '{est}' em '{funil}' encontrado")
                            else:
                                st.error(f"❌ Estágio '{est}' em '{funil}' NÃO encontrado. Disponíveis: {estagios_do_funil}")

                # Etiquetas
                st.markdown("### Etiquetas disponíveis no Pipedrive")
                if resultado["etiquetas"]:
                    df_etiq = pd.DataFrame(resultado["etiquetas"])
                    st.dataframe(df_etiq, use_container_width=True, hide_index=True)

                    nomes_etiq = [e["nome"].strip().upper() for e in resultado["etiquetas"]]
                    etiq_alvo  = pc.ETIQUETA_OBRIGATORIA.strip().upper()
                    if etiq_alvo in nomes_etiq:
                        etiq_match = next(e for e in resultado["etiquetas"]
                                          if e["nome"].strip().upper() == etiq_alvo)
                        st.success(f"✅ Etiqueta '{pc.ETIQUETA_OBRIGATORIA}' encontrada com id={etiq_match['id']}")
                    else:
                        st.error(f"❌ Etiqueta '{pc.ETIQUETA_OBRIGATORIA}' NÃO encontrada.")
                        st.markdown(f"Etiquetas disponíveis: {[e['nome'] for e in resultado['etiquetas']]}")

                # Busca ampla
                total_abertos = resultado.get("total_deals_abertos", "?")
                com_etiq_total = resultado.get("deals_com_etiqueta_total")
                st.markdown("### Varredura ampla — todos os deals abertos")
                if com_etiq_total is not None:
                    st.info(f"Total de deals abertos no Pipedrive: **{total_abertos}** | Com etiqueta '{pc.ETIQUETA_OBRIGATORIA}': **{com_etiq_total}**")
                else:
                    st.warning(f"Total de deals abertos: {total_abertos}. Etiqueta não pôde ser verificada (ID não resolvido).")

                if resultado.get("exemplo_label_bruto"):
                    st.markdown("**Formato do campo `label` (primeiros 10 deals):**")
                    st.dataframe(pd.DataFrame(resultado["exemplo_label_bruto"]),
                                 use_container_width=True, hide_index=True)

                # Deals por estágio
                st.markdown("### Deals nos estágios configurados")
                if resultado["deals_abertos"]:
                    df_deals = pd.DataFrame(resultado["deals_abertos"])
                    com_etiq = df_deals[df_deals["tem_etiqueta_financas"] == True]
                    sem_etiq = df_deals[df_deals["tem_etiqueta_financas"] == False]
                    st.info(f"Deals nos estágios: **{len(df_deals)}** | Com etiqueta: **{len(com_etiq)}** | Sem etiqueta: **{len(sem_etiq)}**")
                    st.dataframe(df_deals, use_container_width=True, hide_index=True)
                else:
                    st.warning("Nenhum deal encontrado nos estágios configurados. Verifique os nomes dos funis e estágios acima.")

                # Sugestão de correção
                st.markdown("---")
                st.markdown("### Corrigir filtros (se necessário)")
                st.markdown("Se os nomes dos pipelines ou estágios estiverem diferentes, corrija aqui e salve:")

                with st.form("form_filtros"):
                    st.markdown("**Funil Nacional — Estágios (um por linha):**")
                    estagios_nac = st.text_area(
                        "Estágios Nacional",
                        value="\n".join(pc.FILTROS.get("Nacional", [])),
                        height=100, label_visibility="collapsed"
                    )
                    st.markdown("**Funil Exportação — Estágios (um por linha):**")
                    estagios_exp = st.text_area(
                        "Estágios Exportação",
                        value="\n".join(pc.FILTROS.get("Exportação", [])),
                        height=100, label_visibility="collapsed"
                    )
                    nova_etiq_id = st.number_input(
                        "ID da etiqueta obrigatória",
                        value=int(pc.ETIQUETA_OBRIGATORIA_ID), step=1
                    )
                    novo_nome_etiq = st.text_input(
                        "Nome da etiqueta", value=pc.ETIQUETA_OBRIGATORIA
                    )

                    if st.form_submit_button("💾 Salvar e aplicar filtros"):
                        _atualizar_filtros_pipedrive(
                            estagios_nac, estagios_exp, int(nova_etiq_id), novo_nome_etiq
                        )
                        st.success("✅ Filtros atualizados! Execute o diagnóstico novamente para confirmar.")
                        st.rerun()

    # ─── ABA CONFIGURAR NEGÓCIOS ───────────────────────────────────────────
    with tab_config:
        st.subheader("Configuração dos negócios")
        st.markdown("Configure os parâmetros de fluxo de caixa para cada negócio. Sincronize primeiro para ver os deals disponíveis.")

        configs = db.listar_config_pipedrive()
        configs_ativas = [c for c in configs if c.get("ativo")]

        if not configs_ativas:
            st.info("Nenhum negócio configurado. Clique em **Sincronizar** primeiro.")
            return

        for cfg in configs_ativas:
            did = cfg["deal_id"]
            with st.expander(
                f"🏢 {cfg.get('negocio') or cfg.get('cliente','—')} "
                f"| {cfg.get('funil','—')} | R$ {cfg.get('valor_brl') or 0:,.2f}"
            ):
                # Info somente leitura
                col_i1, col_i2, col_i3, col_i4 = st.columns(4)
                col_i1.markdown(f"**Moeda:** {cfg.get('moeda','BRL')}")
                col_i2.markdown(f"**Valor Original:** {cfg.get('valor_original') or 0:,.2f}")
                col_i3.markdown(f"**Câmbio:** {cfg.get('cambio') or 1:.4f}")
                col_i4.markdown(f"**Data Câmbio:** {cfg.get('data_cambio','—')}")

                # Data de fechamento (editável)
                st.markdown("---")
                col_d1, col_d2 = st.columns(2)
                with col_d1:
                    try:
                        dt_fech_def = datetime.strptime(
                            (cfg.get("data_fechamento") or "")[:10], "%Y-%m-%d"
                        ).date() if cfg.get("data_fechamento") else date.today()
                    except:
                        dt_fech_def = date.today()

                    data_fech = st.date_input("Data de Fechamento *",
                                               value=dt_fech_def, key=f"df_{did}")
                with col_d2:
                    prob = st.selectbox("Probabilidade",
                                        ["ALTA", "MEDIA", "CONFIRMADO"],
                                        index=["ALTA","MEDIA","CONFIRMADO"].index(
                                            cfg.get("probabilidade","ALTA") or "ALTA"),
                                        key=f"pb_{did}")

                # Parâmetros de fluxo
                col_p1, col_p2, col_p3 = st.columns(3)
                with col_p1:
                    tipo_fluxo = st.selectbox("Tipo de Fluxo",
                        options=[1, 2, 3, 4],
                        index=[1,2,3,4].index(cfg.get("tipo_fluxo") or 1),
                        format_func=lambda x: {
                            1: "Tipo 1 — Entrada + Parcelas",
                            2: "Tipo 2 — Entrada + Pós X dias + Fat.",
                            3: "Tipo 3 — Tipo 2 + Pós Faturamento",
                            4: "Tipo 4 — Livre (datas e valores customizados)",
                        }[x],
                        key=f"tf_{did}")
                with col_p2:
                    prazo_ent = st.number_input("Prazo Entrega (dias)", min_value=0,
                                                 value=int(cfg.get("prazo_entrega") or 0),
                                                 key=f"pe_{did}")
                with col_p3:
                    pct_com = st.number_input("% Comissão", min_value=0.0, max_value=100.0,
                                               value=float((cfg.get("pct_comissao") or 0) * 100),
                                               step=0.1, format="%.1f", key=f"pc_{did}")

                st.markdown(f"**Parâmetros — Tipo {tipo_fluxo}**")

                if tipo_fluxo == 4:
                    valor_brl_cfg = float(cfg.get("valor_brl") or 0)
                    st.caption("Configure cada evento de recebimento. A data será calculada como **Fechamento + Dias**.")
                    # cabeçalho das colunas
                    hc = st.columns([3, 2, 2, 2, 2, 1])
                    for lbl, col in zip(["Descrição", "Tipo", "Valor", "Referência", "+ Dias", ""], hc):
                        col.markdown(f"**{lbl}**")
                    parc_livres = _editor_parcelas(
                        key_prefix=f"parc_{did}",
                        parcelas_json=cfg.get("parcelas_livres_json") or "[]",
                        valor_ref=valor_brl_cfg,
                        titulo="Recebimentos",
                        op="CREDITO",
                    )
                    pct_ent = n_parc = interv = pct_pos = pct_fat = pct_pos_f = dias_pos_f = x_dias = 0
                elif tipo_fluxo == 1:
                    col_t1a, col_t1b, col_t1c = st.columns(3)
                    with col_t1a:
                        pct_ent = st.number_input("% Entrada", min_value=0.0, max_value=100.0,
                            value=float((cfg.get("pct_entrada") or 0)*100), step=1.0, key=f"pent_{did}")
                    with col_t1b:
                        n_parc = st.number_input("N° Parcelas", min_value=1,
                            value=int(cfg.get("n_parcelas") or 4), key=f"np_{did}")
                    with col_t1c:
                        interv = st.number_input("Intervalo Parcelas (dias)", min_value=1,
                            value=int(cfg.get("intervalo_parcelas") or 30), key=f"iv_{did}")
                    pct_pos = pct_fat = pct_pos_f = dias_pos_f = x_dias = 0
                    pct_pos = 0; pct_fat = 0; pct_pos_f = 0; dias_pos_f = 30; x_dias = 30

                elif tipo_fluxo in (2, 3):
                    col_t2a, col_t2b, col_t2c = st.columns(3)
                    with col_t2a:
                        pct_ent = st.number_input("% Entrada", min_value=0.0, max_value=100.0,
                            value=float((cfg.get("pct_entrada") or 0)*100), step=1.0, key=f"pent_{did}")
                    with col_t2b:
                        pct_pos = st.number_input("% Pós X dias", min_value=0.0, max_value=100.0,
                            value=float((cfg.get("pct_pos_x") or 0)*100), step=1.0, key=f"pp_{did}")
                    with col_t2c:
                        x_dias = st.number_input("X Dias", min_value=1,
                            value=int(cfg.get("x_dias") or 30), key=f"xd_{did}")

                    col_t2d, col_t2e = st.columns(2)
                    with col_t2d:
                        pct_fat = st.number_input("% Faturamento", min_value=0.0, max_value=100.0,
                            value=float((cfg.get("pct_fat") or 0)*100), step=1.0, key=f"pf_{did}")
                    with col_t2e:
                        if tipo_fluxo == 3:
                            pct_pos_f = st.number_input("% Pós Faturamento", min_value=0.0, max_value=100.0,
                                value=float((cfg.get("pct_pos_fat") or 0)*100), step=1.0, key=f"ppf_{did}")
                            dias_pos_f = st.number_input("Dias Pós Faturamento", min_value=1,
                                value=int(cfg.get("dias_pos_fat") or 30), key=f"dpf_{did}")
                        else:
                            pct_pos_f = 0; dias_pos_f = 30

                    n_parc = 4; interv = 30

                # Impostos (Nacional)
                if cfg.get("funil") != "Exportação":
                    with st.expander("⚙️ Impostos (Nacional)"):
                        col_imp1, col_imp2 = st.columns(2)
                        with col_imp1:
                            pct_icms = st.number_input("% ICMS", min_value=0.0, max_value=100.0,
                                value=float((cfg.get("pct_icms") or 0.088)*100), step=0.1, key=f"icms_{did}")
                            dias_icms = st.number_input("Dia ICMS (mês seguinte)", min_value=1, max_value=31,
                                value=int(cfg.get("dias_icms") or 10), key=f"dicms_{did}")
                        with col_imp2:
                            pct_pis = st.number_input("% PIS/COFINS", min_value=0.0, max_value=100.0,
                                value=float((cfg.get("pct_pis_cofins") or 0.059)*100), step=0.1, key=f"pis_{did}")
                            dias_pis = st.number_input("Dia PIS/COFINS (mês seguinte)", min_value=1, max_value=31,
                                value=int(cfg.get("dias_pis_cofins") or 25), key=f"dpis_{did}")
                else:
                    pct_icms = 0; dias_icms = 10; pct_pis = 0; dias_pis = 25

                # ── Matéria Prima ──
                with st.expander("🏭 Fluxo de Compra de Matéria Prima", expanded=False):
                    st.caption(
                        "Configure os pagamentos de matéria prima como débitos no fluxo. "
                        "A referência pode ser a data de **Fechamento** ou de **Faturamento**."
                    )
                    valor_brl_cfg = float(cfg.get("valor_brl") or 0)
                    hc2 = st.columns([3, 2, 2, 2, 2, 1])
                    for lbl, col in zip(["Descrição", "Tipo", "Valor", "Referência", "+ Dias", ""], hc2):
                        col.markdown(f"**{lbl}**")
                    mp_parcelas = _editor_parcelas(
                        key_prefix=f"mp_{did}",
                        parcelas_json=cfg.get("mp_json") or "[]",
                        valor_ref=valor_brl_cfg,
                        titulo="Matéria Prima",
                        op="DEBITO",
                    )

                obs = st.text_area("Observações", value=cfg.get("obs") or "", key=f"obs_{did}")

                if st.button(f"💾 Salvar configuração", key=f"save_{did}"):
                    # Parcelas livres (Tipo 4)
                    sk_parc = f"_parc_parc_{did}"
                    parc_salvar = st.session_state.get(sk_parc, [])
                    sk_mp = f"_parc_mp_{did}"
                    mp_salvar = st.session_state.get(sk_mp, [])

                    db.salvar_config_deal({
                        "deal_id":             did,
                        "data_fechamento":     str(data_fech),
                        "probabilidade":       prob,
                        "tipo_fluxo":          tipo_fluxo,
                        "prazo_entrega":       int(prazo_ent),
                        "pct_comissao":        pct_com / 100,
                        "pct_entrada":         pct_ent / 100,
                        "n_parcelas":          int(n_parc),
                        "intervalo_parcelas":  int(interv),
                        "pct_pos_x":           pct_pos / 100,
                        "x_dias":              int(x_dias),
                        "pct_fat":             pct_fat / 100,
                        "pct_pos_fat":         pct_pos_f / 100,
                        "dias_pos_fat":        int(dias_pos_f),
                        "pct_icms":            pct_icms / 100,
                        "dias_icms":           int(dias_icms),
                        "pct_pis_cofins":      pct_pis / 100,
                        "dias_pis_cofins":     int(dias_pis),
                        "obs":                 obs,
                        "parcelas_livres_json": json.dumps(parc_salvar),
                        "mp_json":             json.dumps(mp_salvar),
                    })
                    st.success("✅ Configuração salva! Sincronize novamente para atualizar o fluxo.")

    # ─── ABA FLUXO GERADO ─────────────────────────────────────────────────
    with tab_fluxo:
        st.subheader("Linhas de fluxo geradas")

        cfg_ini = st.session_state.get("cfg_dt_ini", str(date(date.today().year, 1, 1)))
        cfg_fim = st.session_state.get("cfg_dt_fim", str(date(date.today().year, 12, 31)))

        col_f1, col_f2, col_f3 = st.columns(3)
        with col_f1:
            dt_ini = st.date_input("De", value=date.fromisoformat(cfg_ini), key="fup_ini")
        with col_f2:
            dt_fim = st.date_input("Até", value=date.fromisoformat(cfg_fim), key="fup_fim")
        with col_f3:
            prob_filtro = st.selectbox("Probabilidade", ["Todas", "ALTA", "MEDIA", "CONFIRMADO"], key="fup_prob")

        dados = db.listar_fup(
            dt_ini=str(dt_ini), dt_fim=str(dt_fim),
            prob=None if prob_filtro == "Todas" else prob_filtro
        )

        if not dados:
            st.info("Nenhuma linha gerada. Sincronize e configure os negócios primeiro.")
            return

        # ── Totais ─────────────────────────────────────────────────────────
        total_cred = sum(r["valor_final"] for r in dados if (r["valor_final"] or 0) > 0)
        total_deb  = sum(r["valor_final"] for r in dados if (r["valor_final"] or 0) < 0)
        col_m1, col_m2, col_m3, col_m4 = st.columns(4)
        col_m1.metric("Entradas projetadas",  f"R$ {total_cred:,.2f}")
        col_m2.metric("Saídas projetadas",    f"R$ {abs(total_deb):,.2f}")
        col_m3.metric("Saldo projetado",      f"R$ {total_cred + total_deb:,.2f}")
        col_m4.metric("Total de linhas",      len(dados))

        st.markdown("---")

        # ── Agrupado por negócio com botão "→ Provisões" ──────────────────
        visao = st.radio("Visualização", ["Por negócio", "Tabela completa"],
                         horizontal=True, key="fup_visao")

        if visao == "Por negócio":
            # Agrupa os dados por deal_id
            deals_map: dict = {}
            for r in dados:
                did = r.get("deal_id") or "?"
                deals_map.setdefault(did, []).append(r)

            for did, linhas in deals_map.items():
                cliente   = linhas[0].get("razao_social", did)
                lote      = linhas[0].get("lote", "")
                prob      = linhas[0].get("probabilidade", "")
                val_liq   = sum(l.get("valor_final", 0) for l in linhas)
                n_linhas  = len(linhas)

                with st.expander(
                    f"{'🟢' if val_liq >= 0 else '🔴'} **{cliente}** "
                    f"| {lote} | {prob} | R$ {val_liq:,.2f} | {n_linhas} linhas"
                ):
                    # Tabela das linhas do negócio
                    df_deal = pd.DataFrame(linhas)
                    df_deal["vencimento"]  = pd.to_datetime(df_deal["vencimento"]).dt.strftime("%d/%m/%Y")
                    df_deal["valor"]       = df_deal["valor"].apply(lambda x: f"R$ {x:,.2f}")
                    df_deal["valor_final"] = df_deal["valor_final"].apply(
                        lambda x: f"🟢 R$ {x:,.2f}" if x >= 0 else f"🔴 R$ {abs(x):,.2f}"
                    )
                    cols_show = ["descricao", "operacao", "vencimento",
                                 "valor", "valor_final", "probabilidade", "imposto"]
                    cols_show = [c for c in cols_show if c in df_deal.columns]
                    st.dataframe(df_deal[cols_show], use_container_width=True, hide_index=True)

                    # Botão de transferência
                    st.markdown("---")
                    col_btn1, col_btn2, col_opt = st.columns([1, 1, 2])
                    with col_opt:
                        manter_fup = st.checkbox(
                            "Manter no FUP após mover",
                            value=False,
                            key=f"manter_{did}",
                            help="Se marcado, as linhas continuam no FUP Vendas "
                                 "além de serem copiadas para Provisões."
                        )
                    with col_btn1:
                        if st.button(
                            "📋 → Mover para Provisões",
                            key=f"mover_{did}",
                            type="primary",
                            help="Copia todas as linhas deste negócio para Provisões"
                        ):
                            # DEBUG temporário — mostra o que está sendo processado
                            linhas_fup = db.listar_fup(deal_id=str(did))
                            st.info(
                                f"🔍 DEBUG | deal_id: `{did}` | "
                                f"linhas no FUP: `{len(linhas_fup)}`"
                            )

                            n, err = db.mover_fup_para_provisoes(
                                deal_id=did,
                                remover_do_fup=not manter_fup
                            )
                            # DEBUG: mostra retorno da função
                            st.info(f"🔍 DEBUG retorno | n=`{n}` | err=`{err}`")
                            if err:
                                st.error(
                                    f"**Erro ao mover para Provisões**\n\n"
                                    f"`{err}`\n\n"
                                    f"deal_id: `{did}`"
                                )
                            elif n:
                                st.success(
                                    f"✅ {n} linha(s) de **{cliente}** movidas para Provisões"
                                    + (" e removidas do FUP." if not manter_fup else " (mantidas no FUP).")
                                )
                                # st.rerun()  # DEBUG: desabilitado para ver a mensagem
                            else:
                                st.warning(f"Nenhuma linha no FUP para deal_id `{did}`.")

        else:
            # Tabela completa (visão original)
            df = pd.DataFrame(dados)
            df["vencimento"] = pd.to_datetime(df["vencimento"]).dt.strftime("%d/%m/%Y")
            df["valor"]       = df["valor"].apply(lambda x: f"R$ {x:,.2f}")
            df["valor_final"] = df["valor_final"].apply(lambda x: f"R$ {x:,.2f}")
            cols_show = ["razao_social", "descricao", "probabilidade", "lote",
                         "vencimento", "operacao", "valor", "valor_final", "imposto"]
            cols_show = [c for c in cols_show if c in df.columns]
            st.dataframe(df[cols_show], use_container_width=True, height=500)


# ─── HELPER: ATUALIZA FILTROS NO pipedrive_core.py ───────────────────────────

def _atualizar_filtros_pipedrive(estagios_nac_txt, estagios_exp_txt, etiq_id, etiq_nome):
    """Reescreve as constantes FILTROS e ETIQUETA no pipedrive_core.py."""
    import re

    nac = [e.strip() for e in estagios_nac_txt.splitlines() if e.strip()]
    exp = [e.strip() for e in estagios_exp_txt.splitlines() if e.strip()]

    core_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "pipedrive_core.py")
    with open(core_path, "r", encoding="utf-8") as f:
        src = f.read()

    # Substitui FILTROS
    nac_repr = repr(nac)
    exp_repr = repr(exp)
    novo_filtro = (
        f'FILTROS = {{\n'
        f'    "Nacional":   {nac_repr},\n'
        f'    "Exportação": {exp_repr},\n'
        f'}}'
    )
    src = re.sub(r'FILTROS\s*=\s*\{[^}]+\}', novo_filtro, src, flags=re.DOTALL)

    # Substitui ETIQUETA_OBRIGATORIA_ID
    src = re.sub(
        r'ETIQUETA_OBRIGATORIA_ID\s*=\s*\d+',
        f'ETIQUETA_OBRIGATORIA_ID = {etiq_id}',
        src
    )
    # Substitui ETIQUETA_OBRIGATORIA (nome)
    src = re.sub(
        r'ETIQUETA_OBRIGATORIA\s*=\s*"[^"]*"',
        f'ETIQUETA_OBRIGATORIA    = "{etiq_nome}"',
        src
    )

    with open(core_path, "w", encoding="utf-8") as f:
        f.write(src)

    # Recarrega o módulo
    import importlib
    import pipedrive_core
    importlib.reload(pipedrive_core)
