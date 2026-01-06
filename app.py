import streamlit as st
import google.generativeai as genai

st.title("🕵️‍♂️ Diagnóstico SDEJT")
st.write("Vamos descobrir o nome correto do modelo para sua conta.")

# 1. Entrada da Chave
api_key = st.text_input("Cole sua API Key aqui:", type="password")

if st.button("Verificar Modelos Disponíveis"):
    if not api_key:
        st.error("Por favor, cole a chave primeiro.")
    else:
        try:
            # 2. Configura a conexão
            genai.configure(api_key=api_key)
            st.info("A conectar ao Google... aguarde.")
            
            # 3. Pede a lista oficial ao Google
            modelos_disponiveis = []
            for m in genai.list_models():
                # Só queremos modelos que geram texto (generateContent)
                if 'generateContent' in m.supported_generation_methods:
                    modelos_disponiveis.append(m.name)
            
            # 4. Mostra o resultado
            if modelos_disponiveis:
                st.success("✅ Sucesso! O Google aceita estes nomes:")
                st.code(modelos_disponiveis)
                st.write("Tire um print desta lista e mande no chat!")
            else:
                st.warning("Nenhum modelo encontrado. A chave pode estar sem permissões.")
                
        except Exception as e:
            st.error(f"Erro de conexão: {e}")
