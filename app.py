import streamlit as st
import google.generativeai as genai
from fpdf import FPDF
import pandas as pd
import time

# --- 1. CONFIGURAÇÃO (Primeira Linha Obrigatória) ---
st.set_page_config(page_title="SDEJT Planos", page_icon="🇲🇿", layout="wide")

# --- 2. ESTILO VISUAL (Dark Mode SNE) ---
st.markdown("""
    <style>
    /* Fundo Escuro Profissional */
    .stApp {
        background-color: #0E1117;
        color: #E0E0E0;
    }
    
    /* Inputs (Caixas de texto) */
    .stTextInput > div > div > input {
        color: #FFFFFF !important;
        background-color: #262730 !important;
        border: 1px solid #4CAF50;
    }
    
    /* Selectbox */
    .stSelectbox > div > div > div {
        color: #FFFFFF !important;
        background-color: #262730 !important;
    }
    
    /* Botões */
    div.stButton > button {
        background-color: #4CAF50; /* Verde Institucional */
        color: white;
        border: none;
        padding: 12px;
        font-weight: bold;
        width: 100%;
        text-transform: uppercase;
        font-family: 'Times New Roman', serif;
        border-radius: 6px;
    }
    div.stButton > button:hover {
        background-color: #45a049;
    }
    
    /* Títulos */
    h1, h2, h3, h4 {
        font-family: 'Times New Roman', serif;
        color: #4CAF50 !important;
    }
    
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    </style>
    """, unsafe_allow_html=True)

# --- 3. LOGIN ---
def check_password():
    if st.session_state.get("password_correct", False):
        return True

    st.markdown("<br>", unsafe_allow_html=True)
    with st.container(border=True):
        st.markdown("<h3 style='text-align: center;'>🇲🇿 SDEJT - INHASSORO</h3>", unsafe_allow_html=True)
        st.markdown("<h6 style='text-align: center; color: #aaa;'>Sistema de Elaboração de Planos</h6>", unsafe_allow_html=True)
        st.divider()
        
        st.info("🔐 Acesso Restrito")
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
    return False

if not check_password():
    st.stop()

# --- 4. BARRA LATERAL ---
with st.sidebar:
    st.success(f"👤 Professor: {st.session_state.get('user_name', '')}")
    if st.button("Sair"):
        st.session_state["password_correct"] = False
        st.rerun()

# --- 5. CLASSE PDF (A4 HORIZONTAL + TIMES) ---
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
            texto = str(text) if text else "-"
            lines = self.multi_cell(widths[i], 5, texto, split_only=True)
            max_lines = max(max_lines, len(lines))
        
        height = max_lines * 5 + 2
        
        # Quebra de página (Altura Paisagem ~180mm útil)
        if self.get_y() + height > 180:
            self.add_page(orientation='L')
            self.create_headers(widths)
            
        x_start = self.get_x()
        y_start = self.get_y()
        
        for i, text in enumerate(data):
            self.set_xy(x_start, y_start)
            self.set_font("Times", size=10)
            texto = str(text) if text else "-"
            self.multi_cell(widths[i], 5, texto, border=0)
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
    pdf.add_page(orientation='L')
    
    pdf.set_font("Times", size=12)
    # Cabeçalho
    pdf.cell(160, 7, f"Escola: _______________________________________________________", 0, 0)
    pdf.cell(0, 7, f"Data: ____/____/2026", 0, 1)
    pdf.cell(0, 7, f"Unidade Temática: {inputs['unidade']}", 0, 1)
    
    pdf.set_font("Times", "B", 12)
    pdf.cell(0, 7, f"Tema: {inputs['tema']}", 0, 1)
    pdf.set_font("Times", size=12)
    
    pdf.cell(110, 7, f"Professor: ___________________________", 0, 0)
    pdf.cell(40, 7, f"Turma: {inputs['turma']}", 0, 0)
    pdf.cell(0, 7, f"Duração: {inputs['duracao']}", 0, 1)
    
    pdf.cell(110, 7, f"Tipo de Aula: {inputs['tipo_aula']}", 0, 0)
    pdf.cell(0, 7, f"Efetivos: M_____  F_____  Total:_____", 0, 1)
    
    pdf.line(10, pdf.get_y()+2, 285, pdf.get_y()+2)
    pdf.ln(5)

    pdf.set_font("Times", "B", 12)
    pdf.cell(0, 6, "OBJECTIVOS:", 0, 1)
    pdf.set_font("Times", size=12)
    pdf.multi_cell(0, 5, objetivos)
    pdf.ln(5)

    # Larguras ajustadas para A4 Horizontal (Total ~275mm)
    # Tempo menor, Conteúdo maior
    widths = [15, 40, 60, 50, 50, 30, 30]
    pdf.create_headers(widths)
    
    for row in dados:
        pdf.table_row(row, widths)
        
    return pdf.output(dest='S').encode('latin-1', 'ignore')

# --- 6. APP PRINCIPAL ---
st.title("🇲🇿 Elaboração de Planos (SNE)")

if "GOOGLE_API_KEY" not in st.secrets:
    st.error("⚠️ ERRO: Configure a Chave API nos Secrets.")
    st.stop()

with st.container(border=True):
    c1, c2 = st.columns(2)
    with c1:
        disciplina = st.text_input("Disciplina", "Língua Portuguesa")
        classe = st.selectbox("Classe", ["1ª Classe", "2ª Classe", "3ª Classe", "4ª Classe", "5ª Classe", "6ª Classe", "7ª Classe", "8ª Classe", "9ª Classe", "10ª Classe", "11ª Classe", "12ª Classe"])
        unidade = st.text_input("Unidade Temática", placeholder="Ex: Textos Normativos")
        tipo_aula = st.selectbox("Tipo de Aula", ["Conteúdo Novo", "Exercitação", "Revisão", "Avaliação"])
    with c2:
        duracao = st.selectbox("Duração", ["45 Min (1 Tempo)", "90 Min (2 Tempos)"])
        turma = st.text_input("Turma", placeholder="A")
        tema = st.text_input("Tema", placeholder="Tema da aula...")

    st.markdown("<br>", unsafe_allow_html=True)
    
    if st.button("🚀 ELABORAR PLANO (PDF)", type="primary"):
        with st.spinner('O Metodólogo Virtual está a processar...'):
            try:
                genai.configure(api_key=st.secrets["GOOGLE_API_KEY"])
                model = genai.GenerativeModel('models/gemini-2.5-flash')
                
                # --- PROMPT PEDAGÓGICO RIGOROSO ---
                prompt = f"""
                Aja como Pedagogo Especialista do MINEDH Moçambique.
                Elabore um Plano de Aula para: {disciplina}, {classe}, Tema: {tema}.
                Tipo de Aula: {tipo_aula}.

                ESTRUTURA OBRIGATÓRIA DA TABELA (Use "||" para separar colunas):
                Colunas: Tempo || Função Didática || Conteúdo || Actividades Professor || Actividades Aluno || Métodos || Meios

                Gere a tabela com ESTAS 4 FUNÇÕES DIDÁTICAS (uma por linha):
                1. Introdução e Motivação
                2. Mediação e Assimilação
                3. Domínio e Consolidação
                4. Controlo e Avaliação

                REGRAS DE PREENCHIMENTO:
                - Coluna 'Tempo': Coloque APENAS os minutos (ex: 5', 10', 15'). Não escreva texto.
                - Coluna 'Função Didática': Use exatamente os nomes listados acima.
                - Conteúdo e Actividades: Detalhados e centrados no aluno.
                - TPC: Deve aparecer na fase de Controlo e Avaliação (Marcação).

                SAÍDA:
                [BLOCO_OBJETIVOS]...[FIM_OBJETIVOS]
                [BLOCO_TABELA]
                ...linhas da tabela...
                [FIM_TABELA]
                """
                
                response = model.generate_content(prompt)
                text = response.text
                
                objs = "..."
                if "[BLOCO_OBJETIVOS]" in text:
                    objs = text.split("[BLOCO_OBJETIVOS]")[1].split("[FIM_OBJETIVOS]")[0].strip()
                
                dados = []
                if "[BLOCO_TABELA]" in text:
                    lines = text.split("[BLOCO_TABELA]")[1].split("[FIM_TABELA]")[0].strip().split('\n')
                    for l in lines:
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

# --- RESULTADOS ---
if st.session_state.get('res_pdf'):
    st.divider()
    st.success("✅ Plano Elaborado!")
    
    pdf_data = create_pdf(st.session_state['i'], st.session_state['d'], st.session_state['o'])
    st.download_button("📄 BAIXAR PDF (A4 HORIZONTAL)", data=pdf_data, file_name="Plano_Aula.pdf", mime="application/pdf", type="primary")
    
    if st.session_state['d']:
        df = pd.DataFrame(st.session_state['d'], columns=["Tempo", "F. Didática", "Conteúdo", "Prof", "Aluno", "Métodos", "Meios"])
        st.dataframe(df, hide_index=True)
    
    if st.button("🔄 Novo Plano"):
        st.session_state['res_pdf'] = False
        st.rerun()
