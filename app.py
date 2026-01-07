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
</style>
""", unsafe_allow_html=True)

# --- LOGIN ---
def check_password():
    if st.session_state.get("password_correct", False): return True
    st.markdown("## 🇲🇿 SDEJT - Elaboração de Planos")
    col1, col2 = st.columns(2)
    with col1:
        usuario = st.text_input("Usuário")
        senha = st.text_input("Senha", type="password")
        if st.button("Entrar", type="primary"):
            if "passwords" in st.secrets and st.secrets["passwords"].get(usuario) == senha:
                st.session_state["password_correct"] = True
                st.rerun()
    return False

if not check_password(): st.stop()

# --- CLASSE PDF BLINDADA ---
class PDF(FPDF):
    def header(self):
        self.set_font('Arial', 'B', 12); self.cell(0, 5, 'REPÚBLICA DE MOÇAMBIQUE', 0, 1, 'C')
        self.set_font('Arial', 'B', 10); self.cell(0, 5, 'GOVERNO DO DISTRITO DE INHASSORO', 0, 1, 'C')
        self.ln(10); self.set_font('Arial', 'B', 14); self.cell(0, 10, 'PLANO DE AULA', 0, 1, 'C'); self.ln(5)

    def draw_table_header(self):
        widths = [15, 30, 45, 45, 25, 30]
        headers = ["TEMPO", "F. DIDÁTICA", "ACT. PROFESSOR", "ACT. ALUNO", "MÉTODOS", "MEIOS"]
        self.set_font("Arial", "B", 8); self.set_fill_color(230, 230, 230)
        for i, h in enumerate(headers): self.cell(widths[i], 7, h, 1, 0, 'C', True)
        self.ln()

    def add_row(self, row):
        widths = [15, 30, 45, 45, 25, 30]
        max_h = 0
        clean_row = [str(col).replace("||", "").strip() for col in row]
        
        # Calcular altura
        for i, txt in enumerate(clean_row):
            lines = self.multi_cell(widths[i], 5, txt, split_only=True)
            max_h = max(max_h, len(lines) * 5)
        
        if self.get_y() + max_h > 260: self.add_page(); self.draw_table_header()
        
        y = self.get_y(); x = 10
        for i, txt in enumerate(clean_row):
            self.set_xy(x, y)
            self.multi_cell(widths[i], 5, txt, border=1, align='L')
            x += widths[i]
        self.set_y(y + max_h)

def create_pdf(inputs, dados, obj_geral, obj_espec):
    pdf = PDF(); pdf.add_page(); pdf.set_font("Arial", size=10)
    pdf.cell(0, 7, "Escola: __________________________________________________  Data: ____/____/2026", 0, 1)
    pdf.cell(0, 7, f"Tema: {inputs['tema']}", 0, 1)
    pdf.cell(0, 7, f"Duração: {inputs['duracao']} | Turma: {inputs['turma']} | Tipo: {inputs['tipo']}", 0, 1)
    pdf.ln(5)
    pdf.set_font("Arial", "B", 10); pdf.cell(0, 7, "OBJETIVO GERAL:", 0, 1)
    pdf.set_font("Arial", "", 10); pdf.multi_cell(0, 6, obj_geral); pdf.ln(3)
    pdf.set_font("Arial", "B", 10); pdf.cell(0, 7, "OBJECTIVOS ESPECÍFICOS:", 0, 1)
    pdf.set_font("Arial", "", 10)
    for o in obj_espec[:3] if "45" in inputs['duracao'] else obj_espec[:5]: pdf.cell(0, 6, f"- {o}", 0, 1)
    pdf.ln(5); pdf.draw_table_header()
    for r in dados: pdf.add_row(r)
    return pdf.output(dest='S').encode('latin-1', 'replace')

# --- GERAÇÃO ---
def processar_ia(arquivo, comando):
    progress = st.progress(0); status = st.empty()
    try:
        status.text("Conectando ao Gemini 2.5 Flash..."); progress.progress(20)
        genai.configure(api_key=st.secrets["GOOGLE_API_KEY"])
        model = genai.GenerativeModel('gemini-2.5-flash')
        
        prompt = f"""Aja como Pedagogo de Moçambique. Tema: {st.session_state.tmp_tema}. Duração: {st.session_state.tmp_duracao}.
        REGRAS: 1. Objetivo Geral: Frase única curta. 2. Específicos: Lista curta (verbo infinitivo).
        3. Tabela: EXATAMENTE 4 linhas (as 4 funções didáticas). Detalhe MUITO as atividades.
        SAÍDA: [GERAL]...[ESPEC]...[TABELA] linha1 || linha2... (use || entre as 6 colunas)"""

        conteudo = [prompt]
        if arquivo: conteudo.append(Image.open(arquivo) if arquivo.type.startswith('image') else {"mime_type": "application/pdf", "data": arquivo.getvalue()})
        
        res = model.generate_content(conteudo).text
        progress.progress(80); status.text("Formatando documento...")
        
        st.session_state.obj_g = res.split("[GERAL]")[1].split("[ESPEC]")[0].strip()
        st.session_state.obj_e = [o.strip("- ") for o in res.split("[ESPEC]")[1].split("[TABELA]")[0].strip().split("\n") if o.strip()]
        
        linhas = []
        for l in res.split("[TABELA]")[1].strip().split("\n"):
            if "||" in l: 
                cols = [c.strip() for c in l.split("||")]
                while len(cols) < 6: cols.append("-")
                linhas.append(cols[:6])
        st.session_state.dados = linhas; st.session_state.pronto = True
        progress.progress(100); status.empty()
    except Exception as e: st.error(f"Erro: {e}"); progress.empty()

# --- INTERFACE ---
st.title("🇲🇿 SDEJT - Gerador de Planos")
c1, c2 = st.columns(2)
with c1: 
    st.text_input("Tema", key="tmp_tema")
    st.selectbox("Duração", ["45 Min", "90 Min"], key="tmp_duracao")
with c2:
    st.text_input("Turma", "A", key="tmp_turma")
    st.selectbox("Tipo", ["Introdução de Matéria Nova", "Consolidação"], key="tmp_tipo")

st.markdown("### 📚 Material de Apoio")
arq = st.file_uploader("Carregar Livro", type=['pdf', 'png', 'jpg'])
cmd = st.text_input("🤖 Comando para IA", placeholder="Ex: Detalhe as atividades da página carregada...")

if st.button("🚀 Gerar Plano Completo", type="primary", use_container_width=True): processar_ia(arq, cmd)

if st.session_state.get("pronto"):
    st.divider()
    df = pd.DataFrame(st.session_state.dados, columns=["Tempo", "Função", "Prof", "Aluno", "Métodos", "Meios"])
    st.dataframe(df, hide_index=True)
    
    pdf_b = create_pdf(st.session_state, st.session_state.dados, st.session_state.obj_g, st.session_state.obj_e)
    st.download_button("📄 Baixar PDF Final", pdf_b, "Plano.pdf", "application/pdf", type="primary", use_container_width=True)
    if st.button("🗑️ Novo Plano"): st.session_state.pronto = False; st.rerun()
