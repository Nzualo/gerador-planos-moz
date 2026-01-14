import streamlit as st
import pandas as pd
from datetime import date, datetime, timedelta

from utils import supa, pin_hash


def list_users_df() -> pd.DataFrame:
    sb = supa()
    r = (
        sb.table("app_users")
        .select("user_key,name,school,status,created_at,approved_at,approved_by,daily_limit")
        .order("created_at", desc=True)
        .execute()
    )
    df = pd.DataFrame(r.data or [])
    if df.empty:
        return pd.DataFrame(columns=["user_key","name","school","status","daily_limit","created_at"])
    if "daily_limit" not in df.columns:
        df["daily_limit"] = 2
    return df


def set_user_status(user_key: str, status: str, approved_by: str | None = None):
    sb = supa()
    payload = {"status": status}

    if status == "approved":
        payload["approved_at"] = datetime.now().isoformat()
        payload["approved_by"] = approved_by

    if status in ("trial", "blocked"):
        payload["approved_at"] = None
        payload["approved_by"] = None

    sb.table("app_users").update(payload).eq("user_key", user_key).execute()


def set_daily_limit(user_key: str, daily_limit: int):
    supa().table("app_users").update({"daily_limit": int(daily_limit)}).eq("user_key", user_key).execute()


def reset_pin(user_key: str, new_pin: str):
    supa().table("app_users").update({"pin_hash": pin_hash(new_pin)}).eq("user_key", user_key).execute()


def delete_user(user_key: str):
    supa().table("app_users").delete().eq("user_key", user_key).execute()


def list_plans_all_df(days_back: int = 30) -> pd.DataFrame:
    sb = supa()
    since = (date.today() - timedelta(days=days_back)).isoformat()
    r = (
        sb.table("user_plans")
        .select("id,created_at,plan_day,disciplina,classe,tema,unidade,turma,user_key,pdf_path")
        .gte("plan_day", since)
        .order("created_at", desc=True)
        .execute()
    )
    df = pd.DataFrame(r.data or [])
    if df.empty:
        return pd.DataFrame(columns=["id","created_at","plan_day","disciplina","classe","tema","unidade","turma","user_key","pdf_path"])
    df["created_at"] = pd.to_datetime(df["created_at"], errors="coerce")
    df["plan_day"] = pd.to_datetime(df["plan_day"], errors="coerce").dt.date
    return df


def admin_panel(admin_name: str = "Admin"):
    st.success(f"Administrador: {admin_name}")

    tabs = st.tabs(["📊 Dashboard", "👥 Utilizadores", "📚 Planos (Todos)"])

    with tabs[0]:
        st.subheader("📊 Dashboard SDEJT")
        days_back = st.selectbox("Janela (dias)", [7, 14, 30, 60, 90], index=2)

        users = list_users_df()
        plans = list_plans_all_df(days_back=days_back)

        c1, c2, c3 = st.columns(3)
        c1.metric("Professores registados", len(users) if not users.empty else 0)
        c2.metric("Planos (janela)", len(plans) if not plans.empty else 0)
        c3.metric("Planos hoje", int(plans[plans["plan_day"] == date.today()].shape[0]) if not plans.empty else 0)

        if plans.empty or users.empty:
            st.info("Ainda sem dados suficientes.")
        else:
            p = plans.merge(users[["user_key","name","school"]], on="user_key", how="left")
            by_school = (
                p.groupby("school", as_index=False)
                .size()
                .rename(columns={"size":"planos"})
                .sort_values("planos", ascending=False)
            )
            st.subheader("Planos por Escola")
            st.dataframe(by_school, use_container_width=True, hide_index=True)

    with tabs[1]:
        st.subheader("👥 Gestão de Utilizadores")
        users = list_users_df()
        if users.empty:
            st.info("Sem utilizadores.")
            return

        st.dataframe(users[["name","school","status","daily_limit","created_at"]], use_container_width=True, hide_index=True)

        users = users.copy()
        users["label"] = users["name"].astype(str) + " — " + users["school"].astype(str) + " (" + users["status"].astype(str) + ")"
        sel = st.selectbox("Selecionar utilizador", users["label"].tolist())
        row = users[users["label"] == sel].iloc[0]
        user_key = row["user_key"]

        colA, colB, colC = st.columns(3)
        with colA:
            if st.button("✅ Aprovar", use_container_width=True):
                set_user_status(user_key, "approved", approved_by=admin_name)
                st.success("Aprovado.")
                st.rerun()
            if st.button("↩️ Revogar (Trial)", use_container_width=True):
                set_user_status(user_key, "trial")
                st.success("Revogado.")
                st.rerun()

        with colB:
            if st.button("⛔ Bloquear", use_container_width=True):
                set_user_status(user_key, "blocked")
                st.success("Bloqueado.")
                st.rerun()
            if st.button("✅ Desbloquear", use_container_width=True):
                set_user_status(user_key, "trial")
                st.success("Desbloqueado.")
                st.rerun()

        with colC:
            new_limit = st.number_input(
                "Limite diário (trial/pending)",
                min_value=0, max_value=20,
                value=int(row.get("daily_limit", 2) or 2),
                step=1
            )
            if st.button("💾 Guardar limite", use_container_width=True):
                set_daily_limit(user_key, int(new_limit))
                st.success("Limite actualizado.")
                st.rerun()

        st.markdown("---")
        st.subheader("🔐 Redefinir PIN")
        new_pin = st.text_input("Novo PIN temporário", type="password")
        if st.button("🔁 Redefinir PIN", use_container_width=True):
            if not new_pin or len(new_pin) < 4:
                st.error("PIN inválido (mínimo 4).")
            else:
                reset_pin(user_key, new_pin)
                st.success("PIN redefinido com sucesso.")

        st.markdown("---")
        st.subheader("🗑️ Apagar utilizador")
        confirm = st.checkbox("Confirmo apagar (irreversível).")
        if st.button("Apagar", disabled=not confirm, use_container_width=True):
            delete_user(user_key)
            st.success("Utilizador apagado.")
            st.rerun()

    with tabs[2]:
        st.subheader("📚 Planos (Todos)")
        days_back = st.selectbox("Mostrar últimos (dias)", [7, 14, 30, 60, 90, 180], index=2, key="all_plans_days")
        plans = list_plans_all_df(days_back=days_back)
        users = list_users_df()

        if plans.empty:
            st.info("Sem planos nesta janela.")
            return

        p = plans.merge(users[["user_key","name","school"]], on="user_key", how="left")
        st.dataframe(
            p[["plan_day","disciplina","classe","tema","unidade","turma","name","school","created_at"]],
            use_container_width=True,
            hide_index=True
        )
