"""
Página FC Resumo — Pivot mensal com cenários ALTA e MEDIA.
"""

import streamlit as st
import pandas as pd
from datetime import date
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import db


def render():
    st.title("📊 FC Resumo — Mensal")
    st.markdown("Pivot do fluxo de caixa agrupado por mês, com dois cenários de probabilidade.")

    cfg_ini   = st.session_state.get("cfg_dt_ini", str(date(date.today().year, 1, 1)))
    cfg_fim   = st.session_state.get("cfg_dt_fim", str(date(date.today().year, 12, 31)))
    cfg_corte = st.session_state.get("cfg_corte_status", True)

    col_f1, col_f2 = st.columns(2)
    with col_f1:
        dt_ini = st.date_input("De", value=date.fromisoformat(cfg_ini), key="fcr_ini")
    with col_f2:
        dt_fim = st.date_input("Até", value=date.fromisoformat(cfg_fim), key="fcr_fim")

    col_c1, col_c2 = st.columns(2)
    with col_c1:
        st.markdown("### Cenário 1 — ALTA")
        inc_alta_c1  = st.checkbox("Incluir ALTA",  value=True,  key="c1_alta")
        inc_media_c1 = st.checkbox("Incluir MEDIA", value=False, key="c1_media")
    with col_c2:
        st.markdown("### Cenário 2 — ALTA + MEDIA")
        inc_alta_c2  = st.checkbox("Incluir ALTA",  value=True,  key="c2_alta")
        inc_media_c2 = st.checkbox("Incluir MEDIA", value=True,  key="c2_media")

    saldo_inicial = db.get_saldo_total()

    dados_c1 = db.fc_diario(str(dt_ini), str(dt_fim), inc_alta_c1, inc_media_c1, erp_corte_status=cfg_corte, saldo_inicial=saldo_inicial)
    dados_c2 = db.fc_diario(str(dt_ini), str(dt_fim), inc_alta_c2, inc_media_c2, erp_corte_status=cfg_corte, saldo_inicial=saldo_inicial)

    df_c1 = _pivot_mensal(dados_c1, "Cenário 1", saldo_inicial)
    df_c2 = _pivot_mensal(dados_c2, "Cenário 2", saldo_inicial)

    if df_c1.empty and df_c2.empty:
        st.info("Nenhum dado para o período selecionado.")
        return

    st.markdown("---")

    col_t1, col_t2 = st.columns(2)
    with col_t1:
        st.markdown("### Cenário 1")
        _exibir_pivot(df_c1)
    with col_t2:
        st.markdown("### Cenário 2")
        _exibir_pivot(df_c2)

    # Comparativo gráfico
    st.markdown("---")
    st.markdown("### Comparativo — Saldo Acumulado por Mês")

    if not df_c1.empty and not df_c2.empty:
        comp = pd.DataFrame({
            "Cenário 1": df_c1.set_index("Mês")["Saldo Acumulado"],
            "Cenário 2": df_c2.set_index("Mês")["Saldo Acumulado"],
        }).fillna(0)
        st.caption(f"Saldo inicial (bancos): R$ {saldo_inicial:,.2f}")
        st.line_chart(comp, height=350)


def _pivot_mensal(dados, label, saldo_inicial=0.0):
    if not dados:
        return pd.DataFrame()

    df = pd.DataFrame(dados)
    df["vencimento_dt"] = pd.to_datetime(df["vencimento"], errors="coerce")
    df["mes"] = df["vencimento_dt"].dt.to_period("M").astype(str)

    resumo = (
        df.groupby("mes")
          .agg(
              entradas=("valor_final", lambda x: x[x > 0].sum()),
              saidas=("valor_final", lambda x: x[x < 0].sum()),
              saldo=("valor_final", "sum"),
          )
          .reset_index()
    )
    resumo.columns = ["Mês", "Entradas", "Saídas", "Saldo Líquido"]
    # Saldo acumulado parte do saldo bancário atual
    resumo["Saldo Acumulado"] = resumo["Saldo Líquido"].cumsum() + float(saldo_inicial)
    return resumo


def _exibir_pivot(df):
    if df.empty:
        st.info("Sem dados.")
        return

    df_show = df.copy()
    for col in ["Entradas", "Saídas", "Saldo Líquido", "Saldo Acumulado"]:
        df_show[col] = df_show[col].apply(
            lambda x: f"R$ {x:,.2f}" if x >= 0 else f"(R$ {abs(x):,.2f})"
        )
    st.dataframe(df_show, use_container_width=True, hide_index=True)
