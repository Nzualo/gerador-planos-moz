import streamlit as st
from utils import supa, pin_hash, make_user_key, normalize_text


@st.cache_data(ttl=3600)
def auth_gate():
    # Já autenticado
    if st.session_state.get("logged_in"):
        return

    st.title("🔐 Acesso ao Sistema SDEJT")

    nome = st.text_input("Nome do Professor")
    escola = st.text_input("Escola onde lecciona")
    pin = st.text_input("PIN", type="password")

    if st.button("Entrar"):
        if not nome or not escola or not pin:
            st.error("Preencha todos os campos.")
            st.stop()

        nome_n = normalize_text(nome)
        escola_n = normalize_text(escola)

        user_key = make_user_key(nome_n, escola_n)
        sb = supa()

        r = sb.table("app_users").select("*").eq("user_key", user_key).limit(1).execute()

        # Primeiro acesso → criar utilizador
        if not r.data:
            sb.table("app_users").insert({
                "user_key": user_key,
                "name": nome,
                "school": escola,
                "pin_hash": pin_hash(pin),
                "status": "trial",
            }).execute()

            user = sb.table("app_users").select("*").eq("user_key", user_key).limit(1).execute().data[0]

        else:
            user = r.data[0]

            if user["pin_hash"] != pin_hash(pin):
                st.error("PIN incorrecto.")
                st.stop()

        st.session_state["logged_in"] = True
        st.session_state["user"] = user
        st.success("Login efectuado com sucesso.")
        st.rerun()
