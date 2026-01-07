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

def create_pdf(inputs, dados, obj_geral, obj_especificos):
    pdf = PDF(); pdf.set_auto_page_break(auto=False); pdf.add_page()
    pdf.set_font("Arial", size=10)
    pdf.cell(130, 7, f"Escola: __________________________________________________", 0, 0)
    pdf.cell(0, 7, f"Data: ____/____/2026", 0, 1)
    pdf.cell(0, 7, f"Unidade Temática: {
