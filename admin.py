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
        return pd.DataFrame(columns=["user_key","name","school","status","daily_limit","created_at","approved_at","approved_by"])
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
    sb = supa()
    sb.table("app_users").update({"daily_limit": int(daily_limit)}).eq("user_key", user_key).execute()


def reset_pin(user_key: str, new_pin: str):
    sb = supa()
    sb.table("app_users").update({"pin_hash": pin_hash(new_pin)}).eq("user_key", user_key).execute()


def delete_user(user_key: str):
    sb = supa()
    sb.table("app_users").delete().eq("user_key", user_key).execute()


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


def usage_daily_df(days_back: int = 30) -> pd.DataFrame:
    sb = supa()
    since = (date.today() - timedelta(days=days_back)).isoformat()
    r = (
        sb.table("usage_daily")
        .select("user_key,day,count")
        .gte("day", since)
        .execute()
    )
    df = pd.DataFrame(r.data or [])
    if df.empty:
        return pd.DataFrame(columns=["user_key","day","count"])
    df["day"] = pd.to_datetime(df["day"], errors="coerce").dt.date
    df["count"] = pd.to_numeric(df["count"], errors="coerce").fillna(0).astype(int)
    return df


def list_access_requests_df(status: str = "pending") -> pd.DataFrame:
    sb = supa()
    r = (
        sb.table("access_requests")
        .select("id,user_key,name,school,status,created_at")
        .eq("status", status)
        .order("created_at", desc=True)
        .execute()
    )
    return pd.DataFrame(r.data or [])


def approve_request(req_id: int, user_key: str, admin_name: str):
    sb = supa()
    sb.table("access_requests").update({
        "status": "approved",
        "processed_at": datetime.now().isoformat(),
        "processed_by": admin_name
    }).eq("id", req_id).execute()
    set_user_status(user_key, "approved", approved_by=admin_name)


def reject_request(req_id: int, user_key: str, admin_name: str):
    sb = supa()
    sb.table("access_requests").update({
        "status": "rejected",
        "processed_at": datetime.now().isoformat(),
        "processed_by": admin_name
    }).eq("id", req_id).execute()
    set_user_status(user_key, "trial")


def admin_panel(admin_name: str = "Admin"):
    tabs = st.tabs(["📊 Dashboard", "👥 Utilizadores", "📩 Pedidos", "📚 Planos (Todos)"])

    # Dashboard
    with tabs[0]:
        st.subheader("📊 Dashboard SDEJT")
        days_back = st.selectbox("Janela (dias)", [7, 14, 30, 60, 90], index=2, key="adm_days")

        users = list_users_df()
        usage = usage_daily_df(days_back=days_back)
        plans = list_plans_all_df(days_back=days_back)

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Professores registados", len(users) if not users.empty else 0)
        c2.metric("Planos (janela)", len(plans) if not plans.empty else 0)
        c3.metric("Planos hoje", int(plans[plans["plan_day"] == date.today()].shape[0]) if not plans.empty else 0)
        c4.metric("Uso hoje (contagem)", int(usage[usage["day"] == date.today()]["count"].sum()) if not usage.empty else 0)

        st.markdown("---")
        st.subheader("📌 Planos por Escola (janela)")

        if plans.empty or users.empty:
            st.info("Ainda sem dados suficientes.")
        else:
            u = users[["user_key","school","name"]].copy()
            p = plans.merge(u, on="user_key", how="left")

            by_school = p.groupby("school", as_index=False).size().rename(columns={"size":"planos"})
            by_school = by_school.sort_values("planos", ascending=False)
            st.dataframe(by_school, use_container_width=True, hide_index=True)

            st.subheader("📌 Top Professores (janela)")
            by_prof = p.groupby(["name","school"], as_index=False).size().rename(columns={"size":"planos"})
            by_prof = by_prof.sort_values("planos", ascending=False).head(20)
            st.dataframe(by_prof, use_container_width=True, hide_index=True)

    # Utilizadores
    with tabs[1]:
        st.subheader("👥 Gestão de Utilizadores")
        users = list_users_df()
        if users.empty:
            st.info("Sem utilizadores.")
        else:
            st.dataframe(users[["name","school","status","daily_limit","created_at"]], use_container_width=True, hide_index=True)

            users = users.copy()
            users["label"] = users["name"].astype(str) + " — " + users["school"].astype(str) + " (" + users["status"].astype(str) + ")"
            sel = st.selectbox("Selecionar utilizador", users["label"].tolist(), key="adm_user_sel")
            row = users[users["label"] == sel].iloc[0]
            user_key = row["user_key"]

            st.markdown("### Ações")
            colA, colB, colC = st.columns(3)

            with colA:
                if st.button("✅ Aprovar", key="adm_appr"):
                    set_user_status(user_key, "approved", approved_by=admin_name)
                    st.success("Aprovado.")
                    st.rerun()
                if st.button("↩️ Revogar (Trial)", key="adm_revoke"):
                    set_user_status(user_key, "trial")
                    st.success("Revogado.")
                    st.rerun()

            with colB:
                if st.button("⛔ Bloquear", key="adm_block"):
                    set_user_status(user_key, "blocked")
                    st.success("Bloqueado.")
                    st.rerun()
                if st.button("✅ Desbloquear (Trial)", key="adm_unblock"):
                    set_user_status(user_key, "trial")
                    st.success("Desbloqueado.")
                    st.rerun()

            with colC:
                new_limit = st.number_input("Limite diário (trial/pending)", min_value=0, max_value=20,
                                            value=int(row.get("daily_limit", 2) or 2), step=1, key="adm_limit")
                if st.button("💾 Guardar limite", key="adm_save_limit"):
                    set_daily_limit(user_key, int(new_limit))
                    st.success("Limite actualizado.")
                    st.rerun()

            st.markdown("---")
            st.subheader("🔐 Redefinir PIN (Admin)")
            new_pin = st.text_input("Novo PIN temporário (mín. 4)", type="password", key="adm_newpin")
            if st.button("🔁 Redefinir PIN", key="adm_resetpin"):
                if not new_pin or len(new_pin.strip()) < 4:
                    st.error("PIN inválido. Use pelo menos 4 caracteres.")
                else:
                    reset_pin(user_key, new_pin.strip())
                    st.success("PIN redefinido com sucesso.")

            st.markdown("---")
            st.subheader("🗑️ Apagar Utilizador (irreversível)")
            confirm = st.checkbox("Confirmo que quero apagar este utilizador (irreversível).", key="adm_del_chk")
            if st.button("Apagar utilizador", disabled=not confirm, key="adm_del_btn"):
                delete_user(user_key)
                st.success("Utilizador apagado.")
                st.rerun()

    # Pedidos
    with tabs[2]:
        st.subheader("📩 Pedidos de Acesso")
        pending = list_access_requests_df("pending")
        if pending.empty:
            st.info("Sem pedidos pendentes.")
        else:
            pending = pending.copy()
            pending["label"] = pending["name"].astype(str) + " — " + pending["school"].astype(str) + " (ID " + pending["id"].astype(str) + ")"
            st.dataframe(pending[["id","name","school","created_at"]], use_container_width=True, hide_index=True)

            sel = st.selectbox("Selecionar pedido", pending["label"].tolist(), key="adm_req_sel")
            row = pending[pending["label"] == sel].iloc[0]
            req_id = int(row["id"])
            user_key = row["user_key"]

            c1, c2 = st.columns(2)
            with c1:
                if st.button("✅ Aprovar pedido", type="primary", key="adm_req_appr"):
                    approve_request(req_id, user_key, admin_name)
                    st.success("Pedido aprovado.")
                    st.rerun()
            with c2:
                if st.button("❌ Rejeitar pedido", key="adm_req_rej"):
                    reject_request(req_id, user_key, admin_name)
                    st.success("Pedido rejeitado.")
                    st.rerun()

    # Planos (Todos)
    with tabs[3]:
        st.subheader("📚 Planos (Todos)")
        days_back = st.selectbox("Mostrar últimos (dias)", [7, 14, 30, 60, 90, 180], index=2, key="adm_pl_days")

        plans = list_plans_all_df(days_back=days_back)
        users = list_users_df()

        if plans.empty:
            st.info("Sem planos nesta janela.")
        else:
            p = plans.copy()
            if not users.empty:
                p = p.merge(users[["user_key","name","school"]], on="user_key", how="left")

            f1, f2, f3 = st.columns(3)
            with f1:
                school_f = st.text_input("Filtrar escola (contém)", "", key="adm_f_school")
            with f2:
                disc_f = st.text_input("Filtrar disciplina (contém)", "", key="adm_f_disc")
            with f3:
                classe_f = st.text_input("Filtrar classe (contém)", "", key="adm_f_cl")

            if school_f.strip():
                p = p[p["school"].astype(str).str.lower().str.contains(school_f.strip().lower(), na=False)]
            if disc_f.strip():
                p = p[p["disciplina"].astype(str).str.lower().str.contains(disc_f.strip().lower(), na=False)]
            if classe_f.strip():
                p = p[p["classe"].astype(str).str.lower().str.contains(classe_f.strip().lower(), na=False)]

            st.dataframe(
                p[["plan_day","disciplina","classe","tema","unidade","turma","name","school","created_at"]],
                use_container_width=True,
                hide_index=True
            )
