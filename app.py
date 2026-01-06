import streamlit as st
import google.generativeai as genai
from fpdf import FPDF
import pandas as pd

# Configuração da Página
st.set_page_config(page_title="SNE Planner Moçambique", page_icon="🇲🇿", layout="wide")

# --- CLASSE DO PDF (TABELA OFICIAL SNE) ---
class PDF(FPDF):
    def header(self):
        self.set_font('Arial', 'B', 12)
        self.cell(0, 5, 'REPÚBLICA DE MOÇAMBIQUE', 0, 1, 'C')
        self.set_font('Arial', 'B', 10)
        self.cell(0, 5, 'GOVERNO DO DISTRITO DE INHASSORO', 0, 1, 'C')
        self.cell(0, 5, 'SERVIÇO DISTRITAL DE EDUCAÇÃO, JUVENTUDE E TECNOLOGIA', 0, 1, 'C')
        self.ln(5)
        self.set_font('Arial', 'B', 14)
        self.cell(0, 10, 'PLANO DE AULA', 0, 1, 'C')
        self.ln(5)

    def footer(self):
        self.set_y(-15)
        self.set_font('Arial', 'I', 6)
        self.cell(0, 10, 'Produzido conforme orientações do SNE - Inhassoro', 0, 0, 'C')

    def table_row(self, data, widths, align='L'):
        # Calcula a altura necessária para a linha (baseada na célula com mais texto)
        max_lines = 1
        for i, text in enumerate(data):
            self.set_font("Arial", size=8)
            # O truque split_only=True calcula quantas linhas o texto vai ocupar
            lines = self.multi_cell(widths[i], 4, text, split_only=True)
            if len(lines) > max_lines:
                max_lines = len(lines)
        
        height = max_lines * 4 + 4 # Altura dinâmica + margem
        
        # Se não couber na página, cria nova página e redesenha o cabeçalho da tabela
        if self.get_y() + height > 270:
            self.add_page()
            headers = ["TEMPO", "F. DIDÁTICA", "CONTEÚDO", "ACTIV. PROFESSOR", "ACTIV. ALUNO", "MÉTODOS", "MEIOS"]
            self.set_font("Arial", "B", 7)
            self.set_fill_color(230, 230, 230)
            for i, h in enumerate(headers):
                self.cell(widths[i], 6, h, 1, 0, 'C', True)
            self.ln()

        # Desenha as células
        x_start = self.get_x()
        y_start = self.get_y()
        
        for i, text in enumerate(data):
            self.set_xy(x_start, y_start)
            self.set_font("Arial", size=8)
            self.multi_cell(widths[i], 4, text, border=0, align=align)
            x_start += widths[i]

        # Desenha as bordas dos retângulos
        self.set_xy(10, y_start)
        x_curr = 10
        for w in widths:
            self.rect(x_curr, y_start, w, height)
            x_curr += w
        
        self.set_y(y_start + height)

def create_pdf_table(disciplina, classe, tema, duracao, table_data, objetivos_text):
    pdf = PDF()
    pdf.set_auto_page_break(auto=False)
    pdf.add_page()
    
    # Cabeçalho dos Dados da Aula
    pdf.set_font("Arial", "B", 10)
    pdf.cell(0, 6, f"DISCIPLINA: {disciplina.upper()}  |  CLASSE: {classe.upper()}", 0, 1)
    pdf.cell(0, 6, f"TEMA: {tema.upper()}", 0, 1)
    pdf.cell(0, 6, f"DURAÇÃO: {duracao.upper()}", 0, 1)
    pdf.ln(3)
    
    # Objetivos (Caixa de Texto)
    pdf.set_font("Arial", "B", 9)
    pdf.cell(0, 6, "OBJECTIVOS DA AULA:", 0, 1)
    pdf.set_font("Arial", size=9)
    pdf.multi_cell(0, 5, objetivos_text)
    pdf.ln(5)

    # Configuração da Tabela
    # Larguras: Tempo, Função, Conteúdo, Prof, Aluno, Métodos, Meios
    widths = [12, 28, 35, 35, 35, 22, 23]
    headers = ["TEMPO", "F. DIDÁTICA", "CONTEÚDO", "ACTIV. PROFESSOR", "ACTIV. ALUNO", "MÉTODOS", "MEIOS"]
    
    # Desenha cabeçalho da tabela
    pdf.set_font("Arial", "B", 7)
    pdf.set_fill_color(230, 230, 230)
    for i, h in enumerate(headers):
        pdf.cell(widths[i], 6, h, 1, 0, 'C', True)
    pdf.ln()
    
    # Preenche linhas
    for row in table_data:
        pdf.table_row(row, widths)

    return pdf.output(dest='S').encode('latin-1', 'ignore')

# --- O SITE ---
st.title("🇲🇿 SNE - Planificador Didático")
st.caption("Gera planos de aula para qualquer disciplina seguindo rigorosamente as normas pedagógicas de Moçambique.")

with st.sidebar:
    api_key = st.text_input("Chave API (Google):", type="password")
    st.info("Dica: Use o modelo Gemini 2.5 Flash para evitar erros de limite.")

# Formulário
col1, col2 = st.columns(2)
with col1:
    disciplina = st.text_input("Disciplina", placeholder="Ex: Biologia, História, Matemática...")
    classe = st.selectbox("Classe", ["1ª Classe", "2ª Classe", "3ª Classe", "4ª Classe", "5ª Classe", "6ª Classe", "7ª Classe", "8ª Classe", "9ª Classe", "10ª Classe", "11ª Classe", "12ª Classe"])
with col2:
    duracao = st.selectbox("Duração", ["45 Minutos", "90 Minutos"])
    tema = st.text_input("Tema da Aula", placeholder="Ex: A Célula, A Luta de Libertação...")

if st.button("Gerar Plano Didático (SNE)", type="primary"):
    if not api_key:
        st.error("⚠️ Por favor, insira a chave API na barra lateral.")
    else:
        with st.spinner('A consultar metodologias do SNE...'):
            try:
                genai.configure(api_key=api_key)
                model = genai.GenerativeModel('models/gemini-2.5-flash')
                
                # --- O CÉREBRO PEDAGÓGICO (PROMPT AVANÇADO) ---
                prompt = f"""
                Aja como um Pedagogo Especialista do SNE (Sistema Nacional de Educação) de Moçambique.
                Sua tarefa é criar um plano de aula rigoroso e didático.
                
                DADOS DA AULA:
                - Disciplina: {disciplina}
                - Classe: {classe}
                - Tema: {tema}
                - Duração: {duracao}

                INSTRUÇÕES DE LINGUAGEM (SNE):
                1. Use verbos operatórios claros nos objetivos.
                2. Na tabela, diferencie claramente a ação do professor (Mediar, Explicar, Orientar) da ação do aluno (Observar, Exercitar, Debater).
                3. Use as Funções Didáticas Clássicas:
                   - Introdução e Motivação
                   - Mediação e Assimilação
                   - Domínio e Consolidação
                   - Controle e Avaliação
                
                FORMATO DE SAÍDA (Rigoroso):
                
                [BLOCO_OBJETIVOS]
                Escreva aqui os objetivos instrutivos e educativos em texto corrido, de forma técnica.
                [FIM_OBJETIVOS]

                [BLOCO_TABELA]
                Gere os dados da tabela separados por "||". NÃO inclua cabeçalhos, apenas os dados.
                Gere exatamente 4 linhas correspondentes às 4 funções didáticas.
                
                Estrutura das colunas:
                Tempo || Função Didática || Conteúdo || Actividade Professor || Actividade Aluno || Métodos || Meios
                
                Exemplo de linha de dados:
                10 min || Introdução e Motivação || Revisão da aula anterior || Orienta a revisão e coloca questões || Responde e participa || Elaboração Conjunta || Quadro e Giz
                [FIM_TABELA]
                """
                
                response = model.generate_content(prompt)
                texto_gerado = response.text
                
                # --- PROCESSAMENTO INTELIGENTE (LIMPEZA) ---
                objetivos_final = "Objetivos não gerados corretamente."
                dados_tabela = []
                
                # Extrair Objetivos
                if "[BLOCO_OBJETIVOS]" in texto_gerado and "[FIM_OBJETIVOS]" in texto_gerado:
                    start = texto_gerado.find("[BLOCO_OBJETIVOS]") + len("[BLOCO_OBJETIVOS]")
                    end = texto_gerado.find("[FIM_OBJETIVOS]")
                    objetivos_final = texto_gerado[start:end].strip()

                # Extrair Tabela
                if "[BLOCO_TABELA]" in texto_gerado:
                    start_tab = texto_gerado.find("[BLOCO_TABELA]") + len("[BLOCO_TABELA]")
                    end_tab = texto_gerado.find("[FIM_TABELA]")
                    if end_tab == -1: end_tab = len(texto_gerado)
                    
                    linhas_tabela = texto_gerado[start_tab:end_tab].strip().split('\n')
                    
                    for linha in linhas_tabela:
                        if "||" in linha:
                            # Ignora se o robô tentar repetir o cabeçalho
                            if "Função Didática" in linha or "Conteúdo" in linha:
                                continue
                            
                            cols = [c.strip() for c in linha.split("||")]
                            # Garante 7 colunas
                            while len(cols) < 7:
                                cols.append("-")
                            dados_tabela.append(cols)

                # --- MOSTRAR PREVIEW ---
                st.divider()
                st.subheader("👁️ Pré-visualização do Conteúdo")
                st.markdown("**Objetivos Definidos:**")
                st.info(objetivos_final)
                
                if dados_tabela:
                    st.markdown("**Grelha Pedagógica:**")
                    df = pd.DataFrame(dados_tabela, columns=["Tempo", "Função", "Conteúdo", "Professor", "Aluno", "Métodos", "Meios"])
                    st.dataframe(df, hide_index=True)

                    # --- GERAR PDF ---
                    pdf_bytes = create_pdf_table(disciplina, classe, tema, duracao, dados_tabela, objetivos_final)
                    st.success("Plano elaborado com sucesso!")
                    st.download_button("⬇️ Baixar PDF SNE (Oficial)", data=pdf_bytes, file_name=f"Plano_{disciplina}_{classe}.pdf", mime="application/pdf")
                else:
                    st.error("A IA não gerou a tabela corretamente. Tente clicar em 'Gerar' novamente.")
                    
            except Exception as e:
                st.error(f"Erro técnico: {e}")
