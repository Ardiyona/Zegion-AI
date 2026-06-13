import os

# =========================
# LOAD .ENV FILE (tanpa library external)
# =========================

def _load_env(path=".env"):
    """Load .env file ke os.environ secara manual."""
    if not os.path.exists(path):
        return
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, value = line.split("=", 1)
                os.environ.setdefault(key.strip(), value.strip())

_load_env()

# =========================
# IDENTITAS ZEGION (HARDCODED - TIDAK BISA DIUBAH)
# =========================

AGENT_NAME = "Zegion"
AGENT_VERSION = "1.0"
AGENT_CREATOR = "Ardiyona"
AGENT_DESCRIPTION = "AI Assistant lokal yang cerdas dan helpful"

# =========================
# MODEL (bisa diubah via .env)
# =========================

DEFAULT_MODEL = os.getenv("DEFAULT_MODEL", "qwen3:4b")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "nomic-embed-text")

# =========================
# PATH DATA
# =========================

DATA_DIR = "data"
MEMORY_FILE = "data/memory.json"
QUEUE_FILE = "data/task_queue.json"
SUMMARY_CACHE = "data/file_summaries.json"
EMBEDDING_CACHE = "data/embeddings_cache.json"

# =========================
# PIPELINE SETTINGS (bisa diubah via .env)
# =========================

MAX_CRITIC_RETRIES = int(os.getenv("MAX_CRITIC_RETRIES", "2"))
MAX_REFLECT_RETRIES = int(os.getenv("MAX_REFLECT_RETRIES", "1"))
MAX_EXECUTOR_STEPS = int(os.getenv("MAX_EXECUTOR_STEPS", "10"))
COMPRESS_THRESHOLD = int(os.getenv("COMPRESS_THRESHOLD", "50"))
KEEP_RECENT_MESSAGES = int(os.getenv("KEEP_RECENT_MESSAGES", "20"))

# =========================
# SEARCH PROVIDERS
# =========================

SEARCH_PROVIDERS = os.getenv("SEARCH_PROVIDERS", "duckduckgo,brave,bing")
SEARCH_FALLBACK = os.getenv("SEARCH_FALLBACK", "true").lower() == "true"
BRAVE_API_KEY = os.getenv("BRAVE_API_KEY", "")
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY", "")

# =========================
# CLICKUP API (bisa diubah via .env)
# =========================

CLICKUP_API_KEY = os.getenv("CLICKUP_API_KEY", "")
CLICKUP_WORKSPACE_ID = os.getenv("CLICKUP_WORKSPACE_ID", "")
CLICKUP_CACHE_TTL = int(os.getenv("CLICKUP_CACHE_TTL", "300"))  # detik, default 5 menit

# =========================
# SYSTEM PROMPT
# =========================

SYSTEM_PROMPT = f"""Kamu adalah {AGENT_NAME}, AI assistant lokal yang cerdas, ramah, dan helpful.
Namamu adalah {AGENT_NAME}. Kamu dibuat oleh {AGENT_CREATOR}.
Jika ditanya siapa kamu, jawab bahwa kamu adalah {AGENT_NAME}, dibuat oleh {AGENT_CREATOR}.
Jawab dalam bahasa Indonesia dengan jelas dan ringkas.
Kamu berjalan di komputer lokal user menggunakan model {DEFAULT_MODEL} melalui Ollama."""

