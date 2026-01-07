import streamlit as st
import google.generativeai as genai
from fpdf import FPDF
import pandas as pd
import time

# --- 1. CONFIGURAÇÃO ---
st.set_page_config(page_title="SDEJT Planos", page_icon="🇲🇿", layout="wide")

# --- 2. ESTILO VISUAL (Dark Mode SNE) ---
st.markdown("""
    <style>
    /* Fundo Escuro */
    .stApp {
        background-color: #0E1117;
        color: #E0E0E0;
    }
    
    /* Inputs Brancos/Legíveis */
    .stTextInput > div > div > input {
        color: #FFFFFF !important;
        background-color: #262730 !important;
        border: 1px solid #4CAF50;
    }
    .stSelectbox > div > div > div {
        color: #FFFFFF !important;
        background-color: #262730 !important;
    }
    
    /* Botões */
    div.stButton > button {
        background-color: #4CAF50;
        color: white;
        border: none;
        padding: 12px;
        font-weight: bold;
        width: 100%;
        text-transform: uppercase;
        font-family: 'Times New Roman', serif;
        border-radius: 6px;
    }
    
    /* Títulos sem SNE */
    h1, h2, h3 {
        font-family: 'Times New Roman', serif;
        color: #4CAF50 !important;
    }
    
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    </style>
    """, unsafe_allow_html=True)

# --- 3. LOGIN ---
def check_password():
    if st.session_state.get("password_correct", False):
        return True

    st.markdown("<br>", unsafe_allow_html=True)
    with st.container(border=True):
        st.markdown("<h3 style='text-align: center;'>🇲🇿 SDEJT - INHASSORO</h3>", unsafe_allow_html=True)
        st.markdown("<h6 style='text-align: center; color: #aaa;'>Sistema Distrital de Elaboração de Planos</h6>", unsafe_allow_html=True)
        st.divider()
        
        st.info("🔐 Acesso Restrito")
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
    return False

if not check_password():
    st.stop()

# --- 4. BARRA LATERAL ---
with st.sidebar:
    st.success(f"👤 Professor: {st.session_state.get('user_name', '')}")
    if st.button("Sair"):
        st.session_state["password_correct"] = False
        st.rerun()

# --- 5. CLASSE PDF (A4 HORIZONTAL + TIMES + 4 FUNÇÕES) ---
class PDF(FPDF):
