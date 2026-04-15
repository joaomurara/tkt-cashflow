"""
Página Simulação de Venda — Preview de impacto no fluxo sem salvar.
"""

import streamlit as st
import pandas as pd
import json
from datetime import date, datetime
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import pipedrive_core as pc
import db

from pages.fup_vendas import _editor_parcelas


MOEDAS = ["BRL", "USD", "EUR", "ARS", "COP", "PEN", "CRC", "HNL", "GTQ", "PAB"]


def render():
    st.title("🧮 Simulação de Venda")
    st.markdown("Simule o impacto de um novo negócio no fluxo de caixa — sem salvar no banco.")

    # ── Dados do negócio ─────────────────────────────────────────────────────
    st.subheader("Dados do negócio")
    col1, col2, col3 = st.columns(3)
    with col1:
        cliente    = st.text_input("Cliente *", value="Simulação")
        funil      = st.selectbox("Funil", ["Nacional", "Exportação"])
        moeda      = st.selectbox("Moeda", MOEDAS)
    with col2:
        valor_orig    = st.number_input("Valor *", min_value=0.01, step=1000.0, format="%.2f")
        cambio_manual = st.number_input("Câmbio (R$/moeda)", min_value=0.0, value=1.0,
                                         step=0.01, format="%.4f",
                                         help="Deixe 0 para buscar automaticamente")
        close_date    = st.date_input("Data de Fechamento *", value=date.today())
    with col3:
        prob       = st.selectbox("Probabilidade", ["ALTA", "MEDIA", "CONFIRMADO"])
        prazo_ent  = st.number_input("Prazo de Entrega (dias)", min_value=0, value=60)
        tipo_fluxo = st.selectbox("Tipo de Fluxo", [1, 2, 3, 4],
                                   format_func=lambda x: {
                                       1: "Tipo 1 — Entrada + Parcelas",
                                       2: "Tipo 2 — Entrada + Pós X dias + Fat.",
                                       3: "Tipo 3 — Tipo 2 + Pós Fat.",
                                       4: "Tipo 4 — Livre (datas e valores customizados)",
                                   }[x])

    # ── Parâmetros de recebimento ─────────────────────────────────────────────
    st.subheader("Parâmetros de recebimento")

    pct_ent = pct_com = pct_pos = pct_fat = pct_pos_f = 0.0
    n_parc = 4; interv = 30; x_dias = 30; dias_pos_f = 30

    if tipo_fluxo == 4:
        st.caption("Configure cada evento de recebimento. A data será **Fechamento + Dias** ou **Faturamento + Dias**.")
        hc = st.columns([3, 2, 2, 2, 2, 1])
        for lbl, col in zip(["Descrição", "Tipo", "Valor", "Referência", "+ Dias", ""], hc):
            col.markdown(f"**{lbl}**")
        _editor_parcelas(
            key_prefix="sim_parc",
            parcelas_json=st.session_state.get("_sim_parc_json", "[]"),
            valor_ref=float(valor_orig),
            titulo="Recebimentos",
            op="CREDITO",
        )
        pct_com = st.number_input("% Comissão", 0.0, 100.0, 0.0, 0.5, key="sim_com4")

    else:
        col_p1, col_p2, col_p3 = st.columns(3)
        with col_p1:
            pct_ent = st.number_input("% Entrada", 0.0, 100.0, 0.0, 1.0)
            pct_com = st.number_input("% Comissão", 0.0, 100.0, 0.0, 0.5)
        with col_p2:
            if tipo_fluxo == 1:
                n_parc = st.number_input("N° Parcelas", 1, 48, 4)
                interv = st.number_input("Intervalo (dias)", 1, 365, 30)
            else:
                pct_pos = st.number_input("% Pós X dias", 0.0, 100.0, 0.0, 1.0)
                x_dias  = st.number_input("X Dias", 1, 365, 30)
        with col_p3:
            if tipo_fluxo in (2, 3):
                pct_fat = st.number_input("% Faturamento", 0.0, 100.0, 0.0, 1.0)
            if tipo_fluxo == 3:
                pct_pos_f  = st.number_input("% Pós Faturamento", 0.0, 100.0, 0.0, 1.0)
                dias_pos_f = st.number_input("Dias Pós Fat.", 1, 365, 30)

    # ── Matéria Prima ────────────────────────────────────────────────────────
    with st.expander("🏭 Fluxo de Compra de Matéria Prima", expanded=False):
        st.caption(
            "Configure os pagamentos de matéria prima como débitos. "
            "Referência pode ser **Fechamento** ou **Faturamento**."
        )
        hc2 = st.columns([3, 2, 2, 2, 2, 1])
        for lbl, col in zip(["Descrição", "Tipo", "Valor", "Referência", "+ Dias", ""], hc2):
            col.markdown(f"**{lbl}**")
        _editor_parcelas(
            key_prefix="sim_mp",
            parcelas_json=st.session_state.get("_sim_mp_json", "[]"),
            valor_ref=float(valor_orig),
            titulo="Matéria Prima",
            op="DEBITO",
        )

    # ── Impostos ─────────────────────────────────────────────────────────────
    pct_icms = pct_pis = 0.0; dias_icms = 10; dias_pis = 25
    if funil == "Nacional":
        with st.expander("⚙️ Impostos"):
            col_i1, col_i2 = st.columns(2)
            with col_i1:
                pct_icms  = st.number_input("% ICMS", 0.0, 100.0, 8.8, 0.1)
                dias_icms = st.number_input("Dia ICMS mês seg.", 1, 31, 10)
            with col_i2:
                pct_pis  = st.number_input("% PIS/COFINS", 0.0, 100.0, 5.9, 0.1)
                dias_pis = st.number_input("Dia PIS mês seg.", 1, 31, 25)

    # ── Botão Simular ─────────────────────────────────────────────────────────
    if st.button("▶️ Simular", type="primary"):
        if cambio_manual > 0:
            cambio = cambio_manual
        elif moeda == "BRL":
            cambio = 1.0
        else:
            with st.spinner("Buscando câmbio..."):
                tabela = pc.buscar_cambio()
            cambio = tabela.get(moeda, 1.0)
            st.info(f"Câmbio buscado: {moeda}/BRL = {cambio:.4f}")

        valor_brl = round(valor_orig * cambio, 2)

        parc_livres_val = st.session_state.get("_parc_sim_parc", [])
        mp_livres_val   = st.session_state.get("_parc_sim_mp", [])

        cfg = {
            "tipo_fluxo":           tipo_fluxo,
            "pct_entrada":          pct_ent / 100,
            "pct_comissao":         pct_com / 100,
            "prazo_entrega":        int(prazo_ent),
            "n_parcelas":           int(n_parc),
            "intervalo_parcelas":   int(interv),
            "pct_pos_x":            pct_pos / 100,
            "x_dias":               int(x_dias),
            "pct_fat":              pct_fat / 100,
            "pct_pos_fat":          pct_pos_f / 100,
            "dias_pos_fat":         int(dias_pos_f),
            "pct_icms":             pct_icms / 100,
            "dias_icms":            int(dias_icms),
            "pct_pis_cofins":       pct_pis / 100,
            "dias_pis_cofins":      int(dias_pis),
            "parcelas_livres_json": json.dumps(parc_livres_val),
            "mp_json":              json.dumps(mp_livres_val),
        }

        linhas = pc.linhas_deal(cfg, "SIM", cliente, funil, str(close_date), valor_brl, prob)

        if not linhas:
            st.warning("Nenhuma linha gerada. Verifique os parâmetros.")
            st.session_state["_sim_linhas"]  = []
            st.session_state["_sim_meta"]    = {}
        else:
            # Persiste no session_state para o envio funcionar após rerun
            st.session_state["_sim_linhas"] = linhas
            st.session_state["_sim_meta"]   = {
                "cliente":   cliente,
                "funil":     funil,
                "prob":      prob,
                "valor_brl": valor_brl,
            }

    # ── Resultado (renderizado sempre que houver linhas em session_state) ─────
    linhas = st.session_state.get("_sim_linhas", [])
    meta   = st.session_state.get("_sim_meta", {})

    if not linhas:
        return

    _cliente   = meta.get("cliente", "")
    _funil     = meta.get("funil", "Nacional")
    _prob      = meta.get("prob", "ALTA")
    _valor_brl = meta.get("valor_brl", 0)

    st.markdown("---")
    st.subheader(f"Resultado da simulação — R$ {_valor_brl:,.2f} BRL")

    total_cred = sum(l["valor_final"] for l in linhas if l.get("valor_final", 0) > 0)
    total_deb  = sum(l["valor_final"] for l in linhas if l.get("valor_final", 0) < 0)
    col_r1, col_r2, col_r3 = st.columns(3)
    col_r1.metric("Entradas",      f"R$ {total_cred:,.2f}")
    col_r2.metric("Saídas",        f"R$ {abs(total_deb):,.2f}")
    col_r3.metric("Saldo Líquido", f"R$ {total_cred + total_deb:,.2f}",
                   delta=f"R$ {total_cred + total_deb:,.2f}")

    df = pd.DataFrame(linhas)
    df_show = df.copy()
    df_show["vencimento"] = pd.to_datetime(df_show["vencimento"]).dt.strftime("%d/%m/%Y")
    df_show["valor"]       = df_show["valor"].apply(lambda x: f"R$ {x:,.2f}")
    df_show["valor_final"] = df_show["valor_final"].apply(
        lambda x: f"🟢 R$ {x:,.2f}" if x >= 0 else f"🔴 R$ {abs(x):,.2f}"
    )
    cols_show = ["descricao", "operacao", "vencimento", "valor", "valor_final", "imposto"]
    cols_show = [c for c in cols_show if c in df_show.columns]
    st.dataframe(df_show[cols_show], use_container_width=True)

    # ── Enviar para Provisões ─────────────────────────────────────────────────
    st.markdown("---")
    st.subheader("📤 Enviar para Provisões")
    st.caption(
        "Salva as linhas desta simulação como provisões no banco de dados. "
        "Após enviar, os lançamentos aparecem nos módulos FC Diário, FC Resumo e Gráfico."
    )

    linhas_validas = [l for l in linhas if l.get("vencimento") and l.get("valor")]

    col_e1, col_e2 = st.columns([3, 1])
    with col_e1:
        filtro_op = st.multiselect(
            "Filtrar por operação",
            options=["CREDITO", "DEBITO"],
            default=["CREDITO", "DEBITO"],
            key="sim_filtro_op",
        )
    with col_e2:
        st.markdown("<br>", unsafe_allow_html=True)
        linhas_enviar = [l for l in linhas_validas if l.get("operacao") in filtro_op]
        st.caption(f"{len(linhas_enviar)} linha(s)")

    if st.button("📤 Confirmar envio para Provisões", type="primary", key="sim_enviar_prov"):
        linhas_enviar = [l for l in linhas_validas if l.get("operacao") in filtro_op]
        if not linhas_enviar:
            st.warning("Nenhuma linha para enviar com o filtro atual.")
        else:
            erros    = []
            enviados = 0
            for l in linhas_enviar:
                try:
                    db.inserir_provisao({
                        "operacao":      l["operacao"],
                        "codigo":        f"SIM-{_cliente[:10].upper()}",
                        "tipo":          "SIMULACAO",
                        "lote":          _funil,
                        "razao_social":  _cliente,
                        "descricao":     l.get("descricao", ""),
                        "vencimento":    l["vencimento"],
                        "valor":         abs(l["valor"]),
                        "probabilidade": _prob,
                        "imposto":       l.get("imposto", "NAO"),
                    })
                    enviados += 1
                except Exception as e:
                    erros.append(str(e))

            if enviados:
                st.success(f"✅ {enviados} lançamento(s) enviado(s) para Provisões!")
                st.session_state["_sim_linhas"] = []   # limpa após envio
                st.session_state["_sim_meta"]   = {}
            if erros:
                st.error(f"⚠️ {len(erros)} erro(s): {erros[0]}")

    # ── Impacto no FC Diário ──────────────────────────────────────────────────
    st.markdown("---")
    st.subheader("Impacto no FC Diário (preview)")
    vens = sorted(set(l["vencimento"] for l in linhas if l.get("vencimento")))
    if vens:
        dt_sim_ini = min(vens)
        dt_sim_fim = max(vens)
        dados_atuais = db.fc_diario(dt_sim_ini, dt_sim_fim, True, False)
        saldo_sem  = dados_atuais[-1]["saldo_acumulado"] if dados_atuais else 0
        saldo_com  = saldo_sem + (total_cred + total_deb)
        col_i1, col_i2, col_i3 = st.columns(3)
        col_i1.metric("Saldo sem simulação", f"R$ {saldo_sem:,.2f}")
        col_i2.metric("Efeito da venda",     f"R$ {total_cred + total_deb:,.2f}")
        col_i3.metric("Saldo com simulação", f"R$ {saldo_com:,.2f}",
                       delta=f"R$ {total_cred + total_deb:,.2f}")
