# app.py
# =========================================================
# SDEJT - Planos SNE (Inhassoro) | Streamlit + Supabase
#
# Actualizações incluídas nesta versão:
# 1) Tipos de escola actualizados: EP, EB, ES1, ES2, Outra
# 2) Painel Admin melhorado:
#    - KPI no topo: total de professores, aprovados, pendentes, bloqueados
#    - KPI: total de planos gerados hoje (global)
#    - Tabela de professores com filtro por estado e por escola
#    - Gestão por professor: limite diário, aprovar, revogar, bloquear, desbloquear, reset contador hoje
# 3) Login: professores entram com Nome + Escola, trial/pending/approved/admin/blocked
# 4) Limite diário por professor (daily_limit) (modo trial/pending); acesso total ilimitado
# 5) Plano: Português de Moçambique, regras de presenças+TPC na 1ª função, marcar TPC na última
# 6) 1ª–6ª: "Livro do aluno" em Meios se disponível
# 7) Pré-visualização em imagens antes do PDF (fpdf 1.x)
# =========================================================

import json
import hashlib
from datetime import date, datetime, timedelta

import streamlit as st
import pandas as pd
from pydantic import BaseModel, Field, ValidationError, conlist

import google.generativeai as genai
from fpdf import FPDF
from PIL import Image, ImageDraw, ImageFont

from supabase import create_client


# =========================================================
# UI
# =========================================================
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


# =========================================================
# Supabase helpers
# =========================================================
def supa():
    if "SUPABASE_URL" not in st.secrets or "SUPABASE_SERVICE_ROLE_KEY" not in st.secrets:
        st.error("Configure SUPABASE_URL e SUPABASE_SERVICE_ROLE_KEY nos Secrets.")
        st.stop()
    return create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_SERVICE_ROLE_KEY"])


def today_iso() -> str:
    return date.today().isoformat()


def make_user_key(name: str, school: str) -> str:
    raw = (name.strip().lower() + "|" + school.strip().lower()).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def is_admin_session() -> bool:
    return st.session_state.get("is_admin", False)


def is_unlimited(status: str) -> bool:
    return status in ("approved", "admin")


def is_blocked(status: str) -> bool:
    return status == "blocked"


def get_user(user_key: str):
    sb = supa()
    r = sb.table("app_users").select("*").eq("user_key", user_key).limit(1).execute()
    return r.data[0] if r.data else None


def upsert_user(user_key: str, name: str, school: str, status: str):
    sb = supa()
    existing = get_user(user_key)
    payload = {"user_key": user_key, "name": name.strip(), "school": school.strip(), "status": status}
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
    sb = supa()
    sb.table("app_users").update({"daily_limit": int(daily_limit)}).eq("user_key", user_key).execute()


def get_daily_limit(user_key: str) -> int:
    u = get_user(user_key)
    if not u:
        return 2
    try:
        v = u.get("daily_limit", 2)
        return int(v) if v is not None else 2
    except Exception:
        return 2


def create_access_request(user_key: str, name: str, school: str):
    sb = supa()
    user = get_user(user_key)
    if user and is_blocked(user.get("status", "")):
        return "blocked"
    if user and user.get("status") in ("admin", "approved"):
        return "already_approved"

    upsert_user(user_key, name, school, "pending")
    sb.table("access_requests").insert(
        {"user_key": user_key, "name": name.strip(), "school": school.strip(), "status": "pending"}
    ).execute()
    return "ok"


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


# -------- Admin data --------
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


# =========================================================
# Access Gate UI
# =========================================================
def access_gate() -> dict:
    with st.sidebar:
        st.markdown("### Administração")
        admin_pwd = st.text_input("Senha do Administrador", type="password", key="admin_pwd")

        if st.button("Entrar como Admin"):
            if "ADMIN_PASSWORD" not in st.secrets:
                st.error("ADMIN_PASSWORD não configurada nos Secrets.")
            elif admin_pwd == st.secrets["ADMIN_PASSWORD"]:
                st.session_state["is_admin"] = True
                st.success("Sessão de Administrador activa.")
            else:
                st.error("Senha inválida.")

        if st.session_state.get("is_admin"):
            if st.button("Sair do Admin"):
                st.session_state["is_admin"] = False
                st.session_state.pop("admin_pwd", None)
                st.rerun()

    st.markdown("## 🇲🇿 SDEJT - Elaboração de Planos")
    st.markdown("##### Serviço Distrital de Educação, Juventude e Tecnologia - Inhassoro")
    st.divider()

    col1, col2 = st.columns([1.2, 0.8])

    with col1:
        st.info("👤 Identificação do Professor (obrigatório)")
        name = st.text_input("Nome do Professor", key="prof_name").strip()
        school = st.text_input("Escola onde lecciona", key="prof_school").strip()

        if not name or not school:
            st.warning("Introduza o seu nome e a escola onde lecciona para continuar.")
            st.stop()

        user_key = make_user_key(name, school)
        user = get_user(user_key)

        if user is None:
            upsert_user(user_key, name, school, "trial")
            user = get_user(user_key)

        status = user["status"]

        # Se admin, marca o próprio como admin (ilimitado)
        if is_admin_session():
            if status != "admin":
                upsert_user(user_key, name, school, "admin")
                status = "admin"

        if is_blocked(status):
            st.error("O seu acesso está bloqueado. Contacte o Administrador.")
            st.stop()

        limit = get_daily_limit(user_key)
        used = get_today_count(user_key)

        if status == "trial":
            st.success(f"Acesso de teste activo. Hoje: **{used}/{limit}** planos.")
        elif status == "pending":
            st.warning("Pedido de acesso total em análise.")
            st.info(f"Hoje: **{used}/{limit}** planos.")
        else:
            st.success("Acesso total activo (ilimitado).")

        if status in ("trial", "pending"):
            st.markdown("### Acesso Total")
            st.write("Para ter acesso total e ilimitado, envie o pedido ao Administrador.")
            if st.button("📝 Solicitar Acesso Total", type="primary"):
                res = create_access_request(user_key, name, school)
                if res == "blocked":
                    st.error("O seu acesso está bloqueado. Não é possível submeter pedido.")
                elif res == "already_approved":
                    st.info("Já tem acesso total.")
                else:
                    st.success("Pedido enviado. O Administrador será notificado por WhatsApp (via Supabase).")
                st.rerun()

    with col2:
        st.warning("ℹ️ Ajuda")
        st.write("O limite diário pode ser ajustado pelo Administrador.")
        st.write("Depois de aprovado, o acesso é ilimitado.")

    return {"user_key": user_key, "name": name, "school": school, "status": status, "is_admin": is_admin_session()}


# =========================================================
# Plano model (JSON)
# =========================================================
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


def make_cache_key(payload: dict) -> str:
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


@st.cache_data(ttl=86400)
def cached_generate(key: str, prompt: str, model_name: str) -> str:
    model = genai.GenerativeModel(model_name)
    resp = model.generate_content(prompt)
    return resp.text


def build_prompt(ctx: dict) -> str:
    return f"""
És Pedagogo(a) Especialista do Sistema Nacional de Educação (SNE) de Moçambique.
Escreve SEMPRE em Português de Moçambique. Evita termos e ortografia do Brasil.

O plano deve reflectir a realidade do Distrito de Inhassoro, Província de Inhambane, Moçambique.

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


# =========================================================
# Enforcers
# =========================================================
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


# =========================================================
# Preview PNG
# =========================================================
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

    # Página 1
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

    # Tabela
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


# =========================================================
# PDF (fpdf 1.x)
# =========================================================
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


# =========================================================
# Edit helpers
# =========================================================
def plano_to_df(plano: PlanoAula) -> pd.DataFrame:
    return pd.DataFrame(plano.tabela, columns=TABLE_COLS)


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


# =========================================================
# START
# =========================================================
if "GOOGLE_API_KEY" not in st.secrets:
    st.error("Configure GOOGLE_API_KEY nos Secrets.")
    st.stop()
if "ADMIN_PASSWORD" not in st.secrets:
    st.error("Configure ADMIN_PASSWORD nos Secrets.")
    st.stop()

access = access_gate()
USER_KEY = access["user_key"]
USER_STATUS = access["status"]
IS_ADMIN = access["is_admin"]


# =========================================================
# ADMIN KPI + FILTROS + GESTÃO (sidebar)
# =========================================================
if IS_ADMIN:
    with st.sidebar:
        st.markdown("---")
        st.markdown("### Painel do Administrador")

        users = list_users_df()
        if users.empty:
            st.info("Ainda não há professores registados.")
        else:
            users2 = usage_stats_users_df(users)

            # KPIs topo
            total_teachers = len(users2)
            approved_n = int((users2["status"] == "approved").sum()) + int((users2["status"] == "admin").sum())
            pending_n = int((users2["status"] == "pending").sum())
            blocked_n = int((users2["status"] == "blocked").sum())
            today_total = global_today_total()

            st.metric("Professores registados", total_teachers)
            c1, c2 = st.columns(2)
            with c1:
                st.metric("Acesso total", approved_n)
                st.metric("Bloqueados", blocked_n)
            with c2:
                st.metric("Pendentes", pending_n)
                st.metric("Planos hoje (total)", today_total)

            st.markdown("---")

            # Filtros
            st.markdown("#### Filtros")
            status_filter = st.selectbox("Estado", ["Todos", "trial", "pending", "approved", "admin", "blocked"], key="f_status")
            school_filter = st.text_input("Escola (contém)", value="", key="f_school").strip().lower()

            filt = users2.copy()
            if status_filter != "Todos":
                filt = filt[filt["status"] == status_filter]
            if school_filter:
                filt = filt[filt["school"].astype(str).str.lower().str.contains(school_filter, na=False)]

            # Tabela resumida no sidebar (top 15)
            show_cols = ["name", "school", "status", "daily_limit", "today_count", "total_count"]
            st.dataframe(filt[show_cols].head(15), hide_index=True, use_container_width=True)

            st.markdown("---")
            st.markdown("#### Gestão de Professor")

            filt["label"] = (
                filt["name"].astype(str)
                + " — "
                + filt["school"].astype(str)
                + " ("
                + filt["status"].astype(str)
                + ")"
            )

            if len(filt) == 0:
                st.info("Sem resultados nos filtros.")
            else:
                sel_label = st.selectbox("Seleccionar", filt["label"].tolist(), key="sel_prof")
                sel_row = filt[filt["label"] == sel_label].iloc[0]
                sel_user_key = sel_row["user_key"]

                st.write(
                    f"**Hoje:** {int(sel_row['today_count'])} | **Total:** {int(sel_row['total_count'])}"
                )

                current_limit = int(sel_row.get("daily_limit", 2) or 2)
                new_limit = st.number_input(
                    "Limite diário (trial/pending)",
                    min_value=0,
                    max_value=20,
                    value=current_limit,
                    step=1,
                    key="limit_input",
                )

                colA, colB = st.columns(2)
                with colA:
                    if st.button("💾 Guardar limite", type="primary", key="save_limit"):
                        set_daily_limit(sel_user_key, int(new_limit))
                        st.success("Limite actualizado.")
                        st.rerun()
                with colB:
                    if st.button("🧹 Reset HOJE", key="reset_today"):
                        reset_today_count(sel_user_key)
                        st.success("Contador de hoje resetado.")
                        st.rerun()

                colC, colD = st.columns(2)
                with colC:
                    if st.button("✅ Aprovar", key="approve_user"):
                        set_user_status(sel_user_key, "approved", approved_by=access["name"])
                        st.success("Acesso total concedido.")
                        st.rerun()
                with colD:
                    if st.button("↩️ Revogar", key="revoke_user"):
                        set_user_status(sel_user_key, "trial")
                        st.success("Acesso revogado (trial).")
                        st.rerun()

                colE, colF = st.columns(2)
                with colE:
                    if st.button("⛔ Bloquear", key="block_user"):
                        set_user_status(sel_user_key, "blocked")
                        st.success("Professor bloqueado.")
                        st.rerun()
                with colF:
                    if st.button("✅ Desbloquear", key="unblock_user"):
                        set_user_status(sel_user_key, "trial")
                        st.success("Professor desbloqueado (trial).")
                        st.rerun()

        # Pedidos pendentes (rápido)
        st.markdown("---")
        st.markdown("### Pedidos pendentes")
        pending = list_pending_requests_df()
        if pending.empty:
            st.caption("Sem pedidos.")
        else:
            st.dataframe(pending, hide_index=True, use_container_width=True)
            sel_id = st.selectbox("ID do pedido", pending["id"].tolist(), key="req_id_sidebar")
            cX, cY = st.columns(2)
            with cX:
                if st.button("✅ Aprovar pedido", type="primary", key="approve_req_sidebar"):
                    sb = supa()
                    req = sb.table("access_requests").select("*").eq("id", sel_id).limit(1).execute().data[0]
                    sb.table("access_requests").update(
                        {"status": "approved", "processed_at": datetime.now().isoformat(), "processed_by": access["name"]}
                    ).eq("id", sel_id).execute()
                    set_user_status(req["user_key"], "approved", approved_by=access["name"])
                    st.success("Pedido aprovado.")
                    st.rerun()
            with cY:
                if st.button("❌ Rejeitar pedido", key="reject_req_sidebar"):
                    sb = supa()
                    sb.table("access_requests").update(
                        {"status": "rejected", "processed_at": datetime.now().isoformat(), "processed_by": access["name"]}
                    ).eq("id", sel_id).execute()
                    st.success("Pedido rejeitado.")
                    st.rerun()


# =========================================================
# APP PRINCIPAL
# =========================================================
st.title("🇲🇿 Elaboração de Planos de Aulas (SNE)")

with st.sidebar:
    st.markdown("---")
    st.markdown("### Contexto da Escola (Inhassoro)")
    localidade = st.text_input("Posto/Localidade", "Inhassoro (Sede)")

    # TIPOS DE ESCOLA ACTUALIZADOS
    tipo_escola = st.selectbox("Tipo de escola", ["EP", "EB", "ES1", "ES2", "Outra"])

    recursos = st.text_area("Recursos disponíveis", "Quadro, giz/marcador, livros, cadernos.")
    tem_livro_aluno = st.checkbox("Há livro do aluno disponível (1ª–6ª)?", value=True)
    nr_alunos = st.text_input("Nº de alunos", "40 (aprox.)")
    obs_turma = st.text_area("Observações da turma", "Turma heterogénea; alguns alunos com dificuldades de leitura/escrita.")
    st.markdown("---")
    st.success(f"Professor: {access['name']}")
    st.info(f"Escola: {access['school']}")
    st.caption(f"Estado: {USER_STATUS}")

    limit = get_daily_limit(USER_KEY)
    if not is_unlimited(USER_STATUS):
        st.caption(f"Limite diário actual: {get_today_count(USER_KEY)}/{limit}")

col1, col2 = st.columns(2)
with col1:
    escola = st.text_input("Escola", access["school"])
    professor = st.text_input("Professor", access["name"])
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


# =========================================================
# GERAR
# =========================================================
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

            prompt = build_prompt(ctx)
            key = make_cache_key({"ctx": ctx})

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


# =========================================================
# RESULTADO + EDIÇÃO + PREVIEW + PDF
# =========================================================
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

            try:
                plano_novo = df_to_plano(edited_df, objetivo_geral, oe_lines, ctx)
                st.session_state["plano_editado"] = plano_novo.model_dump()
                st.session_state["editor_df"] = pd.DataFrame(plano_novo.tabela, columns=TABLE_COLS)
                st.session_state.pop("preview_imgs", None)
                st.success("Alterações aplicadas. Pré-visualização e PDF actualizados.")
                st.rerun()
            except Exception as e:
                st.error(f"Não foi possível aplicar as alterações: {e}")

    with c_reset:
        if st.button("↩️ Repor para o plano gerado pela IA"):
            base = apply_all_enforcers(PlanoAula(**st.session_state["plano_base"]), ctx)
            st.session_state["plano_editado"] = base.model_dump()
            st.session_state["editor_df"] = pd.DataFrame(base.tabela, columns=TABLE_COLS)
            st.session_state.pop("preview_imgs", None)
            st.success("Plano reposto para a versão original.")
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
        st.download_button(
            "📄 Baixar PDF Oficial",
            data=pdf_bytes,
            file_name=f"Plano_{ctx['disciplina']}_{ctx['classe']}_{ctx['tema']}.pdf".replace(" ", "_"),
            mime="application/pdf",
            type="primary",
        )
    except Exception as e:
        st.error(f"Erro ao criar PDF: {e}")
