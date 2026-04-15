"""
app.py — TKT Cash Flow App
Ponto de entrada principal do Streamlit
"""

import streamlit as st
import sys
import os
import base64

# Garante que o diretório do app está no path para imports relativos
sys.path.insert(0, os.path.dirname(__file__))

import db
import auth

# ─── AUTENTICAÇÃO ────────────────────────────────────────────────────────────
# Deve ser chamado ANTES de set_page_config quando não autenticado.
# require_login() chama set_page_config internamente se exibir o login.
auth.require_login()

# ─── CONFIGURAÇÃO DA PÁGINA ──────────────────────────────────────────────────
def _img_to_b64(path: str) -> str:
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode()

_icon_path = os.path.join(os.path.dirname(__file__), "logo_tecnontok_basico.png")
try:
    from PIL import Image as _PIL
    _page_icon = _PIL.open(_icon_path)
except Exception:
    _page_icon = "💰"

st.set_page_config(
    page_title="TKT Cash Flow",
    page_icon=_page_icon,
    layout="wide",
    initial_sidebar_state="expanded",
)

# Logo no topo do app (sidebar header)
if os.path.exists(_icon_path):
    st.logo(_icon_path, size="large")

# ─── INICIALIZA BANCO ────────────────────────────────────────────────────────
db.init_db()

# ─── ESTILO GLOBAL ───────────────────────────────────────────────────────────
st.markdown("""
<style>
    /* Oculta o menu de navegação automático do Streamlit (lista de arquivos) */
    [data-testid="stSidebarNav"] { display: none !important; }

    /* Sidebar */
    [data-testid="stSidebar"] { background-color: #1F4E79; }
    [data-testid="stSidebar"] * { color: white !important; }
    [data-testid="stSidebar"] .stButton > button {
        background-color: #2E75B6; border: none; color: white;
        width: 100%; text-align: left; padding: 0.4rem 1rem;
        border-radius: 6px; margin-bottom: 4px;
    }
    [data-testid="stSidebar"] .stButton > button:hover { background-color: #3A8FD4; }

    /* Métricas */
    [data-testid="metric-container"] {
        background: #f0f4f8; border-radius: 8px;
        padding: 12px 16px; border-left: 4px solid #2E75B6;
    }

    /* Tabela */
    .dataframe thead tr th { background-color: #2E75B6 !important; color: white !important; }

    /* Títulos de seção */
    h2 { color: #1F4E79; }
    h3 { color: #2E75B6; }

    /* Valor positivo/negativo */
    .positivo { color: #1a7c3e; font-weight: bold; }
    .negativo { color: #c0392b; font-weight: bold; }

    /* Logo no topo da sidebar */
    .sidebar-logo img {
        border-radius: 6px;
        margin-bottom: 4px;
    }
</style>
""", unsafe_allow_html=True)

# ─── NAVEGAÇÃO ───────────────────────────────────────────────────────────────
PAGINAS = {
    "🏠 Início":             "home",
    "📂 DATABASE / ERP":     "database_erp",
    "📝 Provisões":          "provisoes",
    "📡 FUP Vendas":         "fup_vendas",
    "📅 FC Diário":          "fc_diario",
    "📉 Recebíveis VP":      "recebiveis_vp",
    "📊 FC Resumo":          "fc_resumo",
    "🧮 Simulação de Venda": "simulacao",
    "📈 Indicadores":        "indicadores",
    "📉 Gráfico":            "grafico",
    "📡 Terminal Financeiro":"terminal_financeiro",
}

with st.sidebar:
    # Logo Tecnotok — salve o arquivo como tkt_app/logo_tecnotok.png
    _logo_path = os.path.join(os.path.dirname(__file__), "logo_tecnotok.png")
    if os.path.exists(_logo_path):
        st.image(_logo_path, width=180)
    else:
        st.markdown("### 🏭 Tecnotok")
    st.markdown("## TKT Cash Flow")

    # Usuário logado + logout
    display = auth.get_display_name()
    if display:
        st.caption(f"👤 {display}")
    if st.button("🚪 Sair", key="btn_logout"):
        auth.logout()

    st.markdown("---")

    if "pagina" not in st.session_state:
        st.session_state.pagina = "home"

    for label, key in PAGINAS.items():
        if st.button(label, key=f"nav_{key}"):
            st.session_state.pagina = key

    st.markdown("---")

    # ─── CONFIGURAÇÕES GLOBAIS DE PERÍODO ────────────────────────────────────
    with st.expander("⚙️ Período de análise", expanded=True):
        from datetime import date, datetime

        ini_salvo, fim_salvo = db.get_cfg_datas()
        try:
            dt_ini_def = datetime.strptime(ini_salvo, "%Y-%m-%d").date()
        except:
            dt_ini_def = date(date.today().year, 1, 1)
        try:
            dt_fim_def = datetime.strptime(fim_salvo, "%Y-%m-%d").date()
        except:
            dt_fim_def = date(date.today().year, 12, 31)

        dt_ini_cfg = st.date_input("De", value=dt_ini_def, key="cfg_ini")
        dt_fim_cfg = st.date_input("Até", value=dt_fim_def, key="cfg_fim")

        st.markdown("**Probabilidades**")
        inc_alta_cfg  = st.checkbox("Incluir ALTA",  value=db.get_cfg("incluir_alta")  == "1", key="cfg_alta")
        inc_media_cfg = st.checkbox("Incluir MEDIA", value=db.get_cfg("incluir_media") == "1", key="cfg_media")

        st.markdown("**ERP — lançamentos em aberto anteriores ao período**")
        corte_status = st.checkbox(
            "Excluir PENDENTES antes da data inicial",
            value=db.get_cfg("erp_corte_status") == "1",
            key="cfg_corte",
            help=(
                "Quando marcado, lançamentos ERP com vencimento anterior à data "
                "inicial e status PENDENTE são ignorados. Isso evita que débitos "
                "não baixados no ERP apareçam em duplicidade com o saldo inicial."
            )
        )

        if st.button("💾 Salvar configurações", key="btn_salvar_cfg"):
            db.set_cfg("dt_ini",           str(dt_ini_cfg))
            db.set_cfg("dt_fim",           str(dt_fim_cfg))
            db.set_cfg("incluir_alta",     "1" if inc_alta_cfg  else "0")
            db.set_cfg("incluir_media",    "1" if inc_media_cfg else "0")
            db.set_cfg("erp_corte_status", "1" if corte_status  else "0")
            st.success("Salvo!")
            st.rerun()

        # Expõe para uso nas páginas via session_state
        st.session_state["cfg_dt_ini"]        = str(dt_ini_cfg)
        st.session_state["cfg_dt_fim"]        = str(dt_fim_cfg)
        st.session_state["cfg_inc_alta"]      = inc_alta_cfg
        st.session_state["cfg_inc_media"]     = inc_media_cfg
        st.session_state["cfg_corte_status"]  = corte_status

    st.markdown("---")
    st.caption("Tecnotok © 2026")

# ─── ROTEAMENTO ─────────────────────────────────────────────────────────────
pagina = st.session_state.get("pagina", "home")

if pagina == "home":
    from pages import home
    home.render()
elif pagina == "database_erp":
    from pages import database_erp
    database_erp.render()
elif pagina == "provisoes":
    from pages import provisoes
    provisoes.render()
elif pagina == "fup_vendas":
    from pages import fup_vendas
    fup_vendas.render()
elif pagina == "fc_diario":
    from pages import fc_diario
    fc_diario.render()
elif pagina == "recebiveis_vp":
    from pages import recebiveis_vp
    recebiveis_vp.render()
elif pagina == "fc_resumo":
    from pages import fc_resumo
    fc_resumo.render()
elif pagina == "simulacao":
    from pages import simulacao
    simulacao.render()
elif pagina == "indicadores":
    from pages import indicadores
    indicadores.render()
elif pagina == "grafico":
    from pages import grafico
    grafico.render()
elif pagina == "terminal_financeiro":
    from pages import terminal_financeiro
    terminal_financeiro.render()
