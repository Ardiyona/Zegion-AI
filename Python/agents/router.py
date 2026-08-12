import re

from config import CLICKUP_API_KEY

_CLICKUP_ENABLED = bool(CLICKUP_API_KEY)

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
    # Web search triggers
    r"cari\s+di\s+internet", r"googling", r"search\s+internet",
    r"harga\s+\w+", r"berita\s+", r"apa\s+itu\s+error",
    r"solusi\s+error", r"cara\s+install", r"download\s+",
    r"rilis\s+terbaru", r"versi\s+terbaru", r"update\s+terbaru",
    r"fetch\s+url", r"buka\s+url", r"baca\s+website",
    r"edit\s+", r"ubah\s+", r"ganti\s+",
    # ClickUp
    r"clickup", r"lihat\s+task", r"buat\s+task", r"update\s+task",
    r"list\s+task", r"task\s+saya", r"space\s+clickup",
    r"sprint", r"backlog", r"comment\s+task",
    r"detail\s+task", r"lihat\s+detail", r"task\s+id",
    r"isi\s+.*task", r"ubah\s+.*task", r"ganti\s+.*task",
    r"tambah\s+komentar", r"status\s+task", r"prioritas\s+task",
    r"\b86[a-z0-9]{7,9}\b",  # ClickUp task ID pattern (e.g. 86exy7d21)
]

# Keyword yang menandakan chat biasa (CHAT)
CHAT_KEYWORDS = [
    r"^halo", r"^hai", r"^hi\b", r"^hey\b", r"^hello",
    r"^apa\s+(itu|kabar)", r"^siapa\s+kamu",
    r"^terima\s*kasih", r"^thanks", r"^makasih",
    r"^jelaskan", r"^ceritakan", r"^apa\s+bedanya",
    r"^kenapa", r"^mengapa", r"^bagaimana\s+cara",
    r"apakah\s+", r"^bisakah\s+",
    r"^tolong\s+jelaskan", r"^apa\s+maksud",
    # Pertanyaan identitas / status model
    r"model\s+(apa|mana|yang)", r"pakai\s+model", r"masih\s+model",
    r"kamu\s+(siapa|apa|pakai|model)", r"anda\s+(siapa|apa|pakai|model)",
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
        # Skip ClickUp patterns if not configured
        if not _CLICKUP_ENABLED and any(kw in pattern for kw in ["clickup", r"86[a-z0-9]"]):
            continue
        if re.search(pattern, text, re.IGNORECASE):
            return MODE_QUICK

    # Cek CHAT
    for pattern in CHAT_KEYWORDS:
        if re.search(pattern, text, re.IGNORECASE):
            return MODE_CHAT

    # Default: chat — unrecognized input is more likely conversational than actionable
    return MODE_CHAT


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
