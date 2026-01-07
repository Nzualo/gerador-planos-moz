import streamlit as st
import google.generativeai as genai
from fpdf import FPDF
import pandas as pd
from PIL import Image
import time

# --- CONFIGURAÇÃO INICIAL ---
st.set_page_config(page_title="SDEJT - Planos SNE", page_icon="🇲🇿", layout="wide")

# --- ESTILO VISUAL (DARK MODE) ---
st.markdown("""
<style>
    .stApp { background-color: #0E1117; color: #FAFAFA; }
    .stTextInput > div > div > input, .stSelectbox > div > div > div, .stTextArea > div > div > textarea { color: #ffffff; }
    h1, h2, h3 { color: #FF4B4B !important; }
    .stFileUploader { background-color: #1E1E1E; border: 2px dashed #FF4B4B; border-radius: 10px; padding: 10px; }
</style>
""", unsafe_allow_html=True)

# --- LOGIN E SUPORTE ---
def check_password():
    if st.session_state.get("password_correct", False): return True
    st.markdown("## 🇲🇿 SDEJT - Elaboração de Planos")
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
    with col2:
        st.warning("⚠️ Suporte Técnico")
        meu_numero = "258867926665"
        mensagem = "Saudações técnico Nzualo. Gostaria de solicitar acesso ao Gerador de Planos de Aulas."
        link_zap = f"https://wa.me/{meu_numero}?text={mensagem.replace(' ', '%20')}"
        st.markdown(f'''<a href="{link_zap}" target="_blank" style="text-decoration: none;"><button style="background-color:#25D366; color:white; border:none; padding:15px 25px; border-radius:8px; width:100%; cursor:pointer; font-size: 16px; font-weight:bold;">📱 Falar no WhatsApp</button></a>''', unsafe_allow_html=True)
    return False

if not check_password(): st.stop()

# --- CLASSE PDF (FOCO NO PREENCHIMENTO MANUAL) ---
class PDF(FPDF):
    def header(self):
        self.set_font('Arial', 'B', 12); self.cell(0, 5, 'REPÚBLICA DE MOÇAMBIQUE', 0, 1, 'C')
        self.set_font('Arial', 'B', 10); self.cell(0, 5, 'GOVERNO DO DISTRITO DE INHASSORO', 0, 1, 'C')
        self.ln(5); self.set_font('Arial', 'B', 14); self.cell(0, 10, 'PLANO DE AULA', 0, 1, 'C'); self.ln(2)
    def footer(self):
        self.set_y(-15); self.set_font('Arial', 'I', 6); self.cell(0, 10, 'SDEJT Inhassoro - Processado por IA', 0, 0, 'C')
    def clean_text(self, text):
        return str(text).encode('latin-1', 'replace').decode('latin-1')
    def draw_table_header(self, widths):
        headers = ["TEMPO", "F. DIDÁTICA", "ACTIV. PROFESSOR", "ACTIV. ALUNO", "MÉTODOS", "MEIOS"]
        self.set_font("Arial", "B", 7); self.set_fill_color(220, 220, 220)
        for i, h in enumerate(headers): self.cell(widths[i], 6, h, 1, 0, 'C', True)
        self.ln()
    def table_row(self, data, widths):
        row_data = [self.clean_text(d) for d in data]; max_lines = 1
        for i, text in enumerate(row_data):
            lines = self.multi_cell(widths[i], 4, text, split_only=True)
            if len(lines) > max_lines: max_lines = len(lines)
        height = max_lines * 4 + 4
        if self.get_y() + height > 270: self.add_page(); self.draw_table_header(widths)
        y_start = self.get_y(); x_start = 10
        for i, text in enumerate(row_data):
            self.set_xy(x_start, y_start); self.multi_cell(widths[i], 4, text, align='L')
            x_start += widths[i]
        x_curr = 10
        for w in widths: self.rect(x_curr, y_start, w, height); x_curr += w
        self.set_y(y_start + height)

def create_pdf(inputs, dados, obj_geral, obj_especificos):
    pdf = PDF(); pdf.set_auto_page_break(auto=False); pdf.add_page()
    pdf.set_font("Arial", size=10)
    pdf.cell(130, 7, f"Escola: __________________________________________________", 0, 0)
    pdf.cell(0, 7, f"Data: ____/____/2026", 0, 1)
    pdf.cell(0, 7, f"Unidade Temática: ____________________________________________________________________", 0, 1)
    pdf.set_font("Arial", "B", 10); pdf.cell(0, 7, f"Tema: {pdf.clean_text(inputs['tema'])}", 0, 1)
    pdf.set_font("Arial", size=10)
    pdf.cell(100, 7, f"Professor: ______________________________", 0, 0)
    pdf.cell(50, 7, f"Turma: {inputs['turma']}", 0, 0)
    pdf.cell(0, 7, f"Duração: {inputs['duracao']}", 0, 1)
    pdf.cell(100, 7, f"Tipo de Aula: {pdf.clean_text(inputs['tipo_aula'])}", 0, 0)
    pdf.cell(0, 7, f"Nº Alunos: M_____  F_____  Total:_____", 0, 1)
    pdf.line(10, pdf.get_y()+2, 200, pdf.get_y()+2); pdf.ln(5)
    
    pdf.set_font("Arial", "B", 10); pdf.cell(40, 6, "OBJETIVO GERAL:", 0, 0)
    pdf.set_font("Arial", size=10); pdf.set_xy(50, pdf.get_y()); pdf.multi_cell(0, 6, pdf.clean_text(obj_geral)); pdf.ln(2)
    pdf.set_font("Arial", "B", 9); pdf.cell(0, 6, "OBJECTIVOS ESPECÍRICOS:", 0, 1)
    pdf.set_font("Arial", size=9); pdf.multi_cell(0, 5, pdf.clean_text(obj_especificos)); pdf.ln(5)
    
    widths = [12, 40, 45, 45, 23, 25]; pdf.draw_table_header(widths)
    for row in dados: pdf.table_row(row, widths)
    return pdf.output(dest='S').encode('latin-1', 'replace')

# --- LÓGICA DE GERAÇÃO (FIXANDO AS 4 FUNÇÕES) ---
def gerar_plano(instrucoes_arquivo="", instrucoes_ajuste="", arquivo=None):
    progress_bar = st.progress(0); status_text = st.empty()
    try:
        status_text.text("Acionando Gemini 2.5 Flash..."); progress_bar.progress(10)
        genai.configure(api_key=st.secrets["GOOGLE_API_KEY"])
        model = genai.GenerativeModel('gemini-2.5-flash')
        
        # LÓGICA DE OBJETIVOS POR TEMPO
        qtd_geral = "2 (Dois)" if "90" in st.session_state['tmp_duracao'] else "1 (Um)"
        qtd_espec = "5 (Cinco)" if "90" in st.session_state['tmp_duracao'] else "3 (Três)"

        prompt = f"""Aja como Pedagogo do SNE Moçambique. Gere um plano técnico detalhado.
        Disciplina: {st.session_state['tmp_disciplina']}, Classe: {st.session_state['tmp_classe']}, Tema: {st.session_state['tmp_tema']}.
        Duração: {st.session_state['tmp_duracao']}.
        
        REGRAS INQUEBRÁVEIS:
        1. A tabela DEVE ter EXATAMENTE 4 LINHAS, uma para cada função didática:
           - 1. Introdução e Motivação
           - 2. Mediação e Assimilação
           - 3. Domínio e Consolidação
           - 4. Controlo e Avaliação
        2. COLUNAS (Exatamente 6): Tempo || Função Didática || Actividade Professor || Actividade Aluno || Métodos || Meios.
        3. OBJETIVOS: Verbos no infinitivo. Geral: {qtd_geral}. Específicos: Máximo {qtd_espec}.
        4. DETALHAMENTO: Descreva minuciosamente as ações do professor e as reações do aluno.
        5. NÃO inclua textos de identificação (Escola, Professor) no corpo do plano.
        
        SAÍDA:
        [BLOCO_GERAL] (Texto) [FIM_GERAL]
        [BLOCO_ESPECIFICOS] (Lista) [FIM_ESPECIFICOS]
        [BLOCO_TABELA]
        Tempo || Função || Actividade Professor (Detalhada) || Actividade Aluno (Detalhada) || Métodos || Meios
        [FIM_TABELA]
        """

        conteudo = [prompt]
        if arquivo:
            if arquivo.type in ['image/png', 'image/jpeg']: conteudo.append(Image.open(arquivo))
            else: conteudo.append({"mime_type": "application/pdf", "data": arquivo.getvalue()})

        progress_bar.progress(50); status_text.text("Estruturando as 4 funções didáticas...")
        response = model.generate_content(conteudo)
        
        progress_bar.progress(90); texto = response.text
        
        st.session_state['obj_geral'] = texto.split("[BLOCO_GERAL]")[1].split("[FIM_GERAL]")[0].strip()
        st.session_state['obj_especificos'] = texto.split("[BLOCO_ESPECIFICOS]")[1].split("[FIM_ESPECIFICOS]")[0].strip()
        
        dados = []
        if "[BLOCO_TABELA]" in texto:
            block = texto.split("[BLOCO_TABELA]")[1].split("[FIM_TABELA]")[0].strip()
            for l in block.split('\n'):
                if "||" in l and "Função" not in l:
                    cols = [c.strip() for c in l.split("||")]
                    while len(cols) < 6: cols.append("-")
                    dados.append(cols[:6])
        
        st.session_state['dados_pdf'] = dados; st.session_state['plano_pronto'] = True
        progress_bar.progress(100); time.sleep(1); status_text.empty(); progress_bar.empty()
    except Exception as e:
        progress_bar.empty(); status_text.empty()
        st.error(f"Erro: {e}")

# --- INTERFACE ---
st.title("🇲🇿 Elaboração de Planos de Aulas")

col1, col2 = st.columns(2)
with col1:
    st.text_input("Disciplina", "Língua Portuguesa", key='tmp_disciplina')
    st.selectbox("Classe", ["1ª", "2ª", "3ª", "4ª", "5ª", "6ª", "7ª", "8ª", "9ª", "10ª", "11ª", "12ª"], key='tmp_classe')
with col2:
    st.selectbox("Duração", ["45 Min", "90 Min"], key='tmp_duracao')
    st.text_input("Tema da Aula", key='tmp_tema')

st.markdown("### 📚 Material de Apoio (Opcional)")
arquivo_enviado = st.file_uploader("Carregar PDF ou Foto do Livro", type=['pdf', 'png', 'jpg', 'jpeg'])
comando_ia = st.text_input("🤖 Comando específico para a IA", placeholder="Ex: Use o conteúdo da pág. 12 do livro enviado.")

tipo_aula = st.selectbox("Tipo de Aula", ["Introdução de Matéria Nova", "Consolidação", "Revisão"], key='tmp_tipo_aula')

if st.button("🚀 Gerar Plano Completo", type="primary", use_container_width=True):
    gerar_plano(instrucoes_arquivo=comando_ia, arquivo=arquivo_enviado)

if st.session_state.get('plano_pronto'):
    st.divider()
    st.subheader("📋 Pré-visualização")
    st.info(f"**Objetivo Geral:** {st.session_state['obj_geral']}")
    df = pd.DataFrame(st.session_state['dados_pdf'], columns=["Tempo", "F. Didática", "Prof", "Aluno", "Métodos", "Meios"])
    st.dataframe(df, hide_index=True, use_container_width=True)

    inputs = {'tema': st.session_state.get('tmp_tema',''), 'turma': 'A', 'duracao': st.session_state.get('tmp_duracao',''), 'tipo_aula': st.session_state.get('tmp_tipo_aula',''), 'unidade': ''}
    pdf_bytes = create_pdf(inputs, st.session_state['dados_pdf'], st.session_state['obj_geral'], st.session_state['obj_especificos'])
    
    st.download_button("📄 Baixar PDF Final", data=pdf_bytes, file_name="Plano_SDEJT_Moçambique.pdf", mime="application/pdf", type="primary", use_container_width=True)
    
    st.markdown("### 🛠️ Ajustar ou Melhorar")
    ajuste_texto = st.text_area("O que deseja mudar no plano gerado?")
    if st.button("🔄 Aplicar Melhorias"):
        gerar_plano(instrucoes_ajuste=ajuste_texto, arquivo=arquivo_enviado); st.rerun()
