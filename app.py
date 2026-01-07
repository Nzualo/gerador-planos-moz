import streamlit as st
import google.generativeai as genai
from fpdf import FPDF
import pandas as pd

# Configuração da Página
st.set_page_config(page_title="Plano SNE Pro", page_icon="🇲🇿", layout="wide")

# --- CLASSE DO PDF ---
class PDF(FPDF):
    def header(self):
        self.set_font('Arial', 'B', 12)
        self.cell(0, 5, 'REPÚBLICA DE MOÇAMBIQUE', 0, 1, 'C')
        self.set_font('Arial', 'B', 10)
        self.cell(0, 5, 'GOVERNO DO DISTRITO DE INHASSORO', 0, 1, 'C')
        self.cell(0, 5, 'SERVIÇO DISTRITAL DE EDUCAÇÃO, JUVENTUDE E TECNOLOGIA', 0, 1, 'C')
        self.ln(5)
        self.set_font('Arial', 'B', 14)
        self.cell(0, 10, 'PLANO DE AULA', 0, 1, 'C')
        self.ln(2)

    def footer(self):
        self.set_y(-15)
        self.set_font('Arial', 'I', 6)
        self.cell(0, 10, 'SNE Inhassoro - Processado por IA', 0, 0, 'C')

    def table_row(self, data, widths, align='L'):
        max_lines = 1
        for i, text in enumerate(data):
            self.set_font("Arial", size=8)
            lines = self.multi_cell(widths[i], 4, text, split_only=True)
            if len(lines) > max_lines:
                max_lines = len(lines)
        height = max_lines * 4 + 4
        if self.get_y() + height > 270:
            self.add_page()
            headers = ["TEMPO", "F. DIDÁTICA", "CONTEÚDO", "ACTIV. PROFESSOR", "ACTIV. ALUNO", "MÉTODOS", "MEIOS"]
            self.set_font("Arial", "B", 7)
            self.set_fill_color(230, 230, 230)
            for i, h in enumerate(headers):
                self.cell(widths[i], 6, h, 1, 0, 'C', True)
            self.ln()
        x_start = self.get_x()
        y_start = self.get_y()
        for i, text in enumerate(data):
            self.set_xy(x_start, y_start)
            self.set_font("Arial", size=8)
            self.multi_cell(widths[i], 4, text, border=0, align=align)
            x_start += widths[i]
        self.set_xy(10, y_start)
        x_curr = 10
        for w in widths:
            self.rect(x_curr, y_start, w, height)
            x_curr += w
        self.set_y(y_start + height)

def create_pdf_table(inputs, table_data, objetivos_text):
    pdf = PDF()
    pdf.set_auto_page_break(auto=False)
    pdf.add_page()
    pdf.set_font("Arial", size=10)
    pdf.cell(130, 7, f"Escola: __________________________________________________", 0, 0)
    pdf.cell(0, 7, f"Data: ____/____/2026", 0, 1)
    pdf.cell(0, 7, f"Unidade Temática: {inputs['unidade']}", 0, 1)
    pdf.set_font("Arial", "B", 10)
    pdf.cell(0, 7, f"Tema: {inputs['tema']}", 0, 1)
    pdf.set_font("Arial", size=10)
    pdf.cell(100, 7, f"Professor: ______________________________", 0, 0)
    pdf.cell(50, 7, f"Turma: {inputs['turma']}", 0, 0)
    pdf.cell(0, 7, f"Duração: {inputs['duracao']}", 0, 1)
    pdf.cell(100, 7, f"Tipo de Aula: {inputs['tipo_aula']}", 0, 0)
    pdf.cell(0, 7, f"Nº Alunos: M_____  F_____  Total:_____", 0, 1)
    pdf.line(10, pdf.get_y()+2, 200, pdf.get_y()+2)
    pdf.ln(5)
    pdf.set_font("Arial", "B", 9)
    pdf.cell(0, 6, "OBJECTIVOS ESPECÍFICOS:", 0, 1)
    pdf.set_font("Arial", size=9)
    pdf.multi_cell(0, 5, objetivos_text)
    pdf.ln(5)
    widths = [12, 28, 35, 35, 35, 22, 23]
    headers = ["TEMPO", "F. DIDÁTICA", "CONTEÚDO", "ACTIV. PROFESSOR", "ACTIV. ALUNO", "MÉTODOS", "MEIOS"]
    pdf.set_font("Arial", "B", 7)
    pdf.set_fill_color(230, 230, 230)
    for i, h in enumerate(headers):
        pdf.cell(widths[i], 6, h, 1, 0, 'C', True)
    pdf.ln()
    for row in table_data:
        pdf.table_row(row, widths)
    return pdf.output(dest='S').encode('latin-1', 'ignore')

# --- O SITE COMEÇA AQUI ---
st.title("🇲🇿 SNE - Planificador Pro")

# --- CONEXÃO COM O COFRE (SECRETS) ---
# Se a chave estiver no cofre, usa ela. Se não, pede na tela.
if "GOOGLE_API_KEY" in st.secrets:
    api_key = st.secrets["GOOGLE_API_KEY"]
    st.sidebar.success("✅ Chave Conectada (Secrets)")
else:
    api_key = st.sidebar.text_input("Cole sua Chave API:", type="password")
    st.sidebar.warning("⚠️ Chave não encontrada nos Secrets.")

# Formulário
col1, col2 = st.columns(2)
with col1:
    disciplina = st.text_input("Disciplina", "Língua Portuguesa")
    classe = st.selectbox("Classe", ["1ª", "2ª", "3ª", "4ª", "5ª", "6ª", "7ª", "8ª", "9ª", "10ª", "11ª", "12ª"])
    unidade = st.text_input("Unidade", placeholder="Ex: Textos Normativos")
    tipo_aula = st.selectbox("Tipo", ["Inicial", "Exercitação", "Revisão", "Avaliação"])
with col2:
    duracao = st.selectbox("Duração", ["45 Min", "90 Min"])
    turma = st.text_input("Turma", placeholder="A")
    tema = st.text_input("Tema", placeholder="Ex: Vogais")

if st.button("Gerar Plano SNE", type="primary"):
    if not api_key:
        st.error("ERRO: Nenhuma chave encontrada. Configure os Secrets ou cole na barra lateral.")
    else:
        with st.spinner('A processar...'):
            try:
                genai.configure(api_key=api_key)
                model = genai.GenerativeModel('models/gemini-2.5-flash')
                prompt = f"""
                Aja como Pedagogo do SNE Moçambique.
                Plano para: {disciplina}, {classe}, Tema: {tema}.
                
                REGRAS:
                1. TPC: Introdução (Correção) e Controle (Marcação).
                2. OBJETIVOS: Max 3, operacionais.
                3. TABELA: Separada por "||".
                Colunas: Tempo || Função || Conteúdo || Prof || Aluno || Métodos || Meios
                
                SAÍDA:
                [BLOCO_OBJETIVOS]...[FIM_OBJETIVOS]
                [BLOCO_TABELA]...[FIM_TABELA]
                """
                response = model.generate_content(prompt)
                texto = response.text
                
                objetivos = "..."
                dados = []
                if "[BLOCO_OBJETIVOS]" in texto:
                    objetivos = texto.split("[BLOCO_OBJETIVOS]")[1].split("[FIM_OBJETIVOS]")[0].strip()
                if "[BLOCO_TABELA]" in texto:
                    lines = texto.split("[BLOCO_TABELA]")[1].split("[FIM_TABELA]")[0].strip().split('\n')
                    for l in lines:
                        if "||" in l and "Função" not in l:
                            cols = [c.strip() for c in l.split("||")]
                            while len(cols) < 7: cols.append("-")
                            dados.append(cols)
                            
                inputs_pdf = {'disciplina': disciplina, 'classe': classe, 'duracao': duracao, 'tema': tema, 'unidade': unidade, 'tipo_aula': tipo_aula, 'turma': turma}
                
                st.subheader("Visualização")
                st.info(objetivos)
                if dados:
                    df = pd.DataFrame(dados, columns=["Tempo", "Função", "Conteúdo", "Prof", "Aluno", "Métodos", "Meios"])
                    st.dataframe(df, hide_index=True)
                    pdf_bytes = create_pdf_table(inputs_pdf, dados, objetivos)
                    st.download_button("⬇️ Baixar Plano PDF", data=pdf_bytes, file_name=f"Plano_{disciplina}.pdf", mime="application/pdf")
            except Exception as e:
                st.error(f"Erro: {e}")
