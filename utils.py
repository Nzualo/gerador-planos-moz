import hashlib
import re
import unicodedata
import streamlit as st
from supabase import create_client


def supa():
    return create_client(
        st.secrets["SUPABASE_URL"],
        st.secrets["SUPABASE_SERVICE_ROLE_KEY"]
    )


def strip_accents(s: str) -> str:
    s = unicodedata.normalize("NFD", s or "")
    return "".join(c for c in s if unicodedata.category(c) != "Mn")


def normalize_text(s: str) -> str:
    s = (s or "").strip().lower()
    s = strip_accents(s)
    s = re.sub(r"[.,\"“”’‘]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def pin_hash(pin: str) -> str:
    pepper = st.secrets["PIN_PEPPER"]
    raw = (pin.strip() + "|" + pepper).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def make_user_key(name: str, school: str) -> str:
    raw = (name.strip().lower() + "|" + school.strip().lower()).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()
