import streamlit as st
import google.generativeai as genai
from fpdf import FPDF
import pandas as pd

# Configuração da Página
st.set_page_config(page_title="Plano Analítico SNE", page_icon="🇲🇿", layout="wide")

# --- CLASSE DO PDF (LAYOUT SNE RIGOROSO) ---
class PDF(FPDF):
    def header(self):
        # Logótipo / Cabeçalho Nacional
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
        self.cell(0, 10, 'Modelo SNE (Adaptado) - Inhassoro', 0, 0, 'C')

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
    
    # --- CABEÇALHO ADMINISTRATIVO (ESTILO FORMULÁRIO) ---
    pdf.set_font("Arial", size=10)
    
    # Linha 1: Escola e Data
    pdf.cell(130, 7, f"Escola: __________________________________________________", 0, 0)
    pdf.cell(0, 7, f"Data: ____/____/2026", 0, 1)
    
    # Linha 2: Unidade Temática
    pdf.cell(0, 7, f"Unidade Temática: {inputs['unidade']}", 0, 1)
    
    # Linha 3: Tema
    pdf.set_font("Arial", "B", 10)
    pdf.cell(0, 7, f"Tema: {inputs['tema']}", 0, 1)
    pdf.set_font("Arial", size=10)
    
    # Linha 4: Professor e Turma
    pdf.cell(100, 7, f"Professor: ______________________________", 0, 0)
    pdf.cell(50, 7, f"Turma: {inputs['turma']}", 0, 0)
    pdf.cell(0, 7, f"Duração: {inputs['duracao']}", 0, 1)
    
    # Linha 5: Tipo de Aula e Alunos
    pdf.cell(100, 7, f"Tipo de Aula: {inputs['tipo_aula']}", 0, 0)
    pdf.cell(0, 7, f"Nº Alunos: M_____  F_____  Total:_____", 0, 1)
    
    pdf.line(10, pdf.get_y()+2, 200, pdf.get_y()+2)
    pdf.ln(5)

    # --- OBJETIVOS (Conciso) ---
    pdf.set_font("Arial", "B", 9)
    pdf.cell(0, 6, "OBJECTIVOS ESPECÍFICOS:", 0, 1)
    pdf.set_font("Arial", size=9)
    pdf.multi_cell(0, 5, objetivos_text)
    pdf.ln(5)

    # --- TABELA ---
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

# --- INTERFACE DO SITE ---
st.title("🇲🇿 SNE - Planificador Profissional")

with st.sidebar:
    api_key = st.text_input("Chave API:", type="password")
    st.info("Modelo ajustado para SNE Moçambique.")

# Formulário Principal
col1, col2 = st.columns(2)
with col1:
    disciplina = st.text_input("Disciplina", "Língua Portuguesa")
    classe = st.selectbox("Classe", ["1ª", "2ª", "3ª", "4ª", "5ª", "6ª", "7ª", "8ª", "9ª", "10ª", "11ª", "12ª"])
    unidade = st.text_input("Unidade Temática", placeholder="Ex: Textos Normativos")
    tipo_aula = st.selectbox("Tipo de Aula", ["Inicial / Conteúdo Novo", "Continuação / Exercitação", "Revisão e Consolidação", "Avaliação (ACS/ACP)"])

with col2:
    duracao = st.selectbox("Duração", ["45 Minutos", "90 Minutos"])
    turma = st.text_input("Turma", placeholder="Ex: A")
    tema = st.text_input("Tema da Aula", placeholder="Ex: Leitura da letra M")

if st.button("Gerar Plano SNE (Completo)", type="primary"):
    if not api_key:
        st.error("Insira a chave API.")
    else:
        with st.spinner('A consultar metodologias participativas...'):
            try:
                genai.configure(api_key=api_key)
                model = genai.GenerativeModel('models/gemini-2.5-flash')
                
                # --- PROMPT PEDAGÓGICO AVANÇADO ---
                prompt = f"""
                Aja como Pedagogo do SNE Moçambique.
                Elabore um plano de aula para:
                Disciplina: {disciplina}, Classe: {classe}
                Unidade: {unidade}, Tema: {tema}
                Tipo de Aula: {tipo_aula}

                REGRAS OBRIGATÓRIAS:
                1. OBJETIVOS: Gere no MÁXIMO 3 objetivos específicos. Devem ser curtos, diretos e operacionais (Ex: Identificar, Mencionar, Resolver).
                
                2. MÉTODOS: Na coluna métodos, dê prioridade a métodos participativos (Ex: Elaboração Conjunta, Chuva de Ideias, Trabalho Independente, Discussão em Grupo).
                
                3. TABELA: Gere os dados separados por "||".
                Colunas: Tempo || Função Didática || Conteúdo || Actividade Professor || Actividade Aluno || Métodos || Meios
                
                Gere 4 linhas correspondentes às Funções Didáticas (Introdução, Mediação, Domínio, Controle).
                
                FORMATO DE SAÍDA:
                [BLOCO_OBJETIVOS]
                - Objetivo 1
                - Objetivo 2
                [FIM_OBJETIVOS]

                [BLOCO_TABELA]
                ...dados...
                [FIM_TABELA]
                """
                
                response = model.generate_content(prompt)
                texto = response.text
                
                # Extração
                objetivos = "..."
                dados = []
                
                if "[BLOCO_OBJETIVOS]" in texto:
                    start = texto.find("[BLOCO_OBJETIVOS]") + 17
                    end = texto.find("[FIM_OBJETIVOS]")
                    objetivos = texto[start:end].strip()

                if "[BLOCO_TABELA]" in texto:
                    start = texto.find("[BLOCO_TABELA]") + 14
                    end = texto.find("[FIM_TABELA]")
                    lines = texto[start:end].strip().split('\n')
                    for l in lines:
                        if "||" in l and "Função Didática" not in l:
                            cols = [c.strip() for c in l.split("||")]
                            while len(cols) < 7: cols.append("-")
                            dados.append(cols)
                
                # Inputs para o PDF
                inputs_pdf = {
                    'disciplina': disciplina, 'classe': classe, 'duracao': duracao,
                    'tema': tema, 'unidade': unidade, 'tipo_aula': tipo_aula, 'turma': turma
                }

                # Preview
                st.subheader("👁️ Pré-visualização")
                st.info(objetivos)
                if dados:
                    df = pd.DataFrame(dados, columns=["Tempo", "F. Didática", "Conteúdo", "Prof.", "Aluno", "Métodos", "Meios"])
                    st.dataframe(df, hide_index=True)
                    
                    pdf_bytes = create_pdf_table(inputs_pdf, dados, objetivos)
                    st.download_button("⬇️ Baixar Plano SNE", data=pdf_bytes, file_name=f"Plano_{disciplina}.pdf", mime="application/pdf")
                
            except Exception as e:
                st.error(f"Erro: {e}")
