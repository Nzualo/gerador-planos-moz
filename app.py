import streamlit as st
import google.generativeai as genai
from fpdf import FPDF
import pandas as pd
from PIL import Image
import time

# --- CONFIGURAÇÃO INICIAL ---
st.set_page_config(page_title="SDEJT - Planos SNE", page_icon="🇲🇿", layout="wide")

# --- ESTILO VISUAL ---
st.markdown("""
<style>
    .stApp { background-color: #0E1117; color: #FAFAFA; }
    .stTextInput > div > div > input, .stSelectbox > div > div > div, .stTextArea > div > div > textarea { color: #ffffff; }
    h1, h2, h3 { color: #FF4B4B !important; }
    .stFileUploader { background-color: #1E1E1E; border: 2px dashed #FF4B4B; border-radius: 10px; padding: 10px; }
</style>
""", unsafe_allow_html=True)

# --- FUNÇÃO DE LOGIN ---
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
        st.warning("⚠️ Suporte")
        meu_numero = "258867926665"
        mensagem = "Saudações técnico Nzualo. Gostaria de solicitar acesso ao Gerador de Planos de Aulas."
        link_zap = f"https://wa.me/{meu_numero}?text={mensagem.replace(' ', '%20')}"
        st.markdown(f'''<a href="{link_zap}" target="_blank" style="text-decoration: none;"><button style="background-color:#25D366; color:white; border:none; padding:15px 25px; border-radius:8px; width:100%; cursor:pointer; font-size: 16px; font-weight:bold;">📱 Falar no WhatsApp</button></a>''', unsafe_allow_html=True)
    return False

if not check_password(): st.stop()

# --- CLASSE PDF ---
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

# --- LÓGICA DE GERAÇÃO ---
def gerar_plano(instrucoes_arquivo="", instrucoes_ajuste="", arquivo=None):
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    try:
        status_text.text("Iniciando IA avançada...")
        progress_bar.progress(10)
        genai.configure(api_key=st.secrets["GOOGLE_API_KEY"])
        
        # FIXO NO MODELO GEMINI 2.5 FLASH
        model = genai.GenerativeModel('gemini-2.5-flash')
        
        duracao = st.session_state['tmp_duracao']
        prompt = f"""Aja como Pedagogo do SNE Moçambique. Disciplina: {st.session_state['tmp_disciplina']}, Tema: {st.session_state['tmp_tema']}.
        Duração: {duracao}. Classe: {st.session_state['tmp_classe']}.
        COMANDO PARA O ARQUIVO: {instrucoes_arquivo}
        COMANDO DE AJUSTE: {instrucoes_ajuste}
        SAÍDA: [BLOCO_GERAL]...[FIM_GERAL] [BLOCO_ESPECIFICOS]...[FIM_ESPECIFICOS] [BLOCO_TABELA]...[FIM_TABELA]
        Regras: Use 6 colunas (Tempo, Função, Act. Prof, Act. Aluno, Métodos, Meios) separadas por ||."""

        conteudo = [prompt]
        if arquivo:
            if arquivo.type in ['image/png', 'image/jpeg']: conteudo.append(Image.open(arquivo))
            else: conteudo.append({"mime_type": "application/pdf", "data": arquivo.getvalue()})

        progress_bar.progress(40)
        status_text.text("Analisando documentos e estruturando didática...")
        
        response = model.generate_content(conteudo)
        
        progress_bar.progress(85)
        status_text.text("Processando tabelas detalhadas...")
        
        texto = response.text
        st.session_state['obj_geral'] = texto.split("[BLOCO_GERAL]")[1].split("[FIM_GERAL]")[0].strip() if "[BLOCO_GERAL]" in texto else ""
        st.session_state['obj_especificos'] = texto.split("[BLOCO_ESPECIFICOS]")[1].split("[FIM_ESPECIFICOS]")[0].strip() if "[BLOCO_ESPECIFICOS]" in texto else ""
        
        dados = []
        if "[BLOCO_TABELA]" in texto:
            block = texto.split("[BLOCO_TABELA]")[1].split("[FIM_TABELA]")[0].strip()
            for l in block.split('\n'):
                if "||" in l:
                    cols = [c.strip() for c in l.split("||")]
                    while len(cols) < 6: cols.append("-")
                    dados.append(cols[:6])
        
        st.session_state['dados_pdf'] = dados
        st.session_state['plano_pronto'] = True
        progress_bar.progress(100)
        status_text.text("Concluído!")
        time.sleep(1)
        status_text.empty()
        progress_bar.empty()

    except Exception as e:
        progress_bar.empty()
        status_text.empty()
        if "429" in str(e): 
            st.error("⚠️ Limite de quota atingido. Aguarde cerca de 30 segundos e tente novamente.")
        elif "404" in str(e):
            st.error("⚠️ Erro de versão do modelo. Contacte o administrador para atualizar a biblioteca.")
        else: 
            st.error(f"Erro inesperado: {e}")

# --- INTERFACE ---
st.title("🇲🇿 Elaboração de Planos de Aulas")

col1, col2 = st.columns(2)
with col1:
    st.text_input("Disciplina", "Língua Portuguesa", key='tmp_disciplina')
    st.selectbox("Classe", ["1ª", "2ª", "3ª", "4ª", "5ª", "6ª", "7ª", "8ª", "9ª", "10ª", "11ª", "12ª"], key='tmp_classe')
with col2:
    st.selectbox("Duração", ["45 Min", "90 Min"], key='tmp_duracao')
    st.text_input("Tema", placeholder="Ex: Vogais", key='tmp_tema')

st.markdown("### 📚 Material de Apoio (Opcional)")
arquivo_enviado = st.file_uploader("Carregar PDF ou Foto do Livro", type=['pdf', 'png', 'jpg', 'jpeg'])
comando_ia_arquivo = st.text_input("🤖 Comando para a IA sobre o ficheiro", placeholder="Ex: Use o texto da página 5 para os exercícios...")

if st.button("🚀 Gerar Plano de Aula", type="primary", use_container_width=True):
    gerar_plano(instrucoes_arquivo=comando_ia_arquivo, arquivo=arquivo_enviado)

if st.session_state.get('plano_pronto'):
    st.divider()
    st.info(f"**Geral:** {st.session_state['obj_geral']}")
    if st.session_state['dados_pdf']:
        df = pd.DataFrame(st.session_state['dados_pdf'], columns=["Tempo", "F. Didática", "Prof", "Aluno", "Métodos", "Meios"])
        st.dataframe(df, hide_index=True, use_container_width=True)

    st.markdown("### 🛠️ Ajustar ou Melhorar")
    ajuste = st.text_area("O que deseja mudar no plano gerado?", key="campo_ajuste")
    
    c1, c2 = st.columns(2)
    with c1:
        if st.button("🔄 Aplicar Ajustes", use_container_width=True):
            gerar_plano(instrucoes_ajuste=ajuste, arquivo=arquivo_enviado); st.rerun()
    with c2:
        if st.button("🗑️ Novo Plano", use_container_width=True):
            st.session_state['plano_pronto'] = False; st.rerun()
