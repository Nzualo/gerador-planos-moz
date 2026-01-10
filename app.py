# app.py
# =========================================================
# SDEJT - Planos SNE (Inhassoro) | Streamlit
# BASE: fpdf (1.x) - estável no Streamlit Community Cloud
#
# ACESSO (novo):
# - Qualquer professor com link: Acesso de teste (2 planos/dia)
# - Solicitar acesso total: Nome + Escola -> fica PENDENTE
# - Admin aprova (painel admin) -> professor vira ACESSO TOTAL (ilimitado)
# - Admin tem acesso total/ilimitado
#
# Inclui:
# - Regras obrigatórias na 1ª e última função didáctica + enforcer
# - Pré-visualização em imagens (PNG) antes do PDF
# - Edição do plano antes do PDF
# =========================================================

import json
import time
import hashlib
import sqlite3
from datetime import date, datetime
from pathlib import Path

import streamlit as st
import pandas as pd
from pydantic import BaseModel, Field, ValidationError, conlist

import google.generativeai as genai
from fpdf import FPDF  # fpdf 1.x

from PIL import Image, ImageDraw, ImageFont


# =========================================================
# CONFIG UI
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
# DB (SQLite) - pedidos e limites
# =========================================================
DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)
DB_PATH = DATA_DIR / "sdejt_access.db"


def db_conn():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL;")
    return conn


def db_init():
    conn = db_conn()
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            user_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            school TEXT NOT NULL,
            status TEXT NOT NULL,       -- trial | pending | approved | admin
            created_at TEXT NOT NULL,
            approved_at TEXT,
            approved_by TEXT
        );
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS usage (
            user_id TEXT NOT NULL,
            day TEXT NOT NULL,          -- YYYY-MM-DD
            count INTEGER NOT NULL,
            PRIMARY KEY(user_id, day)
        );
        """
    )
    conn.commit()
    conn.close()


db_init()


def make_user_id(name: str, school: str) -> str:
    raw = (name.strip().lower() + "|" + school.strip().lower()).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def get_user(user_id: str):
    conn = db_conn()
    cur = conn.cursor()
    cur.execute("SELECT user_id, name, school, status, created_at, approved_at, approved_by FROM users WHERE user_id = ?", (user_id,))
    row = cur.fetchone()
    conn.close()
    return row


def upsert_user(user_id: str, name: str, school: str, status: str):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn = db_conn()
    cur = conn.cursor()
    existing = get_user(user_id)
    if existing is None:
        cur.execute(
            """
            INSERT INTO users (user_id, name, school, status, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (user_id, name.strip(), school.strip(), status, now),
        )
    else:
        # mantém created_at; actualiza nome/escola se necessário
        cur.execute(
            """
            UPDATE users
            SET name = ?, school = ?, status = ?
            WHERE user_id = ?
            """,
            (name.strip(), school.strip(), status, user_id),
        )
    conn.commit()
    conn.close()


def set_user_status(user_id: str, status: str, approved_by: str | None = None):
    conn = db_conn()
    cur = conn.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    if status == "approved":
        cur.execute(
            """
            UPDATE users
            SET status = ?, approved_at = ?, approved_by = ?
            WHERE user_id = ?
            """,
            (status, now, approved_by, user_id),
        )
    else:
        cur.execute("UPDATE users SET status = ? WHERE user_id = ?", (status, user_id))
    conn.commit()
    conn.close()


def list_pending_requests():
    conn = db_conn()
    df = pd.read_sql_query(
        "SELECT user_id, name, school, status, created_at FROM users WHERE status = 'pending' ORDER BY created_at DESC",
        conn,
    )
    conn.close()
    return df


def list_approved_users():
    conn = db_conn()
    df = pd.read_sql_query(
        "SELECT user_id, name, school, status, created_at, approved_at, approved_by FROM users WHERE status IN ('approved','admin') ORDER BY approved_at DESC",
        conn,
    )
    conn.close()
    return df


def get_today_count(user_id: str) -> int:
    today = date.today().isoformat()
    conn = db_conn()
    cur = conn.cursor()
    cur.execute("SELECT count FROM usage WHERE user_id = ? AND day = ?", (user_id, today))
    row = cur.fetchone()
    conn.close()
    return int(row[0]) if row else 0


def inc_today_count(user_id: str):
    today = date.today().isoformat()
    conn = db_conn()
    cur = conn.cursor()
    cur.execute("SELECT count FROM usage WHERE user_id = ? AND day = ?", (user_id, today))
    row = cur.fetchone()
    if row:
        cur.execute("UPDATE usage SET count = ? WHERE user_id = ? AND day = ?", (int(row[0]) + 1, user_id, today))
    else:
        cur.execute("INSERT INTO usage (user_id, day, count) VALUES (?, ?, ?)", (user_id, today, 1))
    conn.commit()
    conn.close()


def is_admin_session() -> bool:
    return st.session_state.get("is_admin", False)


def is_unlimited_access(user_status: str) -> bool:
    return user_status in ("approved", "admin")


TRIAL_LIMIT_PER_DAY = 2


def can_generate_plan(user_id: str, status: str) -> tuple[bool, str]:
    if is_unlimited_access(status):
        return True, ""
    used = get_today_count(user_id)
    if used >= TRIAL_LIMIT_PER_DAY:
        return False, f"Limite de teste atingido: {TRIAL_LIMIT_PER_DAY} planos por dia. Solicite acesso total."
    return True, ""


# =========================================================
# LOGIN/ACESSO (novo)
# =========================================================
def access_gate() -> dict:
    """
    Retorna dict com:
    - user_id, name, school, status
    - is_admin
    """
    # Admin login pequeno no sidebar
    with st.sidebar:
        st.markdown("### Administração")
        admin_pwd = st.text_input("Senha do Administrador", type="password", key="admin_pwd")
        if st.button("Entrar como Admin", key="admin_login_btn"):
            if "ADMIN_PASSWORD" not in st.secrets:
                st.error("ADMIN_PASSWORD não configurada nos Secrets.")
            elif admin_pwd == st.secrets["ADMIN_PASSWORD"]:
                st.session_state["is_admin"] = True
                st.success("Sessão de Administrador activa.")
            else:
                st.error("Senha de administrador inválida.")

        if st.session_state.get("is_admin"):
            if st.button("Sair do Admin", key="admin_logout_btn"):
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

        user_id = make_user_id(name, school)

        # cria utilizador se não existir (trial)
        row = get_user(user_id)
        if row is None:
            upsert_user(user_id, name, school, "trial")
            row = get_user(user_id)

        status = row[3]  # status

        # Se for admin, garantir status admin no registo (para ficar ilimitado)
        if is_admin_session():
            if status != "admin":
                upsert_user(user_id, name, school, "admin")
                status = "admin"

        # Painel rápido do estado
        if status == "trial":
            used = get_today_count(user_id)
            st.success(f"Acesso de teste activo. Já gerou **{used}/{TRIAL_LIMIT_PER_DAY}** planos hoje.")
        elif status == "pending":
            st.warning("Pedido de acesso total em análise pelo Administrador. Enquanto isso, mantém-se o limite de teste.")
            used = get_today_count(user_id)
            st.info(f"Hoje: **{used}/{TRIAL_LIMIT_PER_DAY}** planos usados.")
        elif status in ("approved", "admin"):
            st.success("Acesso total activo (ilimitado).")

        # Botão de solicitar acesso total
        if status in ("trial", "pending"):
            st.markdown("### Acesso Total")
            st.write("Para ter acesso total e ilimitado, envie o pedido ao Administrador.")
            if st.button("📝 Solicitar Acesso Total", type="primary", key="request_full_access"):
                # marca como pendente
                upsert_user(user_id, name, school, "pending")
                st.success("Pedido enviado. Aguarde aprovação do Administrador.")
                st.rerun()

    with col2:
        st.warning("ℹ️ Ajuda")
        st.write(
            "No modo de teste pode gerar até **2 planos por dia**. "
            "Depois de aprovado pelo Administrador, o acesso é **ilimitado**."
        )
        st.write("Para suporte: contacte o Administrador do SDEJT.")

    return {"user_id": user_id, "name": name, "school": school, "status": status, "is_admin": is_admin_session()}


# =========================================================
# MODELO (JSON STRICT)
# =========================================================
class PlanoAula(BaseModel):
    objetivo_geral: str | list[str]
    objetivos_especificos: list[str] = Field(min_length=1)
    tabela: list[conlist(str, min_length=6, max_length=6)]


TABLE_COLS = [
    "Tempo",
    "Função Didáctica",
    "Actividade do Professor",
    "Actividade do Aluno",
    "Métodos",
    "Meios",
]


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
Escreve SEMPRE em Português de Moçambique. Evita termos e ortografia do Brasil (não usar "você", "ônibus", "trem", "a gente" informal).

O plano deve reflectir a realidade do Distrito de Inhassoro, Província de Inhambane, Moçambique.

CONTEXTO LOCAL (obrigatório):
- Distrito: Inhassoro
- Posto/Localidade: {ctx["localidade"]}
- Tipo de escola: {ctx["tipo_escola"]}
- Recursos disponíveis: {ctx["recursos"]}
- Nº de alunos: {ctx["nr_alunos"]}
- Observações da turma: {ctx["obs_turma"]}

REGRAS RIGOROSAS:
1) Devolve APENAS JSON válido (sem texto antes/depois).
2) Campos obrigatórios: "objetivo_geral", "objetivos_especificos", "tabela".
3) Tabela com EXACTAMENTE 6 colunas nesta ordem:
   ["tempo","funcao_didatica","actividade_professor","actividade_aluno","metodos","meios"]
4) Funções didácticas obrigatórias e na ordem:
   - Introdução e Motivação
   - Mediação e Assimilação
   - Domínio e Consolidação
   - Controlo e Avaliação
5) Actividades detalhadas, participativas e realistas, alinhadas ao SNE e aos programas de ensino.
6) Não inventar meios fora dos recursos listados.
7) Contextualizar o tema com exemplos do quotidiano de Inhassoro sempre que possível.
8) Respeitar o tempo total ({ctx["duracao"]}).

REGRAS ESPECIAIS (OBRIGATÓRIO):
A) Na FUNÇÃO 1 (Introdução e Motivação), o professor DEVE:
   - fazer o controlo de presenças (chamada) e registar ausências;
   - orientar a correcção do TPC (caso haja), com participação dos alunos.
B) Na FUNÇÃO 4 (Controlo e Avaliação), o professor DEVE:
   - verificar a aprendizagem com perguntas/exercícios curtos e correcção orientada;
   - marcar/atribuir o TPC, explicando a tarefa e critérios (o que fazer em casa).

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

QUANTIDADES:
- 45 Min: 1 objectivo geral e até 3 específicos.
- 90 Min: 2 objectivos gerais (lista com 2 itens) e até 5 específicos.

FORMATO JSON:
{{
  "objetivo_geral": "...." OU ["....","...."],
  "objetivos_especificos": ["....", "..."],
  "tabela": [
    ["5", "Introdução e Motivação", "...", "...", "...", "..."],
    ["20", "Mediação e Assimilação", "...", "...", "...", "..."],
    ["15", "Domínio e Consolidação", "...", "...", "...", "..."],
    ["5", "Controlo e Avaliação", "...", "...", "...", "..."]
  ]
}}
""".strip()


# =========================================================
# ENFORCER (regras obrigatórias)
# =========================================================
def contains_any(text: str, terms: list[str]) -> bool:
    t = (text or "").lower()
    return any(term.lower() in t for term in terms)


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
        row = plano.tabela[i]
        if (row[1] or "").strip().lower() == "controlo e avaliação":
            controlo_idx = i
            break

    if intro_idx is not None:
        row = plano.tabela[intro_idx]
        prof = row[2] or ""
        aluno = row[3] or ""

        if not contains_any(prof, ["chamada", "presen", "controlo de presen"]):
            prof = (prof + " " if prof else "") + "Faz o controlo de presenças (chamada), regista ausências e organiza a turma."
        if not contains_any(aluno, ["respond", "presen", "confirm"]):
            aluno = (aluno + " " if aluno else "") + "Respondem à chamada e confirmam presenças; organizam-se para a aula."

        if not contains_any(prof, ["tpc", "trabalho para casa", "correc"]):
            prof = (prof + " " if prof else "") + "Orienta a correcção do TPC (se houver): pede respostas, corrige no quadro e esclarece dúvidas."
        if not contains_any(aluno, ["tpc", "trabalho para casa", "corrig"]):
            aluno = (aluno + " " if aluno else "") + "Apresentam o TPC, comparam respostas e corrigem no caderno com orientação do professor."

        plano.tabela[intro_idx] = [row[0], row[1], prof, aluno, row[4], row[5]]

    if controlo_idx is not None:
        row = plano.tabela[controlo_idx]
        prof = row[2] or ""
        aluno = row[3] or ""

        if not contains_any(prof, ["marc", "atrib", "tpc", "trabalho para casa"]):
            prof = (prof + " " if prof else "") + "Marca o TPC: explica a tarefa, como fazer, critérios e prazo de entrega."
        if not contains_any(aluno, ["anot", "tpc", "regist"]):
            aluno = (aluno + " " if aluno else "") + "Anotam o TPC no caderno, colocam dúvidas e confirmam o que deve ser feito."

        plano.tabela[controlo_idx] = [row[0], row[1], prof, aluno, row[4], row[5]]

    return plano


# =========================================================
# PREVIEW IMAGES (PNG)
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
    W, H = 1240, 1754  # A4 ~150dpi
    margin = 60
    img_list = []

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
        draw = ImageDraw.Draw(img)
        return img, draw

    def header(draw, y):
        draw.text((margin, y), "REPÚBLICA DE MOÇAMBIQUE", font=font_h, fill="black")
        y += 30
        draw.text((margin, y), "GOVERNO DO DISTRITO DE INHASSORO", font=font_h, fill="black")
        y += 30
        draw.text((margin, y), "SERVIÇO DISTRITAL DE EDUCAÇÃO, JUVENTUDE E TECNOLOGIA", font=font_h, fill="black")
        y += 50
        draw.text((margin, y), "PLANO DE AULA", font=font_title, fill="black")
        return y + 60

    # Página 1: metadados + objectivos
    img, draw = new_page()
    y = margin
    y = header(draw, y)

    meta_lines = [
        f"Escola: {ctx.get('escola','')}",
        f"Data: {ctx.get('data','')}",
        f"Disciplina: {ctx.get('disciplina','')}   Classe: {ctx.get('classe','')}   Turma: {ctx.get('turma','')}",
        f"Unidade Temática: {ctx.get('unidade','')}",
        f"Tema: {ctx.get('tema','')}",
        f"Professor: {ctx.get('professor','')}   Duração: {ctx.get('duracao','')}   Tipo: {ctx.get('tipo_aula','')}",
        f"Nº de alunos: {ctx.get('nr_alunos','')}",
    ]
    for line in meta_lines:
        for l in wrap_text(draw, line, font_b, W - 2 * margin):
            draw.text((margin, y), l, font=font_b, fill="black")
            y += 24
        y += 6

    y += 10
    draw.text((margin, y), "OBJECTIVO(S) GERAL(IS):", font=font_h, fill="black")
    y += 30

    if isinstance(plano.objetivo_geral, list):
        ogs = [f"{i}. {x}" for i, x in enumerate(plano.objetivo_geral, 1)]
    else:
        ogs = [plano.objetivo_geral]

    for og in ogs:
        for l in wrap_text(draw, og, font_b, W - 2 * margin):
            draw.text((margin, y), l, font=font_b, fill="black")
            y += 22
        y += 6

    y += 10
    draw.text((margin, y), "OBJECTIVOS ESPECÍFICOS:", font=font_h, fill="black")
    y += 30

    for i, oe in enumerate(plano.objetivos_especificos, 1):
        text = f"{i}. {oe}"
        for l in wrap_text(draw, text, font_b, W - 2 * margin):
            draw.text((margin, y), l, font=font_b, fill="black")
            y += 22
        y += 4

    img_list.append(img)

    # Tabela
    headers = ["Tempo", "Função Didáctica", "Activ. Professor", "Activ. Aluno", "Métodos", "Meios"]
    col_w = [90, 210, 300, 300, 160, 160]  # total 1220
    start_x = margin
    row_h = 20

    def draw_table_header(draw, y):
        x = start_x
        for i, htxt in enumerate(headers):
            draw.rectangle([x, y, x + col_w[i], y + 30], outline="black")
            draw.text((x + 6, y + 6), htxt, font=font_s, fill="black")
            x += col_w[i]
        return y + 30

    img, draw = new_page()
    y = margin
    y = header(draw, y)
    y = draw_table_header(draw, y)

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
            img_list.append(img)
            img, draw = new_page()
            y = margin
            y = header(draw, y)
            y = draw_table_header(draw, y)

        x = start_x
        for i, lines in enumerate(wrapped):
            draw.rectangle([x, y, x + col_w[i], y + needed_h], outline="black")
            yy = y + 6
            for ln in lines[:20]:
                draw.text((x + 6, yy), ln, font=font_s, fill="black")
                yy += row_h
            x += col_w[i]
        y += needed_h

    img_list.append(img)
    return img_list


# =========================================================
# PDF (fpdf 1.x)
# =========================================================
def clean_text(text) -> str:
    if text is None:
        return "-"
    t = str(text).strip()
    replacements = {
        "–": "-",
        "—": "-",
        "“": '"',
        "”": '"',
        "‘": "'",
        "’": "'",
        "…": "...",
        "•": "-",
    }
    for k, v in replacements.items():
        t = t.replace(k, v)
    t = " ".join(t.replace("\r", " ").replace("\n", " ").split())
    return t


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

    widths = [12, 32, 52, 52, 21, 21]  # A4
    pdf.draw_table_header(widths)
    for row in plano.tabela:
        pdf.table_row(row, widths)

    return pdf.output(dest="S").encode("latin-1", "replace")


# =========================================================
# EDIT HELPERS
# =========================================================
def plano_to_df(plano: PlanoAula) -> pd.DataFrame:
    return pd.DataFrame(plano.tabela, columns=TABLE_COLS)


def df_to_plano(df: pd.DataFrame, objetivo_geral, objetivos_especificos_list) -> PlanoAula:
    rows = []
    for _, r in df.iterrows():
        row = [str(r.get(c, "") if r.get(c, "") is not None else "").strip() for c in TABLE_COLS]
        while len(row) < 6:
            row.append("")
        rows.append(row[:6])

    plano = PlanoAula(
        objetivo_geral=objetivo_geral,
        objetivos_especificos=[x.strip() for x in objetivos_especificos_list if x.strip()],
        tabela=rows,
    )
    return enforce_didactic_rules(plano)


# =========================================================
# APP START: ACCESS GATE
# =========================================================
if "GOOGLE_API_KEY" not in st.secrets:
    st.error("⚠️ ERRO: Configure GOOGLE_API_KEY nos Secrets!")
    st.stop()
if "ADMIN_PASSWORD" not in st.secrets:
    st.error("⚠️ ERRO: Configure ADMIN_PASSWORD nos Secrets!")
    st.stop()

access = access_gate()  # name+school obrigatório
USER_ID = access["user_id"]
USER_STATUS = access["status"]
IS_ADMIN = access["is_admin"]

# =========================================================
# ADMIN PANEL
# =========================================================
if IS_ADMIN:
    with st.sidebar:
        st.markdown("---")
        st.markdown("### Painel do Administrador")
        tab1, tab2 = st.tabs(["Pedidos Pendentes", "Utilizadores Aprovados"])

        with tab1:
            pending = list_pending_requests()
            if pending.empty:
                st.info("Sem pedidos pendentes.")
            else:
                st.dataframe(pending, hide_index=True, use_container_width=True)
                st.caption("Seleccione um pedido e aprove.")

                sel = st.selectbox(
                    "Seleccionar pedido (user_id)",
                    options=pending["user_id"].tolist(),
                    index=0,
                    key="pending_select",
                )
                if st.button("✅ Aprovar Acesso Total", key="approve_btn", type="primary"):
                    set_user_status(sel, "approved", approved_by=access["name"])
                    st.success("Acesso total aprovado.")
                    st.rerun()

        with tab2:
            approved = list_approved_users()
            if approved.empty:
                st.info("Ainda não há utilizadores aprovados.")
            else:
                st.dataframe(approved, hide_index=True, use_container_width=True)


# =========================================================
# MAIN APP UI
# =========================================================
st.title("🇲🇿 Elaboração de Planos de Aulas (SNE)")

with st.sidebar:
    st.markdown("---")
    st.markdown("### Contexto da Escola (Inhassoro)")
    localidade = st.text_input("Posto/Localidade", "Inhassoro (Sede)")
    tipo_escola = st.selectbox("Tipo de escola", ["EPC", "ESG1", "ESG2", "Outra"])
    recursos = st.text_area("Recursos disponíveis", "Quadro, giz/marcador, livros, cadernos.")
    nr_alunos = st.text_input("Nº de alunos", "40 (aprox.)")
    obs_turma = st.text_area(
        "Observações da turma",
        "Turma heterogénea; alguns alunos com dificuldades de leitura/escrita.",
    )
    st.markdown("---")
    st.success(f"Professor: {access['name']}")
    st.info(f"Escola: {access['school']}")
    st.caption(f"Estado: {USER_STATUS}")

col1, col2 = st.columns(2)
with col1:
    escola = st.text_input("Escola", access["school"])
    professor = st.text_input("Professor", access["name"])
    disciplina = st.text_input("Disciplina", "Língua Portuguesa")
    classe = st.selectbox(
        "Classe",
        ["1ª", "2ª", "3ª", "4ª", "5ª", "6ª", "7ª", "8ª", "9ª", "10ª", "11ª", "12ª"],
    )
    unidade = st.text_input("Unidade Temática", placeholder="Ex: Textos normativos")
    tipo_aula = st.selectbox(
        "Tipo de Aula",
        ["Introdução de Matéria Nova", "Consolidação e Exercitação", "Verificação e Avaliação", "Revisão"],
    )

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
# GENERATE
# =========================================================
if st.button("🚀 Gerar Plano de Aula", type="primary", disabled=bool(missing)):
    allowed, msg = can_generate_plan(USER_ID, USER_STATUS)
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
            plano = PlanoAula(**raw)
            plano = enforce_didactic_rules(plano)

            # Contabiliza uso APENAS se não for ilimitado
            if not is_unlimited_access(USER_STATUS):
                inc_today_count(USER_ID)

            # salvar base e editável
            st.session_state["ctx"] = ctx
            st.session_state["modelo_usado"] = modelo_usado
            st.session_state["plano_base"] = plano.model_dump()
            st.session_state["plano_editado"] = plano.model_dump()
            st.session_state["editor_df"] = plano_to_df(plano)

            # invalida previews
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

    # EDIÇÃO
    st.subheader("✍️ Edição do Plano (antes do PDF)")

    with st.expander("Editar objectivos", expanded=True):
        if isinstance(plano_editado.objetivo_geral, list):
            og_text = "\n".join(plano_editado.objetivo_geral)
            og_mode = "2 objectivos (90 Min)"
        else:
            og_text = str(plano_editado.objetivo_geral)
            og_mode = "1 objectivo (45 Min)"

        st.caption(f"Modo detectado: {og_mode}. Pode editar livremente.")
        og_new = st.text_area("Objectivo(s) Geral(is) (um por linha)", value=og_text, height=100)

        oe_text = "\n".join(plano_editado.objetivos_especificos)
        oe_new = st.text_area("Objectivos Específicos (um por linha)", value=oe_text, height=130)

    with st.expander("Editar tabela (actividades, métodos, meios)", expanded=True):
        df = st.session_state.get("editor_df", plano_to_df(plano_editado))
        edited_df = st.data_editor(
            df,
            use_container_width=True,
            hide_index=True,
            num_rows="dynamic",
            key="data_editor_plano",
        )
        st.caption(
            "Mantenha as funções obrigatórias. O sistema força: chamada + correcção TPC na 1ª função, e marcação de TPC na última."
        )

    c_apply, c_reset = st.columns(2)

    with c_apply:
        if st.button("✅ Aplicar alterações", type="primary"):
            og_lines = [x.strip() for x in og_new.split("\n") if x.strip()]
            if "90" in ctx["duracao"]:
                objetivo_geral = og_lines[:2] if og_lines else ["-"]
            else:
                objetivo_geral = og_lines[0] if og_lines else "-"

            oe_lines = [x.strip() for x in oe_new.split("\n") if x.strip()]
            if not oe_lines:
                oe_lines = ["-"]

            try:
                plano_novo = df_to_plano(edited_df, objetivo_geral, oe_lines)
                st.session_state["plano_editado"] = plano_novo.model_dump()
                st.session_state["editor_df"] = plano_to_df(plano_novo)
                st.session_state.pop("preview_imgs", None)
                st.success("Alterações aplicadas. Pré-visualização e PDF foram actualizados.")
                st.rerun()
            except Exception as e:
                st.error(f"Não foi possível aplicar as alterações: {e}")

    with c_reset:
        if st.button("↩️ Repor para o plano gerado pela IA"):
            plano_base = PlanoAula(**st.session_state["plano_base"])
            st.session_state["plano_editado"] = plano_base.model_dump()
            st.session_state["editor_df"] = plano_to_df(plano_base)
            st.session_state.pop("preview_imgs", None)
            st.success("Plano reposto para a versão original gerada.")
            st.rerun()

    # PREVIEW
    st.divider()
    st.subheader("👁️ Pré-visualização do Plano (Imagens)")

    plano_final = PlanoAula(**st.session_state["plano_editado"])
    if "preview_imgs" not in st.session_state:
        st.session_state["preview_imgs"] = plano_to_preview_images(ctx, plano_final)

    for i, im in enumerate(st.session_state["preview_imgs"], 1):
        st.image(im, caption=f"Pré-visualização - Página {i}", use_container_width=True)

    # PDF
    st.divider()
    st.subheader("📄 Exportação")

    c1, c2 = st.columns(2)
    with c1:
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

    with c2:
        if st.button("🔄 Elaborar Novo Plano"):
            st.session_state["plano_pronto"] = False
            for k in [
                "plano_base",
                "plano_editado",
                "ctx",
                "modelo_usado",
                "preview_imgs",
                "editor_df",
                "data_editor_plano",
            ]:
                st.session_state.pop(k, None)
            st.rerun()
