import streamlit as st

from auth import auth_gate
from admin import admin_panel
from plans import plans_ui

# UI base
st.set_page_config(page_title="SDEJT - Planos SNE", page_icon="🇲🇿", layout="wide")

st.markdown(
    """
<style>
    .stApp { background-color: #0E1117; color: #FAFAFA; }
    [data-testid="stSidebar"] { background-color: #262730; }
    .stTextInput > div > div > input, .stSelectbox > div > div > div, .stTextArea textarea { color: #ffffff; }
    h1, h2, h3 { color: #FF4B4B !important; }
</style>
""",
    unsafe_allow_html=True,
)

# Secrets essenciais
required = ["SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY", "PIN_PEPPER", "ADMIN_PASSWORD", "GOOGLE_API_KEY"]
missing = [k for k in required if k not in st.secrets]
if missing:
    st.error(f"Faltam Secrets: {', '.join(missing)}")
    st.stop()

# Login (se não estiver logado, pára aqui)
auth_gate()

user = st.session_state.get("user")
if not user:
    st.error("Sessão inválida. Faça login novamente.")
    st.stop()

# Header
st.markdown("## 🇲🇿 SDEJT - Elaboração de Planos")
st.caption(
    f"Professor: {user.get('name','-')} | "
    f"Escola: {user.get('school','-')} | "
    f"Estado: {user.get('status','trial')}"
)
st.divider()

# Sair
with st.sidebar:
    if st.button("🚪 Sair"):
        st.session_state.pop("logged_in", None)
        st.session_state.pop("user", None)
        st.session_state.pop("is_admin", None)
        st.rerun()

# Abas principais
tab_planos, tab_admin = st.tabs(["📘 Planos", "🛠️ Admin"])

with tab_planos:
    plans_ui(user)

with tab_admin:
    st.subheader("🛠️ Administração")

    if st.session_state.get("is_admin"):
        c1, c2 = st.columns([1, 1])
        with c1:
            st.success("Sessão de administrador activa.")
        with c2:
            if st.button("Sair do Admin"):
                st.session_state["is_admin"] = False
                st.rerun()

        admin_panel(admin_name=user.get("name", "Admin"))

    else:
        st.info("Introduza a senha do Administrador para aceder ao painel.")
        admin_pwd = st.text_input("Senha do Administrador", type="password")
        if st.button("Entrar como Admin", type="primary"):
            if admin_pwd == st.secrets["ADMIN_PASSWORD"]:
                st.session_state["is_admin"] = True
                st.success("Entrou como Admin.")
                st.rerun()
            else:
                st.error("Senha inválida.")
