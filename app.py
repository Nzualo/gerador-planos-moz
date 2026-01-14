# app.py
# =========================================================
# SDEJT - Planos SNE (Inhassoro) | Streamlit + Supabase
# Versão organizada por módulos:
# - auth.py   (login nome+PIN + escolas)
# - admin.py  (dashboard admin + reset PIN + ver planos de todos)
# - plans.py  (gerar plano + histórico + pdf + storage + currículo)
# - utils.py  (helpers, supabase, hashing)
# =========================================================

import streamlit as st

from auth import auth_gate
from admin import admin_panel
from plans import ui_user_history, ui_generate_plan
from utils import supa


# -------------------------
# UI base
# -------------------------
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


# -------------------------
# Secrets obrigatórios
# -------------------------
required = [
    "SUPABASE_URL",
    "SUPABASE_SERVICE_ROLE_KEY",
    "GOOGLE_API_KEY",
    "ADMIN_PASSWORD",
    "PIN_PEPPER",
]
missing = [k for k in required if k not in st.secrets]
if missing:
    st.error(f"Faltam Secrets: {', '.join(missing)}")
    st.stop()


# -------------------------
# Sidebar: Admin Login + Logout
# -------------------------
with st.sidebar:
    st.markdown("### Administração")
    admin_pwd = st.text_input("Senha do Administrador", type="password", key="admin_pwd")

    if st.button("Entrar como Admin"):
        if admin_pwd == st.secrets["ADMIN_PASSWORD"]:
            st.session_state["is_admin"] = True
            st.success("Sessão de Administrador activa.")
            st.rerun()
        else:
            st.error("Senha inválida.")

    if st.session_state.get("is_admin"):
        if st.button("Sair do Admin"):
            st.session_state["is_admin"] = False
            st.session_state.pop("admin_pwd", None)
            st.rerun()

    st.markdown("---")
    if st.session_state.get("logged_in"):
        if st.button("🚪 Terminar sessão (Logout)"):
            st.session_state.pop("logged_in", None)
            st.session_state.pop("user", None)
            st.session_state.pop("plano_pronto", None)
            st.session_state.pop("ctx", None)
            st.session_state.pop("plano_base", None)
            st.session_state.pop("plano_editado", None)
            st.session_state.pop("editor_df", None)
            st.session_state.pop("preview_imgs", None)
            st.success("Sessão terminada.")
            st.rerun()

    st.markdown("---")
    st.markdown("### Ajuda / Suporte")
    admin_whatsapp = "258867926665"
    msg = "Saudações. Preciso de apoio no sistema de planos (SDEJT)."
    link_zap = f"https://wa.me/{admin_whatsapp}?text={msg.replace(' ', '%20')}"
    st.markdown(
        f"""
<a href="{link_zap}" target="_blank" style="text-decoration:none;">
  <button style="background-color:#25D366;color:white;border:none;padding:12px 16px;border-radius:8px;width:100%;cursor:pointer;font-size:15px;font-weight:bold;">
    📱 Falar com o Administrador no WhatsApp
  </button>
</a>
""",
        unsafe_allow_html=True,
    )


# -------------------------
# Gate: login
# -------------------------
auth_gate()

if not st.session_state.get("logged_in"):
    st.stop()

user = st.session_state.get("user")
if not user:
    st.error("Sessão inválida. Faça login novamente.")
    st.session_state.pop("logged_in", None)
    st.rerun()


# -------------------------
# Carregar user atualizado (status etc.)
# -------------------------
try:
    sb = supa()
    r = sb.table("app_users").select("*").eq("user_key", user["user_key"]).limit(1).execute()
    if r.data:
        user = r.data[0]
        st.session_state["user"] = user
except Exception:
    pass


# -------------------------
# Header principal
# -------------------------
st.markdown("## 🇲🇿 SDEJT - Elaboração de Planos")
st.markdown("##### Serviço Distrital de Educação, Juventude e Tecnologia - Inhassoro")
st.caption(f"Professor: **{user.get('name','-')}**  |  Escola: **{user.get('school','-')}**  |  Estado: **{user.get('status','trial')}**")
st.divider()


# -------------------------
# Admin Panel (se admin)
# -------------------------
if st.session_state.get("is_admin"):
    admin_panel(admin_name=user.get("name", "Admin"))
    st.divider()


# -------------------------
# Professor: histórico + gerar plano
# -------------------------
ui_user_history(user["user_key"])
ui_generate_plan(user)
