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
required = ["SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY", "PIN_PEPPER", "ADMIN_PASSWORD"]
missing = [k for k in required if k not in st.secrets]
if missing:
    st.error(f"Faltam Secrets: {', '.join(missing)}")
    st.stop()

# 1) Autenticação (se não estiver logado, o auth_gate para a app)
auth_gate()

# 2) User da sessão
user = st.session_state.get("user")
if not user:
    st.error("Sessão inválida. Faça login novamente.")
    st.stop()

# Header simples
st.markdown("## MZ SDEJT - Elaboração de Planos")
st.caption(f"Professor: {user.get('name','-')} | Escola: {user.get('school','-')} | Estado: {user.get('status','trial')}")
st.divider()

# 3) Admin (se tiver sessão admin ativa no sidebar, mostra painel)
#    Você já tem a lógica de admin password no seu fluxo; se quiser manter, podemos integrar depois.
if st.session_state.get("is_admin"):
    admin_panel(admin_name=user.get("name", "Admin"))
    st.divider()

# 4) Área de planos (Professor)
plans_ui(user)
