"""
Página FC Diário — Visão consolidada das três camadas com saldo acumulado.
"""

import streamlit as st
import pandas as pd
from datetime import date
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import db


CORES_ORIGEM = {
    "ERP":     "#2E75B6",
    "PROVISAO": "#E67E22",
    "FUP":     "#27AE60",
}


def render():
    st.title("📅 FC Diário — Fluxo Consolidado")
    st.markdown("Visão unificada das três camadas: **DATABASE/ERP** + **Provisões** + **FUP Vendas**.")

    # ─── FILTROS ───────────────────────────────────────────────────────────
    cfg_ini   = st.session_state.get("cfg_dt_ini", str(date(date.today().year, 1, 1)))
    cfg_fim   = st.session_state.get("cfg_dt_fim", str(date(date.today().year, 12, 31)))
    cfg_alta  = st.session_state.get("cfg_inc_alta", True)
    cfg_media = st.session_state.get("cfg_inc_media", False)
    cfg_corte = st.session_state.get("cfg_corte_status", True)

    col_f1, col_f2, col_f3, col_f4, col_f5 = st.columns(5)
    with col_f1:
        dt_ini = st.date_input("De", value=date.fromisoformat(cfg_ini), key="fcd_ini")
    with col_f2:
        dt_fim = st.date_input("Até", value=date.fromisoformat(cfg_fim), key="fcd_fim")
    with col_f3:
        incluir_alta  = st.checkbox("Incluir ALTA",  value=cfg_alta,  key="fcd_alta")
    with col_f4:
        incluir_media = st.checkbox("Incluir MEDIA", value=cfg_media, key="fcd_media")
    with col_f5:
        op_filtro = st.selectbox("Operação", ["Todas", "CREDITO", "DEBITO"], key="fcd_op")

    col_f6, col_f7, col_f8 = st.columns([1, 1, 3])
    with col_f6:
        inc_fci = st.checkbox("Incluir FCI", value=True, key="fcd_fci")
    with col_f7:
        inc_fcf = st.checkbox("Incluir FCF", value=True, key="fcd_fcf")

    st.caption(
        f"⚙️ ERP: {'excluindo PENDENTES anteriores à data inicial' if cfg_corte else 'incluindo todos os lançamentos'}"
        " — altere em **⚙️ Período de análise** na barra lateral."
    )

    saldo_inicial = db.get_saldo_total()

    dados = db.fc_diario(
        dt_ini=str(dt_ini), dt_fim=str(dt_fim),
        incluir_alta=incluir_alta,
        incluir_media=incluir_media,
        erp_corte_status=cfg_corte,
        saldo_inicial=saldo_inicial,
        inc_fci=inc_fci,
        inc_fcf=inc_fcf,
    )

    if op_filtro != "Todas":
        dados = [r for r in dados if r.get("operacao") == op_filtro]

    # ─── MÉTRICAS ──────────────────────────────────────────────────────────
    col_m1, col_m2, col_m3, col_m4, col_m5 = st.columns(5)
    if dados:
        total_cred  = sum(r["valor_final"] for r in dados if (r["valor_final"] or 0) > 0)
        total_deb   = sum(r["valor_final"] for r in dados if (r["valor_final"] or 0) < 0)
        saldo_final = dados[-1]["saldo_acumulado"] if dados else saldo_inicial
        col_m1.metric("Saldo Inicial (Bancos)", f"R$ {saldo_inicial:,.2f}")
        col_m2.metric("Entradas", f"R$ {total_cred:,.2f}")
        col_m3.metric("Saídas",   f"R$ {abs(total_deb):,.2f}")
        col_m4.metric("Saldo do Período", f"R$ {total_cred + total_deb:,.2f}")
        col_m5.metric("Saldo Final Projetado", f"R$ {saldo_final:,.2f}")
    else:
        st.info("Nenhum lançamento encontrado para o período e filtros selecionados.")
        return

    st.markdown("---")

    df = pd.DataFrame(dados)
    df["vencimento_dt"] = pd.to_datetime(df["vencimento"], errors="coerce")

    # ─── AGRUPAMENTO (controla gráfico E tabela) ───────────────────────────
    col_t1, col_t2 = st.columns([3, 1])
    with col_t2:
        agrupar = st.selectbox("Agrupar por", ["Nenhum", "Semana", "Mês", "Origem"])

    # Adiciona colunas de agrupamento no df
    df["mes"]    = df["vencimento_dt"].dt.to_period("M").astype(str)
    df["semana"] = df["semana"].astype(str).str.zfill(2)   # garante ordenação

    # ─── GRÁFICO ───────────────────────────────────────────────────────────
    if agrupar == "Origem":
        # Origem não é série temporal → barras de entradas/saídas por origem
        pivot_orig = (
            df.assign(
                entradas=df["valor_final"].apply(lambda x: x if (x or 0) > 0 else 0),
                saidas=df["valor_final"].apply(lambda x: abs(x) if (x or 0) < 0 else 0),
            )
            .groupby("origem")
            .agg(entradas=("entradas", "sum"), saidas=("saidas", "sum"))
        )
        st.markdown("**Entradas e Saídas por Origem**")
        st.bar_chart(pivot_orig.rename(columns={"entradas": "Entradas 🟢", "saidas": "Saídas 🔴"}),
                     height=250)
    else:
        # Série temporal: usa saldo_acumulado (já inclui saldo_inicial) por período
        col_grupo = {"Nenhum": "vencimento_dt", "Semana": "semana", "Mês": "mes"}[agrupar]
        df_saldo = (
            df.groupby(col_grupo)["saldo_acumulado"]
              .last()
              .reset_index()
        )
        df_saldo.columns = [agrupar if agrupar != "Nenhum" else "Data", "Saldo Acumulado"]
        st.markdown(f"**Saldo acumulado por {agrupar if agrupar != 'Nenhum' else 'dia'}** "
                    f"*(início: R$ {saldo_inicial:,.2f})*")
        st.line_chart(df_saldo.set_index(df_saldo.columns[0]), height=250)

    st.markdown("---")

    # ─── TABELA ────────────────────────────────────────────────────────────
    if agrupar == "Nenhum":
        _tabela_detalhada(df, dados)
    elif agrupar == "Semana":
        _tabela_agrupada(df, "semana", "Semana")
    elif agrupar == "Mês":
        _tabela_agrupada(df, "mes", "Mês")
    elif agrupar == "Origem":
        _tabela_agrupada(df, "origem", "Origem")

    # Exportar
    st.markdown("---")
    if st.button("📥 Exportar CSV"):
        csv = df.to_csv(index=False).encode("utf-8-sig")
        st.download_button(
            "⬇️ Baixar FC_Diario.csv",
            data=csv,
            file_name=f"FC_Diario_{dt_ini}_{dt_fim}.csv",
            mime="text/csv"
        )


def _tabela_detalhada(df, dados):
    df_show = df.copy()
    df_show["vencimento"] = pd.to_datetime(df_show["vencimento"]).dt.strftime("%d/%m/%Y")
    df_show["valor"]         = df_show["valor"].apply(lambda x: f"R$ {x:,.2f}" if x else "")
    df_show["valor_final"]   = df_show["valor_final"].apply(_fmt_valor)
    df_show["saldo_acumulado"] = df_show["saldo_acumulado"].apply(_fmt_valor)

    cols_show = ["origem", "operacao", "razao_social", "descricao", "lote",
                 "vencimento", "valor", "valor_final", "probabilidade",
                 "semana", "saldo_acumulado"]
    cols_show = [c for c in cols_show if c in df_show.columns]

    st.dataframe(df_show[cols_show], use_container_width=True, height=550)


def _tabela_agrupada(df, col_grupo, label):
    resumo = (
        df.groupby(col_grupo)
          .agg(
              entradas=("valor_final", lambda x: x[x > 0].sum()),
              saidas=("valor_final", lambda x: x[x < 0].sum()),
              saldo=("valor_final", "sum"),
              qtd=("valor_final", "count"),
          )
          .reset_index()
    )
    resumo.columns = [label, "Entradas", "Saídas", "Saldo", "Qtd"]
    resumo["Entradas"] = resumo["Entradas"].apply(lambda x: f"R$ {x:,.2f}")
    resumo["Saídas"]   = resumo["Saídas"].apply(lambda x: f"R$ {x:,.2f}")
    resumo["Saldo"]    = resumo["Saldo"].apply(_fmt_valor)
    st.dataframe(resumo, use_container_width=True)


def _fmt_valor(x):
    if x is None:
        return ""
    cor = "🟢" if x >= 0 else "🔴"
    return f"{cor} R$ {x:,.2f}"
