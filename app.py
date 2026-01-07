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
    h1, h2, h3 { color: #FF4B4B !important; }
    .stFileUploader { background-color: #1E1E1E; border: 2px dashed #FF4B4B; border-radius: 10px; padding: 10px; }
    .stButton>button { width: 100%; border-radius: 8px; font-weight: bold; }
</style>
""", unsafe_allow_html=True)

# --- FUNÇÃO DE LOGIN ---
def check_password():
    if st.session_state.get("password_correct", False): return True
    st.markdown("## 🇲🇿 SDEJT - Elaboração de Planos")
    col1, col2 = st.columns(2)
    with col1:
        u = st.text_input("Usuário")
        p = st.text_input("Senha", type="password")
        if st.button("Entrar", type="primary"):
            if "passwords" in st.secrets and u in st.secrets["passwords"] and st.secrets["passwords"][u] == p:
                st.session_state["password_correct"], st.session_state["user_name"] = True, u
                st.rerun()
    with col2:
        st.warning("⚠️ Suporte: WhatsApp 258867926665")
    return False

if not check_password(): st.stop()

# --- CLASSE PDF REFORMULADA ---
class PDF(FPDF):
    def header(self):
        self.set_font('Arial', 'B', 12); self.cell(0, 5, 'REPÚBLICA DE MOÇAMBIQUE', 0, 1, 'C')
        self.set_font('Arial', 'B', 10); self.cell(0, 5, 'GOVERNO DO DISTRITO DE INHASSORO', 0, 1, 'C')
        self.ln(5); self.set_font('Arial', 'B', 14); self.cell(0, 10, 'PLANO DE AULA', 0, 1, 'C'); self.ln(2)

    def footer(self):
        self.set_y(-15); self.set_font('Arial', 'I', 6); self.cell(0, 10, 'SDEJT Inhassoro - Processado por IA', 0, 0, 'C')

    def clean_text(self, text):
        return str(text).encode('latin-1', 'replace').decode('latin-1')

    def table_row(self, data, widths):
        row_data = [self.clean_text(d) for d in data]
        max_lines = 1
        for i, text in enumerate(row_data):
            lines = self.multi_cell(widths[i], 4, text, split_only=True)
            if len(lines) > max_lines: max_lines = len(lines)
        
        height = max_lines * 4 + 4
        if self.get_y() + height > 270: self.add_page(); self.draw_header(widths)
        
        y = self.get_y(); x = 10
        for i, text in enumerate(row_data):
            self.set_xy(x, y); self.multi_cell(widths[i], 4, text, border=1, align='L')
            x += widths[i]
        self.set_y(y + height)

    def draw_header(self, widths):
        headers = ["TEMPO", "F. DIDÁTICA", "ACTIV. PROFESSOR", "ACTIV. ALUNO", "MÉTODOS", "MEIOS"]
        self.set_font("Arial", "B", 7); self.set_fill_color(220, 220, 220)
        for i, h in enumerate(headers): self.cell(widths[i], 6, h, 1, 0, 'C', True)
        self.ln()

# --- GERAÇÃO IA ---
def gerar_plano(arquivo=None, comando_extra="", ajuste=""):
    bar = st.progress(0); status = st.empty()
    try:
        status.text("Conectando ao sistema...")
        genai.configure(api_key=st.secrets["GOOGLE_API_KEY"])
        model = genai.GenerativeModel('gemini-1.5-flash')
        
        prompt = f"""Aja como Pedagogo SNE Moçambique. Disciplina: {st.session_state.tmp_disciplina}, Tema: {st.session_state.tmp_tema}.
        INSTRUÇÃO CRÍTICA: Não inclua cabeçalhos de identificação (Escola, Professor, etc) nos objetivos. Comece direto no texto pedagógico.
        TABELA: 6 colunas rigorosas separadas por '||'. Sem misturar informações.
        Duração: {st.session_state.tmp_duracao}. {comando_extra} {ajuste}
        SAÍDA: [GERAL]...[FIM] [ESPECIFICOS]...[FIM] [TABELA]...[FIM]"""

        bar.progress(30); status.text("Lendo material e criando plano...")
        conteudo = [prompt]
        if arquivo:
            if arquivo.type.startswith('image'): conteudo.append(Image.open(arquivo))
            else: conteudo.append({"mime_type": "application/pdf", "data": arquivo.getvalue()})

        res = model.generate_content(conteudo).text
        bar.progress(80); status.text("Formatando documento...")

        st.session_state.obj_g = res.split("[GERAL]")[1].split("[FIM]")[0].strip()
        st.session_state.obj_e = res.split("[ESPECIFICOS]")[1].split("[FIM]")[0].strip()
        
        dados = []
        tabela_bruta = res.split("[TABELA]")[1].split("[FIM]")[0].strip()
        for linha in tabela_bruta.split('\n'):
            if "||" in linha:
                cols = [c.strip() for c in linha.split("||")]
                while len(cols) < 6: cols.append("-")
                dados.append(cols[:6])
        
        st.session_state.dados, st.session_state.pronto = dados, True
        bar.progress(100); status.empty(); bar.empty()
    except Exception as e: st.error(f"Erro: {e}"); bar.empty(); status.empty()

# --- INTERFACE ---
st.title("🇲🇿 SDEJT Inhassoro - Planos de Aula")

c1, c2 = st.columns(2)
with c1:
    st.text_input("Disciplina", "Língua Portuguesa", key="tmp_disciplina")
    st.selectbox("Classe", ["1ª", "2ª", "3ª", "4ª", "5ª", "6ª", "7ª", "8ª", "9ª", "10ª", "11ª", "12ª"], key="tmp_classe")
    st.text_input("Unidade Temática", key="tmp_unidade")
with c2:
    st.text_input("Tema", key="tmp_tema")
    st.selectbox("Duração", ["45 Min", "90 Min"], key="tmp_duracao")
    st.selectbox("Tipo de Aula", ["Introdução de Matéria Nova", "Consolidação", "Revisão"], key="tmp_tipo_aula")

st.markdown("### 📚 Material de Apoio & Comandos")
arq = st.file_uploader("Carregar PDF ou Foto", type=['pdf', 'png', 'jpg'])
cmd = st.text_input("🤖 Comando específico para a IA (Ex: Use o texto da pág 5)", key="tmp_cmd")

if st.button("🚀 Gerar Plano de Aula", type="primary"):
    gerar_plano(arquivo=arq, comando_extra=cmd)

if st.session_state.get("pronto"):
    st.divider()
    st.subheader("📋 Pré-visualização")
    st.write(f"**Geral:** {st.session_state.obj_g}")
    st.table(pd.DataFrame(st.session_state.dados, columns=["Tempo", "F. Didática", "Professor", "Aluno", "Métodos", "Meios"]))

    # --- BOTÃO DE DOWNLOAD ---
    pdf = PDF()
    pdf.add_page()
    pdf.set_font("Arial", size=10)
    pdf.cell(130, 7, "Escola: __________________________________", 0, 0)
    pdf.cell(0, 7, "Data: ___/___/2026", 0, 1)
    pdf.cell(0, 7, f"Unidade: {st.session_state.tmp_unidade}", 0, 1)
    pdf.cell(0, 7, f"Tema: {st.session_state.tmp_tema}", 0, 1)
    pdf.cell(100, 7, "Professor: _______________________________", 0, 0)
    pdf.cell(0, 7, f"Duração: {st.session_state.tmp_duracao}", 0, 1)
    pdf.ln(5)
    pdf.set_font("Arial", "B", 10); pdf.cell(0, 7, "OBJETIVO GERAL:", 0, 1)
    pdf.set_font("Arial", size=10); pdf.multi_cell(0, 6, pdf.clean_text(st.session_state.obj_g))
    pdf.ln(2); pdf.set_font("Arial", "B", 10); pdf.cell(0, 7, "OBJETIVOS ESPECÍFICOS:", 0, 1)
    pdf.set_font("Arial", size=10); pdf.multi_cell(0, 6, pdf.clean_text(st.session_state.obj_e))
    pdf.ln(5)
    pdf.draw_header([12, 35, 45, 45, 23, 25])
    for r in st.session_state.dados: pdf.table_row(r, [12, 35, 45, 45, 23, 25])
    
    st.download_button("📄 Baixar PDF Final", pdf.output(dest='S').encode('latin-1'), "Plano_Aula.pdf", "application/pdf", type="primary")

    st.markdown("### 🛠️ Ajustar Plano")
    aj = st.text_area("O que deseja mudar?")
    if st.button("🔄 Aplicar Ajustes"): gerar_plano(arquivo=arq, ajuste=aj); st.rerun()
