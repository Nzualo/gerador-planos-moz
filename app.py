import streamlit as st
import google.generativeai as genai
from fpdf import FPDF
import pandas as pd

# --- CONFIGURAÇÃO INICIAL ---
st.set_page_config(page_title="SDEJT - Planos SNE", page_icon="🇲🇿", layout="wide")

# --- ESTILO VISUAL (DARK MODE) ---
st.markdown("""
<style>
    .stApp { background-color: #0E1117; color: #FAFAFA; }
    [data-testid="stSidebar"] { background-color: #262730; }
    .stTextInput > div > div > input, .stSelectbox > div > div > div { color: #ffffff; }
    h1, h2, h3 { color: #FF4B4B !important; }
</style>
""", unsafe_allow_html=True)

# --- FUNÇÃO DE LOGIN ---
def check_password():
    if st.session_state.get("password_correct", False):
        return True

    st.markdown("## 🇲🇿 SDEJT - Elaboração de Planos")
    st.markdown("##### Serviço Distrital de Educação, Juventude e Tecnologia - Inhassoro")
    st.divider()
    
    col1, col2 = st.columns([1, 1])
    with col1:
        st.info("🔐 Acesso Restrito")
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
    with col2:
        st.warning("⚠️ Suporte")
        st.write("Contacte a Repartição de Educação Geral.")
    return False

if not check_password():
    st.stop()

# --- BARRA LATERAL ---
with st.sidebar:
    st.success(f"👤 Técnico: **{st.session_state['user_name']}**")
    if st.button("Sair"):
        st.session_state["password_correct"] = False
        st.rerun()

# --- CLASSE PDF ---
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

    def clean_text(self, text):
        if text is None: return ""
        replacements = {'–': '-', '“': '"', '”': '"', '‘': "'", '’': "'", '…': '...', '•': '-'}
        text = str(text)
        for k, v in replacements.items():
            text = text.replace(k, v)
        return text

    def table_row(self, data, widths):
        data = [self.clean_text(d) for d in data]
        max_lines = 1
        for i, text in enumerate(data):
            self.set_font("Arial", size=8)
            lines = self.multi_cell(widths[i], 4, text, split_only=True)
            if len(lines) > max_lines: max_lines = len(lines)
        
        height = max_lines * 4 + 4
        if self.get_y() + height > 270:
            self.add_page()
            self.draw_table_header(widths)

        x_start = self.get_x()
        y_start = self.get_y()
        for i, text in enumerate(data):
            self.set_xy(x_start, y_start)
            self.set_font("Arial", size=8)
            self.multi_cell(widths[i], 4, text, border=0)
            x_start += widths[i]

        self.set_xy(10, y_start)
        x_curr = 10
        for w in widths:
            self.rect(x_curr, y_start, w, height)
            x_curr += w
        self.set_y(y_start + height)

    def draw_table_header(self, widths):
        headers = ["TEMPO", "F. DIDÁTICA", "CONTEÚDO", "ACTIV. PROFESSOR", "ACTIV. ALUNO", "MÉTODOS", "MEIOS"]
        self.set_font("Arial", "B", 7)
        self.set_fill_color(220, 220, 220)
        for i, h in enumerate(headers):
            self.cell(widths[i], 6, h, 1, 0, 'C', True)
        self.ln()

def create_pdf(inputs, dados, obj_geral, obj_especificos):
    pdf = PDF()
    pdf.set_auto_page_break(auto=False)
    pdf.add_page()
    
    # --- CABEÇALHO DADOS ---
    pdf.set_font("Arial", size=10)
    pdf.cell(130, 7, f"Escola: __________________________________________________", 0, 0)
    pdf.cell(0, 7, f"Data: ____/____/2026", 0, 1)
    
    pdf.cell(0, 7, f"Unidade Temática: {pdf.clean_text(inputs['unidade'])}", 0, 1)
    pdf.set_font("Arial", "B", 10)
    pdf.cell(0, 7, f"Tema: {pdf.clean_text(inputs['tema'])}", 0, 1)
    
    pdf.set_font("Arial", size=10)
    pdf.cell(100, 7, f"Professor: ______________________________", 0, 0)
    pdf.cell(50, 7, f"Turma: {inputs['turma']}", 0, 0)
    pdf.cell(0, 7, f"Duração: {inputs['duracao']}", 0, 1)
    pdf.cell(100, 7, f"Tipo de Aula: {pdf.clean_text(inputs['tipo_aula'])}", 0, 0)
    pdf.cell(0, 7, f"Nº Alunos: M_____  F_____  Total:_____", 0, 1)
    
    pdf.line(10, pdf.get_y()+2, 200, pdf.get_y()+2)
    pdf.ln(5)

    # --- OBJETIVOS (ATUALIZADO) ---
    pdf.set_font("Arial", "B", 10)
    pdf.cell(40, 6, "OBJETIVO GERAL:", 0, 0)
    pdf.set_font("Arial", size=10)
    # Multi cell para o objetivo geral caso seja longo
    curr_y = pdf.get_y()
    pdf.set_xy(50, curr_y)
    pdf.multi_cell(0, 6, pdf.clean_text(obj_geral))
    pdf.ln(2)

    pdf.set_font("Arial", "B", 9)
    pdf.cell(0, 6, "OBJECTIVOS ESPECÍFICOS:", 0, 1)
    pdf.set_font("Arial", size=9)
    pdf.multi_cell(0, 5, pdf.clean_text(obj_especificos))
    pdf.ln(5)

    # --- TABELA ---
    widths = [12, 35, 30, 35, 35, 20, 20]
    pdf.draw_table_header(widths)
    for row in dados:
        pdf.table_row(row, widths)
    return pdf.output(dest='S').encode('latin-1', 'replace')

# --- TÍTULO ---
st.title("🇲🇿 Elaboração de Planos de Aulas")

if "GOOGLE_API_KEY" not in st.secrets:
    st.error("⚠️ ERRO: Configure os Secrets!")
    st.stop()

# --- INPUTS ---
col1, col2 = st.columns(2)
with col1:
    disciplina = st.text_input("Disciplina", "Língua Portuguesa")
    classe = st.selectbox("Classe", ["1ª", "2ª", "3ª", "4ª", "5ª", "6ª", "7ª", "8ª", "9ª", "10ª", "11ª", "12ª"])
    unidade = st.text_input("Unidade", placeholder="Ex: Textos Normativos")
    tipo_aula = st.selectbox("Tipo de Aula", ["Introdução de Matéria Nova", "Consolidação e Exercitação", "Verificação e Avaliação", "Revisão"])

with col2:
    duracao = st.selectbox("Duração", ["45 Min", "90 Min"])
    turma = st.text_input("Turma", placeholder="A")
    tema = st.text_input("Tema", placeholder="Ex: Vogais")

# --- GERAÇÃO IA ---
if st.button("🚀 Gerar Plano (Alinhado ao Programa)", type="primary"):
    with st.spinner('A consultar os Programas de Ensino de Moçambique...'):
        try:
            genai.configure(api_key=st.secrets["GOOGLE_API_KEY"])
            
            # MODELO MANTIDO (Gemini 2.5 Flash)
            model = genai.GenerativeModel('models/gemini-2.5-flash') 
            
            prompt = f"""
            Aja como Pedagogo Especialista do SNE (Sistema Nacional de Educação) de Moçambique.
            Elabore um plano de aula rigorosamente alinhado aos Programas de Ensino vigentes (Primário ou Secundário conforme a classe).
            
            DADOS: Disciplina: {disciplina}, Classe: {classe}, Tema: {tema}, Duração: {duracao}.

            REGRAS PEDAGÓGICAS ESTRITAS:
            1. OBJETIVOS: Devem começar OBRIGATORIAMENTE com VERBOS NO INFINITIVO (Ex: Identificar, Descrever, Calcular).
            2. ALINHAMENTO: O nível de profundidade deve corresponder exatamente ao programa da {classe} Classe em Moçambique.
            3. ESTRUTURA: Incluir 1 Objetivo Geral e até 3 Específicos.
            4. TABELA: Deve ter EXATAMENTE 4 etapas (Funções Didáticas):
               1. Introdução e Motivação
               2. Mediação e Assimilação
               3. Domínio e Consolidação
               4. Controlo e Avaliação
            5. TEMPO: Apenas números na coluna tempo.

            SAÍDA ESPERADA (Não use markdown, use apenas os blocos):
            
            [BLOCO_GERAL]
            Compreender... (Verbo no Infinitivo)
            [FIM_GERAL]

            [BLOCO_ESPECIFICOS]
            - Identificar...
            - Diferenciar...
            [FIM_ESPECIFICOS]
            
            [BLOCO_TABELA]
            5 || 1. Introdução e Motivação || ...
            15 || 2. Mediação e Assimilação || ...
            [FIM_TABELA]
            """
            
            response = model.generate_content(prompt)
            texto = response.text
            
            # Variáveis
            obj_geral = "Não definido"
            obj_especificos = ""
            dados = []
            
            # Extração segura
            if "[BLOCO_GERAL]" in texto:
                obj_geral = texto.split("[BLOCO_GERAL]")[1].split("[FIM_GERAL]")[0].strip()
            
            if "[BLOCO_ESPECIFICOS]" in texto:
                obj_especificos = texto.split("[BLOCO_ESPECIFICOS]")[1].split("[FIM_ESPECIFICOS]")[0].strip()
            # Caso a IA use o formato antigo por engano
            elif "[BLOCO_OBJETIVOS]" in texto:
                obj_especificos = texto.split("[BLOCO_OBJETIVOS]")[1].split("[FIM_OBJETIVOS]")[0].strip()

            if "[BLOCO_TABELA]" in texto:
                block = texto.split("[BLOCO_TABELA]")[1].split("[FIM_TABELA]")[0].strip()
                lines = block.split('\n')
                for l in lines:
                    if "||" in l and "Função" not in l:
                        cols = [c.strip() for c in l.split("||")]
                        while len(cols) < 7: cols.append("-")
                        dados.append(cols[:7])
            
            st.session_state['plano_pronto'] = True
            st.session_state['dados_pdf'] = dados
            st.session_state['obj_geral'] = obj_geral
            st.session_state['obj_especificos'] = obj_especificos
            st.session_state['inputs_pdf'] = {'disciplina': disciplina, 'classe': classe, 'duracao': duracao, 'tema': tema, 'unidade': unidade, 'tipo_aula': tipo_aula, 'turma': turma}
            st.rerun()

        except Exception as e:
            st.error(f"Erro ao gerar: {e}")

# --- RESULTADO ---
if st.session_state.get('plano_pronto'):
    st.divider()
    st.subheader("✅ Plano Gerado (Padrão SNE)")
    
    dados = st.session_state['dados_pdf']
    obj_geral = st.session_state['obj_geral']
    obj_especificos = st.session_state['obj_especificos']
    inputs = st.session_state['inputs_pdf']
    
    st.markdown(f"**Objetivo Geral:** {obj_geral}")
    st.info(obj_especificos)
    
    if dados:
        df = pd.DataFrame(dados, columns=["Tempo", "F. Didática", "Conteúdo", "Prof", "Aluno", "Métodos", "Meios"])
        st.dataframe(df, hide_index=True, use_container_width=True)
        
        c1, c2 = st.columns(2)
        with c1:
            try:
                pdf_bytes = create_pdf(inputs, dados, obj_geral, obj_especificos)
                st.download_button("📄 Baixar PDF Oficial", data=pdf_bytes, file_name="Plano_Aula.pdf", mime="application/pdf", type="primary")
            except Exception as e:
                st.error(f"Erro PDF: {e}")
        with c2:
            if st.button("🔄 Novo Plano"):
                st.session_state['plano_pronto'] = False
                st.rerun()
