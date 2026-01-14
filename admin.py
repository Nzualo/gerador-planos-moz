import streamlit as st

def admin_panel(admin_name: str = "Admin"):
    st.sidebar.markdown("### Administração")
    st.sidebar.success(f"Administrador: {admin_name}")
    st.sidebar.info("Painel do Administrador (em construção)")
