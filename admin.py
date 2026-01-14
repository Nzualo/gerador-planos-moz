st.sidebar.success(f"Administrador: {admin_name}")
import base64
import pandas as pd
import streamlit as st
import requests
from datetime import date, datetime

from utils import supa

BUCKET_PLANS = "plans"


# -------------------------
# Helpers
# -------------------------
def today_iso() -> str:
    return date.today().isoformat()


def is_unlimited(status: str) -> bool:
    return status in ("approved", "admin")


def is_blocked(status: str) -> bool:
    return status == "blocked"


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
    # Se tens ON DELETE CASCADE no Supabase, isto remove também usage_daily/access_requests/user_plans
    supa().table("app_users").delete().eq("user_key", user_key).execute()


# -------------------------
# ACCESS REQUESTS
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

    # volta para trial
    set_user_status(user_key, "trial")


# -------------------------
# USAGE DAILY
# -------------------------
def usage_daily_all_df() -> pd.DataFrame:
    sb = supa()
    r = sb.table("usage_daily").select("user_key,day,count").execute()
    d = pd.DataFrame(r.data or [])
    if d.empty:
        return pd.DataFrame(columns=["user_key", "day", "count"])
    d["count"] = pd.to_numeric(d["count"], errors="coerce").fillna(0).astype(int)
    d["day"] = pd.to_datetime(d["day"], errors="coerce").dt.date
    return d


def reset_today_count(user_key: str):
    sb = supa()
    day = today_iso()
    r = sb.table("usage_daily").select("count").eq("user_key", user_key).eq("day", day).limit(1).execute()
    if r.data:
        sb.table("usage_daily").update({"count": 0}).eq("user_key", user_key).eq("day", day).execute()
    else:
        sb.table("usage_daily").insert({"user_key": user_key, "day": day, "count": 0}).execute()


def usage_stats_users_df(users_df: pd.DataFrame) -> pd.DataFrame:
    d = usage_daily_all_df()
    if users_df.empty:
        return users_df

    if d.empty:
        users_df["today_count"] = 0
        users_df["total_count"] = 0
        return users_df

    today = date.today()
    total = d.groupby("user_key", as_index=False)["count"].sum().rename(columns={"count": "total_count"})
    today_df = d[d["day"] == today].groupby("user_key", as_index=False)["count"].sum().rename(columns={"count": "today_count"})
    out = users_df.merge(total, on="user_key", how="left").merge(today_df, on="user_key", how="left")
    out["today_count"] = out["today_count"].fillna(0).astype(int)
    out["total_count"] = out["total_count"].fillna(0).astype(int)
    return out


def global_today_total() -> int:
    d = usage_daily_all_df()
    if d.empty:
        return 0
    return int(d[d["day"] == date.today()]["count"].sum())


# -------------------------
# CURRICULUM SNIPPETS
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
    """
    Admin: baixar PDF de qualquer professor
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
            return base64.b64decode(pdf_b64)
        except Exception:
            return None

    return None


# -------------------------
# ADMIN PANEL UI (FULL)
# -------------------------
def admin_panel(admin_name: str = "Admin"):
    st.success(f"Administrador: {admin_name}")

    # Resumo
    users = list_users_df()
    users2 = usage_stats_users_df(users) if not users.empty else users
    st.metric("Professores registados", len(users2) if not users2.empty else 0)
    st.metric("Planos hoje (total)", global_today_total())
    st.divider()

    tab_users, tab_requests, tab_curriculum, tab_plans = st.tabs([
        "👥 Utilizadores",
        "📩 Pedidos Pendentes",
        "📚 Currículo (Snippets)",
        "🗂️ Planos (Todos)"
    ])

    # -------------------------
    # UTILIZADORES
    # -------------------------
    with tab_users:
        st.subheader("👥 Gestão de Utilizadores")

        if users2.empty:
            st.info("Sem utilizadores registados.")
        else:
            st.markdown("### Filtros")
            c1, c2, c3 = st.columns(3)
            with c1:
                status_filter = st.selectbox("Estado", ["Todos", "trial", "pending", "approved", "admin", "blocked"])
            with c2:
                school_filter = st.text_input("Escola (contém)", "").strip().lower()
            with c3:
                name_filter = st.text_input("Nome (contém)", "").strip().lower()

            filt = users2.copy()
            if status_filter != "Todos":
                filt = filt[filt["status"] == status_filter]
            if school_filter:
                filt = filt[filt["school"].astype(str).str.lower().str.contains(school_filter, na=False)]
            if name_filter:
                filt = filt[filt["name"].astype(str).str.lower().str.contains(name_filter, na=False)]

            st.dataframe(
                filt[["name","school","status","daily_limit","today_count","total_count","created_at"]],
                hide_index=True,
                use_container_width=True
            )

            st.markdown("### Ações")
            if len(filt) > 0:
                f2 = filt.copy()
                f2["label"] = f2["name"].astype(str) + " — " + f2["school"].astype(str) + " (" + f2["status"].astype(str) + ")"
                sel_label = st.selectbox("Selecionar utilizador", f2["label"].tolist())
                row = f2[f2["label"] == sel_label].iloc[0]
                sel_user_key = row["user_key"]

                new_limit = st.number_input(
                    "Limite diário (trial/pending)",
                    min_value=0, max_value=20,
                    value=int(row.get("daily_limit", 2) or 2),
                    step=1
                )

                a, b = st.columns(2)
                with a:
                    if st.button("💾 Guardar limite", type="primary", use_container_width=True):
                        set_daily_limit(sel_user_key, int(new_limit))
                        st.success("Limite actualizado.")
                        st.rerun()
                with b:
                    if st.button("🔄 Reset HOJE", use_container_width=True):
                        reset_today_count(sel_user_key)
                        st.success("Reset feito.")
                        st.rerun()

                c, d = st.columns(2)
                with c:
                    if st.button("✅ Aprovar", use_container_width=True):
                        set_user_status(sel_user_key, "approved", approved_by=admin_name)
                        st.success("Aprovado.")
                        st.rerun()
                with d:
                    if st.button("↩️ Revogar (Trial)", use_container_width=True):
                        set_user_status(sel_user_key, "trial")
                        st.success("Revogado.")
                        st.rerun()

                e, f = st.columns(2)
                with e:
                    if st.button("⛔ Bloquear", use_container_width=True):
                        set_user_status(sel_user_key, "blocked")
                        st.success("Bloqueado.")
                        st.rerun()
                with f:
                    if st.button("✅ Desbloquear (Trial)", use_container_width=True):
                        set_user_status(sel_user_key, "trial")
                        st.success("Desbloqueado.")
                        st.rerun()

                st.markdown("---")
                st.subheader("🗑️ Apagar utilizador")
                confirm_del = st.checkbox("Confirmo apagar (irreversível).")
                if st.button("Apagar utilizador", disabled=not confirm_del, use_container_width=True):
                    delete_user(sel_user_key)
                    st.success("Utilizador apagado.")
                    st.rerun()

    # -------------------------
    # PEDIDOS PENDENTES
    # -------------------------
    with tab_requests:
        st.subheader("📩 Pedidos Pendentes (Acesso Total)")
        pending = list_pending_requests_df()

        if pending.empty:
            st.caption("Sem pedidos pendentes.")
        else:
            pending = pending.copy()
            pending["label"] = pending["name"].astype(str) + " — " + pending["school"].astype(str) + " (ID " + pending["id"].astype(str) + ")"

            st.dataframe(pending[["id","name","school","created_at"]], hide_index=True, use_container_width=True)

            sel_label = st.selectbox("Selecionar pedido", pending["label"].tolist())
            sel_row = pending[pending["label"] == sel_label].iloc[0]
            sel_id = int(sel_row["id"])
            sel_user_key = sel_row["user_key"]

            x, y, z = st.columns(3)
            with x:
                if st.button("✅ Aprovar pedido", type="primary", use_container_width=True):
                    approve_request(sel_id, sel_user_key, processed_by=admin_name)
                    st.success("Pedido aprovado.")
                    st.rerun()
            with y:
                if st.button("❌ Rejeitar pedido", use_container_width=True):
                    reject_request(sel_id, sel_user_key, processed_by=admin_name)
                    st.success("Pedido rejeitado.")
                    st.rerun()
            with z:
                if st.button("🗑️ Apagar utilizador (suspeito)", use_container_width=True):
                    delete_user(sel_user_key)
                    st.success("Utilizador apagado.")
                    st.rerun()

    # -------------------------
    # CURRÍCULO
    # -------------------------
    with tab_curriculum:
        st.subheader("📚 Biblioteca do Currículo (Snippets)")
        st.caption("Adicione trechos curtos por disciplina/classe para guiar a IA com rigor.")

        disc = st.text_input("Disciplina", "Língua Portuguesa")
        classe = st.selectbox("Classe", ["1ª","2ª","3ª","4ª","5ª","6ª","7ª","8ª","9ª","10ª","11ª","12ª"], key="curr_classe")
        unidade = st.text_input("Unidade (opcional)", "")
        tema = st.text_input("Tema (opcional)", "")
        snippet = st.text_area("Snippet (curto e directo)", "")
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
            if st.button("🗑️ Apagar snippet seleccionado"):
                delete_curriculum_snippet(int(del_id))
                st.success("Snippet apagado.")
                st.rerun()

    # -------------------------
    # PLANOS (TODOS)
    # -------------------------
    with tab_plans:
        st.subheader("🗂️ Planos (Todos os Professores)")
        plans = list_plans_all_df()

        if plans.empty:
            st.info("Ainda não existem planos guardados.")
        else:
            # junta nome/escola
            users = list_users_df()
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
                use_container_width=True
            )

            # baixar
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
            plan_id = int(row["id"])
            user_key = row["user_key"]

            if st.button("⬇️ Baixar PDF (Admin)", type="primary"):
                pdf_bytes = get_plan_pdf_bytes_any(user_key, plan_id)
                if not pdf_bytes:
                    st.error("Não foi possível carregar o PDF.")
                else:
                    st.download_button(
                        "Clique para descarregar",
                        data=pdf_bytes,
                        file_name=f"Plano_{row['disciplina']}_{row['classe']}_{row['tema']}_{row['name']}.pdf".replace(" ", "_"),
                        mime="application/pdf"
                    )

            )
