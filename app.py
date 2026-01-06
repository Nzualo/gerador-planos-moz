import streamlit as st
import google.generativeai as genai
from fpdf import FPDF

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="SDEJT Inhassoro - Planos", page_icon="🇲🇿")

# --- FUNÇÃO PARA GERAR PDF ---
class PDF(FPDF):
    def header(self):
        # Cabeçalho Oficial
        self.set_font('Arial', 'B', 12)
        self.cell(0, 5, 'REPÚBLICA DE MOÇAMBIQUE', 0, 1, 'C')
        self.set_font('Arial', 'B', 10)
        self.cell(0, 5, 'GOVERNO DO DISTRITO DE INHASSORO', 0, 1, 'C')
        self.cell(0, 5, 'SERVIÇO DISTRITAL DE EDUCAÇÃO, JUVENTUDE E TECNOLOGIA', 0, 1, 'C')
        self.ln(5) # Espaço
        self.set_font('Arial', 'B', 14)
        self.cell(0, 10, 'PLANO DE AULA', 0, 1, 'C')
        self.ln(5)

    def footer(self):
        self.set_y(-15)
        self.set_font('Arial', 'I', 8)
        self.cell(0, 10, 'Gerado por IA - SDEJT Inhassoro', 0, 0, 'C')

def create_pdf(texto_plano, disciplina, classe, tema):
    pdf = PDF()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)
    
    # Detalhes da Aula
    pdf.set_font("Arial", "B", 10)
    pdf.cell(0, 8, f"Disciplina: {disciplina} | Classe: {classe}", 0, 1)
    pdf.cell(0, 8, f"Tema: {tema}", 0, 1)
    pdf.ln(5)
    
    # Conteúdo do Plano
    pdf.set_font("Arial", size=11)
    # O fpdf tem problemas com caracteres especiais diretos, vamos tentar limpar ou usar latin-1
    # Truque simples para acentos: encode('latin-1', 'replace').decode('latin-1')
    texto_limpo = texto_plano.replace('*', '') # Remove asteriscos do Markdown
    
    pdf.multi_cell(0, 6, texto_limpo)
    
    return pdf.output(dest='S').encode('latin-1', 'ignore')

# --- INTERFACE DO SITE ---
st.title("🇲🇿 Planeamento - SDEJT Inhassoro")
st.markdown("Ferramenta de apoio ao professor.")

# Barra lateral para API Key
with st.sidebar:
    api_key = st.text_input("Sua Google API Key", type="password")
    st.info("Cole a chave que copiou do Google AI Studio.")

# Formulário
col1, col2 = st.columns(2)
with col1:
    disciplina = st.text_input("Disciplina", placeholder="Ex: História")
    classe = st.selectbox("Classe", ["1ª Classe", "2ª Classe", "3ª Classe", "4ª Classe", "5ª Classe", "6ª Classe", "7ª Classe", "8ª Classe", "9ª Classe", "10ª Classe", "11ª Classe", "12ª Classe"])
with col2:
    duracao = st.selectbox("Duração", ["45 Minutos", "90 Minutos"])
    tema = st.text_input("Tema", placeholder="Ex: Independência de Moçambique")

# Ação
if st.button("Gerar Documento Oficial", type="primary"):
    if not api_key:
        st.error("Insira a Chave API na barra lateral.")
    else:
        with st.spinner('A consultar o SNE e a formatar o PDF...'):
            try:
                # 1. Gerar Texto com IA
                genai.configure(api_key=api_key)
                model = genai.GenerativeModel('gemini-pro')
                prompt = f"""
                Aja como técnico pedagógico de Moçambique. Crie um plano de aula para:
                {disciplina}, {classe}, Tema: {tema}, Duração: {duracao}.
                
                NÃO use tabelas Markdown complexas, use listas e texto corrido estruturado para facilitar a conversão para PDF.
                Estrutura:
                1. OBJETIVOS
                2. MEIOS DE ENSINO
                3. FUNÇÕES DIDÁTICAS (Introdução, Mediação, Domínio, Controle).
                Descreva as atividades do professor e aluno em cada fase.
                """
                response = model.generate_content(prompt)
                texto_gerado = response.text
                
                # Mostrar na tela
                st.markdown("### Pré-visualização")
                st.write(texto_gerado)
                
                # 2. Gerar PDF
                pdf_bytes = create_pdf(texto_gerado, disciplina, classe, tema)
                
                st.download_button(
                    label="📄 Baixar PDF para Imprimir",
                    data=pdf_bytes,
                    file_name=f"Plano_{disciplina}_{tema}.pdf",
                    mime="application/pdf"
                )
                
            except Exception as e:
                st.error(f"Erro: {e}")
