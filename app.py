import streamlit as st
import google.generativeai as genai
from fpdf import FPDF
import pandas as pd
import time

# --- CONFIGURAÇÃO INICIAL (Obrigatório ser a primeira linha) ---
st.set_page_config(page_title="SDEJT Inhassoro", page_icon="🇲🇿", layout="wide")

# --- ESTILO VISUAL (CSS PREMIUM) ---
st.markdown("""
    <style>
    /* Fundo geral e fontes */
    .stApp {
        background-color: #f8f9fa;
        font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
    }
    
    /* Cabeçalhos */
    h1, h2, h3 {
        color: #0e4d46; /* Verde SNE Escuro */
        font-weight: 700;
    }
    
    /* Caixas (Containers) com efeito de cartão */
    div[data-testid="stVerticalBlock"] > div[style*="flex-direction: column;"] > div[data-testid="stVerticalBlock"] {
        /* Apenas um ajuste fino para containers internos */
    }

    /* Botões Primários (Gerar/Entrar) */
    div.stButton > button:first-child {
        background-color: #0e4d46;
        color: white;
        border-radius: 8px;
        border: none;
        padding: 10px 24px;
        font-weight: bold;
        transition: all 0.3s ease;
    }
    div.stButton > button:first-child:hover {
        background-color: #146c62; /* Verde mais claro ao passar o mouse */
        transform: scale(1.02);
    }
    
    /* Inputs (Caixas de texto) */
    .stTextInput > div > div > input {
        border-radius: 8px;
        border: 1px solid #ced4da;
    }
    
    /* Sidebar */
    section[data-testid="stSidebar"] {
        background-color: #ffffff;
        border-right: 1px solid #e9ecef;
    }
    
    /* Remove marca d'água do Streamlit */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    </style>
    """, unsafe_allow_html=True)

# --- FUNÇÃO DE LOGIN E SEGURANÇA ---
def check_password():
    if st.session_state.get("password_correct", False):
        return True

    # Layout de Login Centralizado e Bonito
    col_vazia1, col_centro, col_vazia2 = st.columns([1, 2, 1])
    
    with col_centro:
        with st.container(border=True): # Cria uma caixa bonita
            st.markdown("<h2 style='text-align: center;'>🇲🇿 SDEJT Inhassoro</h2>", unsafe_allow_html=True)
            st.markdown("<h4 style='text-align: center; color: #666;'>Sistema de Elaboração de Planos</h4>", unsafe_allow_html=True)
            st.divider()
            
            st.info("🔐 **Acesso Restrito**")
            usuario = st.text_input("Nome de Usuário")
            senha = st.text_input("Senha de Acesso", type="password")
            
            if st.button("Entrar no Sistema", type="primary", use_container_width=True):
                if "passwords" in st.secrets and usuario in st.secrets["passwords"]:
                    if st.secrets["passwords"][usuario] == senha:
                        st.session_state["password_correct"] = True
                        st.session_state["user_name"] = usuario
                        st.rerun()
                    else:
                        st.error("🚫 Senha incorreta.")
                else:
                    st.error("🚫 Usuário não encontrado.")

            st.divider()
            st.markdown("<div style='text-align: center; color: grey; font-size: 0.8em;'>Não tem acesso?</div>", unsafe_allow_html=True)
            
            # Botão WhatsApp
            meu_numero = "258867926665"
            mensagem = "Olá Técnico Nzualo, gostaria de solicitar acesso ao Gerador de Planos."
            link_zap = f"https://wa.me/{meu_numero}?text={mensagem.replace(' ', '%20')}"
            
            st.markdown(f'''
                <a href="{link_zap}" target="_blank" style="text-decoration: none;">
                    <button style="
                        background-color: #25D366; 
                        color: white; 
                        border: none; 
                        padding: 8px; 
                        border-radius: 5px; 
                        width: 100%; 
                        cursor: pointer; 
                        font-weight: bold;
                        margin-top: 5px;">
                        📱 Solicitar Senha via WhatsApp
                    </button>
                </a>
                ''', unsafe_allow_html=True)
    return False

if not check_password():
    st.stop()

# --- BARRA LATERAL ---
with st.sidebar:
    st.image("https://upload.wikimedia.org/wikipedia/commons/thumb/a/a2/Emblem_of_Mozambique.svg/1200px-Emblem_of_Mozambique.svg.png", width=80)
    st.markdown("### Painel do Usuário")
    st.write(f"Bem-vindo, **{st.session_state['user_name']}**!")
    st.divider()
    if st.button("🚪 Sair / Logout"):
        st.session_state["password_correct"] = False
        st.rerun()
    st.markdown("---")
    st.markdown("<small>Desenvolvido para SDEJT Inhassoro</small>", unsafe_allow_html=True)

# --- CLASSE PDF (LINHAS PERFEITAS) ---
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
        self.cell(0, 10, 'SDEJT Inhassoro - Processado por IA', 0, 0, 'C')

    def table_row(self, data, widths):
        max_lines = 1
        for i, text in enumerate(data):
            self.set_font("Arial", size=8)
            texto_seguro = str(text) if text is not None else ""
            lines = self.multi_cell(widths[i], 4, texto_seguro, split_only=True)
            if len(lines) > max_lines: max_lines = len(lines)
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
            texto_seguro = str(text) if text is not None else ""
            self.multi_cell(widths[i], 4, texto_seguro, border=0)
            x_start += widths[i]
        self.set_xy(10, y_start)
        x_curr = 10
        for w in widths:
            self.rect(x_curr, y_start, w, height)
            x_curr += w
        self.set_y(y_start + height)

def create_pdf(inputs, dados, objetivos):
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
    pdf.multi_cell(0, 5, objetivos)
    pdf.ln(5)
    widths = [12, 28, 35, 35, 35, 22, 23]
    headers = ["TEMPO", "F. DIDÁTICA", "CONTEÚDO", "ACTIV. PROFESSOR", "ACTIV. ALUNO", "MÉTODOS", "MEIOS"]
    pdf.set_font("Arial", "B", 7)
    pdf.set_fill_color(230, 230, 230)
    for i, h in enumerate(headers):
        pdf.cell(widths[i], 6, h, 1, 0, 'C', True)
    pdf.ln()
    for row in dados:
        pdf.table_row(row, widths)
    return pdf.output(dest='S').encode('latin-1', 'ignore')

# --- TÍTULO PRINCIPAL E LAYOUT ---
st.title("🇲🇿 Elaboração de Planos de Aulas")
st.markdown("Preencha os dados abaixo para gerar o plano oficial do SDEJT.")

if "GOOGLE_API_KEY" not in st.secrets:
    st.error("⚠️ Erro: Configure os Secrets!")
    st.stop()

# --- FORMULÁRIO (DENTRO DE UM CARTÃO PARA FICAR BONITO) ---
with st.container(border=True):
    st.markdown("### 📝 Dados da Aula")
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

    st.markdown("") # Espaço vazio
    # Botão ocupa toda a largura
    if st.button("🚀 Gerar Plano (PDF Oficial)", type="primary", use_container_width=True):
        with st.spinner('A elaborar o plano pedagógico...'):
            try:
                genai.configure(api_key=st.secrets["GOOGLE_API_KEY"])
                model = genai.GenerativeModel('models/gemini-2.5-flash')
                prompt = f"""
                Aja como Pedagogo do SNE Moçambique.
                Plano: {disciplina}, {classe}, Tema: {tema}.
                REGRAS: 1. TPC: Correção (Início), Marcação (Fim). 2. OBJETIVOS: Max 3. 3. TABELA: Separada por "||".
                SAÍDA: [BLOCO_OBJETIVOS]...[FIM_OBJETIVOS] [BLOCO_TABELA]...[FIM_TABELA]
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
                            cols = cols[:7] 
                            dados.append(cols)
                
                # Salvar sessão
                st.session_state['plano_pronto'] = True
                st.session_state['dados_pdf'] = dados
                st.session_state['objs_pdf'] = objetivos
                st.session_state['inputs_pdf'] = {'disciplina': disciplina, 'classe': classe, 'duracao': duracao, 'tema': tema, 'unidade': unidade, 'tipo_aula': tipo_aula, 'turma': turma}
                st.rerun()
            except Exception as e:
                st.error(f"Erro: {e}")

# --- MOSTRAR RESULTADO ---
if st.session_state.get('plano_pronto'):
    st.divider()
    
    # Caixa verde de sucesso
    st.success("✅ Plano gerado com sucesso! Verifique os dados abaixo.")
    
    dados = st.session_state['dados_pdf']
    objetivos = st.session_state['objs_pdf']
    inputs = st.session_state['inputs_pdf']
    
    with st.expander("👁️ Ver Objetivos da Aula", expanded=True):
        st.write(objetivos)
    
    if dados:
        # Tabela visual
        st.markdown("#### Tabela de Planificação")
        df = pd.DataFrame(dados, columns=["Tempo", "Função", "Conteúdo", "Prof", "Aluno", "Métodos", "Meios"])
        st.dataframe(df, hide_index=True, use_container_width=True)
        
        st.markdown("### 📥 Baixar Documento")
        c1, c2 = st.columns([1, 1])
        with c1:
            try:
                pdf_bytes = create_pdf(inputs, dados, objetivos)
                st.download_button("📄 Baixar PDF Oficial (Para Imprimir)", data=pdf_bytes, file_name=f"Plano_{inputs['disciplina']}.pdf", mime="application/pdf", type="primary", use_container_width=True)
            except Exception as e:
                st.error(f"Erro PDF: {e}")
        
        with c2:
            if st.button("🔄 Criar Novo Plano", use_container_width=True):
                st.session_state['plano_pronto'] = False
                st.rerun()
