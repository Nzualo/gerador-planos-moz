# app.py
# =========================================================
# MZ SDEJT - Planos SNE (Inhassoro) | Streamlit + Supabase
# - Login simples: 1ª vez (nome + escola + PIN); depois (nome + PIN)
# - Escola só aceita lista oficial (com tolerância a abreviações EP/EB/ES/II/SDEJT)
# - Professor: Histórico + Gerar Plano (IA) + Guardar + Baixar PDF
# - Admin (separado): entrar por senha e ver/filtrar planos + gerir utilizadores
#
# SECRETS (Streamlit -> Settings -> Secrets):
# SUPABASE_URL=...
# SUPABASE_SERVICE_ROLE_KEY=...
# GOOGLE_API_KEY=...
# ADMIN_PASSWORD=...
# PIN_PEPPER=uma_string_longa_e_secreta (ex.: "9f2c...muito_longo...a1")
# =========================================================

import base64
import hashlib
import json
import re
import unicodedata
from datetime import date, datetime

import pandas as pd
import requests
import streamlit as st
from fpdf import FPDF
from pydantic import BaseModel, Field, ValidationError, conlist
from supabase import create_client

import google.generativeai as genai


# =========================
# UI
# =========================
st.set_page_config(page_title="MZ SDEJT - Planos SNE", page_icon="🇲🇿", layout="wide")
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
# Secrets checks
# =========================
REQ_SECRETS = ["SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY", "GOOGLE_API_KEY", "ADMIN_PASSWORD", "PIN_PEPPER"]
missing_sec = [k for k in REQ_SECRETS if k not in st.secrets]
if missing_sec:
    st.error(f"Faltam Secrets: {', '.join(missing_sec)}")
    st.stop()


# =========================
# Supabase
# =========================
@st.cache_resource
def supa():
    return create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_SERVICE_ROLE_KEY"])


def today_iso() -> str:
    return date.today().isoformat()


# =========================
# Escolas oficiais (Inhassoro)
# =========================
OFFICIAL_SCHOOLS = [
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
    s = unicodedata.normalize("NFKD", s)
    s = "".join([c for c in s if not unicodedata.combining(c)])
    s = re.sub(r"\s+", " ", s)
    return s.strip()


def normalize_school_name(user_school: str) -> str:
    """
    Aceita:
    - "EP ..." ou "Escola Primária ..." -> EP
    - "EB ..." ou "Escola Básica ..." -> EB
    - "ES ..." ou "Escola Secundária ..." -> ES
    - "Instituto ..." pode virar II (mas mantemos o texto)
    - "Serviço Distrital ..." pode virar SDEJT (mas mantemos o texto)
    """
    s = normalize_text(user_school)

    # expand/standardize tokens no começo
    s = re.sub(r"^escola primaria\b", "ep", s)
    s = re.sub(r"^escola basica\b", "eb", s)
    s = re.sub(r"^escola secundaria\b", "es", s)
    s = re.sub(r"^instituto\b", "instituto", s)  # mantém
    s = re.sub(r"^servico distrital\b", "servico distrital", s)  # mantém

    # remove pontuação leve
    s = re.sub(r"[\"'“”‘’]", "", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


OFFICIAL_MAP = {normalize_school_name(x): x for x in OFFICIAL_SCHOOLS}


def resolve_school(user_input: str) -> str | None:
    """
    Retorna o nome oficial se bater EXACTO por normalização.
    """
    key = normalize_school_name(user_input)
    return OFFICIAL_MAP.get(key)


# =========================
# Auth / PIN
# =========================
def make_user_key(name: str, school_official: str) -> str:
    raw = (name.strip().lower() + "|" + school_official.strip().lower()).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def pin_hash(pin: str) -> str:
    pepper = st.secrets["PIN_PEPPER"]
    raw = (pepper + "|" + (pin or "").strip()).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def get_user_by_name(name: str):
    sb = supa()
    r = sb.table("app_users").select("*").eq("name", name.strip()).limit(1).execute()
    return r.data[0] if r.data else None


def get_user(user_key: str):
    sb = supa()
    r = sb.table("app_users").select("*").eq("user_key", user_key).limit(1).execute()
    return r.data[0] if r.data else None


def upsert_user(payload: dict):
    sb = supa()
    existing = get_user(payload["user_key"])
    if existing:
        sb.table("app_users").update(payload).eq("user_key", payload["user_key"]).execute()
    else:
        sb.table("app_users").insert(payload).execute()


def set_user_status(user_key: str, status: str, approved_by: str | None = None):
    sb = supa()
    payload = {"status": status}
    if status == "approved":
        payload["approved_at"] = datetime.now().isoformat()
        payload["approved_by"] = approved_by
    if status in ("trial", "blocked"):
        payload["approved_at"] = None
        payload["approved_by"] = None
    sb.table("app_users").update(payload).eq("user_key", user_key).execute()


def is_admin_session() -> bool:
    return st.session_state.get("is_admin", False)


# =========================
# Plans - DB
# =========================
def list_plans_user(user_key: str) -> pd.DataFrame:
    sb = supa()
    r = (
        sb.table("user_plans")
        .select(
            "id,created_at,plan_day,disciplina,classe,unidade,tema,turma,tipo_aula,duracao,metodos,meios,pdf_b64,upload_details,user_key"
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
            "id,created_at,plan_day,disciplina,classe,unidade,tema,turma,tipo_aula,duracao,metodos,meios,pdf_b64,upload_details,user_key"
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


def get_pdf_bytes_from_b64(pdf_b64: str) -> bytes | None:
    if not pdf_b64:
        return None
    try:
        return base64.b64decode(pdf_b64)
    except Exception:
        return None


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
            "upload_details": upload_details,
            "created_at": datetime.now().isoformat(),
        }
    ).execute()


# =========================
# Plano (IA) - Model
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
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            return json.loads(text[start : end + 1])
        raise


def build_prompt(ctx: dict, upload_hint: str, upload_details: str) -> str:
    det = (upload_details or "").strip()
    extra_file = ""
    if upload_hint:
        extra_file = f"\nFICHEIRO (opcional):\n{upload_hint}\n"
        if det:
            extra_file += f"DETALHES DO FICHEIRO:\n- {det}\n"

    metodos_user = (ctx.get("metodos") or "").strip()
    meios_user = (ctx.get("meios") or "").strip()

    extra_met = ""
    if metodos_user:
        extra_met += f"\nMÉTODOS sugeridos pelo professor (opcional): {metodos_user}\n"
    if meios_user:
        extra_met += f"\nMEIOS/Materiais sugeridos pelo professor (opcional): {meios_user}\n"

    return f"""
És Pedagogo(a) Especialista do Sistema Nacional de Educação (SNE) de Moçambique.
Escreve SEMPRE em Português de Moçambique. Evita termos e ortografia do Brasil.

O plano deve reflectir a realidade do Distrito de Inhassoro, Província de Inhambane.

{extra_file}{extra_met}

REGRAS:
1) Devolve APENAS JSON válido.
2) Campos: "objetivo_geral", "objetivos_especificos", "tabela".
3) Tabela com 6 colunas: ["tempo","funcao_didatica","actividade_professor","actividade_aluno","metodos","meios"]
4) Funções obrigatórias e na ordem:
   - Introdução e Motivação
   - Mediação e Assimilação
   - Domínio e Consolidação
   - Controlo e Avaliação

REGRAS ESPECIAIS:
A) Na 1ª função: controlo de presenças + correcção do TPC (se houver).
B) Na última função: marcar/atribuir TPC com orientação clara.
C) Contextualiza exemplos (pesca, mercado, agricultura local, escola, etc.)

DADOS:
- Escola: {ctx["escola"]}
- Professor: {ctx["professor"]}
- Disciplina: {ctx["disciplina"]}
- Classe: {ctx["classe"]}
- Unidade Temática: {ctx["unidade"]}
- Tema: {ctx["tema"]}
- Duração: {ctx["duracao"]}
- Tipo de Aula: {ctx["tipo_aula"]}
- Turma: {ctx["turma"]}
- Data: {ctx["data"]}

FORMATO JSON:
{{
  "objetivo_geral": "..." OU ["...","..."],
  "objetivos_especificos": ["...","..."],
  "tabela": [
    ["5","Introdução e Motivação","...","...","...","..."],
    ["20","Mediação e Assimilação","...","...","...","..."],
    ["15","Domínio e Consolidação","...","...","...","..."],
    ["5","Controlo e Avaliação","...","...","...","..."]
  ]
}}
""".strip()


def generate_plan_with_gemini(prompt: str) -> str:
    genai.configure(api_key=st.secrets["GOOGLE_API_KEY"])
    # modelo rápido e barato
    try:
        model = genai.GenerativeModel("models/gemini-2.5-flash")
        return model.generate_content(prompt).text
    except Exception:
        model = genai.GenerativeModel("models/gemini-1.5-flash")
        return model.generate_content(prompt).text


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
        self.ln(4)
        self.set_font("Arial", "B", 14)
        self.cell(0, 10, "PLANO DE AULA", 0, 1, "C")
        self.ln(2)

    def footer(self):
        self.set_y(-15)
        self.set_font("Arial", "I", 7)
        self.cell(0, 10, "SDEJT Inhassoro - Processado por IA (validação final: Professor)", 0, 0, "C")


def create_pdf(ctx: dict, plano: PlanoAula) -> bytes:
    pdf = PDF()
    pdf.set_auto_page_break(auto=True, margin=12)
    pdf.add_page()

    pdf.set_font("Arial", "", 10)
    pdf.cell(0, 6, f"Escola: {clean_text(ctx['escola'])}", 0, 1)
    pdf.cell(0, 6, f"Professor: {clean_text(ctx['professor'])}", 0, 1)
    pdf.cell(0, 6, f"Disciplina: {clean_text(ctx['disciplina'])} | Classe: {clean_text(ctx['classe'])} | Turma: {clean_text(ctx['turma'])}", 0, 1)
    pdf.cell(0, 6, f"Unidade Temática: {clean_text(ctx['unidade'])}", 0, 1)
    pdf.cell(0, 6, f"Tema: {clean_text(ctx['tema'])}", 0, 1)
    pdf.cell(0, 6, f"Tipo: {clean_text(ctx['tipo_aula'])} | Duração: {clean_text(ctx['duracao'])} | Data: {clean_text(ctx['data'])}", 0, 1)
    pdf.ln(2)

    pdf.set_font("Arial", "B", 10)
    pdf.cell(0, 6, "OBJECTIVO(S) GERAL(IS):", 0, 1)
    pdf.set_font("Arial", "", 10)
    if isinstance(plano.objetivo_geral, list):
        for i, og in enumerate(plano.objetivo_geral, 1):
            pdf.multi_cell(0, 6, f"{i}. {clean_text(og)}")
    else:
        pdf.multi_cell(0, 6, clean_text(plano.objetivo_geral))
    pdf.ln(1)

    pdf.set_font("Arial", "B", 10)
    pdf.cell(0, 6, "OBJECTIVOS ESPECÍFICOS:", 0, 1)
    pdf.set_font("Arial", "", 10)
    for i, oe in enumerate(plano.objetivos_especificos, 1):
        pdf.multi_cell(0, 6, f"{i}. {clean_text(oe)}")
    pdf.ln(2)

    # tabela simples
    headers = ["Tempo", "Função", "Prof.", "Aluno", "Métodos", "Meios"]
    widths = [12, 30, 48, 48, 26, 26]

    pdf.set_font("Arial", "B", 8)
    for i, h in enumerate(headers):
        pdf.cell(widths[i], 6, h, 1, 0, "C")
    pdf.ln()

    pdf.set_font("Arial", "", 8)
    for row in plano.tabela:
        # altura dinâmica (aprox.)
        cells = [clean_text(x) for x in row]
        max_lines = 1
        for i, txt in enumerate(cells):
            # estimativa de linhas
            max_lines = max(max_lines, int(len(txt) / max(1, widths[i])) + 1)
        h = max(6, max_lines * 4)

        x0 = pdf.get_x()
        y0 = pdf.get_y()

        for i, txt in enumerate(cells):
            pdf.multi_cell(widths[i], 4, txt, border=1)
            pdf.set_xy(x0 + sum(widths[: i + 1]), y0)
        pdf.ln(h)

    return pdf.output(dest="S").encode("latin-1", "replace")


# =========================
# AUTH UI (Professor + Admin separado)
# =========================
def logout():
    st.session_state.pop("auth", None)
    st.session_state.pop("is_admin", None)
    st.rerun()


def auth_gate():
    st.title("🇲🇿 MZ SDEJT - Elaboração de Planos")
    st.caption("Serviço Distrital de Educação, Juventude e Tecnologia - Inhassoro")

    tab_prof, tab_admin = st.tabs(["👤 Professor", "🛠️ Administrador"])

    # -------- Professor --------
    with tab_prof:
        st.subheader("Entrar / Cadastrar")

        name = st.text_input("Nome do Professor", placeholder="Ex.: Cândido").strip()
        if not name:
            st.info("Escreva o seu nome para continuar.")
            st.stop()

        existing = get_user_by_name(name)

        if existing:
            st.success("Conta encontrada. Entre com o seu PIN.")
            pin = st.text_input("PIN", type="password")

            if st.button("Entrar", type="primary"):
                if pin_hash(pin) != (existing.get("pin_hash") or ""):
                    st.error("PIN incorrecto.")
                    st.stop()
                st.session_state["auth"] = {
                    "user_key": existing["user_key"],
                    "name": existing["name"],
                    "school": existing["school"],
                    "status": existing.get("status", "trial"),
                }
                st.rerun()
        else:
            st.warning("Primeiro acesso: registe-se.")
            school_in = st.text_input("Escola (ex.: EP de Inhassoro)").strip()
            pin1 = st.text_input("Criar PIN", type="password")
            pin2 = st.text_input("Confirmar PIN", type="password")

            if st.button("Registar e Entrar", type="primary"):
                school_official = resolve_school(school_in)
                if not school_official:
                    st.error("Escola não registada no sistema. Verifique o nome exacto (ou contacte o SDEJT).")
                    st.stop()
                if not pin1 or len(pin1) < 4:
                    st.error("PIN muito curto. Use pelo menos 4 dígitos/caracteres.")
                    st.stop()
                if pin1 != pin2:
                    st.error("PINs não coincidem.")
                    st.stop()

                user_key = make_user_key(name, school_official)
                payload = {
                    "user_key": user_key,
                    "name": name,
                    "school": school_official,
                    "pin_hash": pin_hash(pin1),
                    "status": "trial",
                    "created_at": datetime.now().isoformat(),
                }
                upsert_user(payload)
                st.session_state["auth"] = {
                    "user_key": user_key,
                    "name": name,
                    "school": school_official,
                    "status": "trial",
                }
                st.success("Registo feito com sucesso.")
                st.rerun()

    # -------- Admin --------
    with tab_admin:
        st.subheader("Entrar como Administrador")
        pwd = st.text_input("Senha do Administrador", type="password")
        if st.button("Entrar como Admin", type="primary"):
            if pwd == st.secrets["ADMIN_PASSWORD"]:
                st.session_state["is_admin"] = True
                st.success("Admin activo.")
                st.rerun()
            else:
                st.error("Senha inválida.")

    # se não autenticou professor nem admin, parar
    if not st.session_state.get("auth") and not st.session_state.get("is_admin"):
        st.stop()


# =========================
# ADMIN PANEL
# =========================
def admin_panel():
    st.sidebar.markdown("### 🛠️ Admin")
    if st.sidebar.button("Sair do Admin"):
        st.session_state["is_admin"] = False
        st.rerun()

    st.header("Painel do Administrador")

    # Utilizadores
    st.subheader("👥 Utilizadores")
    sb = supa()
    ur = sb.table("app_users").select("user_key,name,school,status,created_at,approved_at,approved_by").order("created_at", desc=True).execute()
    users = pd.DataFrame(ur.data or [])
    if users.empty:
        st.info("Sem utilizadores.")
    else:
        st.dataframe(users[["name", "school", "status", "created_at", "approved_at", "approved_by"]], hide_index=True, use_container_width=True)

        users["label"] = users["name"].astype(str) + " — " + users["school"].astype(str) + " (" + users["status"].astype(str) + ")"
        sel = st.selectbox("Seleccionar utilizador", users["label"].tolist())
        row = users[users["label"] == sel].iloc[0]
        uk = row["user_key"]

        c1, c2, c3 = st.columns(3)
        with c1:
            if st.button("Aprovar", type="primary"):
                set_user_status(uk, "approved", approved_by="Admin")
                st.success("Aprovado.")
                st.rerun()
        with c2:
            if st.button("Voltar Trial"):
                set_user_status(uk, "trial")
                st.success("Alterado para trial.")
                st.rerun()
        with c3:
            if st.button("Bloquear"):
                set_user_status(uk, "blocked")
                st.success("Bloqueado.")
                st.rerun()

    st.divider()

    # Planos
    st.subheader("📄 Planos (Todos)")
    plans = list_plans_all()
    if plans.empty:
        st.info("Sem planos guardados.")
        return

    # juntar com user info (nome/escola)
    ur2 = sb.table("app_users").select("user_key,name,school").execute()
    u2 = pd.DataFrame(ur2.data or [])
    if not u2.empty:
        plans = plans.merge(u2, on="user_key", how="left").rename(columns={"name": "professor", "school": "escola"})

    # filtros: data e escola
    colf1, colf2 = st.columns(2)
    with colf1:
        datas = sorted({str(d) for d in plans["plan_day"].dropna().tolist()})
        data_f = st.selectbox("Filtrar por data", ["Todas"] + datas)
    with colf2:
        escolas = sorted({str(s) for s in plans.get("escola", pd.Series([], dtype=str)).dropna().tolist()})
        escola_f = st.selectbox("Filtrar por escola", ["Todas"] + escolas)

    df = plans.copy()
    if data_f != "Todas":
        df = df[df["plan_day"].astype(str) == data_f]
    if escola_f != "Todas" and "escola" in df.columns:
        df = df[df["escola"].astype(str) == escola_f]

    cols_show = ["plan_day", "escola", "professor", "disciplina", "classe", "unidade", "tema", "turma", "upload_details", "created_at"]
    cols_show = [c for c in cols_show if c in df.columns]
    st.dataframe(df[cols_show], hide_index=True, use_container_width=True)

    # download do PDF de qualquer plano
    df["label"] = df["plan_day"].astype(str) + " | " + df.get("escola", "").astype(str) + " | " + df.get("professor", "").astype(str) + " | " + df["disciplina"].astype(str) + " | " + df["tema"].astype(str)
    sel2 = st.selectbox("Seleccionar plano para baixar PDF", df["label"].tolist())
    row2 = df[df["label"] == sel2].iloc[0]
    pdf_bytes = get_pdf_bytes_from_b64(row2.get("pdf_b64", ""))
    if pdf_bytes:
        st.download_button(
            "⬇️ Baixar PDF (Admin)",
            data=pdf_bytes,
            file_name=f"Plano_{row2['plan_day']}_{row2.get('disciplina','')}_{row2.get('tema','')}.pdf".replace(" ", "_"),
            mime="application/pdf",
            type="primary",
        )


# =========================
# PROFESSOR APP
# =========================
def professor_app():
    auth = st.session_state.get("auth")
    if not auth:
        return

    # recarregar estado do DB (para não ficar preso em trial após aprovação)
    sb = supa()
    fresh = get_user(auth["user_key"])
    if fresh:
        auth["status"] = fresh.get("status", "trial")
        st.session_state["auth"] = auth

    # topo
    st.sidebar.markdown("### Sessão")
    st.sidebar.write(f"**Professor:** {auth['name']}")
    st.sidebar.write(f"**Escola:** {auth['school']}")
    st.sidebar.write(f"**Estado:** {auth['status']}")
    if st.sidebar.button("Atualizar estado"):
        st.rerun()
    if st.sidebar.button("Sair"):
        logout()

    st.markdown(
        f"**Professor:** {auth['name']} | **Escola:** {auth['school']} | **Estado:** {auth['status']}"
    )

    tab_hist, tab_gerar = st.tabs(["📚 Meus Planos (Histórico)", "🧠 Gerar Planos"])

    # ---------- Histórico ----------
    with tab_hist:
        st.subheader("📚 Meus Planos (Histórico)")
        hist = list_plans_user(auth["user_key"])
        if hist.empty:
            st.info("Ainda não há planos guardados no seu histórico.")
        else:
            st.dataframe(
                hist[["plan_day", "disciplina", "classe", "unidade", "tema", "turma", "upload_details", "created_at"]],
                hide_index=True,
                use_container_width=True,
            )
            hist["label"] = hist["plan_day"].astype(str) + " | " + hist["disciplina"].astype(str) + " | " + hist["classe"].astype(str) + " | " + hist["tema"].astype(str)
            sel = st.selectbox("Seleccionar plano", hist["label"].tolist())
            row = hist[hist["label"] == sel].iloc[0]
            pdf_bytes = get_pdf_bytes_from_b64(row.get("pdf_b64", ""))
            if pdf_bytes:
                st.download_button(
                    "⬇️ Baixar PDF deste plano",
                    data=pdf_bytes,
                    file_name=f"Plano_{row['plan_day']}_{row['disciplina']}_{row['classe']}_{row['tema']}.pdf".replace(" ", "_"),
                    mime="application/pdf",
                    type="primary",
                )

    # ---------- Gerar com IA ----------
    with tab_gerar:
        st.subheader("🧠 Gerar Planos (IA)")

        # Campos completos (como pediste)
        col1, col2 = st.columns(2)
        with col1:
            disciplina = st.text_input("Disciplina", "Língua Portuguesa")
            classe = st.selectbox("Classe", ["1ª","2ª","3ª","4ª","5ª","6ª","7ª","8ª","9ª","10ª","11ª","12ª"])
            unidade = st.text_input("Unidade Temática", placeholder="Ex.: Textos normativos")
            tipo_aula = st.selectbox("Tipo de Aula", ["Introdução de Matéria Nova","Consolidação e Exercitação","Verificação e Avaliação","Revisão"])
        with col2:
            tema = st.text_input("Tema", placeholder="Ex.: Vogais")
            turma = st.text_input("Turma", "A")
            duracao = st.selectbox("Duração", ["45 Min", "90 Min"])
            data_plano = st.date_input("Data", value=date.today())

        st.markdown("#### Opções (opcionais)")
        metodos = st.text_input("Métodos sugeridos (opcional)", placeholder="Ex.: Expositivo, pergunta-resposta, trabalho em grupo")
        meios = st.text_input("Meios/Materiais sugeridos (opcional)", placeholder="Ex.: Quadro, giz, cartões, livro do aluno, folhas")

        st.markdown("#### Upload (opcional)")
        upload = st.file_uploader("Carregar página do livro / material (PDF/Imagem)", type=["pdf", "png", "jpg", "jpeg"])
        upload_details = st.text_area(
            "Detalhes do ficheiro carregado (opcional)",
            placeholder="Ex.: Página 23 – leitura sobre vogais; usar como base para actividades e exemplos.",
            height=90,
        )

        missing = []
        if not unidade.strip():
            missing.append("Unidade Temática")
        if not tema.strip():
            missing.append("Tema")
        if missing:
            st.warning("Preencha: " + ", ".join(missing))

        # BOTÃO ÚNICO (como pediste)
        if st.button("🚀 Gerar Planos e Guardar", type="primary", disabled=bool(missing)):
            if auth["status"] == "blocked":
                st.error("O seu acesso está bloqueado.")
                st.stop()

            with st.spinner("A gerar o plano com IA e a guardar..."):
                try:
                    upload_name = None
                    upload_type = None
                    upload_b64 = None
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
                                f"- Detalhes do ficheiro: {det}\n"
                                f"Use isto para enriquecer actividades, exemplos e avaliação."
                            )
                        else:
                            upload_hint = f"- Ficheiro enviado: {upload_name} ({upload_type}). Use como referência adicional."

                    ctx = {
                        "escola": auth["school"],
                        "professor": auth["name"],
                        "disciplina": disciplina.strip(),
                        "classe": classe,
                        "unidade": unidade.strip(),
                        "tema": tema.strip(),
                        "duracao": duracao,
                        "tipo_aula": tipo_aula,
                        "turma": turma.strip(),
                        "data": data_plano.strftime("%d/%m/%Y"),
                        "plan_day": data_plano.isoformat(),
                        "metodos": metodos.strip(),
                        "meios": meios.strip(),
                    }

                    prompt = build_prompt(ctx, upload_hint, upload_details)
                    raw_text = generate_plan_with_gemini(prompt)
                    raw = safe_extract_json(raw_text)
                    plano = PlanoAula(**raw)

                    pdf_bytes = create_pdf(ctx, plano)

                    # guardar no DB
                    save_plan(
                        user_key=auth["user_key"],
                        ctx=ctx,
                        plano_json={"ctx": ctx, "plano": plano.model_dump()},
                        pdf_bytes=pdf_bytes,
                        upload_name=upload_name,
                        upload_b64=upload_b64,
                        upload_type=upload_type,
                        upload_details=(upload_details or "").strip() if upload is not None else None,
                    )

                    st.success("Plano gerado e guardado com sucesso ✅")

                    # baixar imediatamente (professor)
                    st.download_button(
                        "⬇️ Baixar PDF agora",
                        data=pdf_bytes,
                        file_name=f"Plano_{ctx['plan_day']}_{ctx['disciplina']}_{ctx['classe']}_{ctx['tema']}.pdf".replace(" ", "_"),
                        mime="application/pdf",
                        type="primary",
                    )

                except ValidationError as ve:
                    st.error("A resposta da IA não respeitou o formato esperado (JSON/estrutura).")
                    st.code(str(ve))
                except Exception as e:
                    st.error(f"Erro ao gerar/guardar: {e}")


# =========================
# MAIN
# =========================
# 1) Se admin activo -> painel admin
if is_admin_session():
    admin_panel()
    st.stop()

# 2) Se professor não autenticado -> gate
if not st.session_state.get("auth"):
    auth_gate()

# 3) Professor app
professor_app()
