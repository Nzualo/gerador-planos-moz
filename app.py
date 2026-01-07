import streamlit as st
import google.generativeai as genai
from fpdf import FPDF
import pandas as pd
import time

# --- 1. CONFIGURAÇÃO GERAL ---
st.set_page_config(page_title="SDEJT Planos", page_icon="🇲🇿", layout="wide")

# --- 2. ESTILO VISUAL (DARK MODE & MOBILE FRIENDLY) ---
st.markdown("""
    <style>
    /* Fundo Escuro Profissional */
    .stApp {
        background-color: #0E1117;
        color: #FFFFFF;
    }
    /* Texto dos Inputs visível */
    .stTextInput input {
        color: white !important;
    }
    /* Botões Grandes e Fortes */
    div.stButton > button {
        width: 100%;
        border-radius: 6px;
        font-weight: bold;
        height: 50px;
        text-transform: uppercase;
        font-family: 'Times New Roman', serif;
    }
    /* Esconder menus do Streamlit */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    </style>
    """, unsafe_allow_html=True)

# --- 3. LOGIN & SEGURANÇA ---
def check_password():
    if st.session_state.get("password_correct", False):
        return True

    st.markdown("<br>", unsafe_allow_html=True)
    
    with st.container(border=True):
        st.markdown("<h3 style='text-align: center; color: #4CAF50; font-family: Times New Roman;'>🇲🇿 SDEJT - INHASSORO</h3>", unsafe_allow_html=True)
        st.markdown("<h6 style='text-align: center; color: #ccc; font-family: Times New Roman;'>Sistema de Elaboração de Planos</h6>", unsafe_allow_html=True)
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
                    padding: 10px; border-radius: 5px; width: 100%; font-weight: bold; font-family: Times New Roman;">
                    📱 Contactar Administrador
                </button>
            </a>
            ''', unsafe_allow_html=True)
    return False

if not check_password():
    st.stop()

# --- 4. BARRA LATERAL ---
with st.sidebar:
    st.success(f"👤 Professor(a): {st.session_state.get('user_name', '')}")
    if st.button("Sair / Logout"):
        st.session_state["password_correct"] = False
        st.rerun()

# --- 5. CLASSE PDF (A4 HORIZONTAL + TIMES NEW ROMAN) ---
class PDF(FPDF):
    def header(self):
        # Configura Fonte Times New Roman (Code: 'Times')
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
        self.cell(0, 10, 'Processado por IA - SDEJT Inhassoro', 0, 0, 'C')

    def table_row(self, data, widths):
        # Calcular altura da linha baseada no texto mais longo
        max_lines = 1
        for i, text in enumerate(data):
            self.set_font("Times", size=10) # Fonte da Tabela
            texto = str(text) if text else ""
            lines = self.multi_cell(widths[i], 4, texto, split_only=True)
            max_lines = max(max_lines, len(lines))
        
        height = max_lines * 4 + 4
        
        # Quebra de página para PAISAGEM (Altura útil ~180mm)
        if self.get_y() + height > 180:
            self.add_page(orientation='L')
            self.create_headers(widths)
            
        x_start = self.get_x()
        y_start = self.get_y()
        
        # Desenhar texto
        for i, text in enumerate(data):
            self.set_xy(x_start, y_start)
            self.set_font("Times", size=10)
            texto = str(text) if text else ""
            self.multi_cell(widths[i], 4, texto, border=0)
            x_start += widths[i]
            
        # Desenhar Bordas (Retângulos) para ficar limpo
        self.set_xy(10, y_start)
        x_curr = 10
        for w in widths:
            self.rect(x_curr, y_start, w, height)
            x_curr += w
        self.set_y(y_start + height)

    def create_headers(self, widths):
        headers = ["TEMPO", "F. DIDÁTICA", "CONTEÚDOS", "ACTIV. PROF", "ACTIV. ALUNO", "MÉTODOS", "MEIOS"]
        self.set_font("Times", "B", 9)
        self.set_fill_color(230, 230, 230) # Cinza claro
        for i, h in enumerate(headers):
            self.cell(widths[i], 6, h, 1, 0, 'C', True)
        self.ln()

def create_pdf(inputs, dados, objetivos):
    pdf = PDF()
    pdf.set_auto_page_break(auto=False)
    
    # --- PÁGINA HORIZONTAL (L = Landscape) ---
    pdf.add_page(orientation='L')
    
    pdf.set_font("Times", size=12)
    
    # Cabeçalho Administrativo (Largo para Paisagem)
    # Linha 1
    pdf.cell(160, 7, f"Escola: _______________________________________________________", 0, 0)
    pdf.cell(0, 7, f"Data: ____/____/2026", 0, 1)
    
    # Linha 2
    pdf.cell(0, 7, f"Unidade Temática: {inputs['unidade']}", 0, 1)
    
    # Linha 3 (Tema em Negrito)
    pdf.set_font("Times", "B", 12)
    pdf.cell(0, 7, f"Tema: {inputs['tema']}", 0, 1)
    pdf.set_font("Times", size=12)
    
    # Linha 4
    pdf.cell(110, 7, f"Professor: ___________________________", 0, 0)
    pdf.cell(40, 7, f"Turma: {inputs['turma']}", 0, 0)
    pdf.cell(0, 7, f"Duração: {inputs['duracao']}", 0, 1)
    
    # Linha 5
    pdf.cell(110, 7, f"Tipo de Aula: {inputs['tipo_aula']}", 0, 0)
    pdf.cell(0, 7, f"Alunos: M_____  F_____  Total:_____", 0, 1)
    
    # Linha divisória longa
    pdf.line(10, pdf.get_y()+2, 285, pdf.get_y()+2)
    pdf.ln(5)

    # Objetivos
    pdf.set_font("Times", "B", 12)
    pdf.cell(0, 6, "OBJECTIVOS:", 0, 1)
    pdf.set_font("Times", size=12)
    pdf.multi_cell(0, 5, objetivos)
    pdf.ln(5)

    # Tabela (Largura Total ~275mm para ocupar a folha toda)
    # [Tempo, F.Didatica, Conteudos, Prof, Aluno, Metodos, Meios]
    widths = [15, 35, 55, 55, 55, 30, 32]
    pdf.create_headers(widths)
