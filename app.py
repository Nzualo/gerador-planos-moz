import streamlit as st
from supabase import create_client

st.title("Teste Supabase")

SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_ANON_KEY = st.secrets["SUPABASE_ANON_KEY"]

supabase = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)

st.success("Secrets carregados com sucesso.")

# Teste simples: perguntar ao banco usando uma tabela que existe
# Vamos testar listando 1 linha de app_users (se existir)
try:
    resp = supabase.table("app_users").select("*").limit(1).execute()
    st.write("Resposta app_users:", resp.data)
    st.success("Conexão com Supabase OK.")
except Exception as e:
    st.error("Erro ao conectar ou consultar app_users:")
    st.exception(e)
