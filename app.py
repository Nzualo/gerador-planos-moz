import streamlit as st
import google.generativeai as genai
from fpdf import FPDF
import pandas as pd
from PIL import Image

# --- CONFIGURAÇÃO INICIAL ---
st.set_page_config(page_title="SDEJT - Planos SNE", page_icon="🇲🇿", layout="wide")

# --- ESTILO VISUAL (DARK MODE) ---
st.markdown("""
<style>
    .stApp { background-color: #0E1117; color: #FAFAFA; }
    [data-testid="stSidebar"] { background-color: #262730; }
    .stTextInput > div > div > input, .stSelectbox > div > div > div, .stTextArea > div > div > textarea { color: #ffffff; }
    h1, h2, h3 { color: #FF4B4B !important; }
    /* Estilo para o campo de upload */
    .stFileUploader { background-color: #1E1E1E; border: 2px dashed #FF4B4B; border-radius: 10px; padding: 10px; }
</style>
""", unsafe_allow_html=True)

# --- FUNÇÃO DE LOGIN E CONTACTO ---
def check_password():
    if st.session_state.get("password_correct", False):
        return True

    st.markdown("## 🇲🇿 SDEJT - Elaboração de Planos")
    st.markdown("##### Serviço Distrital de Educação, Juventude e Tecnologia - Inhassoro")
    st.divider()
    
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
                else:
                    st.error("Senha incorreta.")
            else:
                st.error("Usuário desconhecido.")

    with col2:
        st.warning("⚠️ Suporte / Aquisição de Acesso")
        st.markdown("**Precisa de acesso?**")
        st.write("Clique no botão abaixo para solicitar ao Administrador:")
        meu_numero = "258867926665"
        mensagem = "Saudações técnico Nzualo. Gostaria de solicitar acesso ao Gerador de Planos de Aulas."
        link_zap = f"https://wa.me/{meu_numero}?text={mensagem.replace(' ', '%20')}"
        st.markdown(f'''<a href="{link_zap}" target="_blank" style="text-decoration: none;"><button style="background-color:#25D366; color:white; border:none; padding:15px 25px; border-radius:8px; width:100%; cursor:pointer; font-size: 16px; font-weight:bold;">📱 Falar no WhatsApp</button></a>''', unsafe_allow_html=True)
    return False

if not check_password():
    st.stop()

# --- BARRA LATERAL ---
with st.sidebar:
    st.success(f"👤 Técnico: **{st.session_state['user_name']}**")
    if st.button("Sair"):
        st.session_state["password_correct"] = False
        st.rerun()

# --- CLASSE PDF ---
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
        self.ln(2)

    def footer(self):
        self.set_y(-15)
        self.set_font('Arial', 'I', 6)
        self.cell(0, 10, 'SDEJT Inhassoro - Processado por IA', 0, 0, 'C')

    def clean_text(self, text):
        if text is None: return "-"
        text = str(text).strip()
        replacements = {'–': '-', '“': '"', '”': '"', '‘': "'", '’': "'", '…': '...', '•': '-'}
        for k, v in replacements.items(): text = text.replace(k, v)
        return text

    def table_row(self, data, widths):
        row_data = [self.clean_text(d) for d in data]
        max_lines = 1
        for i, text in enumerate(row_data):
            self.set_font("Arial", size=8)
            lines = self.multi_cell(widths[i], 4, text, split_only=True)
            if len(lines) > max_lines: max_lines = len(lines)
        height = max_lines * 4 + 4
        if self.get_y() + height > 270:
            self.add_page(); self.draw_table_header(widths)
        x_start, y_start = self.get_x(), self.get_y()
        for i, text in enumerate(row_data):
            self.set_xy(x_start, y_start); self.set_font("Arial", size=8)
            self.multi_cell(widths[i], 4, text, border=0, align='L')
            x_start += widths[i]
        self.set_xy(10, y_start); x_curr = 10
        for w in widths: self.rect(x_curr, y_start, w, height); x_curr += w
        self.set_y(y_start + height)

    def draw_table_header(self, widths):
        headers = ["TEMPO", "F. DIDÁTICA", "ACTIV. PROFESSOR", "ACTIV. ALUNO", "MÉTODOS", "MEIOS"]
        self.set_font("Arial", "B", 7); self.set_fill_color(220, 220, 220)
        for i, h in enumerate(headers): self.cell(widths[i], 6, h, 1, 0, 'C', True)
        self.ln()

def create_pdf(inputs, dados, obj_geral, obj_especificos):
    pdf = PDF(); pdf.set_auto_page_break(auto=False); pdf.add_page()
    pdf.set_font("Arial", size=10)
    pdf.cell(130, 7, f"Escola: __________________________________________________", 0, 0)
    pdf.cell(0, 7, f"Data: ____/____/2026", 0, 1)
    pdf.cell(0, 7, f"Unidade Temática: {pdf.clean_text(inputs['unidade'])}", 0, 1)
    pdf.set_font("Arial", "B", 10); pdf.cell(0, 7, f"Tema: {pdf.clean_text(inputs['tema'])}", 0, 1)
    pdf.set_font("Arial", size=10)
    pdf.cell(100, 7, f"Professor: ______________________________", 0, 0)
    pdf.cell(50, 7, f"Turma: {inputs['turma']}", 0, 0)
    pdf.cell(0, 7, f"Duração: {inputs['duracao']}", 0, 1)
    pdf.cell(100, 7, f"Tipo de Aula: {pdf.clean_text(inputs['tipo_aula'])}", 0, 0)
    pdf.cell(0, 7, f"Nº Alunos: M_____  F_____  Total:_____", 0, 1)
    pdf.line(10, pdf.get_y()+2, 200, pdf.get_y()+2); pdf.ln(5)
    pdf.set_font("Arial", "B", 10); pdf.cell(40, 6, "OBJETIVO GERAL:", 0, 0)
    pdf.set_font("Arial", size=10); pdf.set_xy(50, pdf.get_y()); pdf.multi_cell(0, 6, pdf.clean_text(obj_geral)); pdf.ln(2)
    pdf.set_font("Arial", "B", 9); pdf.cell(0, 6, "OBJECTIVOS ESPECÍFICOS:", 0, 1)
    pdf.set_font("Arial", size=9); pdf.multi_cell(0, 5, pdf.clean_text(obj_especificos)); pdf.ln(5)
    widths = [12, 40, 45, 45, 23, 25]; pdf.draw_table_header(widths)
    for row in dados: pdf.table_row(row, widths)
    return pdf.output(dest='S').encode('latin-1', 'replace')

# --- LÓGICA DE GERAÇÃO ---
def gerar_plano(instrucoes_adicionais="", arquivo=None):
    try:
        genai.configure(api_key=st.secrets["GOOGLE_API_KEY"])
        duracao = st.session_state['tmp_duracao']
        qtd_geral = "2 (Dois)" if "90" in duracao else "1 (Um)"
        qtd_especificos = "5 (Cinco)" if "90" in duracao else "3 (Três)"
        
        conteudo_prompt = [f"""Aja como Pedagogo Especialista do SNE Moçambique.
        Plano: {st.session_state['tmp_disciplina']}, {st.session_state['tmp_classe']}, Tema: {st.session_state['tmp_tema']}, Duração: {duracao}.
        Ajustes: {instrucoes_adicionais if instrucoes_adicionais else "Nenhum"}.
        REGRAS:
        - Use as informações do arquivo enviado (se houver) para as atividades.
        - Objetivo Geral: EXATAMENTE {qtd_geral}.
        - Objetivos Específicos: NO MÁXIMO {qtd_especificos}.
        - Tabela: 6 colunas (Tempo, Função, Act. Prof, Act. Aluno, Métodos, Meios).
        - Actividades: MUITO DETALHADAS.
        SAÍDA: [BLOCO_GERAL]...[FIM_GERAL] [BLOCO_ESPECIFICOS]...[FIM_ESPECIFICOS] [BLOCO_TABELA]...[FIM_TABELA]"""]

        if arquivo:
            if arquivo.type in ['image/png', 'image/jpeg', 'image/jpg']:
                conteudo_prompt.append(Image.open(arquivo))
            else:
                conteudo_prompt.append({"mime_type": "application/pdf", "data": arquivo.getvalue()})

        try: model = genai.GenerativeModel('models/gemini-2.5-flash')
        except: model = genai.GenerativeModel('models/gemini-1.5-flash')
        
        response = model.generate_content(conteudo_prompt)
        texto = response.text
        
        st.session_state['obj_geral'] = texto.split("[BLOCO_GERAL]")[1].split("[FIM_GERAL]")[0].strip() if "[BLOCO_GERAL]" in texto else "Consultar"
        st.session_state['obj_especificos'] = texto.split("[BLOCO_ESPECIFICOS]")[1].split("[FIM_ESPECIFICOS]")[0].strip() if "[BLOCO_ESPECIFICOS]" in texto else ""
        
        dados = []
        if "[BLOCO_TABELA]" in texto:
            block = texto.split("[BLOCO_TABELA]")[1].split("[FIM_TABELA]")[0].strip()
            for l in block.split('\n'):
                if "||" in l:
                    cols = [c.strip() for c in l.split("||")]
                    while len(cols) < 6: cols.append("-")
                    dados.append(cols[:6])
        st.session_state['dados_pdf'] = dados; st.session_state['plano_pronto'] = True
    except Exception as e: st.error(f"Erro: {e}")

# --- INTERFACE PRINCIPAL ---
st.title("🇲🇿 Elaboração de Planos de Aulas")

col1, col2 = st.columns(2)
with col1:
    disciplina = st.text_input("Disciplina", "Língua Portuguesa", key='tmp_disciplina')
    classe = st.selectbox("Classe", ["1ª", "2ª", "3ª", "4ª", "5ª", "6ª", "7ª", "8ª", "9ª", "10ª", "11ª", "12ª"], key='tmp_classe')
    unidade = st.text_input("Unidade", placeholder="Ex: Textos Normativos", key='tmp_unidade')
with col2:
    duracao = st.selectbox("Duração", ["45 Min", "90 Min"], key='tmp_duracao')
    turma = st.text_input("Turma", placeholder="A", key='tmp_turma')
    tema = st.text_input("Tema", placeholder="Ex: Vogais", key='tmp_tema')

tipo_aula = st.selectbox("Tipo de Aula", ["Introdução de Matéria Nova", "Consolidação e Exercitação", "Verificação e Avaliação", "Revisão"], key='tmp_tipo_aula')

# --- CAMPO DE ARQUIVO NO CENTRO ---
st.markdown("### 📚 Material de Apoio (Opcional)")
arquivo_enviado = st.file_uploader("Carregar PDF ou Foto do Livro", type=['pdf', 'png', 'jpg', 'jpeg'])

if st.button("🚀 Gerar Plano de Aula", type="primary"):
    gerar_plano(arquivo=arquivo_enviado)

# --- RESULTADO E REFINAMENTO ---
if st.session_state.get('plano_pronto'):
    st.divider(); st.subheader("📋 Pré-visualização")
    st.info(f"**Geral:** {st.session_state['obj_geral']}\n\n**Específicos:**\n{st.session_state['obj_especificos']}")
    
    if st.session_state['dados_pdf']:
        df = pd.DataFrame(st.session_state['dados_pdf'], columns=["Tempo", "F. Didática", "Prof", "Aluno", "Métodos", "Meios"])
        st.dataframe(df, hide_index=True, use_container_width=True)

    st.markdown("### 🛠️ Ajustar ou Melhorar")
    ajuste = st.text_area("Descreva o que deseja mudar...", placeholder="Ex: Adicione mais exercícios do livro...")
    
    c1, c2, c3 = st.columns(3)
    with c1:
        if st.button("🔄 Aplicar Melhorias"):
            gerar_plano(ajuste, arquivo=arquivo_enviado); st.rerun()
    with c2:
        inputs = {'unidade': unidade, 'tema': tema, 'turma': turma, 'duracao': duracao, 'tipo_aula': tipo_aula, 'disciplina': disciplina}
        pdf_bytes = create_pdf(inputs, st.session_state['dados_pdf'], st.session_state['obj_geral'], st.session_state['obj_especificos'])
        st.download_button("📄 Baixar PDF Final", data=pdf_bytes, file_name="Plano_SDEJT.pdf", mime="application/pdf", type="primary")
    with c3:
        if st.button("🗑️ Limpar Tudo"):
            st.session_state['plano_pronto'] = False; st.rerun()
