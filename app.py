import streamlit as st
import google.generativeai as genai
from fpdf import FPDF
import pandas as pd # Usado para criar a tabela visual na tela

# Configuração da Página
st.set_page_config(page_title="SDEJT Inhassoro", page_icon="🇲🇿", layout="wide")

# --- CLASSE DO PDF (Mantivemos igual porque funciona bem) ---
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
        self.ln(5)

    def footer(self):
        self.set_y(-15)
        self.set_font('Arial', 'I', 6)
        self.cell(0, 10, 'Processado por IA (Gemini 2.5 Flash) - SDEJT Inhassoro', 0, 0, 'C')

    def table_row(self, data, widths, align='L'):
        max_lines = 1
        for i, text in enumerate(data):
            self.set_font("Arial", size=8)
            lines = self.multi_cell(widths[i], 4, text, split_only=True)
            if len(lines) > max_lines:
                max_lines = len(lines)
        
        height = max_lines * 4 + 2
        
        if self.get_y() + height > 275:
            self.add_page()
            headers = ["TEMPO", "FUNÇÃO", "CONTEÚDO", "ACTIV. PROF", "ACTIV. ALUNO", "MÉTODOS", "MEIOS"]
            self.set_font("Arial", "B", 7)
            self.set_fill_color(220, 220, 220)
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

def create_pdf_table(disciplina, classe, tema, duracao, table_data, objetivos_text):
    pdf = PDF()
    pdf.set_auto_page_break(auto=False)
    pdf.add_page()
    
    pdf.set_font("Arial", "B", 10)
    pdf.cell(0, 6, f"DISCIPLINA: {disciplina.upper()}  |  CLASSE: {classe.upper()}", 0, 1)
    pdf.cell(0, 6, f"TEMA: {tema.upper()}", 0, 1)
    pdf.cell(0, 6, f"DURAÇÃO: {duracao.upper()}", 0, 1)
    pdf.ln(2)
    
    pdf.set_font("Arial", "B", 9)
    pdf.cell(0, 6, "OBJECTIVOS:", 0, 1)
    pdf.set_font("Arial", size=9)
    pdf.multi_cell(0, 5, objetivos_text)
    pdf.ln(5)

    widths = [12, 25, 35, 35, 35, 25, 23]
    headers = ["TEMPO", "FUNÇÃO", "CONTEÚDO", "ACTIV. PROF", "ACTIV. ALUNO", "MÉTODOS", "MEIOS"]
    
    pdf.set_font("Arial", "B", 7)
    pdf.set_fill_color(220, 220, 220)
    for i, h in enumerate(headers):
        pdf.cell(widths[i], 6, h, 1, 0, 'C', True)
    pdf.ln()
    
    for row in table_data:
        pdf.table_row(row, widths)

    return pdf.output(dest='S').encode('latin-1', 'ignore')

# --- O SITE ---
st.title("🇲🇿 SDEJT - Tabela Oficial")
st.caption("Gerador de Planos em Grelha (Preview + PDF)")

with st.sidebar:
    api_key = st.text_input("Chave API:", type="password")

col1, col2 = st.columns(2)
with col1:
    disciplina = st.text_input("Disciplina", "Língua Portuguesa")
    classe = st.selectbox("Classe", ["1ª Classe", "2ª Classe", "3ª Classe", "4ª Classe", "5ª Classe", "6ª Classe", "7ª Classe"])
with col2:
    duracao = st.selectbox("Duração", ["45 Minutos", "90 Minutos"])
    tema = st.text_input("Tema", "Ex: Leitura da letra i")

if st.button("Gerar Plano e Ver Preview", type="primary"):
    if not api_key:
        st.error("Insira a chave na barra lateral.")
    else:
        with st.spinner('A Inteligência Artificial está a escrever...'):
            try:
                genai.configure(api_key=api_key)
                model = genai.GenerativeModel('models/gemini-2.5-flash')
                
                prompt = f"""
                Aja como técnico do SNE Moçambique.
                TEMA: {tema}, DISCIPLINA: {disciplina}, CLASSE: {classe}.
                
                PARTE 1: Escreva apenas os Objetivos (Instrutivos e Educativos) em texto corrido.
                
                PARTE 2: Escreva o plano em formato de DADOS para tabela.
                Use o separador "||" entre as colunas.
                As colunas são:
                Tempo || Função Didática || Conteúdo || Actividade Professor || Actividade Aluno || Métodos || Meios
                
                Gere 3 linhas: Introdução, Mediação, Domínio.
                Seja breve nos textos para caber na tabela.
                
                DADOS_TABELA:
                """
                
                response = model.generate_content(prompt)
                texto_raw = response.text
                
                # --- PROCESSAMENTO ---
                objetivos = ""
                dados_tabela = []
                
                lines = texto_raw.split('\n')
                reading_table = False
                
                for line in lines:
                    if "OBJETIVOS:" in line: # Caso o AI escreva o título
                        continue
                    if "DADOS_TABELA:" in line:
                        reading_table = True
                        continue
                    
                    if not reading_table:
                        if line.strip(): # Só adiciona se não for linha vazia
                            objetivos += line + "\n"
                    else:
                        if "||" in line:
                            cols = [c.strip() for c in line.split("||")]
                            while len(cols) < 7:
                                cols.append("-")
                            dados_tabela.append(cols)
                
                # --- PREVIEW NA TELA (NOVIDADE) ---
                st.divider()
                st.subheader("👁️ Pré-visualização do Plano")
                
                st.markdown("### 1. Objetivos")
                st.info(objetivos) # Mostra os objetivos numa caixa azul
                
                st.markdown("### 2. Grelha de Atividades")
                # Criar um visualizador de tabela na tela
                df = pd.DataFrame(dados_tabela, columns=["Tempo", "Função", "Conteúdo", "Prof.", "Aluno", "Métodos", "Meios"])
                st.dataframe(df, hide_index=True) # Mostra a tabela interativa
                
                st.divider()
                
                # --- GERAR PDF ---
                pdf_bytes = create_pdf_table(disciplina, classe, tema, duracao, dados_tabela, objetivos)
                
                st.success("O plano está pronto! Se gostou da pré-visualização acima, baixe o PDF:")
                st.download_button("⬇️ Baixar PDF Oficial", data=pdf_bytes, file_name=f"Plano_{disciplina}.pdf", mime="application/pdf")
                
            except Exception as e:
                st.error(f"Erro: {e}")
