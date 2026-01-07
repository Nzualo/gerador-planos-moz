import streamlit as st
import google.generativeai as genai
from fpdf import FPDF
import pandas as pd
import time

# --- CONFIGURAÇÃO INICIAL ---
st.set_page_config(page_title="SDEJT - Planos", page_icon="🇲🇿", layout="wide")

# --- FUNÇÃO DE LOGIN E SEGURANÇA ---
def check_password():
    if st.session_state.get("password_correct", False):
        return True

    # --- TÍTULO DO LOGIN (ATUALIZADO) ---
    st.markdown("## 🇲🇿 Elaboração de Planos de Aulas")
    st.markdown("##### Serviço Distrital de Educação, Juventude e Tecnologia - Inhassoro")
    st.divider()
    
    col1, col2 = st.columns([1, 1])
    
    # Coluna 1: Login
    with col1:
        st.info("🔐 Área Restrita")
        usuario = st.text_input("Usuário")
        senha = st.text_input("Senha", type="password")
        if st.button("Entrar", type="primary"):
            if "passwords" in st.secrets and usuario in st.secrets["passwords"]:
                if st.secrets["passwords"][usuario] == senha:
                    st.session_state["password_correct"] = True
                    st.session_state["user_name"] = usuario
                    st.rerun()
                else:
                    st.error("Senha incorreta.")
            else:
                st.error("Usuário desconhecido.")

    # Coluna 2: WhatsApp
    with col2:
        st.warning("⚠️ Suporte")
        st.write("Precisa de acesso? Fale com o Administrador.")
        
        # --- MENSAGEM WHATSAPP (SEM SNE) ---
        meu_numero = "258867926665"
        mensagem = "Olá Técnico Nzualo, gostaria de solicitar acesso ao Gerador de Planos."
        link_zap = f"https://wa.me/{meu_numero}?text={mensagem.replace(' ', '%20')}"
        
        st.markdown(f'''
            <a href="{link_zap}" target="_blank">
                <button style="
                    background-color:#25D366; 
                    color:white; 
                    border:none; 
                    padding:10px 20px; 
                    border-radius:5px; 
                    width:100%; 
                    cursor:pointer;
                    font-weight:bold;">
                    📱 Contactar via WhatsApp
                </button>
            </a>
            ''', unsafe_allow_html=True)
    return False

if not check_password():
    st.stop()

# --- BARRA LATERAL ---
with st.sidebar:
    st.success(f"👤 Olá, **{st.session_state['user_name']}**")
    if st.button("Sair"):
        st.session_state["password_correct"] = False
        st.rerun()

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

# --- TÍTULO PRINCIPAL (ATUALIZADO) ---
st.title("🇲🇿 Elaboração de Planos de Aulas")

# Adicionando estilo CSS personalizado
st.markdown("""
<style>
    .main-header {
        background-color: #4CAF50;
        color: white;
        padding: 10px;
        border-radius: 10px;
        text-align: center;
        margin-bottom: 20px;
    }
    .stButton>button {
        background-color: #4CAF50;
        color: white;
        border: none;
        border-radius: 5px;
        padding: 10px 20px;
        font-weight: bold;
    }
    .stButton>button:hover {
        background-color: #45a049;
    }
    .success-box {
        background-color: #d4edda;
        border-left: 6px solid #28a745;
        padding: 15px;
        margin-bottom: 20px;
        border-radius: 5px;
    }
    .info-box {
        background-color: #d1ecf1;
        border-left: 6px solid #17a2b8;
        padding: 15px;
        margin-bottom: 20px;
        border-radius: 5px;
    }
</style>
""", unsafe_allow_html=True)

if "GOOGLE_API_KEY" not in st.secrets:
    st.error("⚠️ Erro: Configure os Secrets!")
    st.stop()

# --- FORMULÁRIO ---
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

# --- BOTÃO GERAR ---
if st.button("🚀 Gerar Plano (PDF)", type="primary"):
    with st.spinner('A elaborar o plano...'):
        try:
            genai.configure(api_key=st.secrets["GOOGLE_API_KEY"])
            model = genai.GenerativeModel('models/gemini-2.5-flash')
            prompt = f"""
            Aja como Pedagogo do SNE Moçambique.
            Plano: {disciplina}, {classe}, Tema: {tema}.
            REGRAS:
            1. TPC: Correção (Início), Marcação (Fim).
            2. OBJETIVOS: Max 3.
            3. TABELA: Separada por "||".
            4. TEMPO: Use apenas números (ex: 5, 10, 15).
            5. FUNÇÕES DIDÁTICAS: Use exatamente estas quatro:
               - Introdução e Motivação
               - Mediação e Assimilação
               - Domínio e Consolidação
               - Controlo e Avaliação
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
                        
                        # --- PROTEÇÃO PARA NÃO TRAVAR O PDF ---
                        while len(cols) < 7: cols.append("-") 
                        cols = cols[:7] 
                        
                        dados.append(cols)
            
            # SALVAR NA MEMÓRIA
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
    st.markdown('<div class="success-box"><h3>✅ Plano Gerado com Sucesso!</h3></div>', unsafe_allow_html=True)
    
    dados = st.session_state['dados_pdf']
    objetivos = st.session_state['objs_pdf']
    inputs = st.session_state['inputs_pdf']
    
    st.markdown('<div class="info-box"><h4>🎯 Objectivos Específicos:</h4></div>', unsafe_allow_html=True)
    st.info(objetivos)
    
    if dados:
        # Criar DataFrame com os dados
        df = pd.DataFrame(dados, columns=["Tempo", "Função Didática", "Conteúdo", "Activ. Professor", "Activ. Aluno", "Métodos", "Meios"])
        st.subheader("📋 Estrutura do Plano")
        st.dataframe(df, hide_index=True)
        
        # Explicação sobre as funções didáticas
        with st.expander("ℹ️ Sobre as Funções Didáticas"):
            st.markdown("""
            **As Quatro Funções Didáticas:**
            1. **Introdução e Motivação** - Apresentação do tema e envolvimento dos alunos
            2. **Mediação e Assimilação** - Desenvolvimento do conteúdo com interação
            3. **Domínio e Consolidação** - Fixação e prática dos conhecimentos
            4. **Controlo e Avaliação** - Verificação do aprendizado
            """)
        
        c1, c2 = st.columns([1, 1])
        with c1:
            try:
                pdf_bytes = create_pdf(inputs, dados, objetivos)
                st.download_button("📄 Baixar PDF Oficial", data=pdf_bytes, file_name=f"Plano_{inputs['disciplina']}.pdf", mime="application/pdf", type="primary")
            except Exception as e:
                st.error(f"Erro ao criar PDF: {e}")
        
        with c2:
            if st.button("🔄 Gerar Novo Plano"):
                st.session_state['plano_pronto'] = False
                st.rerun()
