"""
Página Câmbios Disponíveis — Gestão de posições em moeda estrangeira de exportações.
"""

import streamlit as st
import pandas as pd
import requests
from datetime import date, timedelta
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import db


# ─── PTAX via Banco Central do Brasil ────────────────────────────────────────

def _buscar_ptax(moeda: str = "USD", data: date | None = None) -> float | None:
    """
    Busca a taxa PTAX de venda do BCB para a data informada (ou hoje).
    Tenta até 5 dias anteriores para cobrir fins de semana/feriados.
    """
    if data is None:
        data = date.today()

    for delta in range(5):
        d = data - timedelta(days=delta)
        d_str = d.strftime("%m-%d-%Y")  # formato exigido pela API BCB
        try:
            if moeda == "USD":
                url = (
                    "https://olinda.bcb.gov.br/olinda/servico/PTAX/versao/v1/odata/"
                    f"CotacaoDolarDia(dataCotacao=@dataCotacao)?"
                    f"@dataCotacao='{d_str}'&$top=1&$format=json&$select=cotacaoVenda"
                )
            else:
                url = (
                    "https://olinda.bcb.gov.br/olinda/servico/PTAX/versao/v1/odata/"
                    f"CotacaoMoedaDia(moeda=@moeda,dataCotacao=@dataCotacao)?"
                    f"@moeda='{moeda}'&@dataCotacao='{d_str}'&$top=1&$format=json&$select=cotacaoVenda"
                )
            resp = requests.get(url, timeout=5)
            data_json = resp.json().get("value", [])
            if data_json:
                return float(data_json[0]["cotacaoVenda"])
        except Exception:
            continue
    return None


def _ptax_cached(moeda: str, ref_date: date | None = None) -> float | None:
    """Wrapper com cache de sessão para evitar múltiplas chamadas à API."""
    key = f"_ptax_{moeda}_{ref_date or 'hoje'}"
    if key not in st.session_state:
        st.session_state[key] = _buscar_ptax(moeda, ref_date)
    return st.session_state[key]


# ─── RENDER ───────────────────────────────────────────────────────────────────

def render():
    st.title("💱 Câmbios Disponíveis")
    st.markdown("Posições em moeda estrangeira de exportações — aguardando conversão ou já fechadas.")

    can_edit = st.session_state.get("can_edit", True)

    tab_disp, tab_novo, tab_hist = st.tabs([
        "📥 Disponíveis", "➕ Novo Câmbio", "📋 Histórico"
    ])

    # ─── ABA DISPONÍVEIS ──────────────────────────────────────────────────────
    with tab_disp:
        st.subheader("Posições em aberto")

        cambios = db.listar_cambios(status="DISPONIVEL")

        if not cambios:
            st.info("Nenhuma posição disponível. Use **➕ Novo Câmbio** para registrar.")
        else:
            # Busca PTAX atual para cada moeda única
            moedas_unicas = {c["moeda"] for c in cambios}
            ptax_hoje = {m: _ptax_cached(m) for m in moedas_unicas}

            rows = []
            for c in cambios:
                taxa = ptax_hoje.get(c["moeda"])
                valor_brl = (c["valor_me"] or 0) * taxa if taxa else None
                rows.append({
                    "id":              c["id"],
                    "Descrição":       c["descricao"] or "—",
                    "Origem":          f"{c['origem']} #{c['origem_id']}" if c.get("origem_id") else c.get("origem", "MANUAL"),
                    "Moeda":           c["moeda"],
                    "Valor ME":        c["valor_me"],
                    "Data Entrada":    c["data_entrada"],
                    "PTAX Entrada":    c["taxa_ptax_entrada"],
                    "PTAX Hoje":       taxa,
                    "BRL Projetado":   valor_brl,
                    "Obs":             c.get("observacoes") or "",
                })

            df = pd.DataFrame(rows)

            # Exibição formatada
            df_show = df.copy()
            df_show["Valor ME"]      = df_show.apply(lambda r: f"{r['Moeda']} {r['Valor ME']:,.2f}", axis=1)
            df_show["PTAX Entrada"]  = df_show["PTAX Entrada"].apply(lambda x: f"R$ {x:,.4f}" if x else "—")
            df_show["PTAX Hoje"]     = df_show["PTAX Hoje"].apply(lambda x: f"R$ {x:,.4f}" if x else "—")
            df_show["BRL Projetado"] = df_show["BRL Projetado"].apply(lambda x: f"R$ {x:,.2f}" if x else "—")
            df_show["Data Entrada"]  = pd.to_datetime(df_show["Data Entrada"], errors="coerce").dt.strftime("%d/%m/%Y")

            cols_show = ["id", "Descrição", "Origem", "Valor ME", "Data Entrada",
                         "PTAX Entrada", "PTAX Hoje", "BRL Projetado", "Obs"]
            st.dataframe(df_show[cols_show], use_container_width=True, hide_index=True)

            # Totais por moeda
            st.markdown("**Totais por moeda (valor projetado em BRL):**")
            cols_tot = st.columns(min(len(moedas_unicas), 4))
            for i, moeda in enumerate(sorted(moedas_unicas)):
                total_me  = sum(c["valor_me"] or 0 for c in cambios if c["moeda"] == moeda)
                taxa_m    = ptax_hoje.get(moeda)
                total_brl = total_me * taxa_m if taxa_m else None
                brl_txt   = f"R$ {total_brl:,.2f}" if total_brl else "taxa indisponível"
                cols_tot[i % 4].metric(
                    f"{moeda} total",
                    f"{moeda} {total_me:,.2f}",
                    delta=brl_txt,
                )

            if can_edit:
                st.markdown("---")
                st.subheader("Fechar Câmbio")
                st.caption("Informe a data e a taxa efetiva da operação. O spread em relação à PTAX é calculado automaticamente.")

                opcoes = {f"#{c['id']} — {c['descricao']} ({c['moeda']} {c['valor_me']:,.2f})": c for c in cambios}
                escolha_label = st.selectbox("Câmbio a fechar", list(opcoes.keys()), key="sel_fechar")
                escolha = opcoes[escolha_label]

                col_f1, col_f2, col_f3 = st.columns(3)
                with col_f1:
                    data_fech = st.date_input("Data efetiva", value=date.today(), key="fech_data")
                with col_f2:
                    taxa_ef = st.number_input(
                        f"Taxa efetiva (BRL/{escolha['moeda']})",
                        min_value=0.0001, step=0.0001, format="%.4f",
                        key="fech_taxa"
                    )
                with col_f3:
                    ptax_fech = _ptax_cached(escolha["moeda"], data_fech)
                    ptax_display = ptax_fech or 0.0
                    ptax_ef = st.number_input(
                        f"PTAX do dia ({escolha['moeda']})",
                        value=ptax_display,
                        min_value=0.0001, step=0.0001, format="%.4f",
                        key="fech_ptax",
                        help="Preenchido automaticamente via BCB. Ajuste se necessário."
                    )

                if taxa_ef > 0 and ptax_ef > 0:
                    spread     = taxa_ef - ptax_ef
                    spread_pct = spread / ptax_ef * 100
                    valor_me   = escolha["valor_me"] or 0
                    valor_brl_ef = valor_me * taxa_ef
                    valor_brl_ptax = valor_me * ptax_ef

                    col_p1, col_p2, col_p3 = st.columns(3)
                    col_p1.metric("Valor BRL (taxa efetiva)", f"R$ {valor_brl_ef:,.2f}")
                    col_p2.metric("Valor BRL (PTAX)",         f"R$ {valor_brl_ptax:,.2f}")
                    spread_delta = f"{'▲' if spread >= 0 else '▼'} {abs(spread_pct):.2f}%"
                    col_p3.metric(
                        "Spread (efetiva − PTAX)",
                        f"R$ {spread:,.4f}",
                        delta=spread_delta,
                        delta_color="normal"
                    )

                obs_fech = st.text_input("Observações (opcional)", key="fech_obs")

                if st.button("✅ Confirmar fechamento", type="primary", key="btn_fechar"):
                    if taxa_ef <= 0:
                        st.error("Informe a taxa efetiva.")
                    elif ptax_ef <= 0:
                        st.error("Informe a PTAX do fechamento.")
                    else:
                        db.fechar_cambio(
                            cambio_id=escolha["id"],
                            data_fechamento=str(data_fech),
                            taxa_efetiva=taxa_ef,
                            ptax_fechamento=ptax_ef,
                            observacoes=obs_fech or None,
                        )
                        st.success(f"✅ Câmbio #{escolha['id']} fechado. Spread: {spread_pct:+.2f}%")
                        for k in list(st.session_state.keys()):
                            if k.startswith("_ptax_"):
                                del st.session_state[k]
                        st.rerun()

                st.markdown("---")
                st.subheader("↩️ Reverter Câmbio")
                st.caption(
                    "Cancela o câmbio disponível e restaura o lançamento original: "
                    "DATABASE → status PENDENTE | PROVISÕES → re-inserido."
                )

                opc_rev = {
                    f"#{c['id']} — {c['descricao']} ({c['moeda']} {c['valor_me']:,.2f}) "
                    f"| origem: {c.get('origem','MANUAL')}"
                    + (f" #{c['origem_id']}" if c.get("origem_id") else ""): c
                    for c in cambios
                }
                sel_rev = st.selectbox("Câmbio a reverter", list(opc_rev.keys()), key="sel_reverter")
                cambio_rev = opc_rev[sel_rev]

                confirmar_rev = st.checkbox(
                    f"Confirmo a reversão do câmbio #{cambio_rev['id']}",
                    key="rev_confirm"
                )
                if st.button("↩️ Reverter câmbio", type="secondary", key="btn_reverter",
                             disabled=not confirmar_rev):
                    msg = db.reverter_cambio(cambio_rev["id"])
                    st.success(f"✅ Câmbio #{cambio_rev['id']} cancelado. {msg}")
                    st.rerun()

    # ─── ABA NOVO CÂMBIO ──────────────────────────────────────────────────────
    with tab_novo:
        if not can_edit:
            st.info("👁️ Você tem acesso somente leitura.")
        else:
            st.subheader("Registrar novo câmbio disponível")

            # Busca de recebíveis para vincular
            st.markdown("**Vincular a recebível existente (opcional)**")
            st.caption("Busque na DATABASE ou PROVISÕES para associar este câmbio a um lançamento.")

            busca_term = st.text_input("🔍 Buscar recebível", placeholder="Razão social, código, descrição...", key="novo_busca")
            recebiveis = db.buscar_recebiveis_exportacao(busca_term) if busca_term else []

            origem_id  = None
            origem_sel = "MANUAL"

            if recebiveis:
                opcoes_rec = {"— Não vincular —": None}
                for r in recebiveis:
                    lbl = (
                        f"[{r['origem']}] {r['razao_social']} | "
                        f"{r['descricao'] or ''} | "
                        f"Venc. {r['vencimento'][:10] if r.get('vencimento') else '?'} | "
                        f"R$ {r['valor_final']:,.2f}"
                    )
                    opcoes_rec[lbl] = r
                escolha_rec_lbl = st.selectbox("Selecione o recebível", list(opcoes_rec.keys()), key="novo_rec_sel")
                escolha_rec = opcoes_rec[escolha_rec_lbl]
                if escolha_rec:
                    origem_id  = escolha_rec["id"]
                    origem_sel = escolha_rec["origem"]
            elif busca_term:
                st.caption("Nenhum recebível CREDITO PENDENTE encontrado para esse termo.")

            st.markdown("---")
            st.markdown("**Dados do câmbio**")

            col_n1, col_n2, col_n3 = st.columns(3)
            with col_n1:
                moeda_novo = st.selectbox("Moeda", ["USD", "EUR", "GBP", "CHF", "JPY", "ARS", "CNY"], key="novo_moeda")
            with col_n2:
                valor_me_novo = st.number_input(
                    f"Valor em {moeda_novo}",
                    min_value=0.0, step=100.0, format="%.2f", key="novo_valor_me"
                )
            with col_n3:
                data_entrada_novo = st.date_input("Data de entrada", value=date.today(), key="novo_data")

            # Busca PTAX automaticamente
            ptax_novo = _ptax_cached(moeda_novo, data_entrada_novo)
            col_p1, col_p2 = st.columns(2)
            with col_p1:
                ptax_entrada = st.number_input(
                    f"PTAX de entrada ({moeda_novo})",
                    value=ptax_novo or 0.0,
                    min_value=0.0, step=0.0001, format="%.4f",
                    key="novo_ptax",
                    help="Preenchido via BCB. Ajuste se necessário."
                )
            with col_p2:
                if ptax_entrada > 0 and valor_me_novo > 0:
                    st.metric("BRL Projetado", f"R$ {valor_me_novo * ptax_entrada:,.2f}")

            descricao_novo = st.text_input(
                "Descrição",
                value=(escolha_rec["razao_social"] if recebiveis and escolha_rec else ""),
                key="novo_desc"
            )
            obs_novo = st.text_area("Observações", key="novo_obs", height=80)

            if st.button("💾 Salvar câmbio", type="primary", key="btn_novo_salvar"):
                if valor_me_novo <= 0:
                    st.error("Informe o valor em moeda estrangeira.")
                elif not descricao_novo:
                    st.error("Informe a descrição.")
                else:
                    novo_id = db.inserir_cambio({
                        "descricao":         descricao_novo,
                        "moeda":             moeda_novo,
                        "valor_me":          valor_me_novo,
                        "data_entrada":      str(data_entrada_novo),
                        "taxa_ptax_entrada": ptax_entrada or None,
                        "origem":            origem_sel,
                        "origem_id":         origem_id,
                        "observacoes":       obs_novo or None,
                    })
                    msg = f"✅ Câmbio #{novo_id} registrado!"
                    # Baixa imediata do lançamento vinculado
                    if origem_id:
                        db.marcar_recebivel_recebido(origem_sel, origem_id)
                        baixa_txt = "marcado como RECEBIDO" if origem_sel == "DATABASE" else "excluído das PROVISÕES"
                        msg += f" | {origem_sel} #{origem_id} {baixa_txt}."
                    st.success(msg)
                    for k in list(st.session_state.keys()):
                        if k.startswith("_ptax_"):
                            del st.session_state[k]
                    st.rerun()

    # ─── ABA HISTÓRICO ────────────────────────────────────────────────────────
    with tab_hist:
        st.subheader("Câmbios fechados e cancelados")

        todos = db.listar_cambios()
        historico = [c for c in todos if c["status"] in ("FECHADO", "CANCELADO")]

        if not historico:
            st.info("Nenhum câmbio fechado ainda.")
        else:
            col_hf1, col_hf2 = st.columns(2)
            with col_hf1:
                status_filtro = st.selectbox(
                    "Status", ["Todos", "FECHADO", "CANCELADO"], key="hist_status"
                )
            with col_hf2:
                moeda_filtro = st.selectbox(
                    "Moeda", ["Todas"] + sorted({c["moeda"] for c in historico}),
                    key="hist_moeda"
                )

            dados_hist = historico
            if status_filtro != "Todos":
                dados_hist = [c for c in dados_hist if c["status"] == status_filtro]
            if moeda_filtro != "Todas":
                dados_hist = [c for c in dados_hist if c["moeda"] == moeda_filtro]

            if not dados_hist:
                st.info("Nenhum registro para os filtros selecionados.")
            else:
                rows_h = []
                for c in dados_hist:
                    rows_h.append({
                        "id":            c["id"],
                        "Status":        c["status"],
                        "Descrição":     c["descricao"] or "—",
                        "Moeda":         c["moeda"],
                        "Valor ME":      c["valor_me"],
                        "Entrada":       c.get("data_entrada", ""),
                        "Fechamento":    c.get("data_fechamento", ""),
                        "PTAX Entrada":  c.get("taxa_ptax_entrada"),
                        "PTAX Fech.":    c.get("ptax_fechamento"),
                        "Taxa Efetiva":  c.get("taxa_efetiva"),
                        "Spread R$":     c.get("spread"),
                        "Spread %":      c.get("spread_pct"),
                        "Obs":           c.get("observacoes") or "",
                    })

                df_h = pd.DataFrame(rows_h)

                def _fmt_taxa(v):
                    return f"R$ {v:,.4f}" if v else "—"

                def _fmt_spread(v):
                    if v is None: return "—"
                    return f"{'▲' if v >= 0 else '▼'} {abs(v):.2f}%"

                df_show_h = df_h.copy()
                df_show_h["Valor ME"]     = df_show_h.apply(lambda r: f"{r['Moeda']} {r['Valor ME']:,.2f}" if r["Valor ME"] else "—", axis=1)
                df_show_h["Entrada"]      = pd.to_datetime(df_show_h["Entrada"], errors="coerce").dt.strftime("%d/%m/%Y")
                df_show_h["Fechamento"]   = pd.to_datetime(df_show_h["Fechamento"], errors="coerce").dt.strftime("%d/%m/%Y")
                df_show_h["PTAX Entrada"] = df_show_h["PTAX Entrada"].apply(_fmt_taxa)
                df_show_h["PTAX Fech."]   = df_show_h["PTAX Fech."].apply(_fmt_taxa)
                df_show_h["Taxa Efetiva"] = df_show_h["Taxa Efetiva"].apply(_fmt_taxa)
                df_show_h["Spread R$"]    = df_show_h["Spread R$"].apply(lambda v: f"R$ {v:,.4f}" if v else "—")
                df_show_h["Spread %"]     = df_show_h["Spread %"].apply(_fmt_spread)

                fechados = [c for c in dados_hist if c["status"] == "FECHADO"]
                if fechados:
                    sp_vals = [c["spread_pct"] for c in fechados if c.get("spread_pct") is not None]
                    if sp_vals:
                        col_s1, col_s2, col_s3 = st.columns(3)
                        col_s1.metric("Câmbios fechados", len(fechados))
                        col_s2.metric("Spread médio", f"{sum(sp_vals)/len(sp_vals):+.2f}%")
                        col_s3.metric("Melhor spread", f"{max(sp_vals):+.2f}%")
                        st.markdown("---")

                st.dataframe(
                    df_show_h[["id","Status","Descrição","Valor ME","Entrada",
                               "Fechamento","PTAX Entrada","PTAX Fech.","Taxa Efetiva",
                               "Spread R$","Spread %","Obs"]],
                    use_container_width=True, hide_index=True
                )

                if st.button("📥 Exportar CSV", key="hist_export"):
                    csv = pd.DataFrame(dados_hist).to_csv(index=False).encode("utf-8-sig")
                    st.download_button("⬇️ Baixar histórico.csv", data=csv,
                                       file_name="cambios_historico.csv", mime="text/csv")

                if can_edit:
                    st.markdown("---")
                    st.subheader("Reabrir câmbio fechado")
                    fechados_lista = [c for c in dados_hist if c["status"] == "FECHADO"]
                    if fechados_lista:
                        opc_reab = {
                            f"#{c['id']} — {c['descricao']} ({c['moeda']} {c['valor_me']:,.2f}) fechado em {c.get('data_fechamento','?')}": c
                            for c in fechados_lista
                        }
                        sel_reab = st.selectbox("Câmbio a reabrir", list(opc_reab.keys()), key="sel_reabrir")
                        if st.button("↩️ Reabrir", key="btn_reabrir"):
                            db.reabrir_cambio(opc_reab[sel_reab]["id"])
                            st.success("Câmbio reaberto e movido para Disponíveis.")
                            st.rerun()
