# app.py
# =========================================================
# SDEJT - Planos SNE (Inhassoro) | Streamlit
# JSON estrito + validação + contexto local + PDF UTF-8 (fpdf2)
# Fix definitivo do erro: "Not enough horizontal space to render a single character"
# =========================================================

import json
import time
import hashlib
from datetime import date
from pathlib import Path

import streamlit as st
import pandas as pd
from pydantic import BaseModel, Field, ValidationError, conlist

import google.generativeai as genai
from fpdf import FPDF  # fpdf2


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
3) Tabela com EXACTAMENTE 6 colunas:
   ["tempo", "funcao_didatica", "actividade_professor", "actividade_aluno", "metodos", "meios"]
4) Funções didácticas obrigatórias e na ordem:
   - Introdução e Motivação
   - Mediação e Assimilação
   - Domínio e Consolidação
   - Controlo e Avaliação
5) Actividades detalhadas e realistas (SNE + programas).
6) Não inventar meios fora dos recursos listados.
7) Contextualizar com exemplos do quotidiano de Inhassoro quando possível.
8) Respeitar o tempo total ({ctx["duracao"]}) com distribuição realista.

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
# PDF UTF-8 (FPDF2 + TTF)
# FIX DEFINITIVO: margens + epw + x no l_margin + quebra de palavras longas
# =========================================================
FONT_REGULAR = Path(__file__).parent / "DejaVuSans.ttf"
FONT_BOLD = Path(__file__).parent / "DejaVuSans-Bold.ttf"

# pesos base (serão escalados pelo epw)
BASE_WIDTHS = [12, 32, 48, 48, 25, 25]  # soma 190 (referência)


def sanitize_cell(text: str) -> str:
    t = str(text or "")
    t = t.replace("\r", " ").replace("\n", " ")
    t = " ".join(t.split())  # normaliza espaços
    # melhora quebras: após pontos e dois-pontos coloca espaço
    t = t.replace("1.", "1. ").replace("2.", "2. ").replace("3.", "3. ").replace("4.", "4. ")
    t = t.replace(":", ": ").replace(";", "; ")
    t = " ".join(t.split())
    return t.strip()


def break_long_words(text: str, max_word_len: int = 28) -> str:
    """
    Quebra palavras/tokens muito longos sem espaços para evitar erro do fpdf2.
    Insere um espaço a cada max_word_len caracteres quando necessário.
    """
    words = text.split(" ")
    out = []
    for w in words:
        if len(w) <= max_word_len:
            out.append(w)
        else:
            chunks = [w[i : i + max_word_len] for i in range(0, len(w), max_word_len)]
            out.append(" ".join(chunks))
    return " ".join(out)


class PDF(FPDF):
    def header(self):
        self.set_font("DejaVu", "B", 12)
        self.cell(0, 5, "REPÚBLICA DE MOÇAMBIQUE", 0, 1, "C")
        self.set_font("DejaVu", "B", 10)
        self.cell(0, 5, "GOVERNO DO DISTRITO DE INHASSORO", 0, 1, "C")
        self.cell(0, 5, "SERVIÇO DISTRITAL DE EDUCAÇÃO, JUVENTUDE E TECNOLOGIA", 0, 1, "C")
        self.ln(5)
        self.set_font("DejaVu", "B", 14)
        self.cell(0, 10, "PLANO DE AULA", 0, 1, "C")
        self.ln(2)

    def footer(self):
        self.set_y(-15)
        self.set_font("DejaVu", "", 7)
        self.cell(0, 10, "SDEJT Inhassoro - Processado por IA (validação final: Professor)", 0, 0, "C")

    def draw_table_header(self, widths):
        headers = ["TEMPO", "F. DIDÁTICA", "ACTIV. PROFESSOR", "ACTIV. ALUNO", "MÉTODOS", "MEIOS"]
        self.set_x(self.l_margin)  # FIX: garante início na margem esquerda
        self.set_font("DejaVu", "B", 8)
        self.set_fill_color(220, 220, 220)
        for i, h in enumerate(headers):
            self.cell(widths[i], 7, h, 1, 0, "C", True)
        self.ln()

    def table_row(self, data, widths):
        self.set_font("DejaVu", "", 8)

        row = []
        for x in data:
            txt = sanitize_cell(x)
            txt = break_long_words(txt, 28)
            if txt == "":
                txt = "-"
            row.append(txt)

        # mede linhas
        max_lines = 1
        for i, txt in enumerate(row):
            lines = self.multi_cell(widths[i], 4, txt, split_only=True)
            max_lines = max(max_lines, len(lines))

        height = max_lines * 4 + 4

        if self.get_y() + height > 270:
            self.add_page()
            self.draw_table_header(widths)

        y_start = self.get_y()
        x_start = self.l_margin  # FIX: não depende do get_x()

        # escreve células
        for i, txt in enumerate(row):
            self.set_xy(x_start, y_start)
            self.multi_cell(widths[i], 4, txt, border=0, align="L")
            x_start += widths[i]

        # desenha bordas
        self.set_xy(self.l_margin, y_start)
        x_curr = self.l_margin
        for w in widths:
            self.rect(x_curr, y_start, w, height)
            x_curr += w

        self.set_y(y_start + height)


def compute_widths(pdf: FPDF) -> list[float]:
    """
    Calcula larguras dinâmicas com base no epw (effective page width),
    para nunca ultrapassar as margens.
    """
    epw = pdf.w - pdf.l_margin - pdf.r_margin
    base_sum = sum(BASE_WIDTHS)
    scale = epw / base_sum
    return [w * scale for w in BASE_WIDTHS]


def create_pdf(ctx: dict, plano: PlanoAula) -> bytes:
    if not FONT_REGULAR.exists() or not FONT_BOLD.exists():
        raise FileNotFoundError(
            "Faltam as fontes TTF. Coloque DejaVuSans.ttf e DejaVuSans-Bold.ttf no mesmo directório do app.py"
        )

    pdf = PDF()

    # FIX: margens explícitas (não depender de defaults)
    pdf.set_margins(10, 10, 10)

    # FIX: registar fontes ANTES de add_page (porque header usa DejaVu)
    pdf.add_font("DejaVu", "", str(FONT_REGULAR), uni=True)
    pdf.add_font("DejaVu", "B", str(FONT_BOLD), uni=True)

    pdf.set_auto_page_break(auto=False)
    pdf.add_page()

    pdf.set_font("DejaVu", "", 10)
    pdf.cell(130, 7, f"Escola: {sanitize_cell(ctx['escola'])}", 0, 0)
    pdf.cell(0, 7, f"Data: {sanitize_cell(ctx['data'])}", 0, 1)

    pdf.cell(0, 7, f"Unidade Temática: {sanitize_cell(ctx['unidade'])}", 0, 1)
    pdf.set_font("DejaVu", "B", 10)
    pdf.cell(0, 7, f"Tema: {sanitize_cell(ctx['tema'])}", 0, 1)

    pdf.set_font("DejaVu", "", 10)
    pdf.cell(100, 7, f"Professor: {sanitize_cell(ctx['professor'])}", 0, 0)
    pdf.cell(50, 7, f"Turma: {sanitize_cell(ctx['turma'])}", 0, 0)
    pdf.cell(0, 7, f"Duração: {sanitize_cell(ctx['duracao'])}", 0, 1)

    pdf.cell(100, 7, f"Tipo de Aula: {sanitize_cell(ctx['tipo_aula'])}", 0, 0)
    pdf.cell(0, 7, f"Nº de alunos: {sanitize_cell(ctx['nr_alunos'])}", 0, 1)

    pdf.line(pdf.l_margin, pdf.get_y() + 2, pdf.w - pdf.r_margin, pdf.get_y() + 2)
    pdf.ln(5)

    pdf.set_font("DejaVu", "B", 10)
    pdf.cell(0, 6, "OBJECTIVO(S) GERAL(IS):", 0, 1)
    pdf.set_font("DejaVu", "", 10)

    if isinstance(plano.objetivo_geral, list):
        for i, og in enumerate(plano.objetivo_geral, 1):
            pdf.multi_cell(0, 6, f"{i}. {sanitize_cell(og)}")
    else:
        pdf.multi_cell(0, 6, sanitize_cell(plano.objetivo_geral))

    pdf.ln(2)

    pdf.set_font("DejaVu", "B", 10)
    pdf.cell(0, 6, "OBJECTIVOS ESPECÍFICOS:", 0, 1)
    pdf.set_font("DejaVu", "", 10)
    for i, oe in enumerate(plano.objetivos_especificos, 1):
        pdf.multi_cell(0, 6, f"{i}. {sanitize_cell(oe)}")

    pdf.ln(4)

    widths = compute_widths(pdf)  # FIX: larguras sempre cabem no epw
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
    st.markdown("---")
    st.caption("PDF: confirme DejaVuSans.ttf e DejaVuSans-Bold.ttf junto do app.py.")

col1, col2 = st.columns(2)
with col1:
    escola = st.text_input("Escola", "EPC de Inhassoro")
    professor = st.text_input("Professor", st.session_state.get("user_name", ""))
    disciplina = st.text_input("Disciplina", "Língua Portuguesa")
    classe = st.selectbox("Classe", ["1ª", "2ª", "3ª", "4ª", "5ª", "6ª", "7ª", "8ª", "9ª", "10ª", "11ª", "12ª"])
    unidade = st.text_input("Unidade Temática", placeholder="Ex: Textos normativos")
    tipo_aula = st.selectbox("Tipo de Aula", ["Introdução de Matéria Nova", "Consolidação e Exercitação", "Verificação e Avaliação", "Revisão"])

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

            st.session_state["plano"] = plano.model_dump()
            st.session_state["ctx"] = ctx
            st.session_state["modelo_usado"] = modelo_usado
            st.session_state["plano_pronto"] = True

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

    st.markdown("#### Objectivo(s) Geral(is)")
    if isinstance(plano.objetivo_geral, list):
        for i, x in enumerate(plano.objetivo_geral, 1):
            st.write(f"{i}. {x}")
    else:
        st.write(plano.objetivo_geral)

    st.markdown("#### Objectivos Específicos")
    for i, x in enumerate(plano.objetivos_especificos, 1):
        st.write(f"{i}. {x}")

    df = pd.DataFrame(
        plano.tabela,
        columns=["Tempo", "Função Didáctica", "Actividade do Professor", "Actividade do Aluno", "Métodos", "Meios"],
    )
    st.dataframe(df, hide_index=True, use_container_width=True)

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
            st.session_state.pop("modelo_usado", None)
            st.rerun()
