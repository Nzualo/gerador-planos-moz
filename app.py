import io
import re
import textwrap
from datetime import date, datetime

import streamlit as st
import pandas as pd
from supabase import create_client

import google.generativeai as genai
from fpdf import FPDF
from PIL import Image, ImageDraw, ImageFont


# ---------------- CONFIG ----------------
st.set_page_config(page_title="SDEJT - Planos SNE", page_icon="🇲🇿", layout="wide")

SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_SERVICE_ROLE = st.secrets["SUPABASE_SERVICE_ROLE"]
GOOGLE_API_KEY = st.secrets["GOOGLE_API_KEY"]
ADMIN_PASSWORD = st.secrets["ADMIN_PASSWORD"]
ADMIN_WHATSAPP = st.secrets.get("ADMIN_WHATSAPP", "+258867926665")

sb = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE)

SCHOOL_TYPES = ["EP", "EB", "ES1", "ES2"]


# ---------------- STYLE ----------------
st.markdown("""
<style>
    .stApp { background-color: #0E1117; color: #FAFAFA; }
    [data-testid="stSidebar"] { background-color: #262730; }
    h1, h2, h3 { color: #FF4B4B !important; }
</style>
""", unsafe_allow_html=True)


# ---------------- HELPERS ----------------
def norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip())

def wa_link(number: str, message: str) -> str:
    n = re.sub(r"[^\d]", "", number)
    t = message.replace(" ", "%20")
    return f"https://wa.me/{n}?text={t}"

def today_iso() -> str:
    return date.today().isoformat()

def get_user(name: str, school: str):
    r = sb.table("app_users").select("*").ilike("name", name).ilike("school", school).limit(1).execute()
    return r.data[0] if r.data else None

def get_user_exact(name: str, school: str):
    r = sb.table("app_users").select("*").eq("name", name).eq("school", school).limit(1).execute()
    return r.data[0] if r.data else None

def create_trial_user(name: str, school: str, school_type: str):
    ins = sb.table("app_users").insert({
        "name": name,
        "school": school,
        "school_type": school_type,
        "status": "trial",
        "daily_limit": 2
    }).execute()
    return ins.data[0] if ins.data else None

def get_usage(user_id: str):
    r = sb.table("usage_daily").select("*").eq("user_id", user_id).eq("day", today_iso()).limit(1).execute()
    if not r.data:
        return 0
    return int(r.data[0]["count"])

def inc_usage(user_id: str):
    used = get_usage(user_id)
    sb.table("usage_daily").upsert({
        "user_id": user_id,
        "day": today_iso(),
        "count": used + 1
    }).execute()
    return used + 1

def can_generate(user):
    if user["status"] == "blocked":
        return False, "O seu acesso foi bloqueado."
    used = get_usage(user["id"])
    limit = int(user.get("daily_limit", 2))
    if used >= limit:
        return False, f"Limite diário atingido ({used}/{limit})."
    return True, f"Hoje: {used}/{limit} planos."

def save_plan(user_id: str, class_level: int, discipline: str, topic: str, plan_text: str):
    sb.table("plans").insert({
        "user_id": user_id,
        "day": today_iso(),
        "class_level": class_level,
        "discipline": discipline,
        "topic": topic,
        "plan_text": plan_text
    }).execute()

def list_my_plans(user_id: str):
    r = sb.table("plans").select("*").eq("user_id", user_id).order("created_at", desc=True).execute()
    return r.data or []

def request_access(name: str, school: str, school_type: str):
    # evita duplicado "pending"
    r = sb.table("access_requests").select("*").eq("name", name).eq("school", school).eq("status", "pending").limit(1).execute()
    if r.data:
        return
    sb.table("access_requests").insert({
        "name": name,
        "school": school,
        "school_type": school_type,
        "status": "pending"
    }).execute()


# ---------------- PREVIEW IMAGES ----------------
def plan_to_images(plan_text: str):
    W, H = 1240, 1754
    margin = 70
    line_spacing = 8

    try:
        font = ImageFont.truetype("DejaVuSans.ttf", 28)
        font_b = ImageFont.truetype("DejaVuSans-Bold.ttf", 34)
    except Exception:
        font = ImageFont.load_default()
        font_b = ImageFont.load_default()

    lines = []
    for p in plan_text.split("\n"):
        if p.strip() == "":
            lines.append("")
            continue
        lines.extend(textwrap.wrap(p, width=92))

    pages = []
    img = Image.new("RGB", (W, H), "white")
    draw = ImageDraw.Draw(img)
    y = margin
    draw.text((margin, y), "Plano de Aula (Pré-visualização)", fill="black", font=font_b)
    y += 60

    for line in lines:
        bbox = draw.textbbox((0, 0), line if line else " ", font=font)
        h = (bbox[3] - bbox[1]) + line_spacing
        if y + h > H - margin:
            pages.append(img)
            img = Image.new("RGB", (W, H), "white")
            draw = ImageDraw.Draw(img)
            y = margin
            draw.text((margin, y), "Plano de Aula (Pré-visualização)", fill="black", font=font_b)
            y += 60
        draw.text((margin, y), line, fill="black", font=font)
        y += h

    pages.append(img)
    return pages


# ---------------- PDF (FPDF) ----------------
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

def generate_pdf(plan_text: str) -> bytes:
    pdf = PDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    pdf.set_font("Arial", size=10)

    # evita palavras gigantes quebrando
    for p in plan_text.split("\n"):
        if p.strip() == "":
            pdf.ln(2)
            continue
        p = re.sub(r"(\S{55,})", lambda m: "\n".join(textwrap.wrap(m.group(0), 40)), p)
        pdf.multi_cell(0, 5, p)

    return pdf.output(dest="S").encode("latin-1", errors="replace")


# ---------------- PLAN (GEMINI) ----------------
def build_prompt(discipline: str, class_level: int, topic: str, duration: int, school_type: str):
    # Ajuste: 1ª–6ª incluir Livro do Aluno como meio sempre que fizer sentido
    livro_aluno = "Inclua 'Livro do Aluno' nos Meios sempre que a classe for 1ª a 6ª." if 1 <= class_level <= 6 else ""

    return f"""
Aja como Pedagogo Especialista do SNE Moçambique. Use Português de Moçambique (evite brasileiro).
A aula deve espelhar a realidade de Inhassoro, depois província, país e mundo. Traga exemplos do dia-a-dia.

Disciplina: {discipline}
Classe: {class_level}ª
Tema: {topic}
Duração: {duration} minutos
Tipo de escola: {school_type}

REGRAS OBRIGATÓRIAS:
1) A 1ª Função Didática (Introdução e Motivação) deve incluir:
   - controlo de presenças
   - orientação e correção do TPC (se houver)
2) A última Função (Controlo e Avaliação) deve incluir:
   - síntese e verificação
   - marcar TPC
3) Sempre que possível, use metodologias realistas para escolas locais (perguntas orientadoras, trabalho em pares, exercícios no quadro, etc.).
4) {livro_aluno}

SAÍDA:
- Escreva um plano completo em texto corrido (sem tabela obrigatória), com:
  - Objetivo geral e objetivos específicos
  - Meios
  - Metodologias
  - Desenvolvimento por Funções Didáticas (4 funções)
  - TPC no fim

Escreva de forma clara e aplicável.
"""


# ---------------- SESSION ----------------
if "role" not in st.session_state:
    st.session_state.role = None  # "admin" ou "teacher"
if "user" not in st.session_state:
    st.session_state.user = None
if "draft" not in st.session_state:
    st.session_state.draft = None


# ---------------- SIDEBAR ----------------
with st.sidebar:
    st.write("### Sessão")
    if st.session_state.role == "admin":
        st.success("Administrador")
        if st.button("Sair"):
            st.session_state.role = None
            st.session_state.user = None
            st.session_state.draft = None
            st.rerun()
    elif st.session_state.role == "teacher" and st.session_state.user:
        u = st.session_state.user
        st.success(f"{u['name']}")
        st.caption(f"{u['school']} ({u['school_type']})")
        if st.button("Sair"):
            st.session_state.role = None
            st.session_state.user = None
            st.session_state.draft = None
            st.rerun()

    st.divider()
    st.write("### Ajuda")
    st.link_button("WhatsApp do Administrador", wa_link(ADMIN_WHATSAPP, "Olá! Preciso de apoio no Gerador de Planos."))


# ---------------- LOGIN SCREEN ----------------
st.title("🇲🇿 SDEJT - Gerador de Planos (SNE)")

tabs = st.tabs(["Professor", "Administrador"])

# ---- Teacher ----
with tabs[0]:
    st.subheader("Entrada do Professor (Nome + Escola)")
    c1, c2 = st.columns(2)
    with c1:
        t_name = st.text_input("Nome do professor")
        t_school = st.text_input("Escola")
    with c2:
        t_school_type = st.selectbox("Tipo de escola", SCHOOL_TYPES, index=0)

    if st.button("Entrar como Professor", type="primary"):
        name = norm(t_name)
        school = norm(t_school)
        if not name or not school:
            st.warning("Preencha Nome e Escola.")
        else:
            user = get_user_exact(name, school)
            if not user:
                user = create_trial_user(name, school, t_school_type)
                st.info("Criado acesso de teste (2 planos/dia). Para acesso total, faça um pedido.")
            if user["status"] == "blocked":
                st.error("O seu acesso foi bloqueado.")
            else:
                st.session_state.role = "teacher"
                st.session_state.user = user
                st.session_state.draft = None
                st.rerun()

    st.caption("Acesso total: o administrador aprova e pode aumentar o limite diário.")
    if st.button("Pedir Acesso Total"):
        name = norm(t_name)
        school = norm(t_school)
        if not name or not school:
            st.warning("Preencha Nome e Escola primeiro.")
        else:
            request_access(name, school, t_school_type)
            st.success("Pedido enviado ao administrador.")

# ---- Admin ----
with tabs[1]:
    st.subheader("Entrada do Administrador (Senha)")
    pwd = st.text_input("Senha do administrador", type="password")
    if st.button("Entrar como Administrador"):
        if pwd == ADMIN_PASSWORD:
            st.session_state.role = "admin"
            st.session_state.user = None
            st.session_state.draft = None
            st.rerun()
        else:
            st.error("Senha incorreta.")


# ---------------- ADMIN PANEL ----------------
if st.session_state.role == "admin":
    st.divider()
    st.header("Painel do Administrador")

    t1, t2, t3 = st.tabs(["Pedidos", "Professores", "Planos (hoje)"])

    with t1:
        st.subheader("Pedidos pendentes")
        reqs = sb.table("access_requests").select("*").eq("status", "pending").order("created_at", desc=True).execute().data or []
        if not reqs:
            st.success("Sem pedidos pendentes.")
        else:
            for r in reqs:
                with st.container(border=True):
                    st.write(f"**{r['name']}** — {r['school']} ({r['school_type']})")
                    cols = st.columns([1, 1, 2])
                    with cols[0]:
                        if st.button("Aprovar", key=f"ap_{r['id']}"):
                            # garante user e aprova
                            u = get_user_exact(r["name"], r["school"])
                            if not u:
                                u = create_trial_user(r["name"], r["school"], r["school_type"])
                            sb.table("app_users").update({
                                "status": "approved",
                                "daily_limit": 6  # default aprovado (pode mudar)
                            }).eq("id", u["id"]).execute()
                            sb.table("access_requests").update({"status": "approved"}).eq("id", r["id"]).execute()
                            st.success("Aprovado.")
                            st.rerun()
                    with cols[1]:
                        if st.button("Rejeitar", key=f"rj_{r['id']}"):
                            sb.table("access_requests").update({"status": "rejected"}).eq("id", r["id"]).execute()
                            st.warning("Rejeitado.")
                            st.rerun()
                    with cols[2]:
                        st.caption("Aprovar dá acesso total e aumenta limite por padrão (pode ajustar em Professores).")

    with t2:
        st.subheader("Lista de professores (bloquear / aumentar limite / remover)")
        users = sb.table("app_users").select("*").order("created_at", desc=True).execute().data or []
        if not users:
            st.info("Sem utilizadores.")
        else:
            for u in users:
                used = get_usage(u["id"])
                with st.container(border=True):
                    st.write(f"**{u['name']}** — {u['school']} ({u['school_type']})")
                    st.caption(f"Status: {u['status']} | Limite: {u['daily_limit']} | Hoje: {used}/{u['daily_limit']}")

                    c1, c2, c3, c4 = st.columns([1, 1, 1, 2])
                    with c1:
                        new_limit = st.number_input("Novo limite", 0, 50, int(u["daily_limit"]), key=f"lim_{u['id']}")
                        if st.button("Guardar limite", key=f"sl_{u['id']}"):
                            sb.table("app_users").update({"daily_limit": int(new_limit)}).eq("id", u["id"]).execute()
                            st.success("Atualizado.")
                            st.rerun()

                    with c2:
                        if st.button("Aprovar", key=f"ok_{u['id']}"):
                            sb.table("app_users").update({"status": "approved"}).eq("id", u["id"]).execute()
                            st.success("Aprovado.")
                            st.rerun()
                        if st.button("Bloquear", key=f"bk_{u['id']}"):
                            sb.table("app_users").update({"status": "blocked"}).eq("id", u["id"]).execute()
                            st.warning("Bloqueado.")
                            st.rerun()

                    with c3:
                        if st.button("Remover", key=f"rm_{u['id']}"):
                            # remove também planos e uso (cascade)
                            sb.table("app_users").delete().eq("id", u["id"]).execute()
                            st.error("Utilizador removido.")
                            st.rerun()

                    with c4:
                        st.caption("Use Remover para utilizadores estranhos/desconhecidos. É irreversível.")

    with t3:
        st.subheader("Planos gerados hoje")
        # simples: lista plans do dia
        plans = sb.table("plans").select("*").eq("day", today_iso()).order("created_at", desc=True).execute().data or []
        if not plans:
            st.info("Nenhum plano hoje.")
        else:
            for p in plans:
                u = sb.table("app_users").select("name,school").eq("id", p["user_id"]).limit(1).execute().data
                who = f"{u[0]['name']} — {u[0]['school']}" if u else "Desconhecido"
                st.write(f"**{who}** | {p['class_level']}ª | {p['discipline']} | {p['topic']} | {p['created_at']}")

    st.stop()


# ---------------- TEACHER APP ----------------
if st.session_state.role == "teacher" and st.session_state.user:
    u = st.session_state.user

    # re-carregar do DB (para refletir aprovação/limite)
    u2 = sb.table("app_users").select("*").eq("id", u["id"]).limit(1).execute().data
    if u2:
        u = u2[0]
        st.session_state.user = u

    st.divider()
    st.header("Área do Professor")

    ok, msg = can_generate(u)
    st.info(msg)

    tabs2 = st.tabs(["Gerar Plano", "Meus Planos", "Ajuda"])

    # ---- Gerar ----
    with tabs2[0]:
        col1, col2 = st.columns(2)
        with col1:
            discipline = st.text_input("Disciplina", "Língua Portuguesa")
            class_level = st.selectbox("Classe", list(range(1, 13)), index=0)
        with col2:
            duration = st.selectbox("Duração (min)", [45, 90], index=0)
            topic = st.text_input("Tema", placeholder="Ex.: Leitura de pequenos textos; Frações...")

        if st.button("Gerar Pré-visualização", type="primary"):
            if not ok:
                st.error("Não pode gerar agora. Limite diário atingido ou acesso bloqueado.")
            elif not norm(topic):
                st.warning("Preencha o tema.")
            else:
                genai.configure(api_key=GOOGLE_API_KEY)
                prompt = build_prompt(discipline, int(class_level), norm(topic), int(duration), u["school_type"])
                model = genai.GenerativeModel("models/gemini-1.5-flash")
                resp = model.generate_content(prompt)
                st.session_state.draft = resp.text.strip()
                st.rerun()

        if st.session_state.draft:
            st.subheader("Pré-visualização (imagens)")
            imgs = plan_to_images(st.session_state.draft)
            for i, im in enumerate(imgs, start=1):
                st.image(im, caption=f"Página {i}", use_container_width=True)

            st.subheader("Texto (editável)")
            edited = st.text_area("Plano", st.session_state.draft, height=320)

            c1, c2 = st.columns([1, 1])
            with c1:
                if st.button("Confirmar e Gerar PDF"):
                    # incrementa uso + salva plano + gera pdf
                    ok2, msg2 = can_generate(u)
                    if not ok2:
                        st.error(msg2)
                    else:
                        inc_usage(u["id"])
                        save_plan(u["id"], int(class_level), discipline, norm(topic), edited)
                        pdf_bytes = generate_pdf(edited)
                        st.download_button(
                            "Baixar PDF",
                            data=pdf_bytes,
                            file_name=f"Plano_{discipline}_{class_level}a_{today_iso()}.pdf",
                            mime="application/pdf",
                            type="primary"
                        )
                        st.success("Plano registado e PDF gerado. Pode baixar novamente em 'Meus Planos'.")
                        st.session_state.draft = None
                        st.rerun()

            with c2:
                if st.button("Cancelar rascunho"):
                    st.session_state.draft = None
                    st.rerun()

    # ---- Meus Planos ----
    with tabs2[1]:
        st.subheader("Planos já gerados (baixar novamente)")
        plans = list_my_plans(u["id"])
        if not plans:
            st.info("Ainda não gerou planos.")
        else:
            # filtros simples
            f1, f2 = st.columns(2)
            with f1:
                cls = st.selectbox("Filtrar por classe", ["Todas"] + sorted(list({p["class_level"] for p in plans})))
            with f2:
                disc = st.selectbox("Filtrar por disciplina", ["Todas"] + sorted(list({p["discipline"] for p in plans})))

            def match(p):
                if cls != "Todas" and p["class_level"] != cls:
                    return False
                if disc != "Todas" and p["discipline"] != disc:
                    return False
                return True

            for p in [x for x in plans if match(x)]:
                with st.container(border=True):
                    st.write(f"**{p['created_at']}** — {p['class_level']}ª — {p['discipline']} — {p['topic']}")
                    if st.button("Ver e Baixar PDF", key=f"bx_{p['id']}"):
                        pdf_bytes = generate_pdf(p["plan_text"])
                        st.text_area("Plano", p["plan_text"], height=220)
                        st.download_button(
                            "Baixar PDF novamente",
                            data=pdf_bytes,
                            file_name=f"Plano_{p['discipline']}_{p['class_level']}a_{p['day']}.pdf",
                            mime="application/pdf"
                        )

    # ---- Ajuda ----
    with tabs2[2]:
        st.subheader("Ajuda")
        msg = f"Olá! Preciso de apoio no Gerador de Planos. Nome: {u['name']} | Escola: {u['school']}."
        st.link_button("Falar com o Administrador no WhatsApp", wa_link(ADMIN_WHATSAPP, msg))

    st.stop()
