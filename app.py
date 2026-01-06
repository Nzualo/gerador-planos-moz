import streamlit as st
import google.generativeai as genai
from fpdf import FPDF

# Configuração
st.set_page_config(page_title="SDEJT Inhassoro", page_icon="🇲🇿")

# --- FUNÇÃO DO PDF ---
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
        self.set_font('Arial', 'I', 8)
        self.cell(0, 10, 'Gerado por IA - SDEJT Inhassoro', 0, 0, 'C')

def create_pdf(texto, disciplina, classe, tema):
    pdf = PDF()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.set_font("Arial", "B", 11)
    pdf.cell(0, 8, f"Disciplina: {disciplina}  |  Classe: {classe}", 0, 1)
    pdf.cell(0, 8, f"Tema: {tema}", 0, 1)
    pdf.ln(5)
    pdf.set_font("Arial", size=11)
    texto_limpo = texto.replace("*", "").encode('latin-1', 'ignore').decode('latin-1')
    pdf.multi_cell(0, 6, texto_limpo)
    return pdf.output(dest='S').encode('latin-1', 'ignore')

# --- O SITE ---
st.title("🇲🇿 Gerador Oficial SDEJT")

with st.sidebar:
    api_key = st.text_input("Cole sua API Key aqui:", type="password")
    # Botão de diagnóstico
    if api_key:
        try:
            genai.configure(api_key=api_key)
            st.success("Chave Conectada!")
        except:
            st.error("Chave Inválida")

col1, col2 = st.columns(2)
with col1:
    disciplina = st.text_input("Disciplina", "Matemática")
    classe = st.selectbox("Classe", ["1ª", "2ª", "3ª", "4ª", "5ª", "6ª", "7ª", "8ª", "9ª", "10ª", "11ª", "12ª"])
with col2:
    duracao = st.selectbox("Tempo", ["45 min", "90 min"])
    tema = st.text_input("Tema", "Ex: Vogais")

if st.button("Gerar Documento PDF", type="primary"):
    if not api_key:
        st.error("Insira a chave na barra lateral!")
    else:
        with st.spinner('A conectar ao servidor...'):
            try:
                genai.configure(api_key=api_key)
                
                # --- AUTO-DETECÇÃO DE MODELO ---
                # Tenta o modelo mais novo, se falhar, tenta o antigo
                try:
                    model = genai.GenerativeModel('gemini-1.5-flash')
                    response_check = model.generate_content("Teste")
                except:
                    # Se o Flash falhar, usa o Pro antigo
                    model = genai.GenerativeModel('gemini-pro')
                
                # Gera o conteúdo
                prompt = f"Crie um plano de aula do SNE Moçambique. Disciplina: {disciplina}, Classe: {classe}, Tema: {tema}. Estruture com: 1.Objetivos, 2.Meios, 3.Funções Didáticas. Não use tabelas Markdown."
                resposta = model.generate_content(prompt)
                
                # Cria o PDF
                pdf_bytes = create_pdf(resposta.text, disciplina, classe, tema)
                
                st.success("Sucesso! Plano gerado.")
                st.download_button("📄 Baixar PDF Oficial", data=pdf_bytes, file_name="Plano_Aula.pdf", mime="application/pdf")
                
            except Exception as e:
                st.error(f"Erro técnico: {e}")
                st.info("Dica: Tente clicar em 'Reboot App' no menu do site.")
