import base64
import pandas as pd
import streamlit as st
import requests

from utils import supa

BUCKET_PLANS = "plans"


def list_user_plans(user_key: str) -> pd.DataFrame:
    sb = supa()
    r = (
        sb.table("user_plans")
        .select("id,created_at,plan_day,disciplina,classe,tema,unidade,turma,pdf_path,pdf_b64")
        .eq("user_key", user_key)
        .order("created_at", desc=True)
        .execute()
    )
    df = pd.DataFrame(r.data or [])
    if df.empty:
        return df
    df["created_at"] = pd.to_datetime(df["created_at"], errors="coerce")
    df["plan_day"] = pd.to_datetime(df["plan_day"], errors="coerce").dt.date
    return df


def get_plan_pdf_bytes(user_key: str, plan_id: int) -> bytes | None:
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


def plans_ui(user: dict):
    st.subheader("📚 Meus Planos (Histórico)")

    status = (user.get("status") or "trial").lower()
    if status == "blocked":
        st.error("O seu acesso está bloqueado. Contacte o Administrador.")
        st.stop()

    df = list_user_plans(user["user_key"])
    if df.empty:
        st.info("Ainda não há planos guardados no seu histórico.")
        st.caption("Se você já tem o módulo de geração, continue a usar. Aqui é só o histórico + download.")
        return

    c1, c2, c3 = st.columns(3)
    with c1:
        classe_f = st.selectbox("Filtrar por classe", ["Todas"] + sorted(df["classe"].astype(str).unique().tolist()))
    with c2:
        datas = sorted({str(d) for d in df["plan_day"].dropna().tolist()})
        data_f = st.selectbox("Filtrar por data do plano", ["Todas"] + datas)
    with c3:
        ordem = st.selectbox("Ordenar", ["Mais recente", "Mais antigo"])

    out = df.copy()
    if classe_f != "Todas":
        out = out[out["classe"].astype(str) == classe_f]
    if data_f != "Todas":
        out = out[out["plan_day"].astype(str) == data_f]
    out = out.sort_values("created_at", ascending=(ordem == "Mais antigo"))

    out["label"] = (
        out["plan_day"].astype(str) + " | " +
        out["classe"].astype(str) + " | " +
        out["disciplina"].astype(str) + " | " +
        out["tema"].astype(str)
    )

    st.dataframe(
        out[["plan_day","classe","disciplina","tema","unidade","turma","created_at"]],
        hide_index=True,
        use_container_width=True
    )

    sel = st.selectbox("Selecionar plano para baixar", out["label"].tolist())
    plan_id = int(out[out["label"] == sel].iloc[0]["id"])

    pdf_bytes = get_plan_pdf_bytes(user["user_key"], plan_id)
    if not pdf_bytes:
        st.error("Não foi possível carregar o PDF deste plano.")
        return

    st.download_button(
        "⬇️ Baixar PDF",
        data=pdf_bytes,
        file_name=f"Plano_{sel}.pdf".replace(" ", "_").replace("|", "-"),
        mime="application/pdf",
        type="primary",
    )
