"""
Página Recebíveis VP — Valor Presente dos recebíveis futuros.
"""

import streamlit as st
import pandas as pd
from datetime import date, datetime
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import db


def render():
    st.title("📉 Recebíveis — Valor Presente")
    st.markdown("Calcule o valor presente (VP) dos recebíveis futuros descontados a uma taxa mensal.")

    cfg_fim = st.session_state.get("cfg_dt_fim", str(date(date.today().year, 12, 31)))

    col_f1, col_f2, col_f3, col_f4 = st.columns(4)
    with col_f1:
        dt_base = st.date_input("Data base (hoje)", value=date.today())
    with col_f2:
        dt_fim = st.date_input("Até", value=date.fromisoformat(cfg_fim), key="vp_fim")
    with col_f3:
        taxa_am = st.number_input("Taxa de desconto (% a.m.)", min_value=0.0, max_value=100.0,
                                   value=1.5, step=0.1, format="%.2f")
    with col_f4:
        incluir_fup = st.checkbox("Incluir FUP Vendas (ALTA)", value=True)

    if st.button("🧮 Calcular VP", type="primary"):
        # Busca todos os créditos futuros
        erp_rows  = db.listar_erp(dt_ini=str(dt_base), dt_fim=str(dt_fim), operacao="CREDITO")
        prov_rows = db.listar_provisoes(dt_ini=str(dt_base), dt_fim=str(dt_fim), operacao="CREDITO")
        fup_rows  = db.listar_fup(dt_ini=str(dt_base), dt_fim=str(dt_fim), prob="ALTA") if incluir_fup else []

        todos = []
        for r in erp_rows:
            r["origem_label"] = "ERP"
            todos.append(r)
        for r in prov_rows:
            r["origem_label"] = "PROVISÃO"
            todos.append(r)
        for r in fup_rows:
            if r.get("operacao") == "CREDITO":
                r["origem_label"] = "FUP"
                todos.append(r)

        if not todos:
            st.warning("Nenhum recebível futuro encontrado no período.")
            return

        taxa_diaria = (1 + taxa_am / 100) ** (1/30) - 1
        hoje = dt_base

        linhas = []
        for r in todos:
            try:
                ven = datetime.strptime(r["vencimento"][:10], "%Y-%m-%d").date()
            except:
                continue
            dias = (ven - hoje).days
            if dias < 0:
                dias = 0
            vn = abs(r.get("valor") or 0)
            vp = vn / ((1 + taxa_diaria) ** dias)
            linhas.append({
                "Origem":       r.get("origem_label", ""),
                "Razão Social": r.get("razao_social", ""),
                "Descrição":    r.get("descricao", ""),
                "Vencimento":   ven.strftime("%d/%m/%Y"),
                "Dias":         dias,
                "Valor Nominal": vn,
                "Valor Presente": round(vp, 2),
                "Desconto":     round(vn - vp, 2),
            })

        df = pd.DataFrame(linhas)
        total_vn = df["Valor Nominal"].sum()
        total_vp = df["Valor Presente"].sum()
        total_desc = df["Desconto"].sum()

        col_m1, col_m2, col_m3 = st.columns(3)
        col_m1.metric("Valor Nominal Total", f"R$ {total_vn:,.2f}")
        col_m2.metric("Valor Presente Total", f"R$ {total_vp:,.2f}")
        col_m3.metric("Desconto Total", f"R$ {total_desc:,.2f}",
                       delta=f"-{total_desc/total_vn*100:.1f}%" if total_vn else "")

        st.markdown("---")

        # Formata para exibição
        df_show = df.copy()
        df_show["Valor Nominal"]   = df_show["Valor Nominal"].apply(lambda x: f"R$ {x:,.2f}")
        df_show["Valor Presente"]  = df_show["Valor Presente"].apply(lambda x: f"R$ {x:,.2f}")
        df_show["Desconto"]        = df_show["Desconto"].apply(lambda x: f"R$ {x:,.2f}")
        st.dataframe(df_show, use_container_width=True)

        # Gráfico por mês
        df["Vencimento_dt"] = pd.to_datetime(df["Vencimento"], format="%d/%m/%Y")
        df["Mês"] = df["Vencimento_dt"].dt.to_period("M").astype(str)
        mensal = df.groupby("Mês")[["Valor Nominal", "Valor Presente"]].sum().reset_index()
        st.markdown("**Nominal vs Valor Presente por Mês**")
        st.bar_chart(mensal.set_index("Mês"), height=300)
