# =========================================================
# MZ SDEJT - Planos SNE (Inhassoro) | Streamlit + Supabase
# FINAL: Login com PIN + validação de escolas + abas Professor/Admin
# Mantém: gerador, edição, PDF, histórico, currículo, admin completo
# =========================================================

import json
import hashlib
import base64
import re
import unicodedata
from datetime import date, datetime

import requests
import streamlit as st
import pandas as pd
from pydantic import BaseModel, Field, ValidationError, conlist

import google.generativeai as genai
from fpdf import FPDF
from PIL import Image, ImageDraw, ImageFont

from supabase import create_client

# =========================
# UI
# =========================
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

# =========================
# Secrets check
# =========================
REQ = ["SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY", "GOOGLE_API_KEY", "ADMIN_PASSWORD", "PIN_PEPPER"]
miss = [k for k in REQ if k not in st.secrets]
if miss:
    st.error(f"Configure nos Secrets: {', '.join(miss)}")
    st.stop()

# =========================
# Supabase
# =========================
def supa():
    return create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_SERVICE_ROLE_KEY"])

BUCKET_PLANS = "plans"

def today_iso() -> str:
    return date.today().isoformat()

# =========================
# Normalização + PIN
# =========================
def normalize_text(text: str) -> str:
    if not text:
        return ""
    t = text.strip().lower()
    t = unicodedata.normalize("NFKD", t)
    t = "".join(c for c in t if not unicodedata.combining(c))
    t = re.sub(r"[^\w\s]", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t

def make_user_key(name: str, school: str) -> str:
    raw = (normalize_text(name) + "|" + normalize_text(school)).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()

def pin_hash(pin: str) -> str:
    pepper = st.secrets["PIN_PEPPER"]
    raw = (str(pin) + pepper).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()

# =========================
# Lista de escolas (oficial)
# =========================
SCHOOLS = [
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
SCHOOL_MAP = {normalize_text(s): s for s in SCHOOLS}

ALIASES = {
    "sdejt": "Serviço Distrital de Educação, Juventude e Tecnologia de Inhassoro",
    "servico distrital": "Serviço Distrital de Educação, Juventude e Tecnologia de Inhassoro",
    "servico distrital de educacao juventude e tecnologia": "Serviço Distrital de Educação, Juventude e Tecnologia de Inhassoro",
    "instituto estrela do mar": 'Instituto Industrial e Comercial "Estrela do Mar" de Inhassoro',
    "ii estrela do mar": 'Instituto Industrial e Comercial "Estrela do Mar" de Inhassoro',
    "ii": 'Instituto Industrial e Comercial "Estrela do Mar" de Inhassoro',
}

ABBR = {
    "escola primaria": "ep",
    "primaria": "ep",
    "escola basica": "eb",
    "basica": "eb",
    "escola secundaria": "es",
    "secundaria": "es",
    "instituto": "ii",
}

def canonicalize_school(user_input: str) -> str | None:
    raw = normalize_text(user_input)
    if raw in ALIASES:
        return ALIASES[raw]
    for k, v in ABBR.items():
        raw = raw.replace(k, v)
    raw = normalize_text(raw)
    if raw in SCHOOL_MAP:
        return SCHOOL_MAP[raw]
    # tolerância "de/do/da"
    raw2 = raw.replace(" de ", " ").replace(" do ", " ").replace(" da ", " ")
    for norm, original in SCHOOL_MAP.items():
        n2 = norm.replace(" de ", " ").replace(" do ", " ").replace(" da ", " ")
        if raw2 == n2:
            return original
    return None

# =========================
# DB helpers
# =========================
def get_user(user_key: str):
    sb = supa()
    r = sb.table("app_users").select("*").eq("user_key", user_key).limit(1).execute()
    return r.data[0] if r.data else None

def get_user_fresh(user_key: str):
    u = get_user(user_key)
    return u

def is_admin_session() -> bool:
    return st.session_state.get("is_admin", False)

def is_unlimited(status: str) -> bool:
    return status in ("approved", "admin")

def is_blocked(status: str) -> bool:
    return status == "blocked"

# ---------- Users ----------
def upsert_user(user_key: str, name: str, school: str, status: str, pin_h: str | None = None):
    sb = supa()
    existing = get_user(user_key)
    payload = {"user_key": user_key, "name": name.strip(), "school": school.strip(), "status": status}
    if pin_h is not None:
        payload["pin_hash"] = pin_h
    if existing:
        sb.table("app_users").update(payload).eq("user_key", user_key).execute()
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

def set_daily_limit(user_key: str, daily_limit: int):
    supa().table("app_users").update({"daily_limit": int(daily_limit)}).eq("user_key", user_key).execute()

def get_daily_limit(user_key: str) -> int:
    u = get_user(user_key)
    if not u:
        return 2
    try:
        v = u.get("daily_limit", 2)
        return int(v) if v is not None else 2
    except Exception:
        return 2

def delete_user(user_key: str):
    supa().table("app_users").delete().eq("user_key", user_key).execute()

# ---------- Requests (access) ----------
def create_access_request(user_key: str, name: str, school: str):
    sb = supa()
    user = get_user(user_key)
    if user and is_blocked(user.get("status", "")):
        return "blocked"
    if user and user.get("status") in ("admin", "approved"):
        return "already_approved"

    # mantém status pending
    upsert_user(user_key, name, school, "pending")
    sb.table("access_requests").insert(
        {"user_key": user_key, "name": name.strip(), "school": school.strip(), "status": "pending"}
    ).execute()
    return "ok"

def list_pending_requests_df():
    sb = supa()
    r = (
        sb.table("access_requests")
        .select("id,user_key,name,school,status,created_at")
        .eq("status", "pending")
        .order("created_at", desc=True)
        .execute()
    )
    return pd.DataFrame(r.data or [])

# ---------- Usage daily ----------
def get_today_count(user_key: str) -> int:
    sb = supa()
    r = sb.table("usage_daily").select("count").eq("user_key", user_key).eq("day", today_iso()).limit(1).execute()
    if r.data:
        return int(r.data[0]["count"])
    return 0

def inc_today_count(user_key: str):
    sb = supa()
    day = today_iso()
    r = sb.table("usage_daily").select("count").eq("user_key", user_key).eq("day", day).limit(1).execute()
    if r.data:
        new_count = int(r.data[0]["count"]) + 1
        sb.table("usage_daily").update({"count": new_count}).eq("user_key", user_key).eq("day", day).execute()
    else:
        sb.table("usage_daily").insert({"user_key": user_key, "day": day, "count": 1}).execute()

def reset_today_count(user_key: str):
    sb = supa()
    day = today_iso()
    r = sb.table("usage_daily").select("count").eq("user_key", user_key).eq("day", day).limit(1).execute()
    if r.data:
        sb.table("usage_daily").update({"count": 0}).eq("user_key", user_key).eq("day", day).execute()
    else:
        sb.table("usage_daily").insert({"user_key": user_key, "day": day, "count": 0}).execute()

def can_generate(user_key: str, status: str) -> tuple[bool, str]:
    if is_blocked(status):
        return False, "O seu acesso está bloqueado. Contacte o Administrador."
    if is_unlimited(status):
        return True, ""
    limit = get_daily_limit(user_key)
    used = get_today_count(user_key)
    if used >= limit:
        return False, f"Limite diário atingido: {used}/{limit}. Solicite acesso total ou contacte o Administrador."
    return True, ""

# ---------- Admin list users + stats ----------
def list_users_df():
    sb = supa()
    r = (
        sb.table("app_users")
        .select("user_key,name,school,status,created_at,approved_at,approved_by,daily_limit")
        .order("created_at", desc=True)
        .execute()
    )
    df = pd.DataFrame(r.data or [])
    if df.empty:
        return df
    if "daily_limit" not in df.columns:
        df["daily_limit"] = 2
    return df

def usage_daily_all_df() -> pd.DataFrame:
    sb = supa()
    r = sb.table("usage_daily").select("user_key,day,count").execute()
    d = pd.DataFrame(r.data or [])
    if d.empty:
        return pd.DataFrame(columns=["user_key", "day", "count"])
    d["count"] = pd.to_numeric(d["count"], errors="coerce").fillna(0).astype(int)
    d["day"] = pd.to_datetime(d["day"], errors="coerce").dt.date
    return d

def usage_stats_users_df(users_df: pd.DataFrame) -> pd.DataFrame:
    d = usage_daily_all_df()
    if users_df.empty:
        return users_df
    if d.empty:
        users_df["today_count"] = 0
        users_df["total_count"] = 0
        return users_df

    today = date.today()
    total = d.groupby("user_key", as_index=False)["count"].sum().rename(columns={"count": "total_count"})
    today_df = d[d["day"] == today].groupby("user_key", as_index=False)["count"].sum().rename(columns={"count": "today_count"})
    out = users_df.merge(total, on="user_key", how="left").merge(today_df, on="user_key", how="left")
    out["today_count"] = out["today_count"].fillna(0).astype(int)
    out["total_count"] = out["total_count"].fillna(0).astype(int)
    return out

def global_today_total() -> int:
    d = usage_daily_all_df()
    if d.empty:
        return 0
    return int(d[d["day"] == date.today()]["count"].sum())

# =========================
# Curriculum library
# =========================
def add_curriculum_snippet(disciplina: str, classe: str, unidade: str | None, tema: str | None, snippet: str, fonte: str | None):
    sb = supa()
    sb.table("curriculum_snippets").insert({
        "disciplina": disciplina.strip(),
        "classe": classe.strip(),
        "unidade": (unidade or "").strip() or None,
        "tema": (tema or "").strip() or None,
        "snippet": snippet.strip(),
        "fonte": (fonte or "").strip() or None,
    }).execute()

def list_curriculum_snippets(disciplina: str, classe: str) -> pd.DataFrame:
    sb = supa()
    r = (
        sb.table("curriculum_snippets")
        .select("id,disciplina,classe,unidade,tema,snippet,fonte,created_at")
        .eq("disciplina", disciplina.strip())
        .eq("classe", classe.strip())
        .order("created_at", desc=True)
        .execute()
    )
    return pd.DataFrame(r.data or [])

def delete_curriculum_snippet(snippet_id: int):
    sb = supa()
    sb.table("curriculum_snippets").delete().eq("id", snippet_id).execute()

def get_curriculum_context(disciplina: str, classe: str, unidade: str, tema: str) -> str:
    df = list_curriculum_snippets(disciplina, classe)
    if df.empty:
        return ""

    unidade = (unidade or "").strip().lower()
    tema = (tema or "").strip().lower()

    def norm(x): return (x or "").strip().lower()

    df["unid_n"] = df["unidade"].apply(norm)
    df["tema_n"] = df["tema"].apply(norm)

    picks = []
    m = (df["unid_n"] == unidade) & (df["tema_n"] == tema) & (unidade != "") & (tema != "")
    picks += df[m]["snippet"].tolist()
    m = (df["unid_n"] == unidade) & (df["tema_n"] == "") & (unidade != "")
    picks += df[m]["snippet"].tolist()
    m = (df["unid_n"] == "") & (df["tema_n"] == tema) & (tema != "")
    picks += df[m]["snippet"].tolist()
    m = (df["unid_n"] == "") & (df["tema_n"] == "")
    picks += df[m]["snippet"].tolist()

    picks = [p.strip() for p in picks if p and p.strip()]
    picks = picks[:6]
    if not picks:
        return ""
    return "\n".join([f"- {p}" for p in picks])

# =========================
# Histórico de planos (Storage)
# =========================
def list_user_plans(user_key: str) -> pd.DataFrame:
    sb = supa()
    r = (
        sb.table("user_plans")
        .select("id,created_at,plan_day,disciplina,classe,tema,unidade,turma,pdf_path,pdf_b64")
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

def save_plan_to_history_storage(user_key: str, ctx: dict, plano_dict: dict, pdf_bytes: bytes):
    sb = supa()
    plan_day_iso = datetime.strptime(ctx["data"], "%d/%m/%Y").date().isoformat()

    inserted = sb.table("user_plans").insert({
        "user_key": user_key,
        "plan_day": plan_day_iso,
        "disciplina": ctx.get("disciplina", ""),
        "classe": ctx.get("classe", ""),
        "tema": ctx.get("tema", ""),
        "unidade": ctx.get("unidade", ""),
        "turma": ctx.get("turma", ""),
        "pdf_b64": base64.b64encode(pdf_bytes).decode("utf-8"),
        "plan_json": {"ctx": ctx, "plano": plano_dict},
        "pdf_path": None
    }).execute()

    plan_id = inserted.data[0]["id"]
    safe_classe = ctx.get("classe", "").replace(" ", "_")
    path = f"{user_key}/{plan_day_iso}/{plan_id}_{safe_classe}.pdf"

    sb.storage.from_(BUCKET_PLANS).upload(
        path=path,
        file=pdf_bytes,
        file_options={"content-type": "application/pdf", "upsert": "true"},
    )

    sb.table("user_plans").update({"pdf_path": path}).eq("id", plan_id).eq("user_key", user_key).execute()

def get_plan_pdf_bytes(user_key: str, plan_id: int) -> bytes | None:
    sb = supa()
    r = (
        sb.table("user_plans")
        .select("pdf_path,pdf_b64")
        .eq("user_key", user_key)
        .eq("id", plan_id)
        .limit(1)
        .execute()
    )
    if not r.data:
        return None

    pdf_path = r.data[0].get("pdf_path")
    pdf_b64 = r.data[0].get("pdf_b64")

    if pdf_path:
        signed = sb.storage.from_(BUCKET_PLANS).create_signed_url(pdf_path, 60)
        url = signed.get("signedURL") or signed.get("signedUrl") or signed.get("signed_url")
        if url:
            resp = requests.get(url, timeout=30)
            if resp.status_code == 200:
                return resp.content

    if pdf_b64:
        try:
            return base64.b64decode(pdf_b64)
        except Exception:
            return None

    return None

# =========================
# LOGIN com PIN (Professor + Admin)
# =========================
def auth_gate():
    if st.session_state.get("logged_in"):
        return st.session_state["user_key"]

    st.title("🇲🇿 MZ SDEJT - Elaboração de Planos")
    st.caption("Login com PIN (Inhassoro).")

    colA, colB = st.columns([1.2, 0.8])

    with colA:
        st.info("👤 Acesso do Professor")
        nome = st.text_input("Nome do Professor").strip()
        escola_in = st.text_input("Escola (ex.: EP de Inhassoro)").strip()
        modo = st.radio("Modo", ["Entrar", "Primeiro acesso (criar PIN)"], horizontal=True)

        escola_ok = canonicalize_school(escola_in) if escola_in else None
        if escola_in and not escola_ok:
            st.error("Escola não registada. Verifique o nome (ou contacte o SDEJT).")

        if modo == "Entrar":
            pin = st.text_input("PIN", type="password")
            if st.button("✅ Entrar", type="primary"):
                if not nome or not escola_in or not pin:
                    st.error("Preencha nome, escola e PIN.")
                    st.stop()
                if not escola_ok:
                    st.error("Escola inválida.")
                    st.stop()

                user_key = make_user_key(nome, escola_ok)
                u = get_user(user_key)
                if not u:
                    st.error("Utilizador não encontrado. Use 'Primeiro acesso (criar PIN)'.")
                    st.stop()

                if u.get("pin_hash") != pin_hash(pin):
                    st.error("PIN incorrecto.")
                    st.stop()

                st.session_state["logged_in"] = True
                st.session_state["user_key"] = user_key
                st.rerun()

        else:
            pin1 = st.text_input("Criar PIN", type="password")
            pin2 = st.text_input("Confirmar PIN", type="password")
            if st.button("📝 Registar e Entrar", type="primary"):
                if not nome or not escola_in or not pin1 or not pin2:
                    st.error("Preencha tudo.")
                    st.stop()
                if not escola_ok:
                    st.error("Escola inválida.")
                    st.stop()
                if pin1 != pin2:
                    st.error("Os PINs não coincidem.")
                    st.stop()
                if len(pin1) < 4:
                    st.error("PIN muito curto. Use no mínimo 4 dígitos/caracteres.")
                    st.stop()

                user_key = make_user_key(nome, escola_ok)
                if get_user(user_key):
                    st.error("Esse utilizador já existe. Use 'Entrar'.")
                    st.stop()

                upsert_user(user_key, nome, escola_ok, "trial", pin_h=pin_hash(pin1))
                # default daily_limit
                set_daily_limit(user_key, 2)

                st.session_state["logged_in"] = True
                st.session_state["user_key"] = user_key
                st.rerun()

    with colB:
        st.warning("🛠️ Admin")
        admin_pwd = st.text_input("Senha do Administrador", type="password", key="admin_pwd")
        if st.button("Entrar como Admin"):
            if admin_pwd == st.secrets["ADMIN_PASSWORD"]:
                st.session_state["is_admin"] = True
                st.success("Sessão de Administrador activa.")
                st.rerun()
            else:
                st.error("Senha inválida.")

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

    st.stop()

# =========================
# MODELO Plano
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

@st.cache_data(ttl=86400)
def cached_generate(key: str, prompt: str, model_name: str) -> str:
    model = genai.GenerativeModel(model_name)
    resp = model.generate_content(prompt)
    return resp.text

def make_cache_key(payload: dict) -> str:
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()

def build_prompt(ctx: dict, curriculum_text: str) -> str:
    return f"""
És Pedagogo(a) Especialista do Sistema Nacional de Educação (SNE) de Moçambique.
Escreve SEMPRE em Português de Moçambique. Evita termos e ortografia do Brasil.

O plano deve reflectir a realidade do Distrito de Inhassoro, Província de Inhambane, Moçambique.

CONTEÚDO DO CURRÍCULO / PROGRAMA (para seguir com rigor):
{curriculum_text if curriculum_text else "- (Sem snippet registado. Segue boas práticas do SNE e programas oficiais.)"}

CONTEXTO LOCAL:
- Distrito: Inhassoro
- Posto/Localidade: {ctx["localidade"]}
- Tipo de escola: {ctx["tipo_escola"]}
- Recursos disponíveis: {ctx["recursos"]}
- Nº de alunos: {ctx["nr_alunos"]}
- Observações da turma: {ctx["obs_turma"]}
- Livro do aluno disponível (1ª–6ª): {ctx["tem_livro_aluno"]}

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
C) Para 1ª–6ª, se houver livro disponível, incluir "Livro do aluno" nos MEIOS.
D) Sempre que possível, contextualiza o tema com exemplos do dia a dia (Inhassoro: pesca, mercado, escola, agricultura local, etc.)

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

# =========================
# Enforcers (mantido)
# =========================
def contains_any(text: str, terms: list[str]) -> bool:
    t = (text or "").lower()
    return any(term.lower() in t for term in terms)

def is_1a_6a(classe: str) -> bool:
    try:
        n = int("".join([c for c in str(classe) if c.isdigit()]) or "0")
        return 1 <= n <= 6
    except Exception:
        return False

def enforce_didactic_rules(plano: PlanoAula) -> PlanoAula:
    if not plano.tabela:
        return plano

    intro_idx = None
    for i, row in enumerate(plano.tabela):
        if (row[1] or "").strip().lower() == "introdução e motivação":
            intro_idx = i
            break

    controlo_idx = None
    for i in range(len(plano.tabela) - 1, -1, -1):
        if (plano.tabela[i][1] or "").strip().lower() == "controlo e avaliação":
            controlo_idx = i
            break

    if intro_idx is not None:
        row = plano.tabela[intro_idx]
        prof = row[2] or ""
        aluno = row[3] or ""

        if not contains_any(prof, ["chamada", "presen"]):
            prof = (prof + " " if prof else "") + "Faz o controlo de presenças (chamada), regista ausências e organiza a turma."
        if not contains_any(prof, ["tpc", "correc"]):
            prof = (prof + " " if prof else "") + "Orienta a correcção do TPC (se houver), com participação dos alunos."

        if not contains_any(aluno, ["chamada", "presen", "respond"]):
            aluno = (aluno + " " if aluno else "") + "Respondem à chamada e confirmam presenças."
        if not contains_any(aluno, ["tpc", "corrig"]):
            aluno = (aluno + " " if aluno else "") + "Apresentam o TPC e corrigem no caderno."

        plano.tabela[intro_idx] = [row[0], row[1], prof, aluno, row[4], row[5]]

    if controlo_idx is not None:
        row = plano.tabela[controlo_idx]
        prof = row[2] or ""
        aluno = row[3] or ""
        if not contains_any(prof, ["tpc", "marc", "atrib"]):
            prof = (prof + " " if prof else "") + "Marca o TPC: explica a tarefa, critérios e prazo."
        if not contains_any(aluno, ["tpc", "anot"]):
            aluno = (aluno + " " if aluno else "") + "Anotam o TPC e confirmam o que deve ser feito."
        plano.tabela[controlo_idx] = [row[0], row[1], prof, aluno, row[4], row[5]]

    return plano

def enforce_livro_aluno_meios(plano: PlanoAula, ctx: dict) -> PlanoAula:
    if not plano.tabela:
        return plano
    if not ctx.get("tem_livro_aluno", True):
        return plano
    if not is_1a_6a(ctx.get("classe", "")):
        return plano

    for i, row in enumerate(plano.tabela):
        meios = (row[5] or "").strip()
        if "livro do aluno" not in meios.lower():
            meios = f"{meios}; Livro do aluno" if meios and meios != "-" else "Livro do aluno"
        plano.tabela[i] = [row[0], row[1], row[2], row[3], row[4], meios]
    return plano

def apply_all_enforcers(plano: PlanoAula, ctx: dict) -> PlanoAula:
    plano = enforce_didactic_rules(plano)
    plano = enforce_livro_aluno_meios(plano, ctx)
    return plano

# =========================
# Preview Images (mantido)
# =========================
def wrap_text(draw, text, font, max_width):
    words = (text or "").split()
    lines, line = [], ""
    for w in words:
        test = (line + " " + w).strip()
        if draw.textlength(test, font=font) <= max_width:
            line = test
        else:
            if line:
                lines.append(line)
            line = w
    if line:
        lines.append(line)
    return lines

def plano_to_preview_images(ctx: dict, plano: PlanoAula) -> list[Image.Image]:
    W, H = 1240, 1754
    margin = 60
    imgs = []

    try:
        font_title = ImageFont.truetype("DejaVuSans.ttf", 36)
        font_h = ImageFont.truetype("DejaVuSans.ttf", 22)
        font_b = ImageFont.truetype("DejaVuSans.ttf", 18)
        font_s = ImageFont.truetype("DejaVuSans.ttf", 16)
    except Exception:
        font_title = ImageFont.load_default()
        font_h = ImageFont.load_default()
        font_b = ImageFont.load_default()
        font_s = ImageFont.load_default()

    def new_page():
        img = Image.new("RGB", (W, H), "white")
        return img, ImageDraw.Draw(img)

    def header(draw, y):
        draw.text((margin, y), "REPÚBLICA DE MOÇAMBIQUE", font=font_h, fill="black"); y += 30
        draw.text((margin, y), "GOVERNO DO DISTRITO DE INHASSORO", font=font_h, fill="black"); y += 30
        draw.text((margin, y), "SERVIÇO DISTRITAL DE EDUCAÇÃO, JUVENTUDE E TECNOLOGIA", font=font_h, fill="black"); y += 50
        draw.text((margin, y), "PLANO DE AULA", font=font_title, fill="black")
        return y + 60

    img, draw = new_page()
    y = header(draw, margin)

    meta = [
        f"Escola: {ctx.get('escola','')}",
        f"Data: {ctx.get('data','')}",
        f"Disciplina: {ctx.get('disciplina','')}   Classe: {ctx.get('classe','')}   Turma: {ctx.get('turma','')}",
        f"Unidade Temática: {ctx.get('unidade','')}",
        f"Tema: {ctx.get('tema','')}",
        f"Professor: {ctx.get('professor','')}   Duração: {ctx.get('duracao','')}   Tipo: {ctx.get('tipo_aula','')}",
        f"Nº de alunos: {ctx.get('nr_alunos','')}",
    ]
    for line in meta:
        for l in wrap_text(draw, line, font_b, W - 2 * margin):
            draw.text((margin, y), l, font=font_b, fill="black"); y += 24
        y += 6

    y += 10
    draw.text((margin, y), "OBJECTIVO(S) GERAL(IS):", font=font_h, fill="black"); y += 30
    ogs = [f"{i}. {x}" for i, x in enumerate(plano.objetivo_geral, 1)] if isinstance(plano.objetivo_geral, list) else [plano.objetivo_geral]
    for og in ogs:
        for l in wrap_text(draw, og, font_b, W - 2 * margin):
            draw.text((margin, y), l, font=font_b, fill="black"); y += 22
        y += 6

    y += 10
    draw.text((margin, y), "OBJECTIVOS ESPECÍFICOS:", font=font_h, fill="black"); y += 30
    for i, oe in enumerate(plano.objetivos_especificos, 1):
        text = f"{i}. {oe}"
        for l in wrap_text(draw, text, font_b, W - 2 * margin):
            draw.text((margin, y), l, font=font_b, fill="black"); y += 22
        y += 4

    imgs.append(img)

    headers = ["Tempo", "Função Didáctica", "Activ. Professor", "Activ. Aluno", "Métodos", "Meios"]
    col_w = [90, 210, 300, 300, 160, 160]
    start_x = margin
    row_h = 20

    def table_header(draw, y):
        x = start_x
        for i, htxt in enumerate(headers):
            draw.rectangle([x, y, x + col_w[i], y + 30], outline="black")
            draw.text((x + 6, y + 6), htxt, font=font_s, fill="black")
            x += col_w[i]
        return y + 30

    img, draw = new_page()
    y = header(draw, margin)
    y = table_header(draw, y)

    for row in plano.tabela:
        cells = [str(c or "-") for c in row]
        wrapped = []
        max_lines = 1
        for i, c in enumerate(cells):
            lines = wrap_text(draw, c, font_s, col_w[i] - 12)
            wrapped.append(lines)
            max_lines = max(max_lines, len(lines))
        needed_h = max(30, 8 + max_lines * row_h)

        if y + needed_h > H - margin:
            imgs.append(img)
            img, draw = new_page()
            y = header(draw, margin)
            y = table_header(draw, y)

        x = start_x
        for i, lines in enumerate(wrapped):
            draw.rectangle([x, y, x + col_w[i], y + needed_h], outline="black")
            yy = y + 6
            for ln in lines[:20]:
                draw.text((x + 6, yy), ln, font=font_s, fill="black")
                yy += row_h
            x += col_w[i]
        y += needed_h

    imgs.append(img)
    return imgs

# =========================
# PDF (mantido)
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
        self.cell(0, 10, "SDEJT Inhassoro - Processado por IA (validação final: Professor)", 0, 0, "C")

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

    pdf.cell(0, 7, f"Unidade Temática: {clean_text(ctx['unidade'])}", 0, 1)
    pdf.set_font("Arial", "B", 10)
    pdf.cell(0, 7, f"Tema: {clean_text(ctx['tema'])}", 0, 1)

    pdf.set_font("Arial", "", 10)
    pdf.cell(100, 7, f"Professor: {clean_text(ctx['professor'])}", 0, 0)
    pdf.cell(50, 7, f"Turma: {clean_text(ctx['turma'])}", 0, 0)
    pdf.cell(0, 7, f"Duração: {clean_text(ctx['duracao'])}", 0, 1)

    pdf.cell(100, 7, f"Tipo de Aula: {clean_text(ctx['tipo_aula'])}", 0, 0)
    pdf.cell(0, 7, f"Nº de alunos: {clean_text(ctx['nr_alunos'])}", 0, 1)

    pdf.line(10, pdf.get_y() + 2, 200, pdf.get_y() + 2)
    pdf.ln(5)

    pdf.set_font("Arial", "B", 10)
    pdf.cell(0, 6, "OBJECTIVO(S) GERAL(IS):", 0, 1)
    pdf.set_font("Arial", "", 10)
    if isinstance(plano.objetivo_geral, list):
        for i, og in enumerate(plano.objetivo_geral, 1):
            pdf.multi_cell(0, 6, f"{i}. {clean_text(og)}")
    else:
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
# Edit helpers
# =========================
def df_to_plano(df: pd.DataFrame, objetivo_geral, objetivos_especificos_list, ctx: dict) -> PlanoAula:
    rows = []
    for _, r in df.iterrows():
        row = [str(r.get(c, "") if r.get(c, "") is not None else "").strip() for c in TABLE_COLS]
        while len(row) < 6:
            row.append("")
        rows.append(row[:6])

    plano = PlanoAula(
        objetivo_geral=objetivo_geral,
        objetivos_especificos=[x.strip() for x in objetivos_especificos_list if x.strip()] or ["-"],
        tabela=rows,
    )
    return apply_all_enforcers(plano, ctx)

# =========================
# -------- START ----------
# =========================

# autenticação
USER_KEY = auth_gate()  # pára e pede login se não houver

# carregar user (fresh)
u0 = get_user_fresh(USER_KEY)
if not u0:
    st.error("Utilizador não encontrado no sistema.")
    st.stop()

# Admin session separada (senha)
IS_ADMIN = bool(st.session_state.get("is_admin", False))
USER_STATUS = (u0.get("status") or "trial").lower()

# topo
st.markdown("## 🇲🇿 SDEJT - Elaboração de Planos")
st.markdown("##### Serviço Distrital de Educação, Juventude e Tecnologia - Inhassoro")
st.caption(f"Professor: {u0.get('name','-')} | Escola: {u0.get('school','-')} | Estado: {USER_STATUS}")
st.divider()

# abas (Professor / Admin)
tab_prof, tab_admin = st.tabs(["📘 Professor", "🛠️ Administrador"])

# =========================
# TAB PROFESSOR
# =========================
with tab_prof:
    # Histórico
    st.subheader("📚 Meus Planos (Histórico)")
    hist = list_user_plans(USER_KEY)
    if hist.empty:
        st.info("Ainda não há planos guardados no seu histórico.")
    else:
        c1, c2, c3 = st.columns(3)
        with c1:
            classe_f = st.selectbox("Filtrar por classe", ["Todas"] + sorted(hist["classe"].astype(str).unique().tolist()))
        with c2:
            datas = sorted({str(d) for d in hist["plan_day"].dropna().tolist()})
            data_f = st.selectbox("Filtrar por data do plano", ["Todas"] + datas)
        with c3:
            ordem = st.selectbox("Ordenar", ["Mais recente", "Mais antigo"])

        dfh = hist.copy()
        if classe_f != "Todas":
            dfh = dfh[dfh["classe"].astype(str) == classe_f]
        if data_f != "Todas":
            dfh = dfh[dfh["plan_day"].astype(str) == data_f]
        dfh = dfh.sort_values("created_at", ascending=(ordem == "Mais antigo"))

        dfh["label"] = (
            dfh["plan_day"].astype(str) + " | " +
            dfh["classe"].astype(str) + " | " +
            dfh["disciplina"].astype(str) + " | " +
            dfh["tema"].astype(str)
        )

        st.dataframe(dfh[["plan_day","classe","disciplina","tema","unidade","turma","created_at"]], hide_index=True, use_container_width=True)

        sel = st.selectbox("Seleccionar um plano para baixar novamente", dfh["label"].tolist())
        plan_id = int(dfh[dfh["label"] == sel].iloc[0]["id"])
        pdf_bytes_hist = get_plan_pdf_bytes(USER_KEY, plan_id)

        if pdf_bytes_hist:
            st.download_button(
                "⬇️ Baixar PDF deste plano",
                data=pdf_bytes_hist,
                file_name=f"Plano_{sel}.pdf".replace(" ", "_").replace("|", "-"),
                mime="application/pdf",
                type="primary",
            )
        else:
            st.error("Não foi possível carregar o PDF deste plano.")

    st.divider()

    # Sidebar de contexto (como antes)
    with st.sidebar:
        st.markdown("### Contexto da Escola (Inhassoro)")
        localidade = st.text_input("Posto/Localidade", "Inhassoro (Sede)")
        tipo_escola = st.selectbox("Tipo de escola", ["EP", "EB", "ES1", "ES2", "Outra"])
        recursos = st.text_area("Recursos disponíveis", "Quadro, giz/marcador, livros, cadernos.")
        tem_livro_aluno = st.checkbox("Há livro do aluno disponível (1ª–6ª)?", value=True)
        nr_alunos = st.text_input("Nº de alunos", "40 (aprox.)")
        obs_turma = st.text_area("Observações da turma", "Turma heterogénea; alguns alunos com dificuldades de leitura/escrita.")
        st.markdown("---")
        st.success(f"Professor: {u0.get('name','-')}")
        st.info(f"Escola: {u0.get('school','-')}")
        st.caption(f"Estado: {USER_STATUS}")
        if not is_unlimited(USER_STATUS):
            st.caption(f"Limite diário: {get_today_count(USER_KEY)}/{get_daily_limit(USER_KEY)}")
        if st.button("🚪 Sair"):
            st.session_state.clear()
            st.rerun()

    # Form de plano (como antes)
    st.title("🇲🇿 Elaboração de Planos de Aulas (SNE)")

    col1, col2 = st.columns(2)
    with col1:
        escola = st.text_input("Escola", u0.get("school",""))
        professor = st.text_input("Professor", u0.get("name",""))
        disciplina = st.text_input("Disciplina", "Língua Portuguesa")
        classe = st.selectbox("Classe", ["1ª","2ª","3ª","4ª","5ª","6ª","7ª","8ª","9ª","10ª","11ª","12ª"])
        unidade = st.text_input("Unidade Temática", placeholder="Ex: Textos normativos")
        tipo_aula = st.selectbox("Tipo de Aula", ["Introdução de Matéria Nova","Consolidação e Exercitação","Verificação e Avaliação","Revisão"])

    with col2:
        duracao = st.selectbox("Duração", ["45 Min", "90 Min"])
        turma = st.text_input("Turma", "A")
        tema = st.text_input("Tema", placeholder="Ex: Vogais")
        data_plano = st.date_input("Data", value=date.today())

    missing = []
    if not unidade.strip():
        missing.append("Unidade Temática")
    if not tema.strip():
        missing.append("Tema")
    if missing:
        st.warning(f"Preencha: {', '.join(missing)}")

    if st.button("🚀 Gerar Plano de Aula", type="primary", disabled=bool(missing)):
        allowed, msg = can_generate(USER_KEY, USER_STATUS)
        if not allowed:
            st.error(msg)
            st.stop()

        with st.spinner("A processar o plano com Inteligência Artificial..."):
            try:
                genai.configure(api_key=st.secrets["GOOGLE_API_KEY"])

                ctx = {
                    "localidade": localidade.strip(),
                    "tipo_escola": tipo_escola,
                    "recursos": recursos.strip(),
                    "tem_livro_aluno": bool(tem_livro_aluno),
                    "nr_alunos": nr_alunos.strip(),
                    "obs_turma": obs_turma.strip(),
                    "escola": escola.strip(),
                    "professor": professor.strip(),
                    "disciplina": disciplina.strip(),
                    "classe": classe,
                    "unidade": unidade.strip(),
                    "tema": tema.strip(),
                    "duracao": duracao,
                    "tipo_aula": tipo_aula,
                    "turma": turma.strip(),
                    "data": data_plano.strftime("%d/%m/%Y"),
                }

                curriculum_text = get_curriculum_context(disciplina, classe, unidade, tema)
                prompt = build_prompt(ctx, curriculum_text)
                key = make_cache_key({"ctx": ctx, "curriculum": curriculum_text})

                try:
                    texto = cached_generate(key, prompt, "models/gemini-2.5-flash")
                    modelo_usado = "gemini-2.5-flash"
                except Exception:
                    texto = cached_generate(key, prompt, "models/gemini-1.5-flash")
                    modelo_usado = "gemini-1.5-flash"

                raw = safe_extract_json(texto)
                plano = apply_all_enforcers(PlanoAula(**raw), ctx)

                if not is_unlimited(USER_STATUS):
                    inc_today_count(USER_KEY)

                st.session_state["ctx"] = ctx
                st.session_state["modelo_usado"] = modelo_usado
                st.session_state["plano_base"] = plano.model_dump()
                st.session_state["plano_editado"] = plano.model_dump()
                st.session_state["editor_df"] = pd.DataFrame(plano.tabela, columns=TABLE_COLS)
                st.session_state.pop("preview_imgs", None)
                st.session_state["plano_pronto"] = True
                st.rerun()

            except ValidationError as ve:
                st.error("A resposta da IA não respeitou o formato esperado (JSON/estrutura).")
                st.code(str(ve))
                st.code(texto)
            except Exception as e:
                st.error(f"Ocorreu um erro no sistema: {e}")

    if st.session_state.get("plano_pronto"):
        st.divider()
        st.subheader("✅ Plano Gerado com Sucesso")
        st.caption(f"Modelo IA usado: {st.session_state.get('modelo_usado', '-')}")
        ctx = st.session_state["ctx"]
        plano_editado = PlanoAula(**st.session_state["plano_editado"])

        st.subheader("✍️ Edição do Plano (antes do PDF)")

        with st.expander("Editar objectivos", expanded=True):
            og_text = "\n".join(plano_editado.objetivo_geral) if isinstance(plano_editado.objetivo_geral, list) else str(plano_editado.objetivo_geral)
            og_new = st.text_area("Objectivo(s) Geral(is) (um por linha)", value=og_text, height=100)

            oe_text = "\n".join(plano_editado.objetivos_especificos)
            oe_new = st.text_area("Objectivos Específicos (um por linha)", value=oe_text, height=130)

        with st.expander("Editar tabela (actividades, métodos, meios)", expanded=True):
            df = st.session_state.get("editor_df", pd.DataFrame(plano_editado.tabela, columns=TABLE_COLS))
            edited_df = st.data_editor(df, use_container_width=True, hide_index=True, num_rows="dynamic", key="data_editor_plano")

        c_apply, c_reset = st.columns(2)
        with c_apply:
            if st.button("✅ Aplicar alterações", type="primary"):
                og_lines = [x.strip() for x in og_new.split("\n") if x.strip()]
                if "90" in ctx["duracao"]:
                    objetivo_geral = og_lines[:2] if og_lines else ["-"]
                else:
                    objetivo_geral = og_lines[0] if og_lines else "-"
                oe_lines = [x.strip() for x in oe_new.split("\n") if x.strip()] or ["-"]

                plano_novo = df_to_plano(edited_df, objetivo_geral, oe_lines, ctx)
                st.session_state["plano_editado"] = plano_novo.model_dump()
                st.session_state["editor_df"] = pd.DataFrame(plano_novo.tabela, columns=TABLE_COLS)
                st.session_state.pop("preview_imgs", None)
                st.success("Alterações aplicadas.")
                st.rerun()

        with c_reset:
            if st.button("↩️ Repor para o plano gerado pela IA"):
                base = apply_all_enforcers(PlanoAula(**st.session_state["plano_base"]), ctx)
                st.session_state["plano_editado"] = base.model_dump()
                st.session_state["editor_df"] = pd.DataFrame(base.tabela, columns=TABLE_COLS)
                st.session_state.pop("preview_imgs", None)
                st.success("Plano reposto.")
                st.rerun()

        st.divider()
        st.subheader("👁️ Pré-visualização do Plano (Imagens)")
        plano_final = PlanoAula(**st.session_state["plano_editado"])
        if "preview_imgs" not in st.session_state:
            st.session_state["preview_imgs"] = plano_to_preview_images(ctx, plano_final)
        for i, im in enumerate(st.session_state["preview_imgs"], 1):
            st.image(im, caption=f"Pré-visualização - Página {i}", use_container_width=True)

        st.divider()
        st.subheader("📄 Exportação")

        try:
            pdf_bytes = create_pdf(ctx, plano_final)

            colA, colB = st.columns(2)

            with colA:
                if st.button("💾 Guardar no histórico (Storage) e baixar", type="primary"):
                    save_plan_to_history_storage(USER_KEY, ctx, plano_final.model_dump(), pdf_bytes)
                    st.success("Plano guardado no histórico.")
                    st.download_button(
                        "⬇️ Baixar PDF agora",
                        data=pdf_bytes,
                        file_name=f"Plano_{ctx['disciplina']}_{ctx['classe']}_{ctx['tema']}.pdf".replace(" ", "_"),
                        mime="application/pdf",
                        type="primary",
                    )

            with colB:
                st.download_button(
                    "📄 Baixar PDF (sem guardar)",
                    data=pdf_bytes,
                    file_name=f"Plano_{ctx['disciplina']}_{ctx['classe']}_{ctx['tema']}.pdf".replace(" ", "_"),
                    mime="application/pdf",
                )

        except Exception as e:
            st.error(f"Erro ao criar PDF: {e}")

# =========================
# TAB ADMIN
# =========================
with tab_admin:
    if not IS_ADMIN:
        st.warning("Acesso restrito. Entre como Admin na tela de login.")
        st.stop()

    st.subheader("🛠️ Painel do Administrador")

    users = list_users_df()
    if not users.empty:
        users2 = usage_stats_users_df(users)
        st.metric("Professores registados", len(users2))
        st.metric("Planos hoje (total)", global_today_total())

        st.markdown("#### Filtros")
        status_filter = st.selectbox("Estado", ["Todos", "trial", "pending", "approved", "admin", "blocked"])
        school_filter = st.text_input("Escola (contém)", "").strip().lower()
        name_filter = st.text_input("Nome (contém)", "").strip().lower()

        filt = users2.copy()
        if status_filter != "Todos":
            filt = filt[filt["status"] == status_filter]
        if school_filter:
            filt = filt[filt["school"].astype(str).str.lower().str.contains(school_filter, na=False)]
        if name_filter:
            filt = filt[filt["name"].astype(str).str.lower().str.contains(name_filter, na=False)]

        st.dataframe(filt[["name","school","status","daily_limit","today_count","total_count"]], hide_index=True, use_container_width=True)

        st.markdown("#### Gestão de Professor")
        if len(filt) > 0:
            filt = filt.copy()
            filt["label"] = filt["name"].astype(str) + " — " + filt["school"].astype(str) + " (" + filt["status"].astype(str) + ")"
            sel_label = st.selectbox("Seleccionar", filt["label"].tolist())
            sel_row = filt[filt["label"] == sel_label].iloc[0]
            sel_user_key = sel_row["user_key"]

            new_limit = st.number_input("Limite diário (trial/pending)", min_value=0, max_value=20, value=int(sel_row.get("daily_limit",2) or 2), step=1)

            a,b = st.columns(2)
            with a:
                if st.button("Guardar limite", type="primary"):
                    set_daily_limit(sel_user_key, int(new_limit))
                    st.success("Limite actualizado.")
                    st.rerun()
            with b:
                if st.button("Reset HOJE"):
                    reset_today_count(sel_user_key)
                    st.success("Reset feito.")
                    st.rerun()

            c,d = st.columns(2)
            with c:
                if st.button("Aprovar"):
                    set_user_status(sel_user_key, "approved", approved_by="Admin")
                    st.success("Aprovado.")
                    st.rerun()
            with d:
                if st.button("Revogar"):
                    set_user_status(sel_user_key, "trial")
                    st.success("Revogado.")
                    st.rerun()

            e,f = st.columns(2)
            with e:
                if st.button("Bloquear"):
                    set_user_status(sel_user_key, "blocked")
                    st.success("Bloqueado.")
                    st.rerun()
            with f:
                if st.button("Desbloquear"):
                    set_user_status(sel_user_key, "trial")
                    st.success("Desbloqueado.")
                    st.rerun()

            st.markdown("#### Remover utilizador estranho")
            confirm_del = st.checkbox("Confirmo apagar (irreversível).")
            if st.button("Apagar utilizador", disabled=not confirm_del):
                delete_user(sel_user_key)
                st.success("Utilizador apagado.")
                st.rerun()

    st.markdown("---")
    st.markdown("### Pedidos pendentes")
    try:
        pending = list_pending_requests_df()
        if pending.empty:
            st.caption("Sem pedidos pendentes.")
        else:
            pending = pending.copy()
            pending["label"] = pending["name"].astype(str) + " — " + pending["school"].astype(str) + " (ID " + pending["id"].astype(str) + ")"
            st.dataframe(pending[["id","name","school","created_at"]], hide_index=True, use_container_width=True)
            sel_label = st.selectbox("Seleccionar pedido", pending["label"].tolist())
            sel_row = pending[pending["label"] == sel_label].iloc[0]
            sel_id = int(sel_row["id"])
            sel_user_key = sel_row["user_key"]

            x,y,z = st.columns(3)
            with x:
                if st.button("Aprovar pedido", type="primary"):
                    sb = supa()
                    sb.table("access_requests").update({"status":"approved","processed_at":datetime.now().isoformat(),"processed_by":"Admin"}).eq("id", sel_id).execute()
                    set_user_status(sel_user_key, "approved", approved_by="Admin")
                    st.success("Pedido aprovado.")
                    st.rerun()
            with y:
                if st.button("Rejeitar pedido"):
                    sb = supa()
                    sb.table("access_requests").update({"status":"rejected","processed_at":datetime.now().isoformat(),"processed_by":"Admin"}).eq("id", sel_id).execute()
                    set_user_status(sel_user_key, "trial")
                    st.success("Pedido rejeitado.")
                    st.rerun()
            with z:
                if st.button("Apagar utilizador (suspeito)"):
                    delete_user(sel_user_key)
                    st.success("Utilizador apagado.")
                    st.rerun()
    except Exception:
        st.warning("Tabela access_requests não existe/sem permissões.")

    st.markdown("---")
    st.markdown("### Biblioteca do Currículo")
    st.caption("Adicione pequenos trechos por disciplina/classe para guiar a IA com rigor.")
    try:
        disc_c = st.text_input("Disciplina (currículo)", "Língua Portuguesa")
        classe_c = st.selectbox("Classe (currículo)", ["1ª","2ª","3ª","4ª","5ª","6ª","7ª","8ª","9ª","10ª","11ª","12ª"], key="classe_curr")
        unidade_c = st.text_input("Unidade (opcional)", "")
        tema_c = st.text_input("Tema (opcional)", "")
        snippet_c = st.text_area("Snippet do currículo (curto e directo)", "")
        fonte_c = st.text_input("Fonte (opcional)", "Programa oficial / Guia do professor")

        if st.button("Adicionar snippet"):
            if not snippet_c.strip():
                st.error("Escreva o snippet.")
            else:
                add_curriculum_snippet(disc_c, classe_c, unidade_c, tema_c, snippet_c, fonte_c)
                st.success("Snippet adicionado.")
                st.rerun()

        dfcs = list_curriculum_snippets(disc_c, classe_c)
        if not dfcs.empty:
            st.dataframe(dfcs[["id","unidade","tema","snippet","fonte","created_at"]], hide_index=True, use_container_width=True)
            del_id = st.selectbox("ID para apagar snippet", dfcs["id"].tolist())
            if st.button("Apagar snippet seleccionado"):
                delete_curriculum_snippet(int(del_id))
                st.success("Snippet apagado.")
                st.rerun()
    except Exception:
        st.warning("Tabela curriculum_snippets não existe/sem permissões.")

    st.divider()
    if st.button("🚪 Sair (Admin e Professor)"):
        st.session_state.clear()
        st.rerun()
