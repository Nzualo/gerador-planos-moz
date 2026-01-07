import streamlit as st
import google.generativeai as genai
from fpdf import FPDF
import pandas as pd
import time

# --- 1. CONFIGURAÇÃO ---
st.set_page_config(page_title="SDEJT Inhassoro", page_icon="🇲🇿", layout="wide")

# --- 2. ESTILO VISUAL (DARK MODE / MÓVEL) ---
st.markdown("""
    <style>
    .stApp {
        background-color: #0E1117;
        color: #FFFFFF;
    }
    .stTextInput input {
        color: white !important;
    }
    div.stButton > button {
        width: 100%;
        border-radius: 8px;
        font-weight: bold;
        height: 50px;
        text-transform: uppercase;
    }
    /* Esconde menus desnecessários */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    </style>
    """, unsafe_allow_html=True)

# --- 3. FUNÇÃO DE LOGIN (TÍTULOS CORRIGIDOS) ---
def check_password():
    if st.session_state.get("password_correct", False):
        return True

    st.markdown("<br>", unsafe_allow_html=True)
    
    with st.container(border=True):
        # TÍTULO CORRIGIDO AQUI
        st.markdown("<h3 style='text-align: center; color: #4CAF50;'>🇲🇿 SDEJT - INHASSORO</h3>", unsafe_allow_html=True)
        st.markdown("<h5 style='text-align: center; color: #ccc;'>Serviço Distrital de Educação, Juventude e Tecnologia</h5>", unsafe_allow_html=True)
        st.divider()
        
        st.info("🔐 Área Restrita")
        usuario = st.text_input("Usuário")
        senha = st.text_input("Senha", type="password")
        
        if st.button("ENTRAR", type="primary"):
            if "passwords" in st.secrets and usuario in st.secrets["passwords"]:
                if st.secrets["passwords"][usuario] == senha:
                    st.session_state["password_correct"] = True
                    st.session_state["user_name"] = usuario
                    st.rerun()
                else:
                    st.error("Senha incorreta.")
            else:
                st.error("Usuário não encontrado.")

        st.markdown("---")
        # Botão WhatsApp
        link_zap = "https://wa.me/258867926665?text=Ola%20Tecnico%20Nzualo,%20peço%20acesso%20ao%20sistema."
        st.markdown(f'''
            <a href="{link_zap}" target="_blank">
                <button style="
                    background-color: #25D366; color: white; border: none; 
                    padding: 10px; border-radius: 5px; width: 100%; font-weight: bold;">
                    📱 Falar com Administrador
                </button>
            </a>
            ''', unsafe_allow_html=True)
    return False

if not check_password():
    st.stop()

# --- 4. BARRA LATERAL ---
with st.sidebar:
    st.success(f"👤 Olá, {st.session_state.get('user_name', 'Professor')}")
    if st.button("Sair / Logout"):
        st.session_state["password_correct"] = False
        st.rerun()

# --- 5. CLASSE PDF (A4 HORIZONTAL) ---
class PDF(FPDF):
    def header(self):
        self.set_font('Times', 'B', 12)
        self.cell(0, 5, 'REPÚBLICA DE MOÇAMBIQUE', 0, 1, 'C')
        self.set_font('Times', 'B', 11)
        self.cell(0, 5, 'MINISTÉRIO DA EDUCAÇÃO E DESENVOLVIMENTO HUMANO', 0, 1, 'C')
        self.cell(0, 5, 'SDEJT - DISTRITO DE INHASSORO', 0, 1, 'C')
        self.ln(5)
        self.set_font('Times', 'B', 14)
        self.cell(0, 10, 'PLANO DE LIÇÃO', 0, 1, 'C')
        self.ln(2)

    def footer(self):
        self.set_y(-15)
        self.set_font('Times', 'I', 8)
        self.cell(0, 10, 'SDEJT Inhassoro - Processado por IA', 0, 0, 'C')

    def table_row(self, data, widths):
        max_lines = 1
        for i, text in enumerate(data):
            self.set_font("Times", size=10)
            texto = str(text) if text else ""
            lines = self.multi_cell(widths[i], 4, texto, split_only=True)
            max_lines = max(max_lines, len(lines))
        
        height = max_lines * 4 + 4
        
        if self.get_y() + height > 180:
            self.add_page(orientation='L')
            self.create_headers(widths)
            
        x_start = self.get_x()
        y_start = self.get_y()
        
        for i, text in enumerate(data):
            self.set_xy(x_start, y_start)
            texto = str(text) if text else ""
            self.multi_cell(widths[i], 4, texto, border=0)
            x_start += widths[i]
            
        self.set_xy(10, y_start)
        x_curr = 10
        for w in widths:
            self.rect(x_curr, y_start, w, height)
            x_curr += w
        self.set_y(y_start + height)

    def create_headers(self, widths):
        headers = ["TEMPO", "F. DIDÁTICA", "CONTEÚDOS", "ACTIV. PROF", "ACTIV. ALUNO", "MÉTODOS", "MEIOS"]
        self.set_font("Times", "B", 9)
        self.set_fill_color(220, 220, 220)
        for i, h in enumerate(headers):
            self.cell(widths[i], 6, h, 1, 0, 'C', True)
        self.ln()

def create_pdf(inputs, dados, objetivos):
    pdf = PDF()
    pdf.set_auto_page_break(auto=False)
    pdf.add_page(orientation='L') # Paisagem
    
    pdf.set_font("Times", size=12)
    # Cabeçalho
    pdf.cell(160, 7, f"Escola: _______________________________________________________", 0, 0)
    pdf.cell(0, 7, f"Data: ____/____/2026", 0, 1)
    pdf.cell(0, 7, f"Unidade: {inputs['unidade']}", 0, 1)
    
    pdf.set_font("Times", "B", 12)
    pdf.cell(0, 7, f"Tema: {inputs['tema']}", 0, 1)
    pdf.set_font("Times", size=12)
    
    pdf.cell(110, 7, f"Professor: ___________________________", 0, 0)
    pdf.cell(40, 7, f"Turma: {inputs['turma']}", 0, 0)
    pdf.cell(0, 7, f"Duração: {inputs['duracao']}", 0, 1)
    
    pdf.cell(110, 7, f"Tipo de Aula: {inputs['tipo_aula']}", 0, 0)
    pdf.cell(0, 7, f"Alunos: M_____  F_____  Total:_____", 0, 1)
    pdf.line(10, pdf.get_y()+2, 285, pdf.get_y()+2)
    pdf.ln(5)

    pdf.set_font("Times", "B", 12)
    pdf.cell(0, 6, "OBJECTIVOS:", 0, 1)
    pdf.set_font("Times", size=12)
    pdf.multi_cell(0, 5, objetivos)
    pdf.ln(5)

    widths = [15, 35, 55, 55, 55, 30, 32]
    pdf.create_headers(widths)
    
    for row in dados:
        pdf.table_row(row, widths)
        
    return pdf.output(dest='S').encode('latin-1', 'ignore')

# --- 6. APLICATIVO PRINCIPAL ---
# TÍTULO CORRIGIDO AQUI
st.title("🇲🇿 Elaboração de Planos de Aulas")
st.markdown("##### Serviço Distrital de Educação, Juventude e Tecnologia - Inhassoro")
st.divider()

if "GOOGLE_API_KEY" not in st.secrets:
    st.error("⚠️ ERRO: Configure a Chave API nos Secrets.")
    st.stop()

# Formulário
with st.container(border=True):
    c1, c2 = st.columns(2)
    with c1:
        disciplina = st.text_input("Disciplina", "Língua Portuguesa")
        classe = st.selectbox("Classe", ["1ª", "2ª", "3ª", "4ª", "5ª", "6ª", "7ª", "8ª", "9ª", "10ª", "11ª", "12ª"])
        unidade = st.text_input("Unidade", placeholder="Ex: Textos Normativos")
        tipo_aula = st.selectbox("Tipo de Aula", [
            "Conteúdo Novo", "Continuação", "Exercícios de Aplicação", 
            "Revisão", "Avaliação", "Correção"
        ])
    with c2:
        duracao = st.selectbox("Duração", ["45 Min", "90 Min"])
        turma = st.text_input("Turma", placeholder="A")
        tema = st.text_input("Tema", placeholder="Tema da aula...")

    st.markdown("<br>", unsafe_allow_html=True)
    
    if st.button("🚀 GERAR PLANO PDF", type="primary"):
        with st.spinner('A processar...'):
            try:
                genai.configure(api_key=st.secrets["GOOGLE_API_KEY"])
                model = genai.GenerativeModel('models/gemini-2.5-flash')
                
                prompt = f"""
                Pedagogo do MINEDH Moçambique.
                Plano: {disciplina}, {classe}, Tema: {tema}, Tipo: {tipo_aula}.
                Regras: Centrado no aluno. TPC (Correção/Marcação).
                Saída: [BLOCO_OBJETIVOS]...[FIM] [BLOCO_TABELA]...[FIM] (Separação ||)
                """
                response = model.generate_content(prompt)
                text = response.text
                
                objs = text.split("[BLOCO_OBJETIVOS]")[1].split("[FIM]")[0].strip() if "[BLOCO_OBJETIVOS]" in text else "..."
                raw_table = text.split("[BLOCO_TABELA]")[1].split("[FIM]")[0].strip().split('\n') if "[BLOCO_TABELA]" in text else []
                
                dados = []
                for l in raw_table:
                    if "||" in l and "Função" not in l:
                        cols = [c.strip() for c in l.split("||")]
                        while len(cols) < 7: cols.append("-")
                        dados.append(cols[:7])
                
                st.session_state['res_pdf'] = True
                st.session_state['d'] = dados
                st.session_state['o'] = objs
                st.session_state['i'] = {'disciplina': disciplina, 'classe': classe, 'duracao': duracao, 'tema': tema, 'unidade': unidade, 'tipo_aula': tipo_aula, 'turma': turma}
                st.rerun()
            except Exception as e:
                st.error(f"Erro: {e}")

if st.session_state.get('res_pdf'):
    st.divider()
    st.success("✅ Plano Pronto!")
    
    pdf_data = create_pdf(st.session_state['i'], st.session_state['d'], st.session_state['o'])
    st.download_button("📄 BAIXAR PDF (HORIZONTAL)", data=pdf_data, file_name="Plano.pdf", mime="application/pdf", type="primary")
    
    if st.session_state['d']:
        df = pd.DataFrame(st.session_state['d'], columns=["Min", "F. Didática", "Conteúdo", "Prof", "Aluno", "Métodos", "Meios"])
        st.dataframe(df, hide_index=True)
    
    if st.button("🔄 Novo Plano"):
        st.session_state['res_pdf'] = False
        st.rerun()
