import io
import re
import textwrap
from datetime import date, datetime
from uuid import uuid4

import streamlit as st
from PIL import Image, ImageDraw, ImageFont
from supabase import create_client

# FPDF (não fpdf2)
from fpdf import FPDF


# ---------------- CONFIG ----------------
st.set_page_config(page_title="Gerador de Planos", layout="wide")

SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_ANON_KEY = st.secrets["SUPABASE_ANON_KEY"]
SUPABASE_SERVICE_ROLE_KEY = st.secrets["SUPABASE_SERVICE_ROLE_KEY"]
ADMIN_WHATSAPP = st.secrets.get("ADMIN_WHATSAPP", "+258867926665")

# Usamos service-role no backend do Streamlit para poder:
# - aprovar/bloquear/remover
# - listar planos e downloads
# Segurança: fica só no servidor.
sb = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)


SCHOOL_TYPES = ["EP", "EB", "ES1", "ES2"]
CLASS_LEVELS = [1, 2, 3, 4, 5, 6, 7, 8, 9]
DISCIPLINES = [
    "Português", "Matemática", "Ciências Naturais", "Educação Moral e Cívica",
    "História", "Geografia", "Inglês", "Educação Física", "Outra"
]


# ---------------- UTILS ----------------
def norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip())


def now_iso() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def whatsapp_link(number: str, text: str) -> str:
    n = re.sub(r"[^\d]", "", number)
    t = text.replace(" ", "%20")
    return f"https://wa.me/{n}?text={t}"


def get_or_create_request(name, school, school_type, whatsapp):
    name_n = norm(name)
    school_n = norm(school)
    whatsapp_n = norm(whatsapp)

    # Já existe pedido pendente?
    r = sb.table("access_requests") \
        .select("*") \
        .eq("name", name_n) \
        .eq("school", school_n) \
        .order("created_at", desc=True) \
        .limit(1).execute()

    if r.data:
        return r.data[0]

    ins = sb.table("access_requests").insert({
        "name": name_n,
        "school": school_n,
        "school_type": school_type,
        "whatsapp": whatsapp_n,
        "status": "pending"
    }).execute()
    return ins.data[0] if ins.data else None


def get_user_by_name_school(name, school):
    name_n = norm(name)
    school_n = norm(school)
    r = sb.table("app_users") \
        .select("*") \
        .eq("name", name_n) \
        .eq("school", school_n) \
        .limit(1).execute()
    return r.data[0] if r.data else None


def ensure_user_from_request(req, approved_by="admin"):
    """Se aprovado, cria/atualiza app_users."""
    existing = get_user_by_name_school(req["name"], req["school"])
    if existing:
        upd = sb.table("app_users").update({
            "status": "approved",
            "school_type": req.get("school_type", "EP"),
            "approved_at": now_iso(),
            "approved_by": approved_by
        }).eq("id", existing["id"]).execute()
        return upd.data[0] if upd.data else existing

    ins = sb.table("app_users").insert({
        "name": req["name"],
        "school": req["school"],
        "school_type": req.get("school_type", "EP"),
        "status": "approved",
        "daily_limit": 2,
        "approved_at": now_iso(),
        "approved_by": approved_by
    }).execute()
    return ins.data[0] if ins.data else None


def get_usage_today(user_id):
    today = date.today().isoformat()
    r = sb.table("usage_daily") \
        .select("*") \
        .eq("user_id", user_id) \
        .eq("day", today) \
        .limit(1).execute()
    if not r.data:
        return 0
    return int(r.data[0]["count"])


def can_generate(user):
    used = get_usage_today(user["id"])
    limit = int(user.get("daily_limit", 2))
    return (used < limit), used, limit


def bump_usage(user_id):
    today = date.today().isoformat()
    used = get_usage_today(user_id)
    sb.table("usage_daily").upsert({
        "user_id": user_id,
        "day": today,
        "count": used + 1
    }).execute()
    return used + 1


def list_user_plans(user_id):
    r = sb.table("user_plans") \
        .select("*") \
        .eq("user_id", user_id) \
        .order("created_at", desc=True) \
        .execute()
    return r.data or []


def upload_pdf_to_storage(user_id, pdf_bytes: bytes, filename: str):
    # path organizado por data e user
    yyyy = datetime.now().strftime("%Y")
    mm = datetime.now().strftime("%m")
    dd = datetime.now().strftime("%d")
    safe_name = re.sub(r"[^a-zA-Z0-9._-]+", "_", filename)
    path = f"{user_id}/{yyyy}/{mm}/{dd}/{uuid4().hex}_{safe_name}"

    # upload
    sb.storage.from_("plans").upload(
        path=path,
        file=pdf_bytes,
        file_options={
            "content-type": "application/pdf",
            "upsert": True
        }
    )
    return path


def download_pdf_from_storage(path: str) -> bytes:
    return sb.storage.from_("plans").download(path)


# ---------------- PLAN BUILDER ----------------
def build_plan_text(name, school, school_type, class_level, discipline, topic, duration_min):
    # Pedidos do utilizador:
    # - 1ª Função: introdução/motivação inclui controle de presenças + correção TPC (se houver)
    # - última: controlo/avaliação inclui marcar TPC
    # - 1 a 6 classe: usar também Livro do Aluno como meio (quando aplicável)
    uses_student_book = (1 <= class_level <= 6)

    meios = [
        "Quadro", "Giz/Marcador", "Caderno do aluno"
    ]
    if uses_student_book:
        meios.append("Livro do Aluno")
    meios.append("Fichas de exercícios (se necessário)")

    objetivos = [
        f"Compreender o tema: {topic}.",
        "Participar ativamente na aula, respondendo a perguntas e resolvendo exercícios.",
        "Aplicar os conhecimentos em exemplos práticos."
    ]

    # Tabela didática ajustada
    # (tempo total aproximado, mas serve como base)
    # Ajuste simples para bater no duration_min
    intro = 5
    mediacao = max(10, duration_min - (intro + 10))  # reserva 10 p/ consolidação+avaliação
    consolidacao = 10
    avaliacao = max(5, duration_min - (intro + mediacao + consolidacao))
    total = intro + mediacao + consolidacao + avaliacao

    if total != duration_min:
        # Ajuste fino no bloco de mediação
        mediacao = max(10, mediacao + (duration_min - total))

    plan = f"""PLANO DE AULA

Professor: {name}
Escola: {school} ({school_type})
Classe: {class_level}ª
Disciplina: {discipline}
Tema: {topic}
Duração: {duration_min} minutos

1) Objetivos
- {objetivos[0]}
- {objetivos[1]}
- {objetivos[2]}

2) Meios e Recursos
- {", ".join(meios)}

3) Estratégias / Metodologia
- Exposição dialogada, perguntas orientadoras, exemplos do quotidiano e exercícios guiados.
- Trabalho individual ou em pares conforme a turma.

4) Desenvolvimento da Aula (Funções Didáticas)
A) Introdução e Motivação ({intro} min)
- Professor: Cumprimenta a turma; faz o controlo de presenças; verifica e orienta a correção do TPC (se houver).
- Professor: Apresenta o objetivo da aula e faz uma pergunta motivadora relacionada ao tema.
- Alunos: Respondem e partilham experiências.

B) Mediação e Assimilação ({mediacao} min)
- Professor: Explica o conteúdo com exemplos; orienta a participação; demonstra no quadro.
- Alunos: Tomam notas; realizam pequenos exercícios; consultam materiais (incl. livro do aluno quando aplicável).

C) Domínio e Consolidação ({consolidacao} min)
- Professor: Propõe exercícios de consolidação; circula e apoia; corrige em plenário.
- Alunos: Resolvem exercícios; justificam respostas.

D) Controlo e Avaliação ({avaliacao} min)
- Professor: Faz perguntas de verificação; recolhe evidências de aprendizagem; resume pontos-chave.
- Professor: Marca o TPC (trabalho para casa) e explica claramente o que deve ser feito.
- Alunos: Respondem; registam o TPC.

5) TPC (Trabalho para Casa)
- Resolver 3–5 exercícios relacionados com o tema "{topic}" (adequar ao nível da turma).

Observações
- Ajustar exemplos ao contexto local da turma e ao tempo real da aula.
"""
    return plan


# ---------------- PREVIEW IMAGES ----------------
def plan_to_preview_images(plan_text: str, title="Pré-visualização do plano"):
    """
    Gera imagens (PIL) com texto paginado para pré-visualização no Streamlit.
    """
    # Config
    W, H = 1240, 1754  # aprox A4 @ 150 dpi
    margin = 70
    line_spacing = 8

    # Font fallback (DejaVu recomendado)
    # Você pode colocar DejaVuSans.ttf no mesmo diretório para melhorar
    try:
        font = ImageFont.truetype("DejaVuSans.ttf", 28)
        font_b = ImageFont.truetype("DejaVuSans-Bold.ttf", 34)
    except Exception:
        font = ImageFont.load_default()
        font_b = ImageFont.load_default()

    # Quebra em linhas
    lines = []
    for paragraph in plan_text.split("\n"):
        if paragraph.strip() == "":
            lines.append("")
            continue
        wrapped = textwrap.wrap(paragraph, width=90)
        lines.extend(wrapped if wrapped else [""])

    # Montar páginas
    pages = []
    img = Image.new("RGB", (W, H), color="white")
    draw = ImageDraw.Draw(img)

    y = margin
    draw.text((margin, y), title, fill="black", font=font_b)
    y += 60

    for line in lines:
        # medir altura
        bbox = draw.textbbox((0, 0), line if line else " ", font=font)
        line_h = (bbox[3] - bbox[1]) + line_spacing

        if y + line_h > H - margin:
            pages.append(img)
            img = Image.new("RGB", (W, H), color="white")
            draw = ImageDraw.Draw(img)
            y = margin
            draw.text((margin, y), title, fill="black", font=font_b)
            y += 60

        draw.text((margin, y), line, fill="black", font=font)
        y += line_h

    pages.append(img)
    return pages


# ---------------- PDF (FPDF) ----------------
class PDF(FPDF):
    pass


def generate_pdf_bytes(plan_text: str) -> bytes:
    pdf = PDF(orientation="P", unit="mm", format="A4")
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()

    # Fontes (coloque DejaVuSans.ttf e DejaVuSans-Bold.ttf no mesmo dir do app.py)
    # Para não dar erro, garantimos fallback.
    try:
        pdf.add_font("DejaVu", "", "DejaVuSans.ttf", uni=True)
        pdf.add_font("DejaVu", "B", "DejaVuSans-Bold.ttf", uni=True)
        base_font = "DejaVu"
    except Exception:
        base_font = "Arial"  # fallback (perde acentos em alguns casos)
        pdf.set_font("Arial", size=12)

    def safe_multicell(txt, bold=False):
        if base_font != "Arial":
            pdf.set_font(base_font, "B" if bold else "", 12)
        else:
            pdf.set_font("Arial", "B" if bold else "", 12)

        # multi_cell robusto
        for paragraph in txt.split("\n"):
            if paragraph.strip() == "":
                pdf.ln(2)
                continue
            # Quebra “palavras gigantes” para evitar erro de espaço horizontal
            paragraph = re.sub(r"(\S{45,})", lambda m: "\n".join(textwrap.wrap(m.group(0), 40)), paragraph)
            pdf.multi_cell(0, 6, paragraph)
        pdf.ln(1)

    safe_multicell(plan_text)

    out = pdf.output(dest="S").encode("latin-1", errors="ignore")
    return out


# ---------------- SESSION ----------------
if "user" not in st.session_state:
    st.session_state.user = None

if "plan_draft" not in st.session_state:
    st.session_state.plan_draft = None

if "plan_inputs" not in st.session_state:
    st.session_state.plan_inputs = {}


# ---------------- LOGIN UI ----------------
def login_screen():
    st.title("Acesso ao Gerador de Planos (Teste/Controlado)")

    st.info(
        "Qualquer professor pode pedir acesso. "
        "Enquanto estiver em aprovação, não consegue gerar planos."
    )

    c1, c2 = st.columns(2)
    with c1:
        name = st.text_input("Nome do professor", placeholder="Ex.: João Matola")
        school = st.text_input("Escola", placeholder="Ex.: Escola Primária de ...")
        school_type = st.selectbox("Tipo de escola", SCHOOL_TYPES, index=0)
    with c2:
        whatsapp = st.text_input("WhatsApp (opcional)", placeholder="Ex.: +258 84....")
        st.caption("Use WhatsApp se quiser ser contactado mais facilmente pelo administrador.")

    if st.button("Entrar / Pedir acesso", type="primary"):
        name_n = norm(name)
        school_n = norm(school)

        if not name_n or not school_n:
            st.warning("Preencha Nome e Escola.")
            return

        user = get_user_by_name_school(name_n, school_n)

        if user:
            if user["status"] == "blocked":
                st.error("O seu acesso foi bloqueado. Contacte o administrador.")
                st.stop()
            if user["status"] == "pending":
                st.info("O seu acesso ainda está em aprovação.")
                st.stop()
            st.session_state.user = user
            st.success("Login realizado.")
            st.rerun()

        # Não existe user -> cria pedido
        req = get_or_create_request(name_n, school_n, school_type, whatsapp)
        st.info("Pedido enviado. Aguarde aprovação do administrador.")
        st.stop()


# ---------------- ADMIN ACTIONS ----------------
def admin_panel(admin_user):
    st.header("Painel do Administrador")

    tab1, tab2, tab3 = st.tabs(["Pedidos de acesso", "Professores", "Planos (visão geral)"])

    # ---- Pedidos ----
    with tab1:
        st.subheader("Pedidos pendentes")
        reqs = sb.table("access_requests").select("*").eq("status", "pending").order("created_at", desc=True).execute().data or []

        if not reqs:
            st.success("Sem pedidos pendentes.")
        else:
            for r in reqs:
                with st.container(border=True):
                    st.write(f"**{r['name']}** — {r['school']} ({r.get('school_type','EP')})")
                    if r.get("whatsapp"):
                        st.caption(f"WhatsApp: {r['whatsapp']}")
                    st.caption(f"Pedido: {r['created_at']}")

                    colA, colB, colC = st.columns([1, 1, 2])
                    with colA:
                        if st.button("Aprovar", key=f"ap_{r['id']}"):
                            user = ensure_user_from_request(r, approved_by=admin_user["name"])
                            sb.table("access_requests").update({
                                "status": "approved",
                                "handled_at": now_iso(),
                                "handled_by": admin_user["name"]
                            }).eq("id", r["id"]).execute()
                            st.success(f"Aprovado: {user['name']}")
                            st.rerun()

                    with colB:
                        if st.button("Rejeitar", key=f"rej_{r['id']}"):
                            sb.table("access_requests").update({
                                "status": "rejected",
                                "handled_at": now_iso(),
                                "handled_by": admin_user["name"]
                            }).eq("id", r["id"]).execute()
                            st.warning("Pedido rejeitado.")
                            st.rerun()

                    with colC:
                        st.caption("Dica: use Rejeitar para pedidos estranhos/nomes desconhecidos.")

    # ---- Professores ----
    with tab2:
        st.subheader("Gerir professores (aprovados/pending/bloqueados)")
        users = sb.table("app_users").select("*").order("created_at", desc=True).execute().data or []

        if not users:
            st.info("Ainda não há utilizadores.")
        else:
            for u in users:
                with st.container(border=True):
                    used = get_usage_today(u["id"])
                    st.write(f"**{u['name']}** — {u['school']} ({u.get('school_type','EP')})")
                    st.caption(f"Status: {u['status']} | Limite diário: {u.get('daily_limit',2)} | Usou hoje: {used}")

                    c1, c2, c3, c4 = st.columns([1, 1, 1, 2])

                    with c1:
                        new_limit = st.number_input(
                            "Limite",
                            min_value=0, max_value=50,
                            value=int(u.get("daily_limit", 2)),
                            key=f"lim_{u['id']}"
                        )
                        if st.button("Atualizar limite", key=f"limbtn_{u['id']}"):
                            sb.table("app_users").update({"daily_limit": int(new_limit)}).eq("id", u["id"]).execute()
                            st.success("Limite atualizado.")
                            st.rerun()

                    with c2:
                        if st.button("Aprovar", key=f"appr_{u['id']}"):
                            sb.table("app_users").update({
                                "status": "approved",
                                "approved_at": now_iso(),
                                "approved_by": admin_user["name"]
                            }).eq("id", u["id"]).execute()
                            st.success("Aprovado.")
                            st.rerun()

                    with c3:
                        if st.button("Bloquear", key=f"blk_{u['id']}"):
                            sb.table("app_users").update({"status": "blocked"}).eq("id", u["id"]).execute()
                            st.warning("Bloqueado.")
                            st.rerun()

                    with c4:
                        # Remover usuário estranho
                        st.caption("Remover apaga o utilizador e todos os planos associados.")
                        if st.button("REMOVER (irreversível)", key=f"del_{u['id']}"):
                            # apagar planos e usage por cascade se FK estiver OK, mas garantimos
                            sb.table("user_plans").delete().eq("user_id", u["id"]).execute()
                            sb.table("usage_daily").delete().eq("user_id", u["id"]).execute()
                            sb.table("app_users").delete().eq("id", u["id"]).execute()
                            st.error("Utilizador removido.")
                            st.rerun()

    # ---- Planos (visão geral) ----
    with tab3:
        st.subheader("Planos gerados (visão geral)")
        plans = sb.table("user_plans").select("*").order("created_at", desc=True).limit(200).execute().data or []
        if not plans:
            st.info("Sem planos ainda.")
        else:
            for p in plans[:200]:
                u = sb.table("app_users").select("name,school").eq("id", p["user_id"]).limit(1).execute().data
                who = f"{u[0]['name']} — {u[0]['school']}" if u else p["user_id"]
                st.write(f"**{who}** | {p['class_level']}ª | {p['discipline']} | {p['topic']} | {p['created_at']}")


# ---------------- USER UI ----------------
def user_app(user):
    st.sidebar.success(f"{user['name']} ({user['school']}) — {user.get('school_type','EP')}")
    if st.sidebar.button("Sair"):
        st.session_state.user = None
        st.session_state.plan_draft = None
        st.session_state.plan_inputs = {}
        st.rerun()

    tabA, tabB, tabC = st.tabs(["Gerar Plano", "Meus Planos", "Ajuda"])

    # ---- GERAR ----
    with tabA:
        st.header("Gerar Plano de Aula")

        allowed, used, limit = can_generate(user)
        st.info(f"Limite diário: **{used}/{limit}** planos usados hoje.")

        if not allowed:
            st.error("Limite diário atingido. Peça aumento ao administrador.")
            st.stop()

        c1, c2, c3 = st.columns(3)
        with c1:
            class_level = st.selectbox("Classe", CLASS_LEVELS, index=0)
            discipline = st.selectbox("Disciplina", DISCIPLINES, index=0)
        with c2:
            topic = st.text_input("Tema", placeholder="Ex.: Grande/Pequeno; Frações; Leitura...")
            duration_min = st.number_input("Duração (min)", min_value=30, max_value=120, value=45, step=5)
        with c3:
            st.caption("Observação")
            st.write("- Para 1ª–6ª classe, o plano inclui **Livro do Aluno** nos meios.")
            st.write("- A introdução inclui **presenças + correção do TPC**.")
            st.write("- No final: **avaliação + marcar TPC**.")

        gen = st.button("Gerar pré-visualização", type="primary")
        if gen:
            if not norm(topic):
                st.warning("Preencha o tema.")
                st.stop()

            plan_text = build_plan_text(
                name=user["name"],
                school=user["school"],
                school_type=user.get("school_type", "EP"),
                class_level=int(class_level),
                discipline=discipline,
                topic=norm(topic),
                duration_min=int(duration_min),
            )
            st.session_state.plan_draft = plan_text
            st.session_state.plan_inputs = {
                "class_level": int(class_level),
                "discipline": discipline,
                "topic": norm(topic),
            }
            st.rerun()

        if st.session_state.plan_draft:
            st.subheader("Pré-visualização (imagens)")
            images = plan_to_preview_images(st.session_state.plan_draft, title="Plano de Aula (Pré-visualização)")
            st.caption("Se estiver tudo certo, clique em “Gerar PDF e Guardar”.")
            for i, im in enumerate(images, start=1):
                st.image(im, caption=f"Página {i}", use_container_width=True)

            st.subheader("Texto do plano")
            st.text_area("Plano (editável)", value=st.session_state.plan_draft, height=300, key="plan_editor")

            colx, coly = st.columns([1, 2])
            with colx:
                if st.button("Gerar PDF e Guardar"):
                    # Usa texto editado (se houve alterações)
                    final_text = st.session_state.plan_editor

                    # Gerar PDF
                    pdf_bytes = generate_pdf_bytes(final_text)

                    # Guardar no Storage
                    inputs = st.session_state.plan_inputs
                    filename = f"Plano_{inputs['class_level']}a_{inputs['discipline']}_{inputs['topic']}.pdf"
                    pdf_path = upload_pdf_to_storage(user["id"], pdf_bytes, filename)

                    # Guardar metadados e texto no banco
                    sb.table("user_plans").insert({
                        "user_id": user["id"],
                        "class_level": inputs["class_level"],
                        "discipline": inputs["discipline"],
                        "topic": inputs["topic"],
                        "plan_text": final_text,
                        "pdf_path": pdf_path
                    }).execute()

                    # Incrementa uso diário
                    bump_usage(user["id"])

                    st.success("Plano guardado. Já pode baixar em “Meus Planos”.")
                    st.session_state.plan_draft = None
                    st.session_state.plan_inputs = {}
                    st.rerun()

            with coly:
                st.caption("Ao guardar: conta 1 plano no limite diário e fica disponível para download posterior.")

    # ---- MEUS PLANOS ----
    with tabB:
        st.header("Meus Planos (por data e classe)")

        plans = list_user_plans(user["id"])
        if not plans:
            st.info("Ainda não há planos guardados.")
        else:
            # filtros
            f1, f2, f3 = st.columns(3)
            with f1:
                cls_filter = st.selectbox("Filtrar por classe", ["Todas"] + [str(x) for x in CLASS_LEVELS], index=0)
            with f2:
                disc_filter = st.selectbox("Filtrar por disciplina", ["Todas"] + sorted(set([p["discipline"] for p in plans])), index=0)
            with f3:
                st.write("")

            def match(p):
                if cls_filter != "Todas" and str(p["class_level"]) != cls_filter:
                    return False
                if disc_filter != "Todas" and p["discipline"] != disc_filter:
                    return False
                return True

            filtered = [p for p in plans if match(p)]

            for p in filtered:
                created = p["created_at"]
                with st.container(border=True):
                    st.write(f"**{p['class_level']}ª — {p['discipline']} — {p['topic']}**")
                    st.caption(f"Data: {created}")

                    col1, col2, col3 = st.columns([1, 1, 2])

                    with col1:
                        if st.button("Ver texto", key=f"vt_{p['id']}"):
                            st.text_area("Plano", value=p["plan_text"], height=250)

                    with col2:
                        if p.get("pdf_path"):
                            try:
                                pdf_bytes = download_pdf_from_storage(p["pdf_path"])
                                st.download_button(
                                    label="Baixar PDF",
                                    data=pdf_bytes,
                                    file_name=f"Plano_{p['class_level']}a_{p['discipline']}_{p['topic']}.pdf",
                                    mime="application/pdf",
                                    key=f"dl_{p['id']}"
                                )
                            except Exception:
                                st.warning("Não foi possível baixar o PDF (verifique Storage/bucket).")
                        else:
                            st.warning("Sem PDF guardado para este plano.")

                    with col3:
                        st.caption("Dica: pode baixar novamente quantas vezes quiser.")

    # ---- AJUDA ----
    with tabC:
        st.header("Ajuda")
        st.write("Para apoio sobre funcionalidades, clique abaixo para falar com o administrador no WhatsApp:")

        msg = f"Olá! Preciso de apoio no Gerador de Planos. Meu nome: {user['name']}, Escola: {user['school']}."
        st.link_button("Falar no WhatsApp do Administrador", whatsapp_link(ADMIN_WHATSAPP, msg))

        st.divider()
        st.subheader("Perguntas rápidas")
        st.write("- Se o limite diário acabou: peça ao admin para aumentar (ex.: 2 → 6).")
        st.write("- Se o acesso estiver pendente: aguarde aprovação.")
        st.write("- Se aparecer erro ao baixar PDF: confirme o bucket `plans` no Storage.")


# ---------------- MAIN ----------------
if not st.session_state.user:
    login_screen()
else:
    user = st.session_state.user

    # Recarrega user do banco para refletir status/limite atualizado
    user_db = sb.table("app_users").select("*").eq("id", user["id"]).limit(1).execute().data
    if user_db:
        user = user_db[0]
        st.session_state.user = user

    if user["status"] == "admin":
        admin_panel(user)
    else:
        if user["status"] == "pending":
            st.info("O seu acesso ainda está em aprovação.")
            st.stop()
        if user["status"] == "blocked":
            st.error("O seu acesso foi bloqueado.")
            st.stop()
        user_app(user)
