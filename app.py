import streamlit as st
from datetime import datetime
import google.generativeai as genai
from fpdf import FPDF

# ---------------- CONFIG ----------------
st.set_page_config(page_title="Gerador de Planos", layout="wide")

ADMIN_PASSWORD = "1234"  # <<< pode mudar
genai.configure(api_key="SUA_GOOGLE_API_KEY")

# ---------------- SESSION ----------------
if "role" not in st.session_state:
    st.session_state.role = None

if "professor" not in st.session_state:
    st.session_state.professor = None

if "logs" not in st.session_state:
    st.session_state.logs = []

# ---------------- LOGIN ----------------
st.title("📘 Gerador de Planos de Aula")

tabs = st.tabs(["Professor", "Administrador"])

# -------- PROFESSOR --------
with tabs[0]:
    nome = st.text_input("Nome do Professor")
    escola = st.text_input("Escola")

    if st.button("Entrar"):
        if nome and escola:
            st.session_state.role = "professor"
            st.session_state.professor = {
                "nome": nome,
                "escola": escola
            }
            st.session_state.logs.append(
                f"{datetime.now()} - {nome} ({escola}) entrou"
            )
            st.rerun()
        else:
            st.warning("Preencha nome e escola.")

# -------- ADMIN --------
with tabs[1]:
    senha = st.text_input("Senha do administrador", type="password")
    if st.button("Entrar como admin"):
        if senha == ADMIN_PASSWORD:
            st.session_state.role = "admin"
            st.rerun()
        else:
            st.error("Senha errada")

# ---------------- PROFESSOR APP ----------------
if st.session_state.role == "professor":
    p = st.session_state.professor
    st.success(f"Bem-vindo(a), {p['nome']} — {p['escola']}")

    disciplina = st.text_input("Disciplina")
    classe = st.selectbox("Classe", [1,2,3,4,5,6,7,8,9,10,11,12])
    tema = st.text_input("Tema")

    if st.button("Gerar Plano"):
        if disciplina and tema:
            prompt = f"""
Crie um plano de aula do SNE de Moçambique.
Disciplina: {disciplina}
Classe: {classe}
Tema: {tema}

Inclua:
- Objetivo geral
- Funções didáticas
- Introdução com controlo de presenças
- Conclusão com TPC
"""
            model = genai.GenerativeModel("models/gemini-1.5-flash")
            resposta = model.generate_content(prompt)

            plano = resposta.text
            st.text_area("Plano Gerado", plano, height=400)

            pdf = FPDF()
            pdf.add_page()
            pdf.set_font("Arial", size=10)
            for linha in plano.split("\n"):
                pdf.multi_cell(0, 5, linha)

            pdf_bytes = pdf.output(dest="S").encode("latin-1", errors="replace")

            st.download_button(
                "Baixar PDF",
                data=pdf_bytes,
                file_name="plano_aula.pdf",
                mime="application/pdf"
            )
        else:
            st.warning("Preencha disciplina e tema.")

# ---------------- ADMIN PANEL ----------------
if st.session_state.role == "admin":
    st.header("Painel do Administrador")

    if st.button("Limpar registros"):
        st.session_state.logs = []

    st.subheader("Registos de acesso")
    for log in st.session_state.logs:
        st.write(log)

    if st.button("Sair"):
        st.session_state.role = None
        st.rerun()
