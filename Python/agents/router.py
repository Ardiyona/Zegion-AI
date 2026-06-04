import re

# =========================
# MODE CONSTANTS
# =========================

MODE_CHAT = "chat"
MODE_QUICK = "quick"
MODE_DEEP = "deep"

# =========================
# KEYWORD PATTERNS
# =========================

# Keyword yang menandakan task coding (DEEP)
DEEP_KEYWORDS = [
    r"refactor", r"debug", r"perbaiki\s+bug", r"fix\s+bug",
    r"implementasi", r"tambahkan\s+fitur", r"redesign",
    r"optimasi", r"migrate", r"upgrade",
    r"multi.?file", r"seluruh\s+project", r"semua\s+file",
]

# Keyword yang menandakan task sederhana (QUICK)
QUICK_KEYWORDS = [
    r"buat(?:kan)?\s+file", r"tulis\s+file", r"buat(?:kan)?\s+script",
    r"hapus\s+file", r"rename", r"pindah(?:kan)?",
    r"baca\s+file", r"lihat\s+file", r"tampilkan",
    r"jalankan", r"execute", r"run\s+",
    r"cari\s+file", r"search", r"list\s+file",
    r"edit\s+", r"ubah\s+", r"ganti\s+",
]

# Keyword yang menandakan chat biasa (CHAT)
CHAT_KEYWORDS = [
    r"^halo", r"^hai", r"^hi\b", r"^hey\b", r"^hello",
    r"^apa\s+(itu|kabar)", r"^siapa\s+kamu",
    r"^terima\s*kasih", r"^thanks", r"^makasih",
    r"^jelaskan", r"^ceritakan", r"^apa\s+bedanya",
    r"^kenapa", r"^mengapa", r"^bagaimana\s+cara",
    r"^apakah\s+", r"^bisakah\s+",
    r"^tolong\s+jelaskan", r"^apa\s+maksud",
]


def detect_mode(user_input):
    """
    Deteksi mode berdasarkan input user (rule-based, tanpa AI).

    Return: MODE_CHAT, MODE_QUICK, atau MODE_DEEP
    """
    text = user_input.lower().strip()

    # Cek DEEP dulu (lebih spesifik)
    for pattern in DEEP_KEYWORDS:
        if re.search(pattern, text, re.IGNORECASE):
            return MODE_DEEP

    # Cek QUICK
    for pattern in QUICK_KEYWORDS:
        if re.search(pattern, text, re.IGNORECASE):
            return MODE_QUICK

    # Cek CHAT
    for pattern in CHAT_KEYWORDS:
        if re.search(pattern, text, re.IGNORECASE):
            return MODE_CHAT

    # Default: kalau pendek → chat, kalau panjang → quick
    if len(text) < 30:
        return MODE_CHAT
    else:
        return MODE_QUICK


def parse_override(user_input):
    """
    Cek apakah user memaksa mode tertentu dengan prefix.

    Return: (forced_mode atau None, clean_input)
    """
    text = user_input.strip()

    if text.lower().startswith("/chat "):
        return MODE_CHAT, text[6:]
    elif text.lower().startswith("/quick "):
        return MODE_QUICK, text[7:]
    elif text.lower().startswith("/deep "):
        return MODE_DEEP, text[6:]

    return None, text


def mode_label(mode):
    """Return icon + label untuk mode."""
    labels = {
        MODE_CHAT: "💬 Chat",
        MODE_QUICK: "⚡ Quick",
        MODE_DEEP: "🔬 Deep",
    }
    return labels.get(mode, mode)
