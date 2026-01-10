# app.py
# =========================================================
# SDEJT - Planos SNE (Inhassoro) | Streamlit
# BASE: fpdf (1.x) - estável no Streamlit Cloud
# Melhorias:
# 1) Regras obrigatórias:
#    - 1ª Função (Introdução e Motivação): controlo de presenças + correcção do TPC (se houver)
#    - Última Função (Controlo e Avaliação): marcar/atribuir TPC
#    - Enforcer no backend (garante mesmo se a IA falhar)
# 2) Pré-visualização do plano em imagens (PNG) antes do PDF
# =========================================================

import json
import time
import hashlib
from datetime import date

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
    .stTextInput > div > div > input, .stSelectbox > div > div > div { color: #ffffff; }
    h1, h2, h3 { color: #FF4B4B !important; }
</style>
""",
    unsafe_allow_html=True,
)

# =========================================================
# SECURITY: SIMPLE LOCKOUT
# =========================================================
MAX_TRIES = 5
LOCK_SECONDS = 120


def validate_credentials(user: str, pwd: str) -> bool:
    if "passwords" not in st.secrets:
        return False
    return user in st.secrets["passwords"] and st.secrets["passwords"][user] == pwd


def check_password() -> bool:
    if st.session_state.get("password_correct", False):
        return True

    now = time.time()
    locked_until = st.session_state.get("locked_until", 0)
    if now < locked_until:
        st.error("Acesso temporariamente bloqueado. Tente novamente mais tarde.")
        return False

    st.markdown("## 🇲🇿 SDEJT - Elaboração de Planos")
    st.markdown("##### Serviço Distrital de Educação, Juventude e Tecnologia - Inhassoro")
    st.divider()

    col1, col2 = st.columns([1, 1])

    with col1:
        st.info("🔐 Acesso Restrito")
        usuario = st.text_input("Utilizador", key="login_user").strip()
        senha = st.text_input("Senha", type="password", key="login_pwd")

        if st.button("Entrar", type="primary"):
            ok = validate_credentials(usuario, senha)
            if ok:
                st.session_state["password_correct"] = True
                st.session_state["user_name"] = usuario
                st.session_state["tries"] = 0
                st.rerun()
            else:
                tries = st.session_state.get("tries", 0) + 1
                st.session_state["tries"] = tries
                st.error("Credenciais inválidas.")
                if tries >= MAX_TRIES:
                    st.session_state["locked_until"] = now + LOCK_SECONDS

    with col2:
        st.warning("⚠️ Suporte / Aquisição de Acesso")
        st.markdown("**Precisa de acesso?**")
        st.write("Clique no botão abaixo para solicitar ao Administrador:")

        meu_numero = "258867926665"
        mensagem = "Saudações técnico Nzualo. Gostaria de solicitar acesso ao Gerador de Planos de Aulas."
        link_zap = f"https://wa.me/{meu_numero}?text={mensagem.replace(' ', '%20')}"

        st.markdown(
            f"""
            <a href="{link_zap}" target="_blank" style="text-decoration: none;">
                <button style="
                    background-color:#25D366;
                    color:white;
                    border:none;
                    padding:15px 25px;
                    border-radius:8px;
                    width:100%;
                    cursor:pointer;
                    font-size: 16px;
                    font-weight:bold;">
                    📱 Falar no WhatsApp
                </button>
            </a>
            """,
            unsafe_allow_html=True,
        )

    return False


if not check_password():
    st.stop()

with st.sidebar:
    st.success(f"👤 Técnico: **{st.session_state['user_name']}**")
    if st.button("Sair"):
        st.session_state["password_correct"] = False
        st.rerun()


# =========================================================
# DATA MODEL (JSON STRICT)
# =========================================================
class PlanoAula(BaseModel):
    objetivo_geral: str | list[str]
    objetivos_especificos: list[str] = Field(min_length=1)
    tabela: list[conlist(str, min_length=6, max_length=6)]


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
# ENFORCER: garante as regras pedagógicas mesmo se a IA falhar
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

    # Função 1: chamada + correcção do TPC
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

    # Função 4: marcar TPC
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
# PREVIEW IMAGES (PNG) - antes do PDF
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
    W, H = 1240, 1754  # A4 approx @150dpi
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

    # Página(s) da tabela
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

    widths = [12, 32, 52, 52, 21, 21]  # cabe no A4
    pdf.draw_table_header(widths)
    for row in plano.tabela:
        pdf.table_row(row, widths)

    return pdf.output(dest="S").encode("latin-1", "replace")


# =========================================================
# APP UI
# =========================================================
st.title("🇲🇿 Elaboração de Planos de Aulas (SNE)")

if "GOOGLE_API_KEY" not in st.secrets:
    st.error("⚠️ ERRO: Configure a Chave de API nos Secrets!")
    st.stop()

with st.sidebar:
    st.markdown("### Contexto da Escola (Inhassoro)")
    localidade = st.text_input("Posto/Localidade", "Inhassoro (Sede)")
    tipo_escola = st.selectbox("Tipo de escola", ["EPC", "ESG1", "ESG2", "Outra"])
    recursos = st.text_area("Recursos disponíveis", "Quadro, giz/marcador, livros, cadernos.")
    nr_alunos = st.text_input("Nº de alunos", "40 (aprox.)")
    obs_turma = st.text_area(
        "Observações da turma",
        "Turma heterogénea; alguns alunos com dificuldades de leitura/escrita.",
    )

col1, col2 = st.columns(2)
with col1:
    escola = st.text_input("Escola", "EPC de Inhassoro")
    professor = st.text_input("Professor", st.session_state.get("user_name", ""))
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

if st.button("🚀 Gerar Plano de Aula", type="primary", disabled=bool(missing)):
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

            # aplica regras obrigatórias (presenças+TPC no início, TPC no fim)
            plano = enforce_didactic_rules(plano)

            st.session_state["plano"] = plano.model_dump()
            st.session_state["ctx"] = ctx
            st.session_state["modelo_usado"] = modelo_usado
            st.session_state["plano_pronto"] = True

            # limpa previews antigos
            st.session_state.pop("preview_imgs", None)

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

    plano = PlanoAula(**st.session_state["plano"])
    ctx = st.session_state["ctx"]

    # =========================
    # PREVIEW EM IMAGENS
    # =========================
    st.subheader("👁️ Pré-visualização do Plano (Imagens)")

    if "preview_imgs" not in st.session_state:
        st.session_state["preview_imgs"] = plano_to_preview_images(ctx, plano)

    for i, im in enumerate(st.session_state["preview_imgs"], 1):
        st.image(im, caption=f"Pré-visualização - Página {i}", use_container_width=True)

    # =========================
    # EXPORTAÇÃO PDF
    # =========================
    st.divider()
    st.subheader("📄 Exportação")

    c1, c2 = st.columns(2)
    with c1:
        try:
            pdf_bytes = create_pdf(ctx, plano)
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
            st.session_state.pop("plano", None)
            st.session_state.pop("ctx", None)
            st.session_state.pop("preview_imgs", None)
            st.session_state.pop("modelo_usado", None)
            st.rerun()
