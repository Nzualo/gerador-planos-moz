# admin.py
import secrets
import streamlit as st
import pandas as pd
import requests
from datetime import date, datetime

from utils import supa, pin_hash

BUCKET_PLANS = "plans"


# -------------------------
# Helpers
# -------------------------
def is_admin_session() -> bool:
    return st.session_state.get("is_admin", False)


def today_iso() -> str:
    return date.today().isoformat()


def _df(rows) -> pd.DataFrame:
    return pd.DataFrame(rows or [])


def _safe_int(x, default=0):
    try:
        return int(x)
    except Exception:
        return default


def generate_temp_pin(length: int = 4) -> str:
    # PIN numérico simples (4 dígitos)
    digits = "0123456789"
    return "".join(secrets.choice(digits) for _ in range(length))


# -------------------------
# Supabase Queries
# -------------------------
def list_users_df() -> pd.DataFrame:
    sb = supa()
    r = (
        sb.table("app_users")
        .select("user_key,name,school,status,created_at,approved_at,approved_by,daily_limit")
        .order("created_at", desc=True)
        .execute()
    )
    df = _df(r.data)
    if df.empty:
        return df
    if "daily_limit" not in df.columns:
        df["daily_limit"] = 2
    return df


def usage_daily_df() -> pd.DataFrame:
    sb = supa()
    r = sb.table("usage_daily").select("user_key,day,count").execute()
    d = _df(r.data)
    if d.empty:
        return pd.DataFrame(columns=["user_key", "day", "count"])
    d["count"] = pd.to_numeric(d["count"], errors="coerce").fillna(0).astype(int)
    d["day"] = pd.to_datetime(d["day"], errors="coerce").dt.date
    return d


def global_today_total() -> int:
    d = usage_daily_df()
    if d.empty:
        return 0
    return int(d[d["day"] == date.today()]["count"].sum())


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


def reset_today_count(user_key: str):
    sb = supa()
    day = today_iso()
    r = sb.table("usage_daily").select("count").eq("user_key", user_key).eq("day", day).limit(1).execute()
    if r.data:
        sb.table("usage_daily").update({"count": 0}).eq("user_key", user_key).eq("day", day).execute()
    else:
        sb.table("usage_daily").insert({"user_key": user_key, "day": day, "count": 0}).execute()


def reset_user_pin(user_key: str, new_pin: str):
    sb = supa()
    sb.table("app_users").update({"pin_hash": pin_hash(new_pin)}).eq("user_key", user_key).execute()


def list_all_plans_df() -> pd.DataFrame:
    sb = supa()
    r = (
        sb.table("user_plans")
        .select("id,user_key,created_at,plan_day,disciplina,classe,tema,unidade,turma,pdf_path,pdf_b64")
        .order("created_at", desc=True)
        .execute()
    )
    df = _df(r.data)
    if df.empty:
        return df
    df["created_at"] = pd.to_datetime(df["created_at"], errors="coerce")
    df["plan_day"] = pd.to_datetime(df["plan_day"], errors="coerce").dt.date
    return df


def get_plan_pdf_bytes(user_key: str, plan_id: int) -> bytes | None:
    """
    Preferência:
    1) Storage via pdf_path (signed url)
    2) fallback: pdf_b64
    """
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
        if url:
            resp = requests.get(url, timeout=60)
            if resp.status_code == 200:
                return resp.content

    if pdf_b64:
        try:
            import base64
            return base64.b64decode(pdf_b64)
        except Exception:
            return None

    return None


# -------------------------
# UI: Admin Panel
# -------------------------
def admin_panel(admin_name: str = "Admin"):
    """
    Chame isto dentro do app quando is_admin_session() == True
    """
    if not is_admin_session():
        return

    st.sidebar.markdown("---")
    st.sidebar.markdown("## 🛠️ Administração (SDEJT)")

    users = list_users_df()
    st.sidebar.metric("Professores registados", 0 if users.empty else len(users))
    st.sidebar.metric("Planos hoje (total)", global_today_total())

    st.markdown("## 🛠️ Painel do Administrador")

    tabs = st.tabs(["👤 Professores", "📄 Planos (Todos)"])

    # ---------------------
    # TAB: Professores
    # ---------------------
    with tabs[0]:
        if users.empty:
            st.info("Ainda não há professores registados.")
            return

        # filtros
        st.subheader("👤 Gestão de Professores")
        c1, c2, c3 = st.columns(3)
        with c1:
            status_filter = st.selectbox("Estado", ["Todos", "trial", "pending", "approved", "admin", "blocked"])
        with c2:
            school_filter = st.text_input("Escola (contém)", "").strip().lower()
        with c3:
            name_filter = st.text_input("Nome (contém)", "").strip().lower()

        filt = users.copy()
        if status_filter != "Todos":
            filt = filt[filt["status"] == status_filter]
        if school_filter:
            filt = filt[filt["school"].astype(str).str.lower().str.contains(school_filter, na=False)]
        if name_filter:
            filt = filt[filt["name"].astype(str).str.lower().str.contains(name_filter, na=False)]

        st.dataframe(
            filt[["name", "school", "status", "daily_limit", "created_at"]],
            hide_index=True,
            use_container_width=True
        )

        st.divider()
        st.subheader("🔧 Ações rápidas")

        filt2 = filt.copy()
        filt2["label"] = filt2["name"].astype(str) + " — " + filt2["school"].astype(str) + " (" + filt2["status"].astype(str) + ")"
        sel_label = st.selectbox("Selecionar professor", filt2["label"].tolist())
        sel = filt2[filt2["label"] == sel_label].iloc[0]
        user_key = sel["user_key"]

        colA, colB, colC = st.columns(3)
        with colA:
            new_limit = st.number_input(
                "Limite diário (trial/pending)",
                min_value=0, max_value=50,
                value=_safe_int(sel.get("daily_limit", 2), 2),
                step=1
            )
            if st.button("Guardar limite", type="primary"):
                set_daily_limit(user_key, int(new_limit))
                st.success("Limite atualizado.")
                st.rerun()

            if st.button("Reset contador HOJE"):
                reset_today_count(user_key)
                st.success("Reset feito.")
                st.rerun()

        with colB:
            st.caption("Estados")
            if st.button("Aprovar"):
                set_user_status(user_key, "approved", approved_by=admin_name)
                st.success("Aprovado.")
                st.rerun()
            if st.button("Revogar para Trial"):
                set_user_status(user_key, "trial")
                st.success("Revogado.")
                st.rerun()
            if st.button("Bloquear"):
                set_user_status(user_key, "blocked")
                st.success("Bloqueado.")
                st.rerun()

        with colC:
            st.caption("🔐 Reset de PIN (muito usado na prática)")
            pin_len = st.selectbox("Tamanho do PIN", [4, 5, 6], index=0)
            if st.button("Gerar PIN temporário e aplicar", type="primary"):
                new_pin = generate_temp_pin(pin_len)
                reset_user_pin(user_key, new_pin)
                st.success("PIN redefinido com sucesso.")
                st.warning(f"PIN temporário do professor: **{new_pin}** (anote e envie ao professor)")
                st.info("Recomendação: o professor entra com esse PIN e depois você manda ele criar um novo no futuro (fase seguinte).")

    # ---------------------
    # TAB: Planos (Todos)
    # ---------------------
    with tabs[1]:
        st.subheader("📄 Todos os Planos (Admin)")
        plans = list_all_plans_df()
        if plans.empty:
            st.info("Ainda não há planos registados.")
            return

        # juntar info de professor
        users_map = users.set_index("user_key")[["name", "school"]].to_dict("index") if not users.empty else {}

        plans2 = plans.copy()
        plans2["professor"] = plans2["user_key"].apply(lambda k: users_map.get(k, {}).get("name", "-"))
        plans2["escola"] = plans2["user_key"].apply(lambda k: users_map.get(k, {}).get("school", "-"))

        f1, f2, f3 = st.columns(3)
        with f1:
            escola_f = st.text_input("Filtrar por escola (contém)", "").strip().lower()
        with f2:
            prof_f = st.text_input("Filtrar por professor (contém)", "").strip().lower()
        with f3:
            classe_f = st.selectbox("Classe", ["Todas"] + sorted(plans2["classe"].astype(str).unique().tolist()))

        view = plans2.copy()
        if escola_f:
            view = view[view["escola"].astype(str).str.lower().str.contains(escola_f, na=False)]
        if prof_f:
            view = view[view["professor"].astype(str).str.lower().str.contains(prof_f, na=False)]
        if classe_f != "Todas":
            view = view[view["classe"].astype(str) == classe_f]

        st.
