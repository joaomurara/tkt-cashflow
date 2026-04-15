"""
auth.py — Autenticação do TKT Cash Flow
Controla login/logout com bcrypt + st.session_state
"""

import streamlit as st
import bcrypt
import os


# ─── HELPERS ────────────────────────────────────────────────────────────────

def _get_user(username: str) -> dict | None:
    """Retorna o dict do usuário nos secrets, ou None se não existir."""
    try:
        return st.secrets["auth"]["users"][username]
    except (KeyError, Exception):
        return None


def _check_password(username: str, password: str) -> bool:
    user = _get_user(username)
    if user is None:
        return False
    try:
        stored = user["password_hash"].encode("utf-8")
        return bcrypt.checkpw(password.encode("utf-8"), stored)
    except Exception:
        return False


# ─── API PÚBLICA ─────────────────────────────────────────────────────────────

def is_authenticated() -> bool:
    return st.session_state.get("authenticated", False)


def get_display_name() -> str:
    return st.session_state.get("display_name", "")


def logout():
    for key in ("authenticated", "username", "display_name"):
        st.session_state.pop(key, None)
    st.rerun()


def require_login():
    """
    Chame no topo do app.py antes de qualquer conteúdo.
    Se não autenticado, exibe o formulário de login e para a execução.
    """
    if is_authenticated():
        return  # já logado — continua normalmente

    # ── Tela de login ────────────────────────────────────────────────────────
    st.set_page_config(
        page_title="TKT Cash Flow — Login",
        page_icon="🔐",
        layout="centered",
    )

    # CSS mínimo para centralizar e estilizar
    st.markdown("""
    <style>
        #MainMenu, footer, header {visibility: hidden;}
        .block-container {padding-top: 6rem;}
        .login-box {
            background: #1F4E79;
            border-radius: 12px;
            padding: 2rem 2.5rem 2rem;
            text-align: center;
            color: white;
        }
    </style>
    """, unsafe_allow_html=True)

    _logo_login = os.path.join(os.path.dirname(__file__), "logo_tecnotok.png")
    col_l, col_c, col_r = st.columns([1, 2, 1])
    with col_c:
        if os.path.exists(_logo_login):
            st.image(_logo_login, use_container_width=True)
        else:
            st.markdown(
                '<div class="login-box">'
                '<h2 style="color:white;margin-bottom:0">🏭 Tecnotok</h2>'
                '<h3 style="color:#a8c8e8;margin-top:4px;margin-bottom:1.5rem">TKT Cash Flow</h3>'
                '</div>',
                unsafe_allow_html=True,
            )

    st.markdown("<br>", unsafe_allow_html=True)

    with st.form("login_form", clear_on_submit=False):
        username = st.text_input("👤 Usuário", placeholder="seu usuário")
        password = st.text_input("🔑 Senha", type="password", placeholder="sua senha")
        submitted = st.form_submit_button("Entrar", use_container_width=True, type="primary")

    if submitted:
        username = username.strip().lower()
        if _check_password(username, password):
            user = _get_user(username)
            st.session_state["authenticated"] = True
            st.session_state["username"] = username
            st.session_state["display_name"] = user.get("name", username)
            st.rerun()
        else:
            st.error("Usuário ou senha incorretos. Tente novamente.")

    st.stop()  # impede que o resto do app seja renderizado
