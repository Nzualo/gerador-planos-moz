import streamlit as st

from auth import auth_gate
from admin import admin_panel
from plans import plans_ui


st.set_page_config(
    page_title="SDEJT - Planos SNE",
    page_icon="🇲🇿",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.write("")  # garante render inicial

# Secrets essenciais
required = ["SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY", "PIN_PEPPER", "ADMIN_PASSWORD", "GOOGLE_API_KEY"]
missing = [k for k in required if k not in st.secrets]
if missing:
    st.error(f"Faltam Secrets: {', '.join(missing)}")
    st.stop()

# Login (registo/entrar)
auth_gate()

user = st.session_state.get("user")
if not user:
    st.error("Sessão inválida. Faça login novamente.")
    st.stop()

# Header
st.title("MZ SDEJT - Elaboração de Planos")
st.caption(
    f"Professor: {user.get('name','-')} | "
    f"Escola: {user.get('school','-')} | "
    f"Estado: {user.get('status','trial')}"
)
st.divider()

# Sidebar pequena só com sair
with st.sidebar:
    if st.button("🚪 Sair", use_container_width=True):
        st.session_state.pop("logged_in", None)
        st.session_state.pop("user", None)
        st.session_state.pop("is_admin", None)
        st.rerun()

# Abas
tab_planos, tab_admin = st.tabs(["📘 Planos", "🛠️ Admin"])

with tab_planos:
    plans_ui(user)

with tab_admin:
    st.subheader("🛠️ Administração")

    if st.session_state.get("is_admin"):
        st.success("Sessão de administrador activa.")
        col1, col2 = st.columns([1, 1])
        with col1:
            if st.button("Sair do Admin", use_container_width=True):
                st.session_state["is_admin"] = False
                st.rerun()
        with col2:
            st.info("Use o painel abaixo para gerir utilizadores e ver planos.")

        admin_panel(admin_name=user.get("name", "Admin"))

    else:
        st.info("Introduza a senha do Administrador para aceder ao painel.")
        admin_pwd = st.text_input("Senha do Administrador", type="password", key="admin_pwd_tab")

        if st.button("Entrar como Admin", type="primary", use_container_width=True, key="admin_login_btn"):
            if admin_pwd == st.secrets["ADMIN_PASSWORD"]:
                st.session_state["is_admin"] = True
                st.success("Entrou como Admin.")
                st.rerun()
            else:
                st.error("Senha inválida.")
