# admin.py
import streamlit as st
import pandas as pd
import requests
from datetime import date, datetime

from utils import supa, pin_hash

BUCKET_PLANS = "plans"


# -----------------------------
# Helpers
# -----------------------------
def _today_iso() -> str:
    return date.today().isoformat()

def _is_admin() -> bool:
    return bool(st.session_state.get("is_admin", False))

def _admin_login_box():
    st.sidebar.markdown("### Administração")

    pwd = st.sidebar.text_input("Senha do Administrador", type="password", key="admin_pwd_box")
    col1, col2 = st.sidebar.columns(2)

    with col1:
        if st.button("Entrar", key="btn_admin_login"):
            if "ADMIN_PASSWORD" not in st.secrets:
                st.sidebar.error("ADMIN_PASSWORD não configurada nos Secrets.")
                return
            if pwd == st.secrets["ADMIN_PASSWORD"]:
                st.session_state["is_admin"] = True
                st.sidebar.success("Admin activo.")
                st.rerun()
            else:
                st.sidebar.error("Senha inválida.")

    with col2:
        if st.button("Sair", key="btn_admin_logout", disabled=not _is_admin()):
            st.session_state["is_admin"] = False
            st.session_state.pop("admin_pwd_box", None)
            st.rerun()


# -----------------------------
# DB queries
# -----------------------------
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
        return df
    if "daily_limit" not in df.columns:
        df["daily_limit"] = 2
    return df

def list_usage_df() -> pd.DataFrame:
    sb = supa()
    r = sb.table("usage_daily").select("user_key,day,count").execute()
    d = pd.DataFrame(r.data or [])
    if d.empty:
        return pd.DataFrame(columns=["user_key", "day", "count"])
    d["count"] = pd.to_numeric(d["count"], errors="coerce").fillna(0).astype(int)
    d["day"] = pd.to_datetime(d["day"], errors="coerce").dt.date
    return d

def usage_stats(users_df: pd.DataFrame) -> pd.DataFrame:
    d = list_usage_df()
    if users_df.empty:
        return users_df
    if d.empty:
        users_df["today_count"] = 0
        users_df["total_count"] = 0
        return users_df

    total = d.groupby("user_key", as_index=False)["count"].sum().rename(columns={"count": "total_count"})
    today_df = (
        d[d["day"] == date.today()]
        .groupby("user_key", as_index=False)["count"]
        .sum()
        .rename(columns={"count": "today_count"})
    )

    out = users_df.merge(total, on="user_key", how="left").merge(today_df, on="user_key", how="left")
    out["today_count"] = out["today_count"].fillna(0).astype(int)
    out["total_count"] = out["total_count"].fillna(0).astype(int)
    return out

def global_today_total() -> int:
    d = list_usage_df()
    if d.empty:
        return 0
    return int(d[d["day"] == date.today()]["count"].sum())

def set_user_status(user_key: str, status: str, approved_by: str | None = None):
    sb = supa()
    payload = {"status": status}

    if status == "approved":
        payload["approved_at"] = datetime.now().isoformat()
        payload["approved_by"] = approved_by

    if status in ("trial", "blocked", "pending"):
        payload["approved_at"] = None
        payload["approved_by"] = None

    sb.table("app_users").update(payload).eq("user_key", user_key).execute()

def set_daily_limit(user_key: str, daily_limit: int):
    sb = supa()
    sb.table("app_users").update({"daily_limit": int(daily_limit)}).eq("user_key", user_key).execute()

def reset_today_count(user_key: str):
    sb = supa()
    day = _today_iso()
    r = sb.table("usage_daily").select("count").eq("user_key", user_key).eq("day", day).limit(1).execute()
    if r.data:
        sb.table("usage_daily").update({"count": 0}).eq("user_key", user_key).eq("day", day).execute()
    else:
        sb.table("usage_daily").insert({"user_key": user_key, "day": day, "count": 0}).execute()

def delete_user(user_key: str):
    sb = supa()
    sb.table("app_users").delete().eq("user_key", user_key).execute()

def reset_pin(user_key: str, new_pin: str):
    sb = supa()
    sb.table("app_users").update({"pin_hash": pin_hash(new_pin)}).eq("user_key", user_key).execute()


# -----------------------------
# Plans (Admin view)
# -----------------------------
def list_all_plans_df() -> pd.DataFrame:
    sb = supa()
    r = (
        sb.table("user_plans")
        .select("id,created_at,plan_day,disciplina,classe,tema,unidade,turma,user_key,pdf_path,pdf_b64")
        .order("created_at", desc=True)
        .execute()
    )
    df = pd.DataFrame(r.data or [])
    if df.empty:
        return df

    df["created_at"] = pd.to_datetime(df["created_at"], errors="coerce")
    df["plan_day"] = pd.to_datetime(df["plan_day"], errors="coerce").dt.date
    return df

def get_pdf_bytes_for_plan(user_key: str, plan_id: int) -> bytes | None:
    sb = supa()
    r = (
        sb.table("user_plans")
        .select("pdf_path,pdf_b64")
        .eq("user_key", user_key)
        .eq("id", plan_id)
        .limit(1)
        .execute()
    )
    if not r.data:
        return None

    pdf_path = r.data[0].get("pdf_path")
    pdf_b64 = r.data[0].get("pdf_b64")

    if pdf_path:
        signed = sb.storage.from_(BUCKET_PLANS).create_signed_url(pdf_path, 600)
        url = signed.get("signedURL") or signed.get("signedUrl") or signed.get("signed_url")
        if not url:
            return None
        resp = requests.get(url, timeout=60)
        if resp.status_code == 200:
            return resp.content

    if pdf_b64:
        import base64
        try:
            return base64.b64decode(pdf_b64)
        except Exception:
            return None

    return None


# -----------------------------
# UI - Admin Panel
# -----------------------------
def admin_panel():
    """
    Chame esta função no app.py.
    Ela trata:
    - Login do admin na sidebar
    - Dashboard
    - Gestão de professores
    - Reset PIN
    - Ver/baixar planos de todos
    """
    _admin_login_box()

    if not _is_admin():
        return  # não mostra painel completo se não for admin

    st.sidebar.markdown("---")
    st.sidebar.success("✅ Painel Admin activo")

    st.markdown("## 🛠️ Painel do Administrador (SDEJT)")

    users = list_users_df()
    users2 = usage_stats(users) if not users.empty else users

    # KPI topo
    c1, c2, c3 = st.columns(3)
    with c1:
        st.metric("Professores registados", int(len(users2)) if not users2.empty else 0)
    with c2:
        st.metric("Planos hoje (total)", global_today_total())
    with c3:
        st.metric("Utilizadores bloqueados", int((users2["status"] == "blocked").sum()) if not users2.empty else 0)

    tabs = st.tabs(["👩🏽‍🏫 Professores", "📚 Planos (Todos)", "🏫 Escolas"])

    # -------------------------
    # TAB 1: Professores
    # -------------------------
    with tabs[0]:
        if users2.empty:
            st.info("Sem professores registados.")
        else:
            st.subheader("Lista de Professores")

            st.markdown("### Filtros")
            colA, colB, colC = st.columns(3)
            with colA:
                status_filter = st.selectbox("Estado", ["Todos", "trial", "pending", "approved", "admin", "blocked"])
            with colB:
                school_filter = st.text_input("Escola (contém)", "").strip().lower()
            with colC:
                name_filter = st.text_input("Nome (contém)", "").strip().lower()

            filt = users2.copy()
            if status_filter != "Todos":
                filt = filt[filt["status"] == status_filter]
            if school_filter:
                filt = filt[filt["school"].astype(str).str.lower().str.contains(school_filter, na=False)]
            if name_filter:
                filt = filt[filt["name"].astype(str).str.lower().str.contains(name_filter, na=False)]

            show_cols = ["name", "school", "status", "daily_limit", "today_count", "total_count"]
            st.dataframe(filt[show_cols], hide_index=True, use_container_width=True)

            st.markdown("---")
            st.subheader("Gestão do Professor")

            filt = filt.copy()
            filt["label"] = filt["name"].astype(str) + " — " + filt["school"].astype(str) + " (" + filt["status"].astype(str) + ")"
            sel_label = st.selectbox("Seleccionar", filt["label"].tolist())
            sel = filt[filt["label"] == sel_label].iloc[0]
            sel_user_key = sel["user_key"]
            sel_status = sel["status"]

            col1, col2, col3 = st.columns(3)
            with col1:
                new_limit = st.number_input(
                    "Limite diário (trial/pending)",
                    min_value=0, max_value=30,
                    value=int(sel.get("daily_limit", 2) or 2), step=1
                )
                if st.button("Guardar limite", type="primary"):
                    set_daily_limit(sel_user_key, int(new_limit))
                    st.success("Limite actualizado.")
                    st.rerun()

                if st.button("Reset HOJE (contador)"):
                    reset_today_count(sel_user_key)
                    st.success("Reset feito.")
                    st.rerun()

            with col2:
                st.markdown("**Estado**")
                if st.button("Aprovar"):
                    set_user_status(sel_user_key, "approved", approved_by="admin")
                    st.success("Aprovado.")
                    st.rerun()

                if st.button("Revogar (trial)"):
                    set_user_status(sel_user_key, "trial")
                    st.success("Revogado.")
                    st.rerun()

                if st.button("Bloquear"):
                    set_user_status(sel_user_key, "blocked")
                    st.success("Bloqueado.")
                    st.rerun()

                if st.button("Desbloquear (trial)"):
                    set_user_status(sel_user_key, "trial")
                    st.success("Desbloqueado.")
                    st.rerun()

            with col3:
                st.markdown("**Reset PIN**")
                tmp_pin = st.text_input("Novo PIN (defina e envie ao professor)", type="password")
                if st.button("Aplicar novo PIN"):
                    if not tmp_pin or len(tmp_pin.strip()) < 4:
                        st.error("PIN muito curto. Use pelo menos 4 caracteres.")
                    else:
                        reset_pin(sel_user_key, tmp_pin.strip())
                        st.success("PIN redefinido com sucesso.")
                st.markdown("---")
                confirm_del = st.checkbox("Confirmo apagar utilizador (irreversível).")
                if st.button("Apagar utilizador", disabled=not confirm_del):
                    delete_user(sel_user_key)
                    st.success("Utilizador apagado.")
                    st.rerun()

    # -------------------------
    # TAB 2: Planos (Todos)
    # -------------------------
    with tabs[1]:
        st.subheader("Planos de Todos os Professores")

        plans = list_all_plans_df()
        if plans.empty:
            st.info("Ainda não existem planos guardados.")
        else:
            st.markdown("### Filtros")
            c1, c2, c3, c4 = st.columns(4)
            with c1:
                classe_f = st.selectbox("Classe", ["Todas"] + sorted(plans["classe"].astype(str).unique().tolist()))
            with c2:
                disc_f = st.selectbox("Disciplina", ["Todas"] + sorted(plans["disciplina"].astype(str).unique().tolist()))
            with c3:
                turma_f = st.selectbox("Turma", ["Todas"] + sorted(plans["turma"].astype(str).unique().tolist()))
            with c4:
                ordem = st.selectbox("Ordenar", ["Mais recente", "Mais antigo"])

            dfp = plans.copy()
            if classe_f != "Todas":
                dfp = dfp[dfp["classe"].astype(str) == classe_f]
            if disc_f != "Todas":
                dfp = dfp[dfp["disciplina"].astype(str) == disc_f]
            if turma_f != "Todas":
                dfp = dfp[dfp["turma"].astype(str) == turma_f]

            dfp = dfp.sort_values("created_at", ascending=(ordem == "Mais antigo"))

            # mostrar tabela
            show = dfp[["plan_day", "classe", "disciplina", "tema", "unidade", "turma", "user_key", "created_at"]]
            st.dataframe(show, hide_index=True, use_container_width=True)

            # selector + download
            dfp["label"] = (
                dfp["plan_day"].astype(str) + " | " +
                dfp["classe"].astype(str) + " | " +
                dfp["disciplina"].astype(str) + " | " +
                dfp["tema"].astype(str) + " | " +
                "ID " + dfp["id"].astype(str)
            )
            sel = st.selectbox("Seleccionar plano para baixar PDF", dfp["label"].tolist())
            row = dfp[dfp["label"] == sel].iloc[0]
            plan_id = int(row["id"])
            user_key = row["user_key"]

            pdf_bytes = get_pdf_bytes_for_plan(user_key, plan_id)
            if pdf_bytes:
                st.download_button(
                    "⬇️ Baixar PDF deste plano",
                    data=pdf_bytes,
                    file_name=f"Plano_{row['disciplina']}_{row['classe']}_{row['tema']}_ID{plan_id}.pdf".replace(" ", "_"),
                    mime="application/pdf",
                    type="primary",
                )
            else:
                st.error("Não foi possível carregar o PDF deste plano.")

    # -------------------------
    # TAB 3: Escolas
    # -------------------------
    with tabs[2]:
        st.subheader("Escolas registadas (tabela schools)")
        sb = supa()
        r = sb.table("schools").select("name,name_norm,active,created_at").order("name").execute()
        df = pd.DataFrame(r.data or [])
        if df.empty:
            st.info("Sem escolas na tabela schools.")
        else:
            st.dataframe(df, hide_index=True, use_container_width=True)

        st.markdown("---")
        st.caption("Para adicionar novas escolas, use o SQL Editor no Supabase (insert into schools...).")
