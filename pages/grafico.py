"""
Página Gráfico — Barras empilhadas + linha de saldo com toggles de probabilidade.
"""

import streamlit as st
import pandas as pd
from datetime import date
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import db


def render():
    st.title("📉 Gráfico de Fluxo")

    # ─── CONTROLES ─────────────────────────────────────────────────────────
    cfg_ini   = st.session_state.get("cfg_dt_ini", str(date(date.today().year, 1, 1)))
    cfg_fim   = st.session_state.get("cfg_dt_fim", str(date(date.today().year, 12, 31)))
    cfg_corte = st.session_state.get("cfg_corte_status", True)

    col_f1, col_f2, col_f3, col_f4, col_f5 = st.columns(5)
    with col_f1:
        dt_ini = st.date_input("De", value=date.fromisoformat(cfg_ini), key="graf_ini")
    with col_f2:
        dt_fim = st.date_input("Até", value=date.fromisoformat(cfg_fim), key="graf_fim")
    with col_f3:
        inc_alta  = st.toggle("ALTA",  value=st.session_state.get("cfg_inc_alta", True),  key="g_alta")
    with col_f4:
        inc_media = st.toggle("MEDIA", value=st.session_state.get("cfg_inc_media", False), key="g_media")
    with col_f5:
        agrupamento = st.selectbox("Agrupar por", ["Semana", "Mês"], key="g_agrup")

    saldo_inicial = db.get_saldo_total()

    dados = db.fc_diario(str(dt_ini), str(dt_fim), inc_alta, inc_media,
                         erp_corte_status=cfg_corte, saldo_inicial=saldo_inicial)

    if not dados:
        st.info("Nenhum dado para os filtros selecionados.")
        return

    df = pd.DataFrame(dados)
    df["vencimento_dt"] = pd.to_datetime(df["vencimento"], errors="coerce")

    if agrupamento == "Semana":
        df["periodo"] = df["vencimento_dt"].dt.to_period("W").dt.start_time.dt.strftime("%d/%m")
    else:
        df["periodo"] = df["vencimento_dt"].dt.to_period("M").astype(str)

    # Entradas / Saídas por período
    pivot = (
        df.assign(
            entradas=df["valor_final"].apply(lambda x: x if (x or 0) > 0 else 0),
            saidas=df["valor_final"].apply(lambda x: x if (x or 0) < 0 else 0),
        )
        .groupby("periodo")
        .agg(entradas=("entradas", "sum"), saidas=("saidas", "sum"))
        .reset_index()
    )
    pivot["saldo"] = pivot["entradas"] + pivot["saidas"]
    # Saldo acumulado parte do saldo bancário atual
    pivot["saldo_acum"] = pivot["saldo"].cumsum() + float(saldo_inicial)

    # ─── GRÁFICO ENTRADAS / SAÍDAS ────────────────────────────────────────
    st.subheader("Entradas e Saídas por " + agrupamento)

    chart_data = pivot.set_index("periodo")[["entradas", "saidas"]].rename(
        columns={"entradas": "Entradas 🟢", "saidas": "Saídas 🔴"}
    )
    st.bar_chart(chart_data, height=350, use_container_width=True)

    # ─── GRÁFICO SALDO ACUMULADO ─────────────────────────────────────────
    st.subheader(f"Saldo Acumulado *(início: R$ {saldo_inicial:,.2f})*")
    saldo_chart = pivot.set_index("periodo")[["saldo_acum"]].rename(
        columns={"saldo_acum": "Saldo Acumulado"}
    )
    st.line_chart(saldo_chart, height=250, use_container_width=True)

    # ─── TABELA RESUMO ────────────────────────────────────────────────────
    st.subheader("Tabela resumo")
    tab_show = pivot.copy()
    tab_show.columns = [agrupamento, "Entradas", "Saídas", "Saldo Líquido", "Saldo Acumulado"]
    for col in ["Entradas", "Saídas", "Saldo Líquido", "Saldo Acumulado"]:
        tab_show[col] = tab_show[col].apply(
            lambda x: f"R$ {x:,.2f}" if x >= 0 else f"(R$ {abs(x):,.2f})"
        )
    st.dataframe(tab_show, use_container_width=True, hide_index=True)

    # ─── COMPOSIÇÃO POR ORIGEM ───────────────────────────────────────────
    with st.expander("📊 Composição por Origem"):
        by_orig = (
            df.groupby(["periodo", "origem"])["valor_final"]
              .sum()
              .reset_index()
              .pivot(index="periodo", columns="origem", values="valor_final")
              .fillna(0)
        )
        st.bar_chart(by_orig, height=300)
