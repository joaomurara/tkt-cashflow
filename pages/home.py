"""Página inicial — resumo rápido do sistema."""

import streamlit as st
from datetime import date
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import db


def render():
    _logo = os.path.join(os.path.dirname(os.path.dirname(__file__)), "logo_tecnontok_basico.png")
    col_logo, col_title = st.columns([1, 8])
    with col_logo:
        if os.path.exists(_logo):
            st.image(_logo, width=72)
    with col_title:
        st.title("TKT Cash Flow")
    st.markdown(f"**{date.today().strftime('%d/%m/%Y')}** — Bem-vindo ao painel de fluxo de caixa.")

    # Totais rápidos
    col1, col2, col3, col4 = st.columns(4)

    try:
        erp_rows   = db.listar_erp()
        prov_rows  = db.listar_provisoes()
        fup_rows   = db.listar_fup()
        saldos     = db.listar_saldos_recentes()

        total_erp  = sum(r["valor_final"] or 0 for r in erp_rows)
        total_prov = sum(r["valor_final"] or 0 for r in prov_rows)
        total_fup_alta  = sum(r["valor_final"] or 0 for r in fup_rows if r["probabilidade"] in ("ALTA", "CONFIRMADO"))
        saldo_bancos = sum(r["saldo"] or 0 for r in saldos)

        col1.metric("DATABASE / ERP", f"R$ {total_erp:,.2f}",
                    f"{len(erp_rows)} lançamentos")
        col2.metric("Provisões", f"R$ {total_prov:,.2f}",
                    f"{len(prov_rows)} lançamentos")
        col3.metric("FUP Vendas (ALTA+)", f"R$ {total_fup_alta:,.2f}",
                    f"{len(fup_rows)} linhas")
        col4.metric("Saldo Bancos", f"R$ {saldo_bancos:,.2f}",
                    f"{len(saldos)} banco(s)")
    except Exception as e:
        st.error(f"Erro ao carregar resumo: {e}")

    st.markdown("---")
    st.markdown("""
    ### Como usar este app

    Use o menu lateral para navegar entre os módulos:

    - **DATABASE / ERP** — Importe os lançamentos do seu ERP via CSV. Suporta mapeamento flexível de colunas.
    - **Provisões** — Adicione manualmente lançamentos futuros que ainda não estão no ERP.
    - **FUP Vendas** — Sincronize com o Pipedrive e visualize as projeções de venda.
    - **FC Diário** — Visão consolidada das três camadas com saldo acumulado.
    - **Recebíveis VP** — Calcule o valor presente dos recebíveis futuros.
    - **FC Resumo** — Pivot mensal com cenários ALTA e MEDIA.
    - **Simulação de Venda** — Simule um novo negócio sem salvar no fluxo.
    - **Indicadores** — KPIs e posição de caixa projetada.
    - **Gráfico** — Visualização com toggles de probabilidade.
    """)
