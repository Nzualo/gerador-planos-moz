import streamlit as st
from utils import supa


def admin_panel(admin_name: str = "Administrador"):
    st.subheader("🛠️ Painel do Administrador")
    st.caption(f"Bem-vindo, {admin_name}")

    sb = supa()

    # -------------------------
    # LISTAR UTILIZADORES
    # -------------------------
    st.markdown("### 👥 Professores registados")

    r = sb.table("app_users").select(
        "name, school, status, created_at"
    ).order("created_at", desc=True).execute()

    if not r.data:
        st.info("Nenhum utilizador registado.")
        return

    st.dataframe(r.data, use_container_width=True)

    # -------------------------
    # ALTERAR ESTADO
    # -------------------------
    st.markdown("### 🔄 Alterar estado do professor")

    nomes = [
        f"{u['name']} | {u['school']} | {u['status']}"
        for u in r.data
    ]

    escolha = st.selectbox("Selecionar professor", nomes)

    novo_estado = st.selectbox(
        "Novo estado",
        ["trial", "approved", "blocked"]
    )

    if st.button("Guardar alteração"):
        nome_sel, escola_sel, _ = escolha.split(" | ")

        sb.table("app_users").update(
            {"status": novo_estado}
        ).eq("name", nome_sel).eq("school", escola_sel).execute()

        st.success("Estado atualizado com sucesso.")
        st.rerun()
