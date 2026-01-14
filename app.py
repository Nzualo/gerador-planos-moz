import streamlit as st

# -----------------------------
# Config
# -----------------------------
st.set_page_config(
    page_title="SDEJT - Planos SNE",
    page_icon="🇲🇿",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# Mensagem para confirmar que ESTA versão está rodando
st.toast("✅ app.py NOVO carregado", icon="✅")

# -----------------------------
# Checar Secrets essenciais
# -----------------------------
required = ["SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY", "PIN_PEPPER", "ADMIN_PASSWORD"]
missing = [k for k in required if k not in st.secrets]
if missing:
    st.error(f"Faltam Secrets: {', '.join(missing)}")
    st.stop()

# GOOGLE_API_KEY só precisa quando gerar plano (não travar o arranque)
if "GOOGLE_API_KEY" not in st.secrets:
    st.warning("GOOGLE_API_KEY não encontrada (só vai afectar a geração de planos).")

# -----------------------------
# Importar módulos (com fallback)
# -----------------------------
AUTH_OK = False
PLANS_OK = False
ADMIN_OK = False

auth_gate = None
plans_ui = None
admin_panel = None

# auth
try:
    from auth import auth_gate  # novo padrão
    AUTH_OK = True
except Exception:
    # fallback: se o teu código antigo tiver outro nome, tenta buscar
    try:
        from auth import access_gate as auth_gate  # antigo
        AUTH_OK = True
    except Exception:
        AUTH_OK = False

# plans
try:
    from plans import plans_ui
    PLANS_OK = True
except Exception:
    # fallback para teu código antigo que provavelmente não tinha plans.py
    plans_ui = None
    PLANS_OK = False

# admin
try:
    from admin import admin_panel
    ADMIN_OK = True
except Exception:
    admin_panel = None
    ADMIN_OK = False


# -----------------------------
# UI básica
# -----------------------------
st.title("MZ SDEJT - Elaboração de Planos")
st.caption("Serviço Distrital de Educação, Juventude e Tecnologia - Inhassoro")
st.divider()

# -----------------------------
# LOGIN (auth_gate)
# -----------------------------
if not AUTH_OK or auth_gate is None:
    st.error("❌ Não encontrei o módulo de login (auth.py) ou a função auth_gate().")
    st.info("Confirme se existe um ficheiro auth.py na raiz e se tem a função: def auth_gate():")
    st.stop()

# desenha login (ou valida sessão)
auth_gate()

user = st.session_state.get("user")
if not user:
    # se ainda não logou, auth_gate normalmente mostra a tela de login e para.
    st.stop()

# -----------------------------
# Sidebar (só sair)
# -----------------------------
with st.sidebar:
    st.success("Sessão activa")
    st.write(f"👤 {user.get('name','-')}")
    st.write(f"🏫 {user.get('school','-')}")
    st.write(f"📌 Estado: {user.get('status','trial')}")

    if st.button("🚪 Sair", use_container_width=True):
        st.session_state.pop("logged_in", None)
        st.session_state.pop("user", None)
        st.session_state.pop("is_admin", None)
        st.rerun()

# -----------------------------
# Abas
# -----------------------------
tab_planos, tab_admin = st.tabs(["📘 Planos", "🛠️ Admin"])

# -----------------------------
# Aba Planos
# -----------------------------
with tab_planos:
    st.subheader("📘 Planos")

    if PLANS_OK and plans_ui is not None:
        plans_ui(user)
    else:
        st.warning("O módulo plans.py não foi encontrado. Vou mostrar um fallback.")
        st.info("Se você ainda está com o código antigo (tudo num app.py), mantenha a parte de 'planos' aí e eu adapto depois.")
        st.write("✅ Login OK. Agora precisamos integrar a UI de planos nesta versão (plans.py).")


# -----------------------------
# Aba Admin (dentro da aba)
# -----------------------------
with tab_admin:
    st.subheader("🛠️ Administração (dentro da aba)")
    st.caption("O painel só aparece depois de entrar com a senha de Admin.")

    # mostrar estado para debug (ajuda a ver se entrou)
    st.write("is_admin =", st.session_state.get("is_admin", False))

    if st.session_state.get("is_admin"):
        st.success("Sessão de administrador activa.")

        if st.button("Sair do Admin", use_container_width=True):
            st.session_state["is_admin"] = False
            st.rerun()

        if ADMIN_OK and admin_panel is not None:
            admin_panel(admin_name=user.get("name", "Admin"))
        else:
            st.error("❌ Não encontrei admin.py / admin_panel().")
            st.info("Crie admin.py na raiz com: def admin_panel(admin_name: str): ...")

    else:
        admin_pwd = st.text_input("Senha do Administrador", type="password", key="admin_pwd_tab")

        if st.button("Entrar como Admin", type="primary", use_container_width=True, key="admin_login_btn"):
            if admin_pwd == st.secrets["ADMIN_PASSWORD"]:
                st.session_state["is_admin"] = True
                st.success("Entrou como Admin.")
                st.rerun()
            else:
                st.error("Senha inválida.")
