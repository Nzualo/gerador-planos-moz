import streamlit as st
import google.generativeai as genai
from fpdf import FPDF
import pandas as pd
import time

# --- CONFIGURAÇÃO INICIAL ---
st.set_page_config(page_title="SDEJT Inhassoro", page_icon="🇲🇿", layout="wide")

# --- ESTILO VISUAL DARK (MODO ESCURO - SNE) ---
st.markdown("""
    <style>
    /* Fundo Principal Escuro */
    .stApp {
        background-color: #0E1117;
        color: #E0E0E0;
    }
    
    /* Inputs (Caixas de texto) */
    .stTextInput > div > div > input {
        background-color: #262730;
        color: white;
        border: 1px solid #4A4A4A;
    }
    .stSelectbox > div > div > div {
        background-color: #262730;
        color: white;
    }
    
    /* Títulos em Verde Oficial */
    h1, h2, h3, h4 {
        color: #4CAF50 !important; /* Verde Bandeira */
        font-family: 'Times New Roman', serif;
    }
    
    /* Botões */
    div.stButton > button:first-child {
        background-color: #D32F2F; /* Vermelho Bandeira */
        color: white;
        font-weight: bold;
        border: none;
        border-radius: 4px;
        text-transform: uppercase;
        font-family: 'Times New Roman', serif;
    }
    div.stButton > button:first-child:hover {
        background-color: #B71C1C;
        border: 1px solid white;
    }

    /* Sidebar */
    section[data-testid="stSidebar"] {
        background-color: #1A1C24;
        border-right: 1px solid #333;
    }
    
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    </style>
    """, unsafe_allow_html=True)

# --- FUNÇÃO DE AUTENTICAÇÃO ---
def check_password():
    if st.session_state.get("password_correct", False):
        return True

    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        with st.container(border=True):
            st.markdown("<h2 style='text-align: center; font-family: Times New Roman;'>🇲🇿 MINEDH / SDEJT</h2>", unsafe_allow_html=True)
            st.markdown("<p style='text-align: center; color: #aaa; font-family: Times New Roman;'>Sistema de Planificação de Aulas - Inhassoro</p>", unsafe_allow_html=True)
            st.divider()
            
            st.info("🔐 Autenticação Obrigatória")
            usuario = st.text_input("Nome de Utilizador")
            senha = st.text_input("Palavra-passe", type="password")
            
            if st.button("ENTRAR NO SISTEMA", type="primary", use_container_width=True):
                if "passwords" in st.secrets and usuario in st.secrets["passwords"]:
                    if st.secrets["passwords"][usuario] == senha:
                        st.session_state["password_correct"] = True
                        st.session_state["user_name"] = usuario
                        st.rerun()
                    else:
                        st.error("Palavra-passe incorreta.")
                else:
                    st.error("Utilizador não registado.")

            st.divider()
            
            meu_numero = "258867926665"
            mensagem = "Saudações Técnico Nzualo. Sou professor e solicito credenciais para o Sistema de Planos."
            link_zap = f"https://wa.me/{meu_numero}?text={mensagem.replace(' ', '%20')}"
            
            st.markdown(f'''
                <a href="{link_zap}" target="_blank" style="text-decoration: none;">
                    <button style="
                        background-color: #25D366; 
                        color: white; 
                        border: none; 
                        padding: 10px; 
                        border-radius: 5px; 
                        width: 100%; 
                        cursor: pointer; 
                        font-weight: bold;
                        font-family: Times New Roman;">
                        📱 Contactar Administrador (WhatsApp)
                    </button>
                </a>
                ''', unsafe_allow_html=True)
    return False

if not check_password():
    st.stop()

# --- SIDEBAR ---
with st.sidebar:
    st.success(f"👤 Professor(a): **{st.session_state['user_name']}**")
    if st.button("Terminar Sessão"):
        st.session_state["password_correct"] = False
        st.rerun()

# --- CLASSE PDF (TIMES NEW ROMAN - HORIZONTAL) ---
class PDF(FPDF):
    def header(self):
        # Times New Roman (Code: 'Times')
        self.set_font('Times', 'B', 12)
        self.cell(0, 5, 'REPÚBLICA DE MOÇAMBIQUE', 0, 1, 'C')
        self.set_font('Times', 'B', 11)
        self.cell(0, 5, 'MINISTÉRIO DA EDUCAÇÃO E DESENVOLVIMENTO HUMANO', 0, 1, 'C')
        self.cell(0, 5, 'SDEJT - DISTRITO DE INHASSORO', 0, 1, 'C')
        self.ln(5)
        self.set_font('Times', 'B', 14)
        self.cell(0, 10, 'PLANO DE LIÇÃO', 0, 1, 'C')
        self.ln
