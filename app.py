import streamlit as st

from auth import auth_gate
from admin import admin_panel
from plans import plans_ui
from utils import get_user_by_key


st.set_page_config(
    page_title="SDEJT - Planos SNE",
    page_icon="🇲🇿",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ----------------
# Verificar Secrets
# ----------------
required = ["SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY", "PIN_PEPPER", "ADMIN_PASSWORD"]
missing = [k for k in required if k not in st.secrets]
if missing:
    st.error(f"Faltam Secrets: {', '.join(missing)}")
    st.stop()

# ----------------
# Login (PIN)
# ----------------
auth_gate()

user = st.session_state.get("user")
if not user:
    st.error("Sessão inválida. Faça login novamente.")
    st.stop()

# 🔄 Refresh do utilizador no DB (resolve: aprovado mas aparece trial)
fresh = get_user_by_key(user["user_key"])
if fresh:
    st.session_state["user"] = fresh
    user = fresh

# ----------------
# Header
# ----------------
st.title("MZ SDEJT - Elaboração de Planos")
st.caption(
    f"Professor: {user.get('name','-')} | "
    f"Escola: {user.get('school','-')} | "
    f"Estado: {user.get('status','trial')}"
)
st.divider()

# ----------------
# Sidebar (Sair / Atualizar)
# ----------------
with st.sidebar:
    if st.button("🔄 Atualizar estado", use_container_width=True):
        fresh2 = get_user_by_key(st.session_state["user"]["user_key"])
        if fresh2:
            st.session_state["user"] = fresh2
        st.rerun()

    if st.button("🚪 Sair", use_container_width=True):
        st.session_state.pop("logged_in", None)
        st.session_state.pop("user", None)
        st.session_state.pop("is_admin", None)
        st.rerun()

# ----------------
# UI principal
# ----------------
status = (user.get("status") or "trial").lower()
is_admin = (status == "admin") or bool(st.session_state.get("is_admin"))

if not is_admin:
    plans_ui(user)
else:
    tab_planos, tab_admin = st.tabs(["📘 Planos", "🛠️ Admin"])

    with tab_planos:
        plans_ui(user)

    with tab_admin:
        st.subheader("🛠️ Administração")

        # Login Admin (senha)
        if not st.session_state.get("is_admin"):
            st.info("Introduza a senha do Administrador para aceder ao painel.")
            admin_pwd = st.text_input("Senha do Administrador", type="password", key="admin_pwd_tab")

            if st.button("Entrar como Admin", type="primary", use_container_width=True):
                if admin_pwd == st.secrets["ADMIN_PASSWORD"]:
                    st.session_state["is_admin"] = True
                    st.success("Entrou como Admin.")
                    st.rerun()
                else:
                    st.error("Senha inválida.")
        else:
            st.success("Sessão de administrador activa.")
            if st.button("Sair do Admin", use_container_width=True):
                st.session_state["is_admin"] = False
                st.rerun()

            admin_panel(admin_name=user.get("name", "Admin"))
