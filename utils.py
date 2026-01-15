import hashlib
import unicodedata
import re
import streamlit as st
from supabase import create_client


# ----------------
# Supabase
# ----------------
def supa():
    return create_client(
        st.secrets["SUPABASE_URL"],
        st.secrets["SUPABASE_SERVICE_ROLE_KEY"],
    )


# ----------------
# Normalização
# ----------------
def normalize_text(text: str) -> str:
    if not text:
        return ""
    t = text.strip().lower()
    t = unicodedata.normalize("NFKD", t)
    t = "".join(c for c in t if not unicodedata.combining(c))
    t = re.sub(r"[^\w\s]", " ", t)   # tira pontuação
    t = re.sub(r"\s+", " ", t).strip()
    return t


# ----------------
# User key
# ----------------
def make_user_key(name: str, school: str) -> str:
    raw = (normalize_text(name) + "|" + normalize_text(school)).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


# ----------------
# PIN hash
# ----------------
def pin_hash(pin: str) -> str:
    pepper = st.secrets["PIN_PEPPER"]
    raw = (str(pin) + pepper).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


# ----------------
# Users
# ----------------Acesso DB
# ----------------
def get_user_by_key(user_key: str):
    sb = supa()
    r = sb.table("app_users").select("*").eq("user_key", user_key).limit(1).execute()
    return r.data[0] if r.data else None
