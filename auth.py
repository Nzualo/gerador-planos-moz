import streamlit as st
from datetime import datetime

from utils import supa, pin_hash, make_user_key, normalize_text


@st.cache_data(ttl=3600)
def load_schools_map():
    sb = supa()
    r = sb.table("schools").select("name,name_norm").eq("active", True).execute()
    rows = r.data or []
    return {row["name_norm"]: row["name"] for row in rows}


def normalize_school_name(s: str) -> str:
    s = normalize_text(s)

    # aceitar nomes completos
    s = s.replace("escola primaria", "ep")
    s = s.replace("escola basica", "eb")
    s = s.replace("escola secundaria", "es")
    s = s.replace("instituto", "ii")
    s = s.replace("servico distrital", "sdejt")

    # atalhos
    if s == "sdejt":
        s = "sdejt de inhassoro"

    return s


def get_official_school(school_input: str) -> str | None:
    schools = load_schools_map()
    key = normalize_school_name(school_input)
    return schools.get(key)


def get_user_by_key(user_key: str):
    sb = supa()
    r = sb.table("app_users").select("*").eq("user_key", user_key).limit(1).execute()
    return r.data[0] if r.data else None


def create_user(name: str, school: str, pin: str):
    user_key = make_user_key(name, school)
    sb = supa()

    exists = sb.table("app_users").select("user_key").eq("user_key", user_key).limit(1).execute()
    if exists.data:
        return False, "Utilizador já existe. Use Entrar."

    sb.table("app_users").insert({
        "user_key": user_key,
        "name": name.strip(),
        "school": school.strip(),
        "pin_hash": pin_hash(pin),
        "status": "trial",
        "created_at": datetime.now().isoformat()
    }).execute()

    return True, user_key


def login_user(name: str, pin: str):
    sb = supa()
    r = sb.table("app_users").select("*").eq("name", name.strip()).execute()
    users = r.data or []

    if not users:
        return False, "Utilizador não encontrado."

    ph = pin_hash(pin)
    for u in users:
        if u.get("pin_hash") == ph:
            return True, u

    return False, "PIN inválido."


def auth_gate():
    # já logado
    if st.session_state.get("logged_in") and st.session_state.get("user"):
        return

    st.title("🔐 Acesso ao Sistema")
    st.caption("MZ SDEJT - Planos SNE (Inhassoro)")

    tabs = st.tabs(["🆕 Primeiro Registo", "🔐 Entrar"])

    with tabs[0]:
        name = st.text_input("Nome do Professor", key="reg_name")
        school = st.text_input("Escola", key="reg_school", placeholder="Ex: EP de Inhassoro")
        pin1 = st.text_input("Criar PIN", type="password", key="reg_pin1")
        pin2 = st.text_input("Confirmar PIN", type="password", key="reg_pin2")

        if st.button("Registar e Entrar", type="primary", key="btn_reg"):
            if not all([name, school, pin1, pin2]):
                st.error("Preencha todos os campos.")
                st.stop()
            if pin1 != pin2:
                st.error("PINs não coincidem.")
                st.stop()
            if len(pin1) < 4:
                st.error("PIN muito curto (mínimo 4).")
                st.stop()

            school_official = get_official_school(school)
            if not school_official:
                st.error("Escola não registada no sistema. Verifique o nome.")
                st.stop()

            ok, result = create_user(name, school_official, pin1)
            if not ok:
                st.error(result)
                st.stop()

            st.session_state["logged_in"] = True
            st.session_state["user"] = get_user_by_key(result)
            st.rerun()

    with tabs[1]:
        name = st.text_input("Nome", key="login_name")
        pin = st.text_input("PIN", type="password", key="login_pin")

        if st.button("Entrar", type="primary", key="btn_login"):
            ok, result = login_user(name, pin)
            if not ok:
                st.error(result)
                st.stop()

            st.session_state["logged_in"] = True
            st.session_state["user"] = result
            st.rerun()
