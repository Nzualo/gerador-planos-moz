import json
import base64
import hashlib
from datetime import date, datetime
import pandas as pd
import streamlit as st
import requests
from pydantic import BaseModel, Field, ValidationError, conlist

from utils import supa

BUCKET_PLANS = "plans"
TABLE_COLS = ["Tempo", "Função Didáctica", "Actividade do Professor", "Actividade do Aluno", "Métodos", "Meios"]


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
            return json.loads(text[start:end + 1])
        raise


def make_cache_key(payload: dict) -> str:
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


@st.cache_data(ttl=86400)
def cached_generate(cache_key: str, prompt: str, model_name: str) -> str:
    import google.generativeai as genai  # import pesado aqui
    model = genai.GenerativeModel(model_name)
    resp = model.generate_content(prompt)
    return resp.text


# -------------------------
# Currículo snippets
# -------------------------
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

    picks = [p.strip() for p in picks if p and p.strip()][:6]
    if not picks:
        return ""
    return "\n".join([f"- {p}" for p in picks])


# -------------------------
# Prompt
# -------------------------
def build_prompt(ctx: dict, curriculum_text: str) -> str:
    return f"""
És Pedagogo(a) Especialista do Sistema Nacional de Educação (SNE) de Moçambique.
Escreve SEMPRE em Português de Moçambique. Evita termos e ortografia do Brasil.

CONTEÚDO DO CURRÍCULO / PROGRAMA:
{curriculum_text if curriculum_text else "- (Sem snippet registado.)"}

REGRAS:
1) Devolve APENAS JSON válido.
2) Campos: "objetivo_geral", "objetivos_especificos", "tabela".
3) Tabela com 6 colunas: ["tempo","funcao_didatica","actividade_professor","actividade_aluno","metodos","meios"]
4) Funções obrigatórias e na ordem:
   - Introdução e Motivação
   - Mediação e Assimilação
   - Domínio e Consolidação
   - Controlo e Avaliação

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


# -------------------------
# Histórico
# -------------------------
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
        signed = sb.storage.from_(BUCKET_PLANS).create_signed_url(pdf_path, 600)
        url = signed.get("signedURL") or signed.get("signedUrl") or signed.get("signed_url")
        if url:
            resp = requests.get(url, timeout=60)
            if resp.status_code == 200:
                return resp.content

    if pdf_b64:
        try:
            return base64.b64decode(pdf_b64)
        except Exception:
            return None

    return None


# -------------------------
# PDF (import pesado só aqui)
# -------------------------
def create_pdf(ctx: dict, plano: PlanoAula) -> bytes:
    from fpdf import FPDF  # import pesado aqui

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

    pdf = PDF()
    pdf.add_page()
    pdf.set_font("Arial", "", 10)

    pdf.cell(130, 7, f"Escola: {clean_text(ctx['escola'])}", 0, 0)
    pdf.cell(0, 7, f"Data: {clean_text(ctx['data'])}", 0, 1)
    pdf.cell(0, 7, f"Disciplina: {clean_text(ctx['disciplina'])}  Classe: {clean_text(ctx['classe'])}  Turma: {clean_text(ctx['turma'])}", 0, 1)
    pdf.cell(0, 7, f"Unidade: {clean_text(ctx['unidade'])}", 0, 1)
    pdf.set_font("Arial", "B", 10)
    pdf.cell(0, 7, f"Tema: {clean_text(ctx['tema'])}", 0, 1)
    pdf.set_font("Arial", "", 10)
    pdf.cell(0, 7, f"Professor: {clean_text(ctx['professor'])}  Duração: {clean_text(ctx['duracao'])}", 0, 1)
    pdf.ln(3)

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
    pdf.ln(2)

    headers = ["Tempo", "Função", "Prof.", "Aluno", "Métodos", "Meios"]
    widths = [12, 30, 52, 52, 22, 22]

    pdf.set_font("Arial", "B", 8)
    for i, h in enumerate(headers):
        pdf.cell(widths[i], 6, h, 1, 0, "C")
    pdf.ln()

    pdf.set_font("Arial", "", 8)
    for row in plano.tabela:
        for i, cell in enumerate(row):
            pdf.cell(widths[i], 6, clean_text(cell)[:60], 1, 0)
        pdf.ln()

    return pdf.output(dest="S").encode("latin-1", "replace")


# -------------------------
# UI
# -------------------------
def plans_ui(user: dict):
    user_key = user["user_key"]
    user_name = user.get("name", "")
    user_school = user.get("school", "")

    st.subheader("📚 Meus Planos (Histórico)")
    hist = list_user_plans(user_key)

    if hist.empty:
        st.info("Ainda não há planos guardados.")
    else:
        hist["label"] = (
            hist["plan_day"].astype(str) + " | " +
            hist["classe"].astype(str) + " | " +
            hist["disciplina"].astype(str) + " | " +
            hist["tema"].astype(str)
        )
        st.dataframe(hist[["plan_day","classe","disciplina","tema","created_at"]], use_container_width=True, hide_index=True)

        sel = st.selectbox("Selecionar plano para baixar", hist["label"].tolist())
        plan_id = int(hist[hist["label"] == sel].iloc[0]["id"])
        pdf_bytes = get_plan_pdf_bytes(user_key, plan_id)
        if pdf_bytes:
            st.download_button("⬇️ Baixar PDF", pdf_bytes, file_name=f"Plano_{sel}.pdf".replace(" ", "_"), mime="application/pdf")
        else:
            st.error("Não foi possível carregar o PDF.")

    st.divider()
    st.subheader("🧩 Novo Plano")

    col1, col2 = st.columns(2)
    with col1:
        escola = st.text_input("Escola", user_school)
        professor = st.text_input("Professor", user_name)
        disciplina = st.text_input("Disciplina", "Língua Portuguesa")
        classe = st.selectbox("Classe", ["1ª","2ª","3ª","4ª","5ª","6ª","7ª","8ª","9ª","10ª","11ª","12ª"])
        unidade = st.text_input("Unidade Temática")
        tipo_aula = st.selectbox("Tipo de Aula", ["Introdução de Matéria Nova","Consolidação e Exercitação","Verificação e Avaliação","Revisão"])

    with col2:
        duracao = st.selectbox("Duração", ["45 Min", "90 Min"])
        turma = st.text_input("Turma", "A")
        tema = st.text_input("Tema")
        data_plano = st.date_input("Data", value=date.today())

    if st.button("🚀 Gerar Plano", type="primary"):
        if not unidade.strip() or not tema.strip():
            st.error("Preencha Unidade e Tema.")
            st.stop()

        # gemini config aqui (import leve)
        import google.generativeai as genai
        genai.configure(api_key=st.secrets["GOOGLE_API_KEY"])

        ctx = {
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

        with st.spinner("A gerar com IA..."):
            texto = cached_generate(key, prompt, "models/gemini-1.5-flash")
            raw = safe_extract_json(texto)
            plano = PlanoAula(**raw)

        st.success("Plano gerado.")
        st.json(plano.model_dump())

        # PDF + guardar
        pdf_bytes = create_pdf(ctx, plano)
        if st.button("💾 Guardar no Histórico"):
            save_plan_to_history_storage(user_key, ctx, plano.model_dump(), pdf_bytes)
            st.success("Guardado.")
            st.rerun()

        st.download_button("⬇️ Baixar PDF agora", pdf_bytes, file_name=f"Plano_{disciplina}_{classe}_{tema}.pdf".replace(" ", "_"), mime="application/pdf")
