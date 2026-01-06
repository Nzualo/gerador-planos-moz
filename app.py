import streamlit as st
import google.generativeai as genai

# Configuração da página
st.set_page_config(page_title="PlanQik Clone - Moçambique", page_icon="🇲🇿")

# Título e Cabeçalho
st.title("🇲🇿 Gerador de Planos de Aula - SNE")
st.write("Baseado no Currículo do MINEDH. Preencha os dados abaixo.")

# Barra lateral para a API Key (Para segurança)
with st.sidebar:
    st.header("Configuração")
    api_key = st.text_input("Insira sua Google API Key", type="password")
    st.info("Obtenha sua chave grátis no Google AI Studio.")

# Formulário de Entrada
col1, col2 = st.columns(2)
with col1:
    disciplina = st.text_input("Disciplina", placeholder="Ex: Matemática")
    classe = st.selectbox("Classe", ["1ª Classe", "2ª Classe", "3ª Classe", "4ª Classe", "5ª Classe", "6ª Classe", "7ª Classe", "8ª Classe", "9ª Classe", "10ª Classe", "11ª Classe", "12ª Classe"])
with col2:
    duracao = st.selectbox("Duração", ["45 Minutos", "90 Minutos"])
    tema = st.text_input("Tema da Aula", placeholder="Ex: Teorema de Pitágoras")

# O Prompt (A instrução secreta)
def gerar_plano(api_key, disc, cla, tem, dur):
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel('gemini-pro')
    
    prompt = f"""
    Aja como um especialista pedagógico do Ministério da Educação (MINEDH) de Moçambique.
    Elabore um plano de aula para:
    Disciplina: {disc} | Classe: {cla} | Tema: {tem} | Duração: {dur}.
    
    ESTRUTURA OBRIGATÓRIA:
    1. Cabeçalho (Objetivos, Meios).
    2. Funções Didáticas (Use tabela Markdown):
       - Introdução e Motivação
       - Mediação e Assimilação
       - Domínio e Consolidação
       - Controlo e Avaliação
    
    Use terminologia moçambicana. Formate em Markdown limpo.
    """
    return model.generate_content(prompt)

# Botão de Ação
if st.button("Gerar Plano de Aula", type="primary"):
    if not api_key:
        st.error("Por favor, insira a API Key na barra lateral primeiro.")
    elif not tema or not disciplina:
        st.warning("Preencha a Disciplina e o Tema.")
    else:
        with st.spinner('A Inteligência Artificial está a escrever o plano...'):
            try:
                resposta = gerar_plano(api_key, disciplina, classe, tema, duracao)
                st.success("Plano Gerado!")
                st.markdown("---")
                st.markdown(resposta.text)
                
                # Botão para baixar (simples)
                st.download_button("Baixar Texto (.txt)", data=resposta.text, file_name=f"Plano_{disciplina}_{tema}.txt")
            except Exception as e:
                st.error(f"Erro: {e}")

