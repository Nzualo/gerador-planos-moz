import hashlib
import re
import unicodedata
import streamlit as st
from supabase import create_client

# ---------------------------
# Supabase
# ---------------------------
def supa():
    return create_client(
        st.secrets["SUPABASE_URL"],
        st.secrets["SUPABASE_SERVICE_ROLE_KEY"]
    )

# ---------------------------
# Texto / normalização
# ---------------------------
def strip_accents(s: str) -> str:
    s = unicodedata.normalize("NFD", s)
    return "".join(c for c in s if unicodedata.category(c) != "Mn")

def normalize_text(s: str) -> str:
    s = (s or "").lower().strip()
    s = strip_accents(s)
    s = re.sub(r"[.,\"“”]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s

# ---------------------------
# PIN
# ---------------------------
def pin_hash(pin: str) -> str:
    pepper = st.secrets["PIN_PEPPER"]
    raw = (pin.strip() + "|" + pepper).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()

def make_user_key(name: str, school: str) -> str:
    raw = (name.strip().lower() + "|" + school.strip().lower()).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()
    def get_user_by_key(user_key: str):
    sb = supa()
    r = sb.table("app_users").select("*").eq("user_key", user_key).limit(1).execute()
    return r.data[0] if r.data else None

