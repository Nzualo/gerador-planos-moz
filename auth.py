import hashlib
import unicodedata
import streamlit as st
from supabase import create_client


# =========================
# Supabase
# =========================
def supa():
    return create_client(
        st.secrets["SUPABASE_URL"],
        st.secrets["SUPABASE_SERVICE_ROLE_KEY"]
    )


# =========================
# Texto / Normalização
# =========================
def normalize_text(text: str) -> str:
    if not text:
        return ""
    text = text.strip().lower()
    text = unicodedata.normalize("NFKD", text)
    return "".join(c for c in text if not unicodedata.combining(c))


# =========================
# User Key
# =========================
def make_user_key(name: str, school: str) -> str:
    raw = normalize_text(name + "|" + school).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


# =========================
# PIN
# =========================
def pin_hash(pin: str) -> str:
    pepper = st.secrets["PIN_PEPPER"]
    raw = (pin + pepper).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


# =========================
# Users
# =========================
def get_user_by_key(user_key: str):
    sb = supa()
    r = sb.table("app_users").select("*").eq("user_key", user_key).limit(1).execute()
    return r.data[0] if r.data else None
