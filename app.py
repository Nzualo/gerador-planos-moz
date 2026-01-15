# app.py
# =========================================================
# MZ SDEJT - Planos SNE (Inhassoro)
# Login simples com PIN:
#  - 1º acesso: Nome + Escola + PIN
#  - Próximos: Nome + PIN
# Admin separado na sidebar (senha própria)
# Supabase: tabelas app_users, user_plans
# =========================================================

import re
import json
import base64
import hashlib
from datetime import datetime, date

import streamlit as st
import pandas as pd
import requests

from supabase import create_client


# =========================
# CONFIG UI
# =========================
st.set_page_config(page_title="MZ SDEJT - Planos", page_icon="🇲🇿", layout="wide")
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

# =========================
# SECRETS
# =========================
REQ_SECRETS = ["SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY", "ADMIN_PASSWORD", "PIN_PEPPER"]
missing = [k for k in REQ_SECRETS if k not in st.secrets]
if missing:
    st.error(f"Faltam Secrets: {', '.join(missing)}")
    st.stop()


# =========================
# SUPABASE
# =========================
@st.cache_resource
def supa():
    return create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_SERVICE_ROLE_KEY"])


# =========================
# ESCOLAS (LISTA OFICIAL)
# =========================
SCHOOLS_RAW = [
    "EP de Petane 1",
    "ES Santo Eusebio",
    "EB de Mananisse",
    "EP de Chibo",
    "EP de Inhassoro",
    "ES de Inhassoro",
    "EP de Fequete",
    "EB de 20 de Junho de Petane 2",
    "EP de Macurrumbe",
    "EP de Gatsala",
    "ES Filipe J. Nyusi",
    "EP de Chibamo",
    "EP Armando E. Guebuza",
    "EP de Vulanjane",
    "EP de Macovane",
    "EB de Vuca",
    "EP de Chitsotso",
    "ES 04 de Outubro",
    "EP de Mangungumete",
    "EP de Jose",
    "EP de Joaquim Mara",
    "EB de Chitsecane",
    "EP Zava",
    "EP de Nguenguemane",
    "EP de Matsanze",
    "EP de Buxane",
    "EP de Ngonhamo",
    "EB de Cometela",
    "EP de Mulepa",
    "EP de Chiquiriva",
    "EP de Manusse",
    "EP de Timane",
    "EP de Tiane",
    "EP de Mahungane",
    "EP de Macheco",
    "EP de Catine",
    "EP de Nhapele",
    "EP de Cachane",
    "EP de Chipongo",
    "EP de Nhamanheca",
    "EP de Mapandzene",
    "EB de Maimelane",
    "ES 07 de Abril de Maimelane",
    "EP de Mabime",
    "EP de Rumbatsatsa",
    "EP de Chihamele",
    "EP de Madacare",
    "EP de Mahoche",
    "EP de Nhamanhate",
    "EP de Mangarelane",
    "EP de Sangazive",
    "EB de bazaruto",
    "EB de Zenguelemo",
    "EP de Pangara",
    "EP de Chitchuete",
    'Instituto Industrial e Comercial "Estrela do Mar" de Inhassoro',
    "Serviço Distrital de Educação, Juventude e Tecnologia de Inhassoro",
]

# =========================
# NORMALIZAÇÃO (aceitar EP/Escola Primária etc.)
# =========================
def normalize_text(s: str) -> str:
    s = (s or "").strip().lower()

    # remover acentos simples
    rep = {
        "á":"a","à":"a","â":"a","ã":"a",
        "é":"e","ê":"e",
        "í":"i",
        "ó":"o","ô":"o","õ":"o",
        "ú":"u",
        "ç":"c",
    }
    for k,v in rep.items():
        s = s.replace(k,v)

    # padronizar aspas
    s = s.replace('"', "").replace("'", "")

    # substituir múltiplos espaços
    s = " ".join(s.split())
    return s


def expand_abbrev(s: str) -> str:
    """
    Permite:
      EP -> escola primaria
      EB -> escola basica
      ES -> escola secundaria
      II -> instituto (industrial/comercial)
      SDEJT -> servico distrital...
    """
    t = normalize_text(s)

    # substituições comuns
    t = re.sub(r"\bep\b", "escola primaria", t)
    t = re.sub(r"\beb\b", "escola basica", t)
    t = re.sub(r"\bes\b", "escola secundaria", t)
    t = re.sub(r"\bii\b", "instituto", t)
    t = re.sub(r"\bsdejt\b", "servico distrital de educacao juventude e tecnologia", t)

    # também aceitar versões por extenso que o usuário digita
    t = t.replace("servico distrital", "servico distrital")
    return t


def school_key(s: str) -> str:
    """Chave comparável de escola."""
    return expand_abbrev(s)


SCHOOLS_KEYS = {school_key(x): x for x in SCHOOLS_RAW}  # key normalizada -> nome oficial


def validate_school(user_input: str) -> tuple[bool, str]:
    k = school_key(user_input)
    if k in SCHOOLS_KEYS:
        return True, SCHOOLS_KEYS[k]
    return False, ""


# =========================
# PIN HASH
# =========================
def pin_hash(pin: str) -> str:
    pepper = st.secrets["PIN_PEPPER"]
    raw = (pepper + "|" + (pin or "").strip()).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


# =========================
# USER KEY (por nome)
# =========================
def make_user_key(name: str) -> str:
    return hashlib.sha256(normalize_text(name).encode("utf-8")).hexdigest()


# =========================
# DB HELPERS
# =========================
def get_user_by_key(user_key: str):
    sb = supa()
    r = sb.table("app_users").select("*").eq("user_key", user_key).limit(1).execute()
    return r.data[0] if r.data else None


def create_user(user_key: str, name: str, school_official: str, pin_h: str):
    sb = supa()
    sb.table("app_users").insert(
        {
            "user_key": user_key,
            "name": name.strip(),
            "school": school_official.strip(),
            "pin_hash": pin_h,
            "status": "trial",
            "created_at": datetime.now().isoformat(),
        }
    ).execute()


def verify_login(name: str, pin: str):
    user_key = make_user_key(name)
    u = get_user_by_key(user_key)
    if not u:
        return None, "Utilizador não registado. Faça cadastro (primeiro acesso)."

    if u.get("pin_hash") != pin_hash(pin):
        return None, "PIN inválido."

    return u, ""


def set_user_status(user_key: str, status: str):
    sb = supa()
    sb.table("app_users").update({"status": status}).eq("user_key", user_key).execute()


def list_users_df() -> pd.DataFrame:
    sb = supa()
    r = sb.table("app_users").select("user_key,name,school,status,created_at").order("created_at", desc=True).execute()
    return pd.DataFrame(r.data or [])


# =========================
# PLANS (HISTÓRICO)
# =========================
def list_plans_user(user_key: str) -> pd.DataFrame:
    sb = supa()
    r = (
        sb.table("user_plans")
        .select("id,created_at,disciplina,classe,tema,pdf_b64,user_key")
        .eq("user_key", user_key)
        .order("created_at", desc=True)
        .execute()
    )
    df = pd.DataFrame(r.data or [])
    if df.empty:
        return df
    df["created_at"] = pd.to_datetime(df["created_at"], errors="coerce")
    return df


def list_plans_all() -> pd.DataFrame:
    sb = supa()
    r = (
        sb.table("user_plans")
        .select("id,created_at,disciplina,classe,tema,pdf_b64,user_key")
        .order("created_at", desc=True)
        .execute()
    )
    df = pd.DataFrame(r.data or [])
    if df.empty:
        return df
    df["created_at"] = pd.to_datetime(df["created_at"], errors="coerce")
    return df


def save_plan(user_key: str, disciplina: str, classe: str, tema: str, pdf_bytes: bytes):
    sb = supa()
    sb.table("user_plans").insert(
        {
            "user_key": user_key,
            "disciplina": disciplina,
            "classe": classe,
            "tema": tema,
            "pdf_b64": base64.b64encode(pdf_bytes).decode("utf-8"),
            "created_at": datetime.now().isoformat(),
        }
    ).execute()


def pdf_from_b64(b64: str) -> bytes | None:
    try:
        return base64.b64decode(b64)
    except Exception:
        return None


# =========================
# PDF SIMPLES (placeholder)
# =========================
def simple_pdf_bytes(title: str, lines: list[str]) -> bytes:
    # PDF mínimo sem libs extras (base64 de um PDF simples gerado por string)
    # (Para produção, você mantém o teu FPDF. Aqui é só pra garantir o app funcional.)
    content = "\n".join(lines).replace("(", "\\(").replace(")", "\\)")
    pdf = f"""%PDF-1.4
1 0 obj<<>>endobj
2 0 obj<< /Length 3 0 R >>stream
BT
/F1 16 Tf
50 780 Td
({title}) Tj
/F1 11 Tf
50 760 Td
({content}) Tj
ET
endstream
endobj
3 0 obj {len(content)+100} endobj
4 0 obj<< /Type /Catalog /Pages 5 0 R >>endobj
5 0 obj<< /Type /Pages /Kids [6 0 R] /Count 1 >>endobj
6 0 obj<< /Type /Page /Parent 5 0 R /MediaBox [0 0 595 842] /Contents 2 0 R
/Resources<< /Font<< /F1 7 0 R >> >> >>endobj
7 0 obj<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>endobj
xref
0 8
0000000000 65535 f
trailer<< /Root 4 0 R /Size 8 >>
startxref
0
%%EOF
"""
    return pdf.encode("latin-1", "ignore")


# =========================
# SESSION HELPERS
# =========================
def logout():
    for k in ["logged_in", "user_key", "user_name", "user_school", "user_status", "is_admin"]:
        st.session_state.pop(k, None)
    st.rerun()


def refresh_user_state():
    if not st.session_state.get("logged_in"):
        return
    if st.session_state.get("is_admin"):
        st.session_state["user_status"] = "admin"
        return
    u = get_user_by_key(st.session_state["user_key"])
    if u:
        st.session_state["user_name"] = u.get("name", "")
        st.session_state["user_school"] = u.get("school", "")
        st.session_state["user_status"] = (u.get("status") or "trial")


# =========================
# SIDEBAR: ADMIN LOGIN (SEPARADO)
# =========================
with st.sidebar:
    st.markdown("## 🛠️ Administrador")
    admin_pwd = st.text_input("Senha do Administrador", type="password", key="admin_pwd")

    if st.button("Entrar como Admin"):
        if admin_pwd == st.secrets["ADMIN_PASSWORD"]:
            st.session_state["is_admin"] = True
            st.session_state["logged_in"] = True
            st.session_state["user_key"] = "__admin__"
            st.session_state["user_name"] = "Administrador"
            st.session_state["user_school"] = "SDEJT"
            st.session_state["user_status"] = "admin"
            st.success("Admin activo.")
            st.rerun()
        else:
            st.error("Senha inválida.")

    if st.session_state.get("is_admin"):
        st.success("✅ Sessão Admin activa")
        if st.button("Sair (Admin)"):
            logout()

    st.markdown("---")
    st.markdown("## 📱 Ajuda / Suporte")
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


# =========================
# HEADER
# =========================
st.markdown("# 🇲🇿 MZ SDEJT - Elaboração de Planos")
st.caption("Serviço Distrital de Educação, Juventude e Tecnologia - Inhassoro")
st.divider()


# =========================
# LOGIN PROFESSOR (NÃO ADMIN)
# =========================
if not st.session_state.get("logged_in"):
    st.subheader("👤 Professor - Entrar")

    tab1, tab2 = st.tabs(["🔐 Entrar", "📝 Primeiro acesso (Cadastro)"])

    with tab1:
        name = st.text_input("Nome do Professor", key="login_name")
        pin = st.text_input("PIN", type="password", key="login_pin")

        if st.button("Entrar", type="primary"):
            u, err = verify_login(name, pin)
            if err:
                st.error(err)
            else:
                st.session_state["logged_in"] = True
                st.session_state["is_admin"] = False
                st.session_state["user_key"] = u["user_key"]
                st.session_state["user_name"] = u.get("name", "")
                st.session_state["user_school"] = u.get("school", "")
                st.session_state["user_status"] = u.get("status", "trial")
                st.rerun()

    with tab2:
        name_c = st.text_input("Nome do Professor", key="cad_name")
        school_c = st.text_input("Escola (ex.: EP de Inhassoro / Escola Primária de Inhassoro)", key="cad_school")
        pin1 = st.text_input("Criar PIN", type="password", key="cad_pin1")
        pin2 = st.text_input("Confirmar PIN", type="password", key="cad_pin2")

        if st.button("Registar e Entrar", type="primary"):
            if not name_c.strip():
                st.error("Escreva o nome.")
            elif not school_c.strip():
                st.error("Escreva a escola.")
            elif not pin1.strip() or len(pin1.strip()) < 4:
                st.error("PIN muito curto (mínimo 4).")
            elif pin1 != pin2:
                st.error("PINs não coincidem.")
            else:
                ok, official = validate_school(school_c)
                if not ok:
                    st.error("Escola não registada no sistema. Verifique o nome (ou contacte o SDEJT).")
                else:
                    user_key = make_user_key(name_c)
                    existing = get_user_by_key(user_key)
                    if existing:
                        st.error("Este nome já está registado. Use a aba 'Entrar'.")
                    else:
                        create_user(user_key, name_c, official, pin_hash(pin1))
                        st.success("Registado com sucesso. A entrar...")
                        st.session_state["logged_in"] = True
                        st.session_state["is_admin"] = False
                        st.session_state["user_key"] = user_key
                        st.session_state["user_name"] = name_c.strip()
                        st.session_state["user_school"] = official
                        st.session_state["user_status"] = "trial"
                        st.rerun()

    st.stop()


# =========================
# LOGGED IN AREA
# =========================
refresh_user_state()

is_admin = bool(st.session_state.get("is_admin"))
user_key = st.session_state.get("user_key")
user_name = st.session_state.get("user_name")
user_school = st.session_state.get("user_school")
user_status = st.session_state.get("user_status", "trial")

top_left, top_right = st.columns([0.75, 0.25])
with top_left:
    st.write(f"**Professor:** {user_name}  |  **Escola:** {user_school}  |  **Estado:** {user_status}")
with top_right:
    if st.button("Sair"):
        logout()


# =========================
# TABS PRINCIPAIS
# =========================
if is_admin:
    tabs = st.tabs(["📚 Histórico (Admin - todos)", "🛠️ Painel do Administrador", "🧑‍🏫 Área do Professor"])
else:
    tabs = st.tabs(["📚 Meus Planos (Histórico)", "🧑‍🏫 Gerar Plano"])


# =========================
# PROFESSOR: HISTÓRICO
# =========================
def render_user_history():
    st.subheader("📚 Meus Planos (Histórico)")
    df = list_plans_user(user_key)
    if df.empty:
        st.info("Ainda não há planos guardados no seu histórico.")
        return

    df2 = df.copy()
    df2["label"] = df2["created_at"].astype(str) + " | " + df2["disciplina"].astype(str) + " | " + df2["classe"].astype(str) + " | " + df2["tema"].astype(str)
    st.dataframe(df2[["created_at", "disciplina", "classe", "tema"]], hide_index=True, use_container_width=True)

    sel = st.selectbox("Seleccionar plano para baixar", df2["label"].tolist())
    row = df2[df2["label"] == sel].iloc[0]
    pdf_bytes = pdf_from_b64(row["pdf_b64"])
    if pdf_bytes:
        st.download_button(
            "⬇️ Baixar PDF",
            data=pdf_bytes,
            file_name=f"Plano_{row['disciplina']}_{row['classe']}_{row['tema']}.pdf".replace(" ", "_"),
            mime="application/pdf",
            type="primary",
        )


# =========================
# PROFESSOR: GERAR (placeholder)
# =========================
def render_generate():
    st.subheader("🧑‍🏫 Gerar Plano (ligar aqui ao teu gerador IA)")
    disciplina = st.text_input("Disciplina", "Língua Portuguesa")
    classe = st.selectbox("Classe", ["1ª","2ª","3ª","4ª","5ª","6ª","7ª","8ª","9ª","10ª","11ª","12ª"])
    tema = st.text_input("Tema", "")

    if st.button("🚀 Gerar e Guardar", type="primary", disabled=(not tema.strip())):
        # Aqui você liga no teu Gemini/FPDF e gera o PDF real.
        # Por agora: PDF simples só para testar o fluxo completo.
        title = "PLANO DE AULA"
        lines = [
            f"Professor: {user_name}",
            f"Escola: {user_school}",
            f"Data: {date.today().strftime('%d/%m/%Y')}",
            f"Disciplina: {disciplina}",
            f"Classe: {classe}",
            f"Tema: {tema}",
        ]
        pdf_bytes = simple_pdf_bytes(title, lines)
        save_plan(user_key, disciplina, classe, tema, pdf_bytes)
        st.success("Plano guardado no histórico.")
        st.download_button(
            "⬇️ Baixar PDF agora",
            data=pdf_bytes,
            file_name=f"Plano_{disciplina}_{classe}_{tema}.pdf".replace(" ", "_"),
            mime="application/pdf",
            type="primary",
        )
        st.rerun()


# =========================
# ADMIN: HISTÓRICO TODOS
# =========================
def render_admin_history():
    st.subheader("📚 Histórico (Admin) — Todos os Planos")
    df = list_plans_all()
    if df.empty:
        st.info("Ainda não há planos no sistema.")
        return

    users = list_users_df()
    users_map = {}
    if not users.empty:
        for _, r in users.iterrows():
            users_map[r["user_key"]] = f"{r['name']} — {r['school']}"

    df2 = df.copy()
    df2["professor"] = df2["user_key"].apply(lambda k: users_map.get(k, k))
    st.dataframe(df2[["created_at","professor","disciplina","classe","tema"]], hide_index=True, use_container_width=True)

    df2["label"] = df2["created_at"].astype(str) + " | " + df2["professor"].astype(str) + " | " + df2["disciplina"].astype(str) + " | " + df2["classe"].astype(str) + " | " + df2["tema"].astype(str)
    sel = st.selectbox("Seleccionar plano para baixar (Admin)", df2["label"].tolist())
    row = df2[df2["label"] == sel].iloc[0]
    pdf_bytes = pdf_from_b64(row["pdf_b64"])
    if pdf_bytes:
        st.download_button(
            "⬇️ Baixar PDF (Admin)",
            data=pdf_bytes,
            file_name=f"Plano_{row['disciplina']}_{row['classe']}_{row['tema']}.pdf".replace(" ", "_"),
            mime="application/pdf",
            type="primary",
        )


# =========================
# ADMIN: PAINEL COMPLETO
# =========================
def render_admin_panel():
    st.subheader("🛠️ Painel do Administrador (Completo)")

    users = list_users_df()
    if users.empty:
        st.info("Sem utilizadores registados.")
        return

    st.dataframe(users[["name","school","status","created_at"]], hide_index=True, use_container_width=True)

    users2 = users.copy()
    users2["label"] = users2["name"].astype(str) + " — " + users2["school"].astype(str) + " (" + users2["status"].astype(str) + ")"
    sel = st.selectbox("Selecionar professor", users2["label"].tolist())
    row = users2[users2["label"] == sel].iloc[0]
    uk = row["user_key"]

    c1, c2, c3 = st.columns(3)
    with c1:
        if st.button("✅ Aprovar"):
            set_user_status(uk, "approved")
            st.success("Aprovado.")
            st.rerun()
    with c2:
        if st.button("🚫 Bloquear"):
            set_user_status(uk, "blocked")
            st.success("Bloqueado.")
            st.rerun()
    with c3:
        if st.button("↩️ Voltar p/ trial"):
            set_user_status(uk, "trial")
            st.success("Estado trial.")
            st.rerun()


# =========================
# RENDER TABS
# =========================
if is_admin:
    with tabs[0]:
        render_admin_history()
    with tabs[1]:
        render_admin_panel()
    with tabs[2]:
        st.info("Esta é a área do professor (para testes).")
        render_user_history()
        st.divider()
        render_generate()
else:
    with tabs[0]:
        render_user_history()
    with tabs[1]:
        render_generate()
