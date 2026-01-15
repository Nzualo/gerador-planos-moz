# app.py
# =========================================================
# MZ SDEJT - Planos SNE (Inhassoro)
# Login com PIN:
#  - 1º acesso: Nome + Escola + PIN
#  - Próximos: Nome + PIN
# Administrador separado (senha própria) na sidebar
#
# Professor:
#  - Gerar rascunho -> Editar -> Guardar -> Baixar
#  - Apagar planos do histórico
#
# Admin:
#  - Ver todos os planos, filtrar por escola/data, baixar e apagar
#  - Aprovar/Bloquear/Trial utilizadores
#
# Nota: a palavra "IA" não aparece em lugar nenhum.
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
# UI
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
# PIN
# =========================
def pin_hash(pin: str) -> str:
    pepper = st.secrets["PIN_PEPPER"]
    raw = (pepper + "|" + (pin or "").strip()).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def make_user_key(name: str) -> str:
    return hashlib.sha256(normalize_text(name).encode("utf-8")).hexdigest()


# =========================
# DB: USERS
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
# DB: PLANS
# =========================
def list_plans_user(user_key: str) -> pd.DataFrame:
    sb = supa()
    r = (
        sb.table("user_plans")
        .select("id,created_at,plan_day,disciplina,classe,unidade,tema,turma,tipo_aula,duracao,metodos,meios,pdf_b64,user_key")
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
        .select("id,created_at,plan_day,disciplina,classe,unidade,tema,turma,tipo_aula,duracao,metodos,meios,pdf_b64,user_key")
        .order("created_at", desc=True)
        .execute()
    )
    df = pd.DataFrame(r.data or [])
    if df.empty:
        return df
    df["created_at"] = pd.to_datetime(df["created_at"], errors="coerce")
    df["plan_day"] = pd.to_datetime(df["plan_day"], errors="coerce").dt.date
    return df


def plan_exists_same_tema(user_key: str, tema: str) -> bool:
    tema_k = normalize_text(tema)
    df = list_plans_user(user_key)
    if df.empty:
        return False
    return any(normalize_text(t) == tema_k for t in df["tema"].astype(str).tolist())


def save_plan(
    user_key: str,
    ctx: dict,
    plano_json: dict,
    pdf_bytes: bytes,
    upload_name: str | None,
    upload_b64: str | None,
    upload_type: str | None,
):
    sb = supa()
    sb.table("user_plans").insert(
        {
            "user_key": user_key,
            "plan_day": ctx["plan_day"],
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
            "created_at": datetime.now().isoformat(),
        }
    ).execute()


def delete_plan_user(user_key: str, plan_id: int):
    sb = supa()
    sb.table("user_plans").delete().eq("id", int(plan_id)).eq("user_key", user_key).execute()


def delete_plan_admin(plan_id: int):
    sb = supa()
    sb.table("user_plans").delete().eq("id", int(plan_id)).execute()


def pdf_from_b64(b64: str) -> bytes | None:
    try:
        return base64.b64decode(b64)
    except Exception:
        return None


# =========================
# PLAN MODEL
# =========================
class PlanoAula(BaseModel):
    objetivo_geral: str | list[str]
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


# =========================
# ENFORCERS
# =========================
def strip_local_word(s: str) -> str:
    if not s:
        return s
    s2 = re.sub(r"\bInhassoro\b", "", s, flags=re.IGNORECASE)
    s2 = re.sub(r"\s{2,}", " ", s2).strip(" -;,.")
    return s2.strip()


def sanitize_prof_activity(text: str, professor_name: str) -> str:
    t = (text or "").strip()
    if not t:
        return "Orienta as actividades previstas."

    pn = (professor_name or "").strip()
    if pn:
        t = re.sub(re.escape(pn), "", t, flags=re.IGNORECASE).strip()

    t = re.sub(r"\b(o|a)\s+professor(a)?\b", "", t, flags=re.IGNORECASE).strip()
    t = re.sub(r"\bprofessor(a)?\b", "", t, flags=re.IGNORECASE).strip()
    t = re.sub(r"^\W+", "", t).strip()
    t = re.sub(r"^\s*(eu|vamos|vou|iremos)\b.*", "", t, flags=re.IGNORECASE).strip()

    if len(t) < 8:
        t = "Orienta as actividades previstas."

    starters = ("Orienta", "Conduz", "Organiza", "Apresenta", "Explica", "Propõe", "Regista", "Verifica", "Distribui", "Acompanha")
    if not t.startswith(starters):
        t = "Orienta: " + t
    return t


def enforce_objectives(plano: PlanoAula, duracao: str) -> PlanoAula:
    is_45 = "45" in (duracao or "")
    target_spec = 3 if is_45 else 4

    og = plano.objetivo_geral
    if isinstance(og, list):
        og = [strip_local_word(str(x)) for x in og if str(x).strip()]
        plano.objetivo_geral = og[0] if og else "Desenvolver competências previstas no conteúdo da aula."
    else:
        plano.objetivo_geral = strip_local_word(str(og).strip()) or "Desenvolver competências previstas no conteúdo da aula."

    specs = [strip_local_word(str(x).strip()) for x in (plano.objetivos_especificos or []) if str(x).strip()]
    fillers = [
        "Identificar conceitos-chave do tema em estudo.",
        "Aplicar o conteúdo em exercícios orientados.",
        "Participar em actividades práticas e responder a questões de verificação.",
        "Consolidar o conteúdo através de exemplos e tarefas no caderno.",
    ]
    i = 0
    while len(specs) < target_spec and i < len(fillers):
        if fillers[i] not in specs:
            specs.append(fillers[i])
        i += 1

    plano.objetivos_especificos = specs[:target_spec] if specs else fillers[:target_spec]
    return plano


def enforce_table_language(plano: PlanoAula, professor_name: str) -> PlanoAula:
    if not plano.tabela:
        return plano
    new_rows = []
    for row in plano.tabela:
        row = list(row)
        row = (row + [""] * 6)[:6]
        row[2] = sanitize_prof_activity(row[2], professor_name)
        new_rows.append(row[:6])
    plano.tabela = new_rows
    return plano


def apply_enforcers(plano: PlanoAula, ctx: dict) -> PlanoAula:
    plano = enforce_objectives(plano, ctx.get("duracao", ""))
    plano = enforce_table_language(plano, ctx.get("professor", ""))
    return plano


# =========================
# PROMPT
# =========================
def build_prompt(ctx: dict, upload_hint: str) -> str:
    dur = ctx.get("duracao") or ""
    is_45 = "45" in dur
    target_spec = 3 if is_45 else 4

    return f"""
És Pedagogo(a) Especialista do Sistema Nacional de Educação (SNE) de Moçambique.
Escreve em Português de Moçambique.

DADOS:
- Escola: {ctx["escola"]}
- Disciplina: {ctx["disciplina"]}
- Classe: {ctx["classe"]}
- Unidade Temática: {ctx["unidade"]}
- Tema: {ctx["tema"]}
- Turma: {ctx["turma"]}
- Duração: {ctx["duracao"]}
- Tipo de Aula: {ctx["tipo_aula"]}
- Data: {ctx["data"]}

OPCIONAL:
- Métodos sugeridos: {ctx.get("metodos") or "-"}
- Meios/Materiais sugeridos: {ctx.get("meios") or "-"}
- Detalhes do ficheiro (se houver): {ctx.get("upload_details") or "-"}

UPLOAD (se houver):
{upload_hint if upload_hint else "- (Sem upload)"}

REGRAS:
1) Devolve APENAS JSON válido.
2) Campos: "objetivo_geral", "objetivos_especificos", "tabela".
3) Para {dur}: 1 objectivo geral e {target_spec} objectivos específicos.
4) Nos objectivos NÃO escrevas nomes de localidades (não usar a palavra "Inhassoro").
5) Na coluna "actividade_professor" nunca escrevas o nome do professor; usa "Orienta...", "Conduz...", "Organiza...".
6) Contexto do quotidiano com moderação (pesca, mercado, agricultura, escola), sem exageros.

TABELA:
- 6 colunas: ["tempo","funcao_didatica","actividade_professor","actividade_aluno","metodos","meios"]
- Funções obrigatórias e na ordem:
   - Introdução e Motivação
   - Mediação e Assimilação
   - Domínio e Consolidação
   - Controlo e Avaliação
- Na 1ª função incluir controlo de presenças + correcção do TPC (se houver).
- Na última função marcar/atribuir TPC com orientação clara.

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
""".strip()


@st.cache_data(ttl=3600)
def cached_generate(prompt: str, model_name: str) -> str:
    model = genai.GenerativeModel(model_name)
    resp = model.generate_content(prompt)
    return resp.text


# =========================
# PDF
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
        self.cell(0, 5, "GOVERNO DO DISTRITO DE INHASSORO", 0, 1, "C")
        self.cell(0, 5, "SERVIÇO DISTRITAL DE EDUCAÇÃO, JUVENTUDE E TECNOLOGIA", 0, 1, "C")
        self.ln(5)
        self.set_font("Arial", "B", 14)
        self.cell(0, 10, "PLANO DE AULA", 0, 1, "C")
        self.ln(2)

    def footer(self):
        self.set_y(-15)
        self.set_font("Arial", "I", 7)
        self.cell(0, 10, "SDEJT Inhassoro - Processamento digital (validação final: Professor)", 0, 0, "C")

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

    pdf.cell(0, 7, f"Disciplina: {clean_text(ctx['disciplina'])}   Classe: {clean_text(ctx['classe'])}   Turma: {clean_text(ctx['turma'])}", 0, 1)
    pdf.cell(0, 7, f"Unidade Temática: {clean_text(ctx['unidade'])}", 0, 1)
    pdf.set_font("Arial", "B", 10)
    pdf.cell(0, 7, f"Tema: {clean_text(ctx['tema'])}", 0, 1)

    pdf.set_font("Arial", "", 10)
    pdf.cell(100, 7, f"Professor: {clean_text(ctx['professor'])}", 0, 0)
    pdf.cell(0, 7, f"Duração: {clean_text(ctx['duracao'])}   Tipo: {clean_text(ctx['tipo_aula'])}", 0, 1)

    if ctx.get("metodos"):
        pdf.multi_cell(0, 6, f"Métodos sugeridos: {clean_text(ctx['metodos'])}")
    if ctx.get("meios"):
        pdf.multi_cell(0, 6, f"Meios/Materiais sugeridos: {clean_text(ctx['meios'])}")
    if ctx.get("upload_details"):
        pdf.multi_cell(0, 6, f"Detalhes do ficheiro: {clean_text(ctx['upload_details'])}")

    pdf.line(10, pdf.get_y() + 2, 200, pdf.get_y() + 2)
    pdf.ln(5)

    pdf.set_font("Arial", "B", 10)
    pdf.cell(0, 6, "OBJECTIVO GERAL:", 0, 1)
    pdf.set_font("Arial", "", 10)
    og = plano.objetivo_geral[0] if isinstance(plano.objetivo_geral, list) and plano.objetivo_geral else plano.objetivo_geral
    pdf.multi_cell(0, 6, clean_text(og))
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
# SESSION
# =========================
def logout():
    for k in [
        "logged_in", "user_key", "user_name", "user_school", "user_status", "is_admin",
        "draft_ctx", "draft_raw", "draft_model", "draft_upload_meta"
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


# =========================
# SIDEBAR ADMIN
# =========================
with st.sidebar:
    st.markdown("## 🛠️ Administrador")
    admin_pwd = st.text_input("Senha do Administrador", type="password", key="admin_pwd")

    if st.button("Entrar (Administrador)"):
        if admin_pwd == st.secrets["ADMIN_PASSWORD"]:
            st.session_state["is_admin"] = True
            st.session_state["logged_in"] = True
            st.session_state["user_key"] = "__admin__"
            st.session_state["user_name"] = "Administrador"
            st.session_state["user_school"] = "SDEJT"
            st.session_state["user_status"] = "admin"
            st.success("Sessão activa.")
            st.rerun()
        else:
            st.error("Senha inválida.")

    if st.session_state.get("is_admin"):
        st.success("✅ Sessão activa")
        if st.button("Sair (Administrador)"):
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
# LOGIN PROFESSOR
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
# LOGGED IN
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
# PROFESSOR HISTORY
# =========================
def render_user_history():
    st.subheader("📚 Meus Planos")
    df = list_plans_user(user_key)
    if df.empty:
        st.info("Ainda não há planos guardados.")
        return

    df2 = df.copy()
    df2["label"] = (
        df2["id"].astype(str) + " | " +
        df2["plan_day"].astype(str) + " | " +
        df2["disciplina"].astype(str) + " | " +
        df2["classe"].astype(str) + " | " +
        df2["tema"].astype(str)
    )

    st.dataframe(
        df2[["id","plan_day","disciplina","classe","unidade","tema","turma","created_at"]],
        hide_index=True,
        use_container_width=True
    )

    sel = st.selectbox("Seleccionar plano", df2["label"].tolist(), key="user_hist_sel")
    row = df2[df2["label"] == sel].iloc[0]
    plan_id = int(row["id"])

    c1, c2 = st.columns(2)
    with c1:
        pdf_bytes = pdf_from_b64(row["pdf_b64"])
        if pdf_bytes:
            st.download_button(
                "⬇️ Baixar PDF",
                data=pdf_bytes,
                file_name=f"Plano_{row['disciplina']}_{row['classe']}_{row['tema']}.pdf".replace(" ", "_"),
                mime="application/pdf",
                type="primary",
            )

    with c2:
        confirm = st.checkbox("Confirmo apagar este plano", key="user_del_confirm")
        if st.button("🗑️ Apagar plano", disabled=not confirm):
            delete_plan_user(user_key, plan_id)
            st.success("Plano apagado.")
            st.rerun()


# =========================
# PROFESSOR CREATE (Draft -> Edit -> Save)
# =========================
def render_create():
    st.subheader("🧑‍🏫 Criar Plano")

    col1, col2 = st.columns(2)
    with col1:
        disciplina = st.text_input("Disciplina", "Língua Portuguesa", key="disciplina_in")
        classe = st.selectbox("Classe", ["1ª","2ª","3ª","4ª","5ª","6ª","7ª","8ª","9ª","10ª","11ª","12ª"], key="classe_in")
        unidade = st.text_input("Unidade Temática *", "", key="unidade_in")
    with col2:
        tema = st.text_input("Tema *", "", key="tema_in")
        turma = st.text_input("Turma", "A", key="turma_in")
        data_plano = st.date_input("Data do Plano", value=date.today(), key="data_in")

    col3, col4 = st.columns(2)
    with col3:
        duracao = st.selectbox("Duração", ["45 Min", "90 Min"], key="duracao_in")
        tipo_aula = st.selectbox("Tipo de Aula", ["Introdução de Matéria Nova", "Consolidação e Exercitação", "Verificação e Avaliação", "Revisão"], key="tipo_in")
    with col4:
        metodos = st.text_area("Métodos (opcional)", "", height=110, key="metodos_in")
        meios = st.text_area("Meios/Materiais didácticos (opcional)", "", height=110, key="meios_in")

    st.markdown("### 📎 Upload opcional (Página de livro / imagem / PDF)")
    upload = st.file_uploader("Carregar ficheiro (png/jpg/pdf) - opcional", type=["png","jpg","jpeg","pdf"], key="upload_in")
    upload_details = st.text_area("Detalhes do ficheiro carregado (opcional)", "", height=80, key="upload_details_in")

    missing_fields = []
    if not unidade.strip():
        missing_fields.append("Unidade Temática")
    if not tema.strip():
        missing_fields.append("Tema")
    if missing_fields:
        st.warning("Preencha: " + ", ".join(missing_fields))

    # Bloquear repetição (antes)
    block_generate = False
    if tema.strip() and plan_exists_same_tema(user_key, tema.strip()):
        st.error("Já existe um plano guardado com este Tema. Apague o anterior se quiser substituir.")
        block_generate = True

    if st.button("🚀 Gerar rascunho", type="primary", disabled=bool(missing_fields) or block_generate):
        with st.spinner("A gerar..."):
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
                    upload_hint = f"- Ficheiro enviado: {upload_name} ({upload_type})."

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
                    "upload_details": upload_details.strip(),
                    "data": data_plano.strftime("%d/%m/%Y"),
                    "plan_day": data_plano.isoformat(),
                }

                prompt = build_prompt(ctx, upload_hint)

                try:
                    raw_text = cached_generate(prompt, "models/gemini-2.5-flash")
                    modelo = "gemini-2.5-flash"
                except Exception:
                    raw_text = cached_generate(prompt, "models/gemini-1.5-flash")
                    modelo = "gemini-1.5-flash"

                raw_json = safe_extract_json(raw_text)
                plano = PlanoAula(**raw_json)
                plano = apply_enforcers(plano, ctx)

                st.session_state["draft_ctx"] = ctx
                st.session_state["draft_raw"] = plano.model_dump()
                st.session_state["draft_model"] = modelo
                st.session_state["draft_upload_meta"] = {
                    "upload_name": upload_name,
                    "upload_b64": upload_b64,
                    "upload_type": upload_type,
                }

                st.success("Rascunho criado. Edite e depois guarde.")
                st.rerun()

            except ValidationError as ve:
                st.error("O rascunho ficou inválido.")
                st.code(str(ve))
            except Exception as e:
                st.error("Erro ao criar rascunho.")
                st.code(str(e))

    st.divider()

    if st.session_state.get("draft_ctx") and st.session_state.get("draft_raw"):
        st.subheader("📝 Rascunho (editar antes de guardar)")

        ctx = st.session_state["draft_ctx"]
        draft = st.session_state["draft_raw"]
        modelo = st.session_state.get("draft_model", "-")
        upload_meta = st.session_state.get("draft_upload_meta", {}) or {}

        og = draft.get("objetivo_geral", "")
        og_text = "\n".join([str(x) for x in og]) if isinstance(og, list) else str(og)
        og_edit = st.text_area("Objectivo geral (apenas 1)", og_text, height=110, key="og_edit")

        oes = draft.get("objetivos_especificos", []) or []
        oes_text = "\n".join([str(x) for x in oes])
        oes_edit = st.text_area("Objectivos específicos (1 por linha)", oes_text, height=140, key="oes_edit")

        tabela = draft.get("tabela", []) or []
        df_tab = pd.DataFrame(tabela, columns=TABLE_COLS) if tabela else pd.DataFrame(columns=TABLE_COLS)
        st.markdown("#### 📋 Tabela didáctica")
        df_tab_edit = st.data_editor(df_tab, use_container_width=True, num_rows="dynamic", key="draft_table_editor")

        colA, colB = st.columns(2)
        with colA:
            if st.button("❌ Cancelar rascunho"):
                for k in ["draft_ctx", "draft_raw", "draft_model", "draft_upload_meta"]:
                    st.session_state.pop(k, None)
                st.rerun()

        with colB:
            if st.button("✅ Guardar plano", type="primary"):
                if plan_exists_same_tema(user_key, ctx["tema"]):
                    st.error("Não é permitido guardar: já existe um plano com este Tema.")
                    st.stop()

                og_lines = [strip_local_word(x.strip()) for x in og_edit.split("\n") if x.strip()]
                og_final = og_lines[0] if og_lines else "Desenvolver competências previstas no conteúdo da aula."

                is_45 = "45" in (ctx.get("duracao") or "")
                target_spec = 3 if is_45 else 4
                oe_lines = [strip_local_word(x.strip()) for x in oes_edit.split("\n") if x.strip()]

                fillers = [
                    "Identificar conceitos-chave do tema em estudo.",
                    "Aplicar o conteúdo em exercícios orientados.",
                    "Participar em actividades práticas e responder a questões de verificação.",
                    "Consolidar o conteúdo através de exemplos e tarefas no caderno.",
                ]
                i = 0
                while len(oe_lines) < target_spec and i < len(fillers):
                    if fillers[i] not in oe_lines:
                        oe_lines.append(fillers[i])
                    i += 1
                oe_final = oe_lines[:target_spec]

                if df_tab_edit is None or df_tab_edit.empty:
                    st.error("A tabela está vazia.")
                    st.stop()

                tabela_final = []
                for _, r in df_tab_edit.iterrows():
                    row = [str(r.get(c, "")) if pd.notna(r.get(c, "")) else "" for c in TABLE_COLS]
                    if normalize_text("".join(row)) == "":
                        continue
                    row[2] = sanitize_prof_activity(row[2], ctx.get("professor", ""))
                    tabela_final.append(row[:6])

                if not tabela_final:
                    st.error("A tabela ficou sem linhas válidas.")
                    st.stop()

                plano_final = PlanoAula(
                    objetivo_geral=og_final,
                    objetivos_especificos=oe_final,
                    tabela=tabela_final
                )
                plano_final = apply_enforcers(plano_final, ctx)

                pdf_bytes = create_pdf(ctx, plano_final)

                plano_payload = {
                    "ctx": ctx,
                    "plano": plano_final.model_dump(),
                    "modelo": modelo,
                    "upload_details": ctx.get("upload_details", ""),
                }

                try:
                    save_plan(
                        user_key=user_key,
                        ctx=ctx,
                        plano_json=plano_payload,
                        pdf_bytes=pdf_bytes,
                        upload_name=upload_meta.get("upload_name"),
                        upload_b64=upload_meta.get("upload_b64"),
                        upload_type=upload_meta.get("upload_type"),
                    )
                except Exception as e:
                    # se o índice único do supabase bloquear duplicado
                    msg = str(e)
                    if "duplicate key" in msg.lower() or "unique" in msg.lower():
                        st.error("Já existe um plano com este Tema. Apague o anterior se quiser substituir.")
                        st.stop()
                    raise

                for k in ["draft_ctx", "draft_raw", "draft_model", "draft_upload_meta"]:
                    st.session_state.pop(k, None)

                st.success("Plano guardado.")
                st.download_button(
                    "⬇️ Baixar PDF",
                    data=pdf_bytes,
                    file_name=f"Plano_{ctx['disciplina']}_{ctx['classe']}_{ctx['tema']}.pdf".replace(" ", "_"),
                    mime="application/pdf",
                    type="primary",
                )
                st.rerun()


# =========================
# ADMIN: PLANS
# =========================
def render_admin_plans():
    st.subheader("📚 Planos (Administrador)")
    df = list_plans_all()
    if df.empty:
        st.info("Ainda não há planos no sistema.")
        return

    users = list_users_df()
    users_map = {r["user_key"]: {"name": r["name"], "school": r["school"]} for _, r in users.iterrows()} if not users.empty else {}

    df2 = df.copy()
    df2["professor"] = df2["user_key"].apply(lambda k: users_map.get(k, {}).get("name", k))
    df2["escola"] = df2["user_key"].apply(lambda k: users_map.get(k, {}).get("school", "-"))

    c1, c2 = st.columns(2)
    with c1:
        escolas = ["Todas"] + sorted(df2["escola"].astype(str).unique().tolist())
        escola_f = st.selectbox("Filtrar por escola", escolas, key="adm_escola_f")
    with c2:
        datas = ["Todas"] + sorted({str(d) for d in df2["plan_day"].dropna().tolist()})
        data_f = st.selectbox("Filtrar por data do plano", datas, key="adm_data_f")

    dff = df2.copy()
    if escola_f != "Todas":
        dff = dff[dff["escola"].astype(str) == escola_f]
    if data_f != "Todas":
        dff = dff[dff["plan_day"].astype(str) == data_f]

    st.dataframe(
        dff[["id","plan_day","escola","professor","disciplina","classe","unidade","tema","turma","created_at"]],
        hide_index=True,
        use_container_width=True
    )

    dff["label"] = (
        dff["id"].astype(str) + " | " +
        dff["plan_day"].astype(str) + " | " +
        dff["escola"].astype(str) + " | " +
        dff["professor"].astype(str) + " | " +
        dff["tema"].astype(str)
    )
    sel = st.selectbox("Seleccionar plano", dff["label"].tolist(), key="adm_plan_sel")
    row = dff[dff["label"] == sel].iloc[0]
    plan_id = int(row["id"])

    cA, cB = st.columns(2)
    with cA:
        sb = supa()
        r = sb.table("user_plans").select("pdf_b64,disciplina,classe,tema").eq("id", plan_id).limit(1).execute()
        if r.data:
            pdf_bytes = pdf_from_b64(r.data[0]["pdf_b64"])
            if pdf_bytes:
                st.download_button(
                    "⬇️ Baixar PDF",
                    data=pdf_bytes,
                    file_name=f"Plano_{r.data[0].get('disciplina','')}_{r.data[0].get('classe','')}_{r.data[0].get('tema','')}.pdf".replace(" ", "_"),
                    mime="application/pdf",
                    type="primary",
                )

    with cB:
        confirm = st.checkbox("Confirmo apagar este plano", key="adm_del_confirm")
        if st.button("🗑️ Apagar plano", disabled=not confirm):
            delete_plan_admin(plan_id)
            st.success("Plano apagado.")
            st.rerun()


# =========================
# ADMIN: USERS
# =========================
def render_admin_users():
    st.subheader("🛠️ Utilizadores")

    users = list_users_df()
    if users.empty:
        st.info("Sem utilizadores registados.")
        return

    st.dataframe(users[["name","school","status","created_at"]], hide_index=True, use_container_width=True)

    users2 = users.copy()
    users2["label"] = users2["name"].astype(str) + " — " + users2["school"].astype(str) + " (" + users2["status"].astype(str) + ")"
    sel = st.selectbox("Selecionar professor", users2["label"].tolist(), key="adm_user_sel")
    row = users2[users2["label"] == sel].iloc[0]
    uk = row["user_key"]

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


# =========================
# MAIN TABS
# =========================
if is_admin:
    tabs = st.tabs(["📚 Planos", "🛠️ Utilizadores", "🧑‍🏫 Professor"])
    with tabs[0]:
        render_admin_plans()
    with tabs[1]:
        render_admin_users()
    with tabs[2]:
        render_user_history()
        st.divider()
        render_create()
else:
    tabs = st.tabs(["📚 Meus Planos", "🧑‍🏫 Criar Plano"])
    with tabs[0]:
        render_user_history()
    with tabs[1]:
        render_create()
