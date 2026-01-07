import streamlit as st
import google.generativeai as genai
from fpdf import FPDF
import pandas as pd
import time

# --- 1. CONFIGURAÇÃO GERAL ---
st.set_page_config(page_title="SDEJT Planos", page_icon="🇲🇿", layout="wide")

# --- 2. ESTILO VISUAL (MODO CLARO / LIMPO) ---
st.markdown("""
    <style>
    /* Forçar visual limpo e profissional */
    .stApp {
        background-color: #FFFFFF;
        color: #000000;
    }
    
    /* Botões Verdes Institucionais */
    div.stButton > button {
        width: 100%;
        border-radius: 6px;
        font-weight: bold;
        height: 50px;
        text-transform: uppercase;
        font-family: 'Times New Roman', serif;
        border: 1px solid #4CAF50;
    }
    
    /* Esconder menus do sistema */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    </style>
    """, unsafe_allow_html=True)

# --- 3. LOGIN & SEGURANÇA ---
def check_password():
    if st.session_state.get("password_correct", False):
        return True

    st.markdown("<br>", unsafe_allow_html=True)
    
    # Caixa de Login Simples
    with st.container(border=True):
        st.markdown("<h3 style='text-align: center; color: #006400; font-family: Times New Roman;'>🇲🇿 SDEJT - INHASSORO</h3>", unsafe_allow_html=True)
        st.markdown("<h6 style='text-align: center; color: #555; font-family: Times New Roman;'>Sistema de Elaboração de Planos</h6>", unsafe_allow_html=True)
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
                    📱 Falar com Administrador
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
