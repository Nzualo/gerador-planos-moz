import streamlit as st
from supabase import create_client
from datetime import datetime
import re

ADMIN_PHONE = "+258867926665"
HELP_WHATSAPP_URL = "https://wa.me/258867926665"

# -------------------------
# Supabase Client
# -------------------------
@st.cache_resource
def supa():
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_SERVICE_ROLE"]
    return create_client(url, key)

db = supa()

# -------------------------
# Helpers
# -------------------------
def normalize_phone(p: str) -> str:
    p = p.strip().replace(" ", "")
    # aceita +258XXXXXXXXX
    return p

def is_valid_phone(p: str) -> bool:
    return bool(re.match(r"^\+\d{8,15}$", p))

def get_user_by_phone(phone: str):
    res = db.table("app_users").select("*").eq("phone", phone).limit(1).execute()
    return res.data[0] if res.data else None

def login(phone: str):
    u = get_user_by_phone(phone)
    if not u:
        return None
    if u["status"] in ("blocked", "pending"):
        return u  # para mostrar mensagem
    return u

def rpc(name: str, params: dict):
    return db.rpc(name, params).execute()

def must_login():
    if "user" not in st.session_state or not st.session_state["user"]:
        st.warning("Faça login para continuar.")
        st.stop()

def is_admin_session() -> bool:
    return st.session_state["user"]["status"] == "admin"

# Placeholder do seu gerador real
def generate_plan_text(class_level: int, subject: str, topic: str) -> str:
    # Aqui você chama seu modelo/rotina real de geração
    return f"""PLANO DE AULA

Classe: {class_level}ª
Disciplina: {subject}
Tema: {topic}

1) Função Didática: Introdução e Motivação
- Fazer controlo de presenças.
- Orientar correção do TPC (se houver).
- Apresentar o tema e objetivos.
- Motivar com exemplo da comunidade/sala.

2) Mediação e Assimilação
- Explicação guiada.
- Atividades práticas.

3) Domínio e Consolidação
- Exercícios de aplicação.

4) Controlo e Avaliação
- Perguntas rápidas para avaliar.
- Síntese final.
- Marcar TPC.
"""

def record_plan(user_key: str, class_level: int, subject: str, topic: str, plan_text: str):
    # Admin ilimitado já está garantido no RPC
    res = rpc("record_plan", {
        "p_user_key": user_key,
        "p_class_level": class_level,
        "p_subject": subject,
        "p_topic": topic,
        "p_plan_text": plan_text,
        "p_pdf_storage_path": None
    })
    return res.data  # retorna UUID do plano

def get_my_plans(user_key: str):
    res = rpc("get_my_plans", {"p_user_key": user_key})
    return res.data or []

# -------------------------
# UI
# -------------------------
st.set_page_config(page_title="Gerador de Planos", layout="wide")

# Sidebar
with st.sidebar:
    st.title("Menu")
    page = st.radio("Ir para", ["Login", "Gerar Plano", "Meus Planos", "Ajuda", "Admin"])
    st.divider()
    if "user" in st.session_state and st.session_state["user"]:
        u = st.session_state["user"]
        st.caption("Sessão")
        st.write(f"**{u['name']}**")
        st.write(f"{u['phone']}")
        st.write(f"Status: `{u['status']}`")
        if st.button("Sair"):
            st.session_state["user"] = None
            st.rerun()

# -------------------------
# Páginas
# -------------------------
if page == "Login":
    st.header("Login (WhatsApp)")
    phone = st.text_input("Seu WhatsApp (ex: +2588XXXXXXXX)", value="")
    if st.button("Entrar"):
        phone = normalize_phone(phone)
        if not is_valid_phone(phone):
            st.error("Número inválido. Use formato +258XXXXXXXXX.")
        else:
            u = login(phone)
            if not u:
                st.info("Você ainda não tem acesso. Faça o pedido abaixo.")
            else:
                if u["status"] == "blocked":
                    st.error("Seu acesso está bloqueado. Contacte o administrador.")
                elif u["status"] == "pending":
                    st.warning("Seu acesso ainda não foi aprovado. Aguarde o administrador.")
                else:
                    st.session_state["user"] = u
                    st.success("Login efetuado.")
                    st.rerun()

    st.subheader("Pedir acesso total (aprovação do administrador)")
    with st.form("req"):
        r_phone = st.text_input("WhatsApp", value="")
        r_name = st.text_input("Nome do Professor", value="")
        r_school = st.text_input("Escola", value="")
        r_school_type = st.selectbox("Tipo de Escola", ["EP", "EB", "ES1", "ES2"], index=0)
        submitted = st.form_submit_button("Enviar pedido")
        if submitted:
            r_phone = normalize_phone(r_phone)
            if not (is_valid_phone(r_phone) and r_name.strip() and r_school.strip()):
                st.error("Preencha WhatsApp, Nome e Escola corretamente.")
            else:
                rpc("request_access", {
                    "p_phone": r_phone,
                    "p_name": r_name.strip(),
                    "p_school": r_school.strip(),
                    "p_school_type": r_school_type
                })
                st.success("Pedido enviado. Aguarde aprovação do administrador.")

elif page == "Gerar Plano":
    must_login()
    st.header("Gerar Plano")

    u = st.session_state["user"]
    user_key = u["user_key"]

    # Checagem de limite (admin sempre true)
    can = rpc("can_generate_plan", {"p_user_key": user_key}).data
    if not can and u["status"] != "admin":
        st.error("Limite diário atingido. Contacte o administrador para aumentar o limite.")
        st.stop()

    col1, col2 = st.columns(2)
    with col1:
        class_level = st.number_input("Classe", min_value=1, max_value=12, value=6, step=1)
        subject = st.text_input("Disciplina", value="Matemática")
    with col2:
        topic = st.text_input("Tema", value="Grande e pequeno")
        st.caption("Admin: ilimitado | Professor: respeita daily_limit")

    if st.button("Gerar agora"):
        plan_text = generate_plan_text(class_level, subject.strip(), topic.strip())

        try:
            plan_id = record_plan(user_key, class_level, subject.strip(), topic.strip(), plan_text)
            st.success(f"Plano registado com sucesso. ID: {plan_id}")
        except Exception as e:
            st.error(f"Erro ao registar plano: {e}")
            st.stop()

        st.subheader("Pré-visualização do plano")
        st.text_area("Plano", plan_text, height=420)

        # Download simples (TXT). Se quiser PDF, plugamos seu gerador depois.
        st.download_button(
            "Baixar (TXT)",
            data=plan_text.encode("utf-8"),
            file_name=f"plano_{class_level}a_{datetime.now().strftime('%Y%m%d_%H%M')}.txt",
            mime="text/plain"
        )

elif page == "Meus Planos":
    must_login()
    st.header("Meus Planos (baixar novamente)")

    u = st.session_state["user"]
    plans = get_my_plans(u["user_key"])

    if not plans:
        st.info("Você ainda não gerou nenhum plano.")
    else:
        # Organiza por data, classe
        for p in plans:
            dt = p["created_at"]
            st.write(f"**{dt}** — {p['class_level']}ª — {p['subject']} — {p['topic']}")
            # Recarrega o texto do plano ao clicar
            if st.button(f"Ver / Baixar novamente ({p['id']})", key=str(p["id"])):
                # Buscar texto completo
                row = db.table("user_plans").select("plan_text").eq("id", p["id"]).limit(1).execute()
                if row.data:
                    txt = row.data[0]["plan_text"]
                    st.text_area("Plano", txt, height=420)
                    st.download_button(
                        "Baixar (TXT)",
                        data=txt.encode("utf-8"),
                        file_name=f"plano_{p['class_level']}a_{datetime.now().strftime('%Y%m%d_%H%M')}.txt",
                        mime="text/plain",
                        key=f"dl_{p['id']}"
                    )
                else:
                    st.error("Não foi possível carregar o plano.")

elif page == "Ajuda":
    st.header("Ajuda")
    st.write("Para suporte e dúvidas sobre funcionalidades, fale com o administrador no WhatsApp.")
    st.link_button("Abrir WhatsApp do Administrador", HELP_WHATSAPP_URL)

elif page == "Admin":
    must_login()
    if not is_admin_session():
        st.error("Apenas o administrador tem acesso a esta página.")
        st.stop()

    st.header("Administração")
    admin_key = st.session_state["user"]["user_key"]

    tab1, tab2 = st.tabs(["Pedidos de acesso", "Usuários"])

    with tab1:
        st.subheader("Pedidos pendentes")
        reqs = db.table("access_requests").select("*").eq("status", "pending").order("created_at", desc=True).execute().data
        if not reqs:
            st.info("Sem pedidos pendentes.")
        else:
            for r in reqs:
                st.write(f"**{r['name']}** — {r['phone']} — {r['school']} ({r['school_type']}) — {r['created_at']}")
                c1, c2 = st.columns(2)
                with c1:
                    new_limit = st.number_input("Limite diário ao aprovar", min_value=0, max_value=100, value=2, key=f"lim_{r['id']}")
                    if st.button("Aprovar", key=f"ap_{r['id']}"):
                        rpc("admin_approve_request", {"p_admin_key": admin_key, "p_request_id": r["id"], "p_limit": int(new_limit)})
                        st.success("Aprovado.")
                        st.rerun()
                with c2:
                    if st.button("Rejeitar", key=f"rej_{r['id']}"):
                        rpc("admin_reject_request", {"p_admin_key": admin_key, "p_request_id": r["id"]})
                        st.warning("Rejeitado.")
                        st.rerun()

    with tab2:
        st.subheader("Usuários (limites, planos e revogar/bloquear)")
        users = rpc("admin_list_users", {"p_admin_key": admin_key}).data or []
        if not users:
            st.info("Nenhum usuário.")
        else:
            for u in users:
                st.write(
                    f"**{u['name']}** — {u['phone']} — {u['school']} ({u['school_type']}) "
                    f"| status=`{u['status']}` | limite={u['daily_limit']} | hoje={u['plans_today']} | total={u['total_plans']}"
                )

                # Remover usuários estranhos / bloquear / aprovar / mudar limite
                c1, c2, c3 = st.columns(3)
                with c1:
                    new_limit = st.number_input("Novo limite", min_value=0, max_value=100, value=int(u["daily_limit"]), key=f"nl_{u['user_key']}")
                    if st.button("Atualizar limite", key=f"ul_{u['user_key']}"):
                        rpc("admin_set_daily_limit", {"p_admin_key": admin_key, "p_user_key": u["user_key"], "p_new_limit": int(new_limit)})
                        st.success("Limite atualizado.")
                        st.rerun()
                with c2:
                    if st.button("Bloquear", key=f"bl_{u['user_key']}"):
                        rpc("admin_set_status", {"p_admin_key": admin_key, "p_user_key": u["user_key"], "p_status": "blocked"})
                        st.warning("Usuário bloqueado.")
                        st.rerun()
                    if st.button("Aprovar", key=f"ok_{u['user_key']}"):
                        rpc("admin_set_status", {"p_admin_key": admin_key, "p_user_key": u["user_key"], "p_status": "approved"})
                        st.success("Usuário aprovado.")
                        st.rerun()
                with c3:
                    # “Remover usuário estranho” = bloquear + (opcional) apagar planos. Aqui só bloqueia por segurança.
                    if st.button("Remover (bloquear)", key=f"rm_{u['user_key']}"):
                        rpc("admin_set_status", {"p_admin_key": admin_key, "p_user_key": u["user_key"], "p_status": "blocked"})
                        st.warning("Removido (bloqueado).")
                        st.rerun()
