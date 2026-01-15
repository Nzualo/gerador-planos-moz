# app.py
# =========================================================
# MZ SDEJT - Elaboração de Planos (SDEJT)
# Login com PIN:
#  - 1º acesso: Nome + Escola + PIN
#  - Próximos acessos: Nome + PIN
# Administrador separado (senha própria) na sidebar
#
# Professor:
# 1) Preenche dados -> Gerar rascunho
# 2) Edita (objectivo geral, 3 específicos se 45 min, 5 se 90 min, + tabela)
# 3) Guardar (não permite repetir tema para o mesmo professor) + Baixar PDF
# Histórico: baixar e apagar planos
#
# Administrador:
# - Ver planos de todos com filtros (data/escola/professor), baixar e apagar
# - Exportar CSV (filtrado e todos)
# - Relatório mensal por escola (CSV)
# - Gestão de utilizadores: aprovar/bloquear/trial, limite diário (2/6), reset PIN, apagar utilizador
# =========================================================

import re
import json
import base64
import hashlib
from datetime import datetime, date

import streamlit as st
import pandas as pd

from supabase import create_client

import google.generativeai as genai
from pydantic import BaseModel, Field, ValidationError, conlist
from fpdf import FPDF


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
REQ_SECRETS = [
    "SUPABASE_URL",
    "SUPABASE_SERVICE_ROLE_KEY",
    "ADMIN_PASSWORD",
    "PIN_PEPPER",
    "GOOGLE_API_KEY",
]
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
    rep = {
        "á": "a", "à": "a", "â": "a", "ã": "a",
        "é": "e", "ê": "e",
        "í": "i",
        "ó": "o", "ô": "o", "õ": "o",
        "ú": "u",
        "ç": "c",
    }
    for k, v in rep.items():
        s = s.replace(k, v)
    s = s.replace('"', "").replace("'", "")
    s = " ".join(s.split())
    return s

def expand_abbrev(s: str) -> str:
    t = normalize_text(s)
    t = re.sub(r"\bep\b", "escola primaria", t)
    t = re.sub(r"\beb\b", "escola basica", t)
    t = re.sub(r"\bes\b", "escola secundaria", t)
    t = re.sub(r"\bii\b", "instituto", t)
    t = re.sub(r"\bsdejt\b", "servico distrital de educacao juventude e tecnologia", t)
    return t

def school_key(s: str) -> str:
    return expand_abbrev(s)

SCHOOLS_KEYS = {school_key(x): x for x in SCHOOLS_RAW}

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
# DB HELPERS (USERS)
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
            "daily_limit": 2,
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

def update_user_daily_limit(user_key: str, daily_limit: int):
    sb = supa()
    sb.table("app_users").update({"daily_limit": int(daily_limit)}).eq("user_key", user_key).execute()

def list_users_df() -> pd.DataFrame:
    sb = supa()
    r = sb.table("app_users").select(
        "user_key,name,school,status,created_at,daily_limit,last_login_at"
    ).order("created_at", desc=True).execute()
    return pd.DataFrame(r.data or [])

def admin_reset_pin(user_key: str, new_pin: str):
    sb = supa()
    sb.table("app_users").update({"pin_hash": pin_hash(new_pin)}).eq("user_key", user_key).execute()

def delete_user_and_data(user_key: str, delete_plans: bool = True):
    sb = supa()
    if delete_plans:
        sb.table("user_plans").delete().eq("user_key", user_key).execute()
    sb.table("app_users").delete().eq("user_key", user_key).execute()

def update_last_login(user_key: str):
    try:
        supa().table("app_users").update({"last_login_at": datetime.now().isoformat()}).eq("user_key", user_key).execute()
    except Exception:
        pass


# =========================
# DB HELPERS (PLANS)
# =========================
def list_plans_user(user_key: str) -> pd.DataFrame:
    sb = supa()
    r = (
        sb.table("user_plans")
        .select(
            "id,created_at,plan_day,disciplina,classe,unidade,tema,turma,tipo_aula,duracao,metodos,meios,pdf_b64,upload_name,upload_type,upload_details,user_key"
        )
        .eq("user_key", user_key)
        .order("created_at", desc=True)
        .execute()
    )
    df = pd.DataFrame(r.data or [])
    if df.empty:
        return df
    df["created_at"] = pd.to_datetime(df["created_at"], errors="coerce")
    df["plan_day"] = pd.to_datetime(df["plan_day"], errors="coerce").dt.date
    return df

def list_plans_all() -> pd.DataFrame:
    sb = supa()
    r = (
        sb.table("user_plans")
        .select(
            "id,created_at,plan_day,disciplina,classe,unidade,tema,turma,tipo_aula,duracao,metodos,meios,pdf_b64,upload_name,upload_type,upload_details,user_key"
        )
        .order("created_at", desc=True)
        .execute()
    )
    df = pd.DataFrame(r.data or [])
    if df.empty:
        return df
    df["created_at"] = pd.to_datetime(df["created_at"], errors="coerce")
    df["plan_day"] = pd.to_datetime(df["plan_day"], errors="coerce").dt.date
    return df

def count_plans_today(user_key: str) -> int:
    sb = supa()
    today = date.today().isoformat()
    r = sb.table("user_plans").select("id", count="exact").eq("user_key", user_key).eq("plan_day", today).execute()
    try:
        return int(getattr(r, "count", 0) or 0)
    except Exception:
        return 0

def tema_ja_existe(user_key: str, tema: str) -> bool:
    sb = supa()
    r = sb.table("user_plans").select("tema").eq("user_key", user_key).execute()
    existentes = [x.get("tema", "") for x in (r.data or [])]
    alvo = normalize_text(tema)
    for t in existentes:
        if normalize_text(t) == alvo:
            return True
    return False

def delete_plan(plan_id: int):
    sb = supa()
    sb.table("user_plans").delete().eq("id", plan_id).execute()

def save_plan(
    user_key: str,
    ctx: dict,
    plano_json: dict,
    pdf_bytes: bytes,
    upload_name: str | None,
    upload_b64: str | None,
    upload_type: str | None,
    upload_details: str | None,
):
    sb = supa()
    sb.table("user_plans").insert(
        {
            "user_key": user_key,
            "plan_day": ctx["plan_day"],  # dia de uso (hoje) para limite diário
            "disciplina": ctx["disciplina"],
            "classe": ctx["classe"],
            "unidade": ctx["unidade"],
            "tema": ctx["tema"],
            "turma": ctx["turma"],
            "tipo_aula": ctx["tipo_aula"],
            "duracao": ctx["duracao"],
            "metodos": ctx.get("metodos", ""),
            "meios": ctx.get("meios", ""),
            "plan_json": plano_json,
            "pdf_b64": base64.b64encode(pdf_bytes).decode("utf-8"),
            "upload_name": upload_name,
            "upload_b64": upload_b64,
            "upload_type": upload_type,
            "upload_details": upload_details,
            "created_at": datetime.now().isoformat(),
        }
    ).execute()

def pdf_from_b64(b64: str) -> bytes | None:
    try:
        return base64.b64decode(b64)
    except Exception:
        return None


# =========================
# PLANO (MODELO)
# =========================
class PlanoAula(BaseModel):
    objetivo_geral: str
    objetivos_especificos: list[str] = Field(min_length=1)
    tabela: list[conlist(str, min_length=6, max_length=6)]

TABLE_COLS = ["Tempo", "Função Didáctica", "Actividade do Professor", "Actividade do Aluno", "Métodos", "Meios"]

def safe_extract_json(text: str) -> dict:
    text = (text or "").strip()
    try:
        return json.loads(text)
    except Exception:
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            return json.loads(text[start:end + 1])
        raise

def objetivos_alvo_por_duracao(duracao: str) -> int:
    d = normalize_text(duracao)
    if "45" in d:
        return 3
    return 5

def build_prompt(ctx: dict, upload_hint: str) -> str:
    n_obj = objetivos_alvo_por_duracao(ctx["duracao"])
    return f"""
És um(a) pedagogo(a) especialista do Sistema Nacional de Educação de Moçambique.
Escreve em Português de Moçambique. Devolve APENAS JSON válido.

DADOS DO PLANO:
- Escola: {ctx["escola"]}
- Disciplina: {ctx["disciplina"]}
- Classe: {ctx["classe"]}
- Unidade Temática: {ctx["unidade"]}
- Tema: {ctx["tema"]}
- Turma: {ctx["turma"]}
- Duração: {ctx["duracao"]}
- Tipo de Aula: {ctx["tipo_aula"]}
- Data: {ctx["data"]}

OPCIONAL (se informado):
- Métodos sugeridos: {ctx.get("metodos") or "-"}
- Meios/Materiais sugeridos: {ctx.get("meios") or "-"}

FICHEIRO (opcional):
{upload_hint if upload_hint else "- (Sem ficheiro)"}

REGRAS:
1) Objectivo geral: 1 (um) apenas, frase clara e mensurável.
2) Objectivos específicos: exactamente {n_obj} itens.
3) Nos objectivos NÃO incluir nomes de localidades.
4) Na tabela, NÃO mencionar nome do professor. Usar sempre expressões como:
   "Orienta...", "Explica...", "Demonstra...", "Solicita...", "Distribui...", "Acompanha...", "Regista...", "Avalia...".
5) Contextualização local: usar exemplos do quotidiano com moderação, sem repetir nomes de localidades.
6) Tabela com 6 colunas, e 4 linhas na ordem exacta:
   - Introdução e Motivação
   - Mediação e Assimilação
   - Domínio e Consolidação
   - Controlo e Avaliação
7) Na 1ª função incluir controlo de presenças + verificação do trabalho de casa (se aplicável).
8) Na última função incluir indicação de trabalho de casa com orientação clara.

FORMATO JSON:
{{
  "objetivo_geral": "...",
  "objetivos_especificos": ["...","...","..."],
  "tabela": [
    ["5","Introdução e Motivação","...","...","...","..."],
    ["20","Mediação e Assimilação","...","...","...","..."],
    ["15","Domínio e Consolidação","...","...","...","..."],
    ["5","Controlo e Avaliação","...","...","...","..."]
  ]
}}

Garante que cada linha da tabela tem exactamente 6 células.
""".strip()

@st.cache_data(ttl=3600)
def cached_generate(prompt: str, model_name: str) -> str:
    model = genai.GenerativeModel(model_name)
    resp = model.generate_content(prompt)
    return resp.text


# =========================
# PDF (FPDF)
# =========================
def clean_text(text) -> str:
    if text is None:
        return "-"
    t = str(text).strip()
    for k, v in {"–": "-", "—": "-", "“": '"', "”": '"', "‘": "'", "’": "'", "…": "...", "•": "-"}.items():
        t = t.replace(k, v)
    return " ".join(t.replace("\r", " ").replace("\n", " ").split())

class PDF(FPDF):
    def header(self):
        self.set_font("Arial", "B", 12)
        self.cell(0, 5, "REPÚBLICA DE MOÇAMBIQUE", 0, 1, "C")
        self.set_font("Arial", "B", 10)
        self.cell(0, 5, "GOVERNO DO DISTRITO", 0, 1, "C")
        self.cell(0, 5, "SERVIÇO DISTRITAL DE EDUCAÇÃO, JUVENTUDE E TECNOLOGIA", 0, 1, "C")
        self.ln(5)
        self.set_font("Arial", "B", 14)
        self.cell(0, 10, "PLANO DE AULA", 0, 1, "C")
        self.ln(2)

    def footer(self):
        self.set_y(-15)
        self.set_font("Arial", "I", 7)
        self.cell(0, 10, "SDEJT - Documento para validação e uso em sala de aula", 0, 0, "C")

    def draw_table_header(self, widths):
        headers = ["TEMPO", "F. DIDÁTICA", "ACTIV. PROFESSOR", "ACTIV. ALUNO", "MÉTODOS", "MEIOS"]
        self.set_font("Arial", "B", 7)
        self.set_fill_color(220, 220, 220)
        for i, h in enumerate(headers):
            self.cell(widths[i], 6, h, 1, 0, "C", True)
        self.ln()

    def table_row(self, data, widths):
        row = [clean_text(x) for x in data]
        self.set_font("Arial", "", 8)
        max_lines = 1
        for i, txt in enumerate(row):
            lines = self.multi_cell(widths[i], 4, txt, split_only=True)
            max_lines = max(max_lines, len(lines))
        height = max_lines * 4 + 4

        if self.get_y() + height > 270:
            self.add_page()
            self.draw_table_header(widths)

        x0 = 10
        y0 = self.get_y()
        x = x0
        for i, txt in enumerate(row):
            self.set_xy(x, y0)
            self.multi_cell(widths[i], 4, txt, border=0, align="L")
            x += widths[i]

        x = x0
        for w in widths:
            self.rect(x, y0, w, height)
            x += w

        self.set_y(y0 + height)

def create_pdf(ctx: dict, plano: PlanoAula) -> bytes:
    pdf = PDF()
    pdf.set_auto_page_break(auto=False)
    pdf.add_page()

    pdf.set_font("Arial", "", 10)
    pdf.cell(130, 7, f"Escola: {clean_text(ctx['escola'])}", 0, 0)
    pdf.cell(0, 7, f"Data: {clean_text(ctx['data'])}", 0, 1)

    pdf.cell(
        0, 7,
        f"Disciplina: {clean_text(ctx['disciplina'])}   Classe: {clean_text(ctx['classe'])}   Turma: {clean_text(ctx['turma'])}",
        0, 1
    )
    pdf.cell(0, 7, f"Unidade Temática: {clean_text(ctx['unidade'])}", 0, 1)
    pdf.set_font("Arial", "B", 10)
    pdf.cell(0, 7, f"Tema: {clean_text(ctx['tema'])}", 0, 1)

    pdf.set_font("Arial", "", 10)
    pdf.cell(0, 7, f"Duração: {clean_text(ctx['duracao'])}   Tipo: {clean_text(ctx['tipo_aula'])}", 0, 1)

    if ctx.get("metodos"):
        pdf.multi_cell(0, 6, f"Métodos sugeridos: {clean_text(ctx['metodos'])}")
    if ctx.get("meios"):
        pdf.multi_cell(0, 6, f"Meios/Materiais sugeridos: {clean_text(ctx['meios'])}")
    if ctx.get("upload_details"):
        pdf.multi_cell(0, 6, f"Detalhes do ficheiro (opcional): {clean_text(ctx['upload_details'])}")

    pdf.line(10, pdf.get_y() + 2, 200, pdf.get_y() + 2)
    pdf.ln(5)

    pdf.set_font("Arial", "B", 10)
    pdf.cell(0, 6, "OBJECTIVO GERAL:", 0, 1)
    pdf.set_font("Arial", "", 10)
    pdf.multi_cell(0, 6, clean_text(plano.objetivo_geral))
    pdf.ln(2)

    pdf.set_font("Arial", "B", 10)
    pdf.cell(0, 6, "OBJECTIVOS ESPECÍFICOS:", 0, 1)
    pdf.set_font("Arial", "", 10)
    for i, oe in enumerate(plano.objetivos_especificos, 1):
        pdf.multi_cell(0, 6, f"{i}. {clean_text(oe)}")
    pdf.ln(4)

    widths = [12, 32, 52, 52, 21, 21]
    pdf.draw_table_header(widths)
    for row in plano.tabela:
        pdf.table_row(row, widths)

    return pdf.output(dest="S").encode("latin-1", "replace")


# =========================
# SESSION HELPERS
# =========================
def logout():
    for k in [
        "logged_in", "user_key", "user_name", "user_school", "user_status", "is_admin",
        "draft_ctx", "draft_plan", "draft_upload_name", "draft_upload_b64", "draft_upload_type", "draft_modelo"
    ]:
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
        st.session_state["daily_limit"] = int(u.get("daily_limit") or 2)


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
            st.success("Sessão administrativa activa.")
            st.rerun()
        else:
            st.error("Senha inválida.")

    if st.session_state.get("is_admin"):
        st.success("✅ Sessão administrativa activa")
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
st.caption("Serviço Distrital de Educação, Juventude e Tecnologia")
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
                update_last_login(u["user_key"])
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
                        update_last_login(user_key)
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
# PROFESSOR: HISTÓRICO + APAGAR
# =========================
def render_user_history():
    st.subheader("📚 Meus Planos (Histórico)")
    df = list_plans_user(user_key)
    if df.empty:
        st.info("Ainda não há planos guardados no seu histórico.")
        return

    df2 = df.copy()
    df2["label"] = (
        df2["plan_day"].astype(str) + " | " +
        df2["disciplina"].astype(str) + " | " +
        df2["classe"].astype(str) + " | " +
        df2["tema"].astype(str)
    )
    st.dataframe(
        df2[["plan_day","disciplina","classe","unidade","tema","turma","upload_details","created_at"]],
        hide_index=True,
        use_container_width=True
    )

    sel = st.selectbox("Seleccionar plano", df2["label"].tolist(), key="usr_sel_plan")
    row = df2[df2["label"] == sel].iloc[0]
    pdf_bytes = pdf_from_b64(row["pdf_b64"])

    c1, c2 = st.columns([0.6, 0.4])
    with c1:
        if pdf_bytes:
            st.download_button(
                "⬇️ Baixar PDF",
                data=pdf_bytes,
                file_name=f"Plano_{row['disciplina']}_{row['classe']}_{row['tema']}.pdf".replace(" ", "_"),
                mime="application/pdf",
                type="primary",
            )
    with c2:
        confirm_del = st.checkbox("Confirmar apagar este plano", key="usr_conf_del_plan")
        if st.button("🗑️ Apagar plano", disabled=not confirm_del, key="usr_del_plan"):
            delete_plan(int(row["id"]))
            st.success("Plano apagado.")
            st.rerun()


# =========================
# PROFESSOR: GERAR -> EDITAR -> GUARDAR (com limite diário)
# =========================
def get_daily_limit(user_key: str) -> int:
    u = get_user_by_key(user_key)
    if not u:
        return 2
    try:
        return int(u.get("daily_limit") or 2)
    except Exception:
        return 2

def render_generate():
    st.subheader("🧑‍🏫 Criar Plano")

    daily_limit = get_daily_limit(user_key)
    used_today = count_plans_today(user_key)
    remaining = max(0, daily_limit - used_today)
    st.info(f"Hoje: **{used_today}/{daily_limit}** planos. Restam: **{remaining}**.")

    # CAMPOS OBRIGATÓRIOS
    col1, col2 = st.columns(2)
    with col1:
        disciplina = st.text_input("Disciplina", "Língua Portuguesa", key="g_disciplina")
        classe = st.selectbox("Classe", ["1ª","2ª","3ª","4ª","5ª","6ª","7ª","8ª","9ª","10ª","11ª","12ª"], key="g_classe")
        unidade = st.text_input("Unidade Temática *", "", key="g_unidade")
    with col2:
        tema = st.text_input("Tema *", "", key="g_tema")
        turma = st.text_input("Turma", "A", key="g_turma")
        data_plano = st.date_input("Data do Plano", value=date.today(), key="g_data")

    # CAMPOS DIDÁTICOS (OPCIONAIS)
    col3, col4 = st.columns(2)
    with col3:
        duracao = st.selectbox("Duração", ["45 Min", "90 Min"], key="g_duracao")
        tipo_aula = st.selectbox(
            "Tipo de Aula",
            ["Introdução de Matéria Nova", "Consolidação e Exercitação", "Verificação e Avaliação", "Revisão"],
            key="g_tipo"
        )
    with col4:
        metodos = st.text_area("Métodos (opcional)", "", height=110, key="g_metodos")
        meios = st.text_area("Meios/Materiais didácticos (opcional)", "", height=110, key="g_meios")

    st.markdown("### 📎 Ficheiro (opcional)")
    upload = st.file_uploader("Carregar ficheiro (png/jpg/pdf) - opcional", type=["png","jpg","jpeg","pdf"], key="g_upload")
    upload_details = st.text_area(
        "Detalhes do ficheiro (opcional)",
        placeholder="Ex.: Página 23 do livro, texto/figura para usar em exemplos e actividades.",
        height=90,
        key="g_upload_details"
    )

    missing_fields = []
    if not unidade.strip():
        missing_fields.append("Unidade Temática")
    if not tema.strip():
        missing_fields.append("Tema")

    if missing_fields:
        st.warning("Preencha: " + ", ".join(missing_fields))

    # Botão: gerar rascunho
    if st.button("Gerar plano", type="primary", disabled=bool(missing_fields) or remaining <= 0, key="btn_gerar"):
        if remaining <= 0:
            st.error("Limite diário atingido. Solicite aumento ao administrador.")
            st.stop()

        # não gerar se já existe tema guardado
        if tema_ja_existe(user_key, tema.strip()):
            st.error("Já existe um plano guardado com este tema. Altere o tema ou apague o plano anterior.")
            st.stop()

        with st.spinner("A gerar o rascunho..."):
            try:
                genai.configure(api_key=st.secrets["GOOGLE_API_KEY"])

                upload_name = None
                upload_b64 = None
                upload_type = None
                upload_hint = ""

                if upload is not None:
                    upload_name = upload.name
                    upload_type = upload.type or ""
                    upload_bytes = upload.getvalue()
                    upload_b64 = base64.b64encode(upload_bytes).decode("utf-8")

                    det = (upload_details or "").strip()
                    if det:
                        upload_hint = (
                            f"- Ficheiro enviado: {upload_name} ({upload_type}).\n"
                            f"- Detalhes: {det}\n"
                            f"Use com moderação para enriquecer exemplos e exercícios."
                        )
                    else:
                        upload_hint = f"- Ficheiro enviado: {upload_name} ({upload_type}). Use com moderação para enriquecer exemplos e exercícios."

                ctx = {
                    "escola": user_school,
                    "professor": user_name,
                    "disciplina": disciplina.strip(),
                    "classe": classe,
                    "unidade": unidade.strip(),
                    "tema": tema.strip(),
                    "turma": turma.strip(),
                    "duracao": duracao,
                    "tipo_aula": tipo_aula,
                    "metodos": metodos.strip(),
                    "meios": meios.strip(),
                    "data": data_plano.strftime("%d/%m/%Y"),
                    "plan_day": date.today().isoformat(),  # limite diário pelo dia de uso
                    "upload_details": (upload_details or "").strip(),
                }

                prompt = build_prompt(ctx, upload_hint)

                # tenta um modelo e fallback
                try:
                    raw_text = cached_generate(prompt, "models/gemini-2.5-flash")
                    modelo = "gemini-2.5-flash"
                except Exception:
                    raw_text = cached_generate(prompt, "models/gemini-1.5-flash")
                    modelo = "gemini-1.5-flash"

                raw_json = safe_extract_json(raw_text)
                plano = PlanoAula(**raw_json)

                alvo = objetivos_alvo_por_duracao(duracao)
                if len(plano.objetivos_especificos) != alvo:
                    oes = list(plano.objetivos_especificos)
                    if len(oes) > alvo:
                        oes = oes[:alvo]
                    while len(oes) < alvo:
                        oes.append("Realizar exercícios de aplicação relacionados ao tema.")
                    plano.objetivos_especificos = oes

                st.session_state["draft_ctx"] = ctx
                st.session_state["draft_plan"] = plano.model_dump()
                st.session_state["draft_upload_name"] = upload_name
                st.session_state["draft_upload_b64"] = upload_b64
                st.session_state["draft_upload_type"] = upload_type
                st.session_state["draft_modelo"] = modelo

                st.success("Rascunho gerado. Pode editar abaixo e depois guardar.")
                st.rerun()

            except ValidationError as ve:
                st.error("A resposta não respeitou o formato esperado (JSON/estrutura).")
                st.code(str(ve))
                st.code(raw_text if "raw_text" in locals() else "")
            except Exception as e:
                st.error(f"Erro ao gerar: {e}")

    # Editar e guardar
    if st.session_state.get("draft_ctx") and st.session_state.get("draft_plan"):
        st.divider()
        st.subheader("✍️ Editar rascunho")

        ctx = st.session_state["draft_ctx"]
        plan = st.session_state["draft_plan"]

        obj_geral = st.text_area("Objectivo geral", value=plan.get("objetivo_geral", ""), height=80, key="ed_obj_geral")

        alvo = objetivos_alvo_por_duracao(ctx["duracao"])
        oes = list(plan.get("objetivos_especificos", []))
        oes = oes[:alvo] + ([""] * max(0, alvo - len(oes)))

        st.markdown(f"**Objectivos específicos ({alvo})**")
        edited_oes = []
        for i in range(alvo):
            edited_oes.append(st.text_input(f"{i+1}.", value=oes[i], key=f"ed_oe_{i}"))

        tabela = list(plan.get("tabela", []))
        while len(tabela) < 4:
            tabela.append(["", "", "", "", "", ""])
        tabela = tabela[:4]

        df_tab = pd.DataFrame(tabela, columns=TABLE_COLS)
        st.markdown("**Tabela de actividades**")
        df_edit = st.data_editor(df_tab, use_container_width=True, num_rows="fixed", key="ed_table")

        c1, c2 = st.columns([0.6, 0.4])
        with c1:
            if st.button("Guardar e baixar PDF", type="primary", key="btn_guardar"):
                daily_limit2 = get_daily_limit(user_key)
                used_today2 = count_plans_today(user_key)
                if used_today2 >= daily_limit2:
                    st.error("Limite diário atingido. Solicite aumento ao administrador.")
                    st.stop()

                if tema_ja_existe(user_key, ctx["tema"]):
                    st.error("Já existe um plano guardado com este tema. Apague o anterior ou altere o tema.")
                    st.stop()

                if not obj_geral.strip():
                    st.error("Preencha o objectivo geral.")
                    st.stop()
                if any(not x.strip() for x in edited_oes):
                    st.error("Preencha todos os objectivos específicos.")
                    st.stop()

                final_plan = {
                    "objetivo_geral": obj_geral.strip(),
                    "objetivos_especificos": [x.strip() for x in edited_oes],
                    "tabela": df_edit.values.tolist(),
                }

                try:
                    plano_obj = PlanoAula(**final_plan)
                except ValidationError as ve:
                    st.error("Há campos inválidos no rascunho (tabela/estrutura).")
                    st.code(str(ve))
                    st.stop()

                pdf_bytes = create_pdf(ctx, plano_obj)

                save_plan(
                    user_key=user_key,
                    ctx=ctx,
                    plano_json={"ctx": ctx, "plano": plano_obj.model_dump(), "modelo": st.session_state.get("draft_modelo", "")},
                    pdf_bytes=pdf_bytes,
                    upload_name=st.session_state.get("draft_upload_name"),
                    upload_b64=st.session_state.get("draft_upload_b64"),
                    upload_type=st.session_state.get("draft_upload_type"),
                    upload_details=ctx.get("upload_details"),
                )

                for k in ["draft_ctx", "draft_plan", "draft_upload_name", "draft_upload_b64", "draft_upload_type", "draft_modelo"]:
                    st.session_state.pop(k, None)

                st.success("Plano guardado com sucesso.")
                st.download_button(
                    "⬇️ Baixar PDF",
                    data=pdf_bytes,
                    file_name=f"Plano_{ctx['disciplina']}_{ctx['classe']}_{ctx['tema']}.pdf".replace(" ", "_"),
                    mime="application/pdf",
                    type="primary",
                    key="dl_after_save"
                )
                st.rerun()

        with c2:
            if st.button("Descartar rascunho", key="btn_descartar"):
                for k in ["draft_ctx", "draft_plan", "draft_upload_name", "draft_upload_b64", "draft_upload_type", "draft_modelo"]:
                    st.session_state.pop(k, None)
                st.info("Rascunho descartado.")
                st.rerun()


# =========================
# ADMIN: PLANOS + FILTROS + CSV + RELATÓRIO + APAGAR
# =========================
def render_admin_history():
    st.subheader("📚 Planos (Administrador)")
    df = list_plans_all()
    if df.empty:
        st.info("Ainda não há planos no sistema.")
        return

    users = list_users_df()
    users_map = {}
    if not users.empty:
        for _, r in users.iterrows():
            users_map[r["user_key"]] = {"name": r["name"], "school": r["school"]}

    df2 = df.copy()
    df2["professor"] = df2["user_key"].apply(lambda k: users_map.get(k, {}).get("name", k))
    df2["escola"] = df2["user_key"].apply(lambda k: users_map.get(k, {}).get("school", "-"))

    # filtros
    c1, c2, c3 = st.columns(3)
    with c1:
        escolas = ["Todas"] + sorted(df2["escola"].astype(str).unique().tolist())
        escola_f = st.selectbox("Filtrar por escola", escolas, key="adm_f_escola")
    with c2:
        datas = ["Todas"] + sorted({str(d) for d in df2["plan_day"].dropna().tolist()})
        data_f = st.selectbox("Filtrar por dia", datas, key="adm_f_data")
    with c3:
        profs = ["Todos"] + sorted(df2["professor"].astype(str).unique().tolist())
        prof_f = st.selectbox("Filtrar por professor", profs, key="adm_f_prof")

    dff = df2.copy()
    if escola_f != "Todas":
        dff = dff[dff["escola"].astype(str) == escola_f]
    if data_f != "Todas":
        dff = dff[dff["plan_day"].astype(str) == data_f]
    if prof_f != "Todos":
        dff = dff[dff["professor"].astype(str) == prof_f]

    # -------------------------
    # Exportar CSV (filtrado e todos)
    # -------------------------
    st.markdown("### ⬇️ Exportar CSV")

    export_df = dff.copy()
    cols = [
        "plan_day","escola","professor","disciplina","classe","unidade","tema","turma",
        "tipo_aula","duracao","metodos","meios","upload_details","created_at","user_key","id"
    ]
    cols = [c for c in cols if c in export_df.columns]
    export_df = export_df[cols]
    csv_filtrado = export_df.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig")

    fname_parts = ["planos_filtrados"]
    if escola_f != "Todas":
        fname_parts.append(normalize_text(escola_f).replace(" ", "_")[:30])
    if data_f != "Todas":
        fname_parts.append(str(data_f))
    if prof_f != "Todos":
        fname_parts.append(normalize_text(prof_f).replace(" ", "_")[:25])
    filename_filtrado = "_".join(fname_parts) + ".csv"

    all_df = df2.copy()
    cols_all = [c for c in cols if c in all_df.columns]
    all_df = all_df[cols_all]
    csv_todos = all_df.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig")

    b1, b2 = st.columns(2)
    with b1:
        st.download_button(
            "📄 Baixar CSV (filtrado)",
            data=csv_filtrado,
            file_name=filename_filtrado,
            mime="text/csv",
            type="primary",
            key="download_csv_admin_filtrado",
        )
    with b2:
        st.download_button(
            "📄 Baixar CSV (todos)",
            data=csv_todos,
            file_name="planos_todos.csv",
            mime="text/csv",
            key="download_csv_admin_todos",
        )

    # -------------------------
    # Relatório mensal por escola
    # -------------------------
    st.divider()
    st.subheader("📊 Relatório mensal por escola")

    hoje = date.today()
    anos = list(range(hoje.year - 2, hoje.year + 1))
    meses = list(range(1, 13))

    cR1, cR2 = st.columns(2)
    with cR1:
        ano_sel = st.selectbox("Ano", anos, index=anos.index(hoje.year), key="rep_ano")
    with cR2:
        mes_sel = st.selectbox("Mês", meses, index=meses.index(hoje.month), key="rep_mes")

    df_rep = df2.copy()
    df_rep = df_rep[df_rep["plan_day"].notna()]
    df_rep["plan_day"] = pd.to_datetime(df_rep["plan_day"], errors="coerce")
    df_rep = df_rep[df_rep["plan_day"].dt.year == int(ano_sel)]
    df_rep = df_rep[df_rep["plan_day"].dt.month == int(mes_sel)]

    if df_rep.empty:
        st.info("Sem planos no mês seleccionado.")
    else:
        rep = (
            df_rep.groupby("escola", dropna=False)
            .agg(
                total_planos=("id", "count"),
                professores_ativos=("professor", "nunique"),
                primeiro_plano=("plan_day", "min"),
                ultimo_plano=("plan_day", "max"),
            )
            .reset_index()
            .sort_values(["total_planos", "escola"], ascending=[False, True])
        )
        rep["media_planos_por_prof"] = (rep["total_planos"] / rep["professores_ativos"]).round(2)

        st.dataframe(
            rep[["escola","total_planos","professores_ativos","media_planos_por_prof","primeiro_plano","ultimo_plano"]],
            hide_index=True,
            use_container_width=True,
        )

        rep_prof = (
            df_rep.groupby(["escola", "professor"], dropna=False)
            .agg(total_planos=("id", "count"))
            .reset_index()
            .sort_values(["escola", "total_planos", "professor"], ascending=[True, False, True])
        )

        csv_escola = rep.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig")
        csv_prof = rep_prof.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig")

        f1 = f"relatorio_escolas_{ano_sel}-{str(mes_sel).zfill(2)}.csv"
        f2 = f"relatorio_escola_prof_{ano_sel}-{str(mes_sel).zfill(2)}.csv"

        bA, bB = st.columns(2)
        with bA:
            st.download_button(
                "📄 Baixar relatório (por escola)",
                data=csv_escola,
                file_name=f1,
                mime="text/csv",
                type="primary",
                key="dl_rel_escola",
            )
        with bB:
            st.download_button(
                "📄 Baixar relatório (escola + professor)",
                data=csv_prof,
                file_name=f2,
                mime="text/csv",
                key="dl_rel_prof",
            )

    # tabela (planos filtrados)
    st.divider()
    st.subheader("📋 Lista (com filtros)")
    st.dataframe(
        dff[["plan_day","escola","professor","disciplina","classe","unidade","tema","turma","upload_details","created_at"]],
        hide_index=True,
        use_container_width=True
    )

    if dff.empty:
        st.info("Nenhum plano para estes filtros.")
        return

    dff = dff.copy()
    dff["label"] = (
        dff["plan_day"].astype(str) + " | " +
        dff["escola"].astype(str) + " | " +
        dff["professor"].astype(str) + " | " +
        dff["disciplina"].astype(str) + " | " +
        dff["classe"].astype(str) + " | " +
        dff["tema"].astype(str)
    )
    sel = st.selectbox("Seleccionar plano", dff["label"].tolist(), key="adm_sel_plan")
    row = dff[dff["label"] == sel].iloc[0]
    pdf_bytes = pdf_from_b64(row["pdf_b64"])

    c4, c5 = st.columns([0.6, 0.4])
    with c4:
        if pdf_bytes:
            st.download_button(
                "⬇️ Baixar PDF",
                data=pdf_bytes,
                file_name=f"Plano_{row['disciplina']}_{row['classe']}_{row['tema']}.pdf".replace(" ", "_"),
                mime="application/pdf",
                type="primary",
            )
    with c5:
        confirm_del = st.checkbox("Confirmar apagar este plano", key="adm_conf_del_plan")
        if st.button("🗑️ Apagar plano", disabled=not confirm_del, key="adm_del_plan"):
            delete_plan(int(row["id"]))
            st.success("Plano apagado.")
            st.rerun()


# =========================
# ADMIN: UTILIZADORES (com limite diário 2/6)
# =========================
def render_admin_users():
    st.subheader("🛠️ Utilizadores (Administrador)")
    users = list_users_df()
    if users.empty:
        st.info("Sem utilizadores registados.")
        return

    st.dataframe(users[["name","school","status","daily_limit","created_at","last_login_at"]], hide_index=True, use_container_width=True)

    users2 = users.copy()
    users2["label"] = users2["name"].astype(str) + " — " + users2["school"].astype(str) + " (" + users2["status"].astype(str) + ")"
    sel = st.selectbox("Selecionar professor", users2["label"].tolist(), key="adm_user_sel")
    row = users2[users2["label"] == sel].iloc[0]
    uk = row["user_key"]

    st.markdown("### Estado")
    c1, c2, c3 = st.columns(3)
    with c1:
        if st.button("✅ Aprovar", key="adm_approve"):
            set_user_status(uk, "approved")
            st.success("Aprovado.")
            st.rerun()
    with c2:
        if st.button("🚫 Bloquear", key="adm_block"):
            set_user_status(uk, "blocked")
            st.success("Bloqueado.")
            st.rerun()
    with c3:
        if st.button("↩️ Trial", key="adm_trial"):
            set_user_status(uk, "trial")
            st.success("Estado trial.")
            st.rerun()

    st.divider()
    st.markdown("### Limite diário (planos por dia)")
    current_daily = int(row.get("daily_limit") or 2)

    daily_limit = st.selectbox("Escolher limite diário", [2, 6], index=0 if current_daily == 2 else 1, key="adm_daily_sel")

    if st.button("💾 Guardar limite diário", key="adm_save_daily"):
        update_user_daily_limit(uk, int(daily_limit))
        st.success("Limite diário actualizado.")
        st.rerun()

    st.divider()
    st.markdown("### Reset PIN")
    new_pin = st.text_input("Novo PIN", type="password", key="adm_new_pin")
    new_pin2 = st.text_input("Confirmar PIN", type="password", key="adm_new_pin2")
    if st.button("🔁 Guardar novo PIN", key="adm_reset_pin"):
        if not new_pin.strip() or len(new_pin.strip()) < 4:
            st.error("PIN muito curto (mínimo 4).")
        elif new_pin != new_pin2:
            st.error("PINs não coincidem.")
        else:
            admin_reset_pin(uk, new_pin.strip())
            st.success("PIN actualizado.")
            st.rerun()

    st.divider()
    st.markdown("### Apagar utilizador")
    delete_plans = st.checkbox("Apagar também os planos deste utilizador", value=True, key="adm_del_plans")
    confirm_del = st.checkbox("Confirmo apagar este utilizador", key="adm_confirm_del_user")
    if st.button("🗑️ Apagar utilizador", disabled=not confirm_del, key="adm_del_user"):
        delete_user_and_data(uk, delete_plans=delete_plans)
        st.success("Utilizador apagado.")
        st.rerun()


# =========================
# TABS PRINCIPAIS
# =========================
if is_admin:
    tabs = st.tabs(["📚 Planos", "🛠️ Utilizadores", "🧑‍🏫 Área do Professor"])
else:
    tabs = st.tabs(["📚 Meus Planos", "🧑‍🏫 Criar Plano"])

if is_admin:
    with tabs[0]:
        render_admin_history()
    with tabs[1]:
        render_admin_users()
    with tabs[2]:
        st.info("Área do professor (para testes / suporte).")
        render_user_history()
        st.divider()
        render_generate()
else:
    with tabs[0]:
        render_user_history()
    with tabs[1]:
        render_generate()
