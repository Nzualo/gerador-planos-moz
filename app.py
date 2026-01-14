import streamlit as st

from auth import auth_gate
from admin import admin_panel
from plans import plans_ui


st.set_page_config(page_title="SDEJT - Planos SNE", page_icon="🇲🇿", layout="wide")

# Sempre mostrar algo logo no início (evita “tela vazia”)
st.write("Carregando...")

# Verificar secrets SEM matar visibilidade (sem CSS)
required = ["SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY", "PIN_PEPPER", "ADMIN_PASSWORD", "GOOGLE_API_KEY"]
missing = [k for k in required if k not in st.secrets]
if missing:
    st.error(f"Faltam Secrets: {', '.join(missing)}")
    st.stop()

# Login
auth_gate()

user = st.session_state.get("user")
if not user:
    st.error("Sessão inválida. Faça login novamente.")
    st.stop()

st.title("MZ SDEJT - Elaboração de Planos")
st.caption(f"Professor: {user.get('name','-')} | Escola: {user.get('school','-')} | Estado: {user.get('status','trial')}")
st.divider()

with st.sidebar:
    if st.button("🚪 Sair"):
        st.session_state.pop("logged_in", None)
        st.session_state.pop("user", None)
        st.session_state.pop("is_admin", None)
        st.rerun()

tab_planos, tab_admin = st.tabs(["📘 Planos", "🛠️ Admin"])

with tab_planos:
    plans_ui(user)

with tab_admin:
    st.subheader("🛠️ Administração")

    if st.session_state.get("is_admin"):
        if st.button("Sair do Admin"):
            st.session_state["is_admin"] = False
            st.rerun()
        admin_panel(admin_name=user.get("name", "Admin"))

    else:
        st.info("Introduza a senha do Administrador.")
        admin_pwd = st.text_input("Senha do Administrador", type="password")
        if st.button("Entrar como Admin", type="primary"):
            if admin_pwd == st.secrets["ADMIN_PASSWORD"]:
                st.session_state["is_admin"] = True
                st.success("Entrou como Admin.")
                st.rerun()
            else:
                st.error("Senha inválida.")
