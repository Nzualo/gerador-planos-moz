import streamlit as st
from utils import supa, pin_hash, make_user_key, normalize_text


# ----------------
# Lista oficial de escolas (Inhassoro)
# ----------------
SCHOOLS = [
    "EP de Petane 1",
    "ES Santo Eusebio",
    "EB de Mananisse",
    "EP de Chibo",
    "EP de Inhassoro",
    "ES de Inhassoro",
    "EP de Fequete",
    "EB de 20 de Junho de Petane 2",
    "EP de Macurrumbe",
    "EP de Gatsala",
    "ES Filipe J. Nyusi",
    "EP de Chibamo",
    "EP Armando E. Guebuza",
    "EP de Vulanjane",
    "EP de Macovane",
    "EB de Vuca",
    "EP de Chitsotso",
    "ES 04 de Outubro",
    "EP de Mangungumete",
    "EP de Jose",
    "EP de Joaquim Mara",
    "EB de Chitsecane",
    "EP Zava",
    "EP de Nguenguemane",
    "EP de Matsanze",
    "EP de Buxane",
    "EP de Ngonhamo",
    "EB de Cometela",
    "EP de Mulepa",
    "EP de Chiquiriva",
    "EP de Manusse",
    "EP de Timane",
    "EP de Tiane",
    "EP de Mahungane",
    "EP de Macheco",
    "EP de Catine",
    "EP de Nhapele",
    "EP de Cachane",
    "EP de Chipongo",
    "EP de Nhamanheca",
    "EP de Mapandzene",
    "EB de Maimelane",
    "ES 07 de Abril de Maimelane",
    "EP de Mabime",
    "EP de Rumbatsatsa",
    "EP de Chihamele",
    "EP de Madacare",
    "EP de Mahoche",
    "EP de Nhamanhate",
    "EP de Mangarelane",
    "EP de Sangazive",
    "EB de bazaruto",
    "EB de Zenguelemo",
    "EP de Pangara",
    "EP de Chitchuete",
    'Instituto Industrial e Comercial "Estrela do Mar" de Inhassoro',
    "Serviço Distrital de Educação, Juventude e Tecnologia de Inhassoro",
]


def _school_norm_map():
    """mapa norm -> nome original"""
    m = {}
    for s in SCHOOLS:
        m[normalize_text(s)] = s
    return m


SCHOOL_MAP = _school_norm_map()

# aliases aceites -> escola oficial
ALIASES = {
    "sdejt": "Serviço Distrital de Educação, Juventude e Tecnologia de Inhassoro",
    "servico distrital": "Serviço Distrital de Educação, Juventude e Tecnologia de Inhassoro",
    "servico distrital de educacao juventude e tecnologia": "Serviço Distrital de Educação, Juventude e Tecnologia de Inhassoro",
    "instituto estrela do mar": 'Instituto Industrial e Comercial "Estrela do Mar" de Inhassoro',
    "ii estrela do mar": 'Instituto Industrial e Comercial "Estrela do Mar" de Inhassoro',
    "ii": 'Instituto Industrial e Comercial "Estrela do Mar" de Inhassoro',
}

# abreviações
ABBR = {
    "escola primaria": "ep",
    "primaria": "ep",
    "escola basica": "eb",
    "basica": "eb",
    "escola secundaria": "es",
    "secundaria": "es",
    "instituto": "ii",
}


def canonicalize_school(user_input: str) -> str | None:
    """
    - aceita EP/EB/ES/II escritos por extenso
    - aceita SDEJT como alias
    - valida contra lista oficial
    """
    raw = normalize_text(user_input)

    # alias directo (ex: "sdejt")
    if raw in ALIASES:
        return ALIASES[raw]

    # substituir termos por abreviações (ex: "escola primaria" -> "ep")
    for k, v in ABBR.items():
        raw = raw.replace(k, v)
    raw = normalize_text(raw)

    # tenta match directo na lista oficial
    if raw in SCHOOL_MAP:
        return SCHOOL_MAP[raw]

    # tenta “começa com” para casos tipo: "ep inhassoro" vs "ep de inhassoro"
    for norm, original in SCHOOL_MAP.items():
        if raw == norm:
            return original
        if raw.replace(" de ", " ").replace(" do ", " ").replace(" da ", " ") == norm.replace(" de ", " ").replace(" do ", " ").replace(" da ", " "):
            return original

    return None


def auth_gate():
    # já logado
    if st.session_state.get("logged_in"):
        return

    st.subheader("🔐 Acesso ao Sistema (PIN)")

    col1, col2 = st.columns(2)
    with col1:
        name = st.text_input("Nome do Professor")
        school_in = st.text_input("Escola (ex.: EP de Inhassoro)")
    with col2:
        mode = st.radio("Modo", ["Entrar", "Primeiro acesso (criar PIN)"], horizontal=True)

    # valida escola
    school_ok = canonicalize_school(school_in) if school_in else None
    if school_in and not school_ok:
        st.error("Escola não registada no sistema. Verifique o nome (ou contacte o SDEJT).")

    if mode == "Entrar":
        pin = st.text_input("PIN", type="password")

        if st.button("✅ Entrar", type="primary"):
            if not name or not school_in or not pin:
                st.error("Preencha nome, escola e PIN.")
                st.stop()

            if not school_ok:
                st.error("Escola inválida.")
                st.stop()

            user_key = make_user_key(name, school_ok)
            sb = supa()
            r = sb.table("app_users").select("*").eq("user_key", user_key).limit(1).execute()

            if not r.data:
                st.error("Utilizador não encontrado. Use 'Primeiro acesso (criar PIN)'.")
                st.stop()

            user = r.data[0]
            if user.get("pin_hash") != pin_hash(pin):
                st.error("PIN incorrecto.")
                st.stop()

            st.session_state["logged_in"] = True
            st.session_state["user"] = user
            st.success("Login efectuado com sucesso.")
            st.rerun()

    else:
        pin1 = st.text_input("Criar PIN", type="password")
        pin2 = st.text_input("Confirmar PIN", type="password")

        if st.button("📝 Registar e Entrar", type="primary"):
            if not name or not school_in or not pin1 or not pin2:
                st.error("Preencha tudo.")
                st.stop()

            if not school_ok:
                st.error("Escola inválida.")
                st.stop()

            if pin1 != pin2:
                st.error("Os PINs não coincidem.")
                st.stop()

            if len(pin1) < 4:
                st.error("PIN muito curto. Use no mínimo 4 dígitos/caracteres.")
                st.stop()

            user_key = make_user_key(name, school_ok)
            sb = supa()
            existing = sb.table("app_users").select("*").eq("user_key", user_key).limit(1).execute()

            if existing.data:
                st.error("Esse utilizador já existe. Use 'Entrar'.")
                st.stop()

            # criar utilizador
            sb.table("app_users").insert({
                "user_key": user_key,
                "name": name.strip(),
                "school": school_ok,
                "pin_hash": pin_hash(pin1),
                "status": "trial",
                "daily_limit": 2,
            }).execute()

            user = sb.table("app_users").select("*").eq("user_key", user_key).limit(1).execute().data[0]
            st.session_state["logged_in"] = True
            st.session_state["user"] = user
            st.success("Registo feito com sucesso.")
            st.rerun()
