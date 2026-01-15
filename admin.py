import base64
import pandas as pd
import streamlit as st
import requests
from datetime import date, datetime

from utils import supa

BUCKET_PLANS = "plans"


def today_iso() -> str:
    return date.today().isoformat()


# -------------------------
# USERS
# -------------------------
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


def delete_user(user_key: str):
    supa().table("app_users").delete().eq("user_key", user_key).execute()


# -------------------------
# REQUESTS (opcional)
# -------------------------
def list_pending_requests_df() -> pd.DataFrame:
    sb = supa()
    r = (
        sb.table("access_requests")
        .select("id,user_key,name,school,status,created_at")
        .eq("status", "pending")
        .order("created_at", desc=True)
        .execute()
    )
    return pd.DataFrame(r.data or [])


def approve_request(req_id: int, user_key: str, processed_by: str):
    sb = supa()
    sb.table("access_requests").update({
        "status": "approved",
        "processed_at": datetime.now().isoformat(),
        "processed_by": processed_by
    }).eq("id", req_id).execute()
    set_user_status(user_key, "approved", approved_by=processed_by)


def reject_request(req_id: int, user_key: str, processed_by: str):
    sb = supa()
    sb.table("access_requests").update({
        "status": "rejected",
        "processed_at": datetime.now().isoformat(),
        "processed_by": processed_by
    }).eq("id", req_id).execute()
    set_user_status(user_key, "trial")


# -------------------------
# CURRÍCULO (opcional)
# -------------------------
def add_curriculum_snippet(disciplina: str, classe: str, unidade: str | None, tema: str | None, snippet: str, fonte: str | None):
    sb = supa()
    sb.table("curriculum_snippets").insert({
        "disciplina": disciplina.strip(),
        "classe": classe.strip(),
        "unidade": (unidade or "").strip() or None,
        "tema": (tema or "").strip() or None,
        "snippet": snippet.strip(),
        "fonte": (fonte or "").strip() or None,
    }).execute()


def list_curriculum_snippets(disciplina: str, classe: str) -> pd.DataFrame:
    sb = supa()
    r = (
        sb.table("curriculum_snippets")
        .select("id,disciplina,classe,unidade,tema,snippet,fonte,created_at")
        .eq("disciplina", disciplina.strip())
        .eq("classe", classe.strip())
        .order("created_at", desc=True)
        .execute()
    )
    return pd.DataFrame(r.data or [])


def delete_curriculum_snippet(snippet_id: int):
    supa().table("curriculum_snippets").delete().eq("id", snippet_id).execute()


# -------------------------
# PLANS (ALL) + DOWNLOAD
# -------------------------
def list_plans_all_df() -> pd.DataFrame:
    sb = supa()
    r = (
        sb.table("user_plans")
        .select("id,created_at,plan_day,disciplina,classe,tema,unidade,turma,user_key,pdf_path,pdf_b64")
        .order("created_at", desc=True)
        .execute()
    )
    df = pd.DataFrame(r.data or [])
    if df.empty:
        return pd.DataFrame(columns=["id","created_at","plan_day","disciplina","classe","tema","unidade","turma","user_key","pdf_path"])
    df["created_at"] = pd.to_datetime(df["created_at"], errors="coerce")
    df["plan_day"] = pd.to_datetime(df["plan_day"], errors="coerce").dt.date
    return df


def get_plan_pdf_bytes_any(user_key: str, plan_id: int) -> bytes | None:
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
            return base64.b64decode(pdf_b64)
        except Exception:
            return None

    return None


# -------------------------
# ADMIN PANEL UI
# -------------------------
def admin_panel(admin_name: str = "Admin"):
    st.success(f"Administrador: {admin_name}")

    tab_users, tab_requests, tab_curriculum, tab_plans = st.tabs([
        "👥 Utilizadores",
        "📩 Pedidos Pendentes",
        "📚 Currículo",
        "🗂️ Planos (Todos)",
    ])

    # -------------------------
    # Utilizadores
    # -------------------------
    with tab_users:
        st.subheader("👥 Gestão de Utilizadores")
        users = list_users_df()

        if users.empty:
            st.info("Sem utilizadores registados.")
        else:
            st.dataframe(
                users[["name","school","status","daily_limit","created_at"]],
                hide_index=True,
                use_container_width=True,
            )

            users = users.copy()
            users["label"] = users["name"].astype(str) + " — " + users["school"].astype(str) + " (" + users["status"].astype(str) + ")"
            sel = st.selectbox("Selecionar utilizador", users["label"].tolist())
            row = users[users["label"] == sel].iloc[0]
            user_key = row["user_key"]

            new_limit = st.number_input(
                "Limite diário (trial)",
                min_value=0,
                max_value=50,
                value=int(row.get("daily_limit", 2) or 2),
                step=1,
            )

            c1, c2, c3, c4 = st.columns(4)
            with c1:
                if st.button("✅ Aprovar", use_container_width=True):
                    set_user_status(user_key, "approved", approved_by=admin_name)
                    st.success("Aprovado.")
                    st.rerun()
            with c2:
                if st.button("↩️ Trial", use_container_width=True):
                    set_user_status(user_key, "trial")
                    st.success("Voltou para trial.")
                    st.rerun()
            with c3:
                if st.button("⛔ Bloquear", use_container_width=True):
                    set_user_status(user_key, "blocked")
                    st.success("Bloqueado.")
                    st.rerun()
            with c4:
                if st.button("💾 Guardar limite", use_container_width=True):
                    set_daily_limit(user_key, int(new_limit))
                    st.success("Limite actualizado.")
                    st.rerun()

            st.divider()
            confirm = st.checkbox("Confirmo apagar utilizador (irreversível).")
            if st.button("🗑️ Apagar utilizador", disabled=not confirm, use_container_width=True):
                delete_user(user_key)
                st.success("Utilizador apagado.")
                st.rerun()

    # -------------------------
    # Pedidos pendentes (se tabela existir)
    # -------------------------
    with tab_requests:
        st.subheader("📩 Pedidos Pendentes")
        try:
            pending = list_pending_requests_df()
        except Exception:
            st.warning("Tabela access_requests não existe (ou não está acessível).")
            pending = pd.DataFrame()

        if pending.empty:
            st.info("Sem pedidos pendentes.")
        else:
            pending = pending.copy()
            pending["label"] = pending["name"].astype(str) + " — " + pending["school"].astype(str) + " (ID " + pending["id"].astype(str) + ")"
            st.dataframe(pending[["id","name","school","created_at"]], hide_index=True, use_container_width=True)

            sel = st.selectbox("Selecionar pedido", pending["label"].tolist())
            row = pending[pending["label"] == sel].iloc[0]
            req_id = int(row["id"])
            user_key = row["user_key"]

            a, b = st.columns(2)
            with a:
                if st.button("✅ Aprovar pedido", type="primary", use_container_width=True):
                    approve_request(req_id, user_key, processed_by=admin_name)
                    st.success("Pedido aprovado.")
                    st.rerun()
            with b:
                if st.button("❌ Rejeitar pedido", use_container_width=True):
                    reject_request(req_id, user_key, processed_by=admin_name)
                    st.success("Pedido rejeitado.")
                    st.rerun()

    # -------------------------
    # Currículo (se tabela existir)
    # -------------------------
    with tab_curriculum:
        st.subheader("📚 Biblioteca do Currículo")
        try:
            disc = st.text_input("Disciplina", "Língua Portuguesa")
            classe = st.selectbox("Classe", ["1ª","2ª","3ª","4ª","5ª","6ª","7ª","8ª","9ª","10ª","11ª","12ª"])
            unidade = st.text_input("Unidade (opcional)", "")
            tema = st.text_input("Tema (opcional)", "")
            snippet = st.text_area("Snippet", "")
            fonte = st.text_input("Fonte (opcional)", "Programa oficial / Guia do professor")

            if st.button("➕ Adicionar snippet", type="primary"):
                if not snippet.strip():
                    st.error("Escreva o snippet.")
                else:
                    add_curriculum_snippet(disc, classe, unidade, tema, snippet, fonte)
                    st.success("Snippet adicionado.")
                    st.rerun()

            dfcs = list_curriculum_snippets(disc, classe)
            if dfcs.empty:
                st.info("Sem snippets para esta disciplina/classe.")
            else:
                st.dataframe(dfcs[["id","unidade","tema","snippet","fonte","created_at"]], hide_index=True, use_container_width=True)
                del_id = st.selectbox("ID para apagar snippet", dfcs["id"].tolist())
                if st.button("🗑️ Apagar snippet"):
                    delete_curriculum_snippet(int(del_id))
                    st.success("Snippet apagado.")
                    st.rerun()
        except Exception:
            st.warning("Tabela curriculum_snippets não existe (ou não está acessível).")

    # -------------------------
    # Planos de todos + download
    # -------------------------
    with tab_plans:
        st.subheader("🗂️ Planos (Todos)")
        plans = list_plans_all_df()
        users = list_users_df()

        if plans.empty:
            st.info("Sem planos guardados.")
            return

        p = plans.merge(users[["user_key","name","school"]], on="user_key", how="left")

        c1, c2, c3 = st.columns(3)
        with c1:
            escola_f = st.text_input("Filtrar escola (contém)", "").strip().lower()
        with c2:
            nome_f = st.text_input("Filtrar professor (contém)", "").strip().lower()
        with c3:
            ordem = st.selectbox("Ordenar", ["Mais recente", "Mais antigo"])

        if escola_f:
            p = p[p["school"].astype(str).str.lower().str.contains(escola_f, na=False)]
        if nome_f:
            p = p[p["name"].astype(str).str.lower().str.contains(nome_f, na=False)]

        p = p.sort_values("created_at", ascending=(ordem == "Mais antigo"))

        st.dataframe(
            p[["plan_day","disciplina","classe","tema","unidade","turma","name","school","created_at"]],
            hide_index=True,
            use_container_width=True,
        )

        p = p.copy()
        p["label"] = (
            p["plan_day"].astype(str) + " | " +
            p["classe"].astype(str) + " | " +
            p["disciplina"].astype(str) + " | " +
            p["tema"].astype(str) + " | " +
            p["name"].astype(str)
        )
        sel = st.selectbox("Selecionar plano para baixar PDF", p["label"].tolist())
        row = p[p["label"] == sel].iloc[0]

        if st.button("⬇️ Baixar PDF (Admin)", type="primary", use_container_width=True):
            pdf = get_plan_pdf_bytes_any(row["user_key"], int(row["id"]))
            if not pdf:
                st.error("Não foi possível carregar o PDF.")
            else:
                st.download_button(
                    "Clique para descarregar",
                    data=pdf,
                    file_name=f"Plano_{row['disciplina']}_{row['classe']}_{row['tema']}_{row['name']}.pdf".replace(" ", "_"),
                    mime="application/pdf",
                    use_container_width=True,
                )
