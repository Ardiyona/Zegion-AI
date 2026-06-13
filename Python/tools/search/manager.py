import os
import time
import datetime
from tools.search.base import SearchProvider
from tools.search.providers import DuckDuckGoProvider, BraveHTMLProvider, BingHTMLProvider

# Registry: nama provider → class
_PROVIDER_REGISTRY: dict[str, type[SearchProvider]] = {
    "duckduckgo": DuckDuckGoProvider,
    "brave": BraveHTMLProvider,
    "bing": BingHTMLProvider,
}

COOLDOWN_SECONDS = 300  # 5 menit

# Runtime state (reset saat proses restart)
_provider_cooldown: dict[str, float] = {}
_provider_stats: dict[str, dict] = {}

# Pola error yang menandakan quota/rate limit → trigger cooldown
_QUOTA_PATTERNS = [
    "quota exceeded",
    "429",
    "too many requests",
    "rate limit",
    "ratelimit",
    "daily limit",
    "monthly limit",
    "usage limit",
    "exceeded your",
]


# =========================
# STATS
# =========================

def _get_stats(name: str) -> dict:
    if name not in _provider_stats:
        _provider_stats[name] = {
            "success": 0,
            "failed": 0,
            "last_success": None,
            "last_error": None,
            "total_ms": 0,
        }
    return _provider_stats[name]


def _record_success(name: str, elapsed_ms: int, result_count: int):
    s = _get_stats(name)
    s["success"] += 1
    s["total_ms"] += elapsed_ms
    s["last_success"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[SEARCH] Success: {result_count} results ({elapsed_ms}ms)")


def _record_failure(name: str, error_msg: str):
    s = _get_stats(name)
    s["failed"] += 1
    s["last_error"] = error_msg[:200]


def get_stats() -> dict:
    """Return statistik semua provider (public API)."""
    result = {}
    for name, s in _provider_stats.items():
        total = s["success"] + s["failed"]
        rate = round(s["success"] / total * 100, 1) if total > 0 else 0
        avg_ms = round(s["total_ms"] / s["success"]) if s["success"] > 0 else 0
        result[name] = {
            **s,
            "total": total,
            "success_rate": rate,
            "avg_ms": avg_ms,
        }
    return result


def print_stats():
    """Print ringkasan statistik provider ke console."""
    stats = get_stats()
    if not stats:
        print("[SEARCH] Belum ada data statistik (belum ada query yang dijalankan).")
        return
    print("\n[SEARCH] === Provider Statistics ===")
    for name, s in stats.items():
        cooldown_info = ""
        if _is_on_cooldown(name):
            remaining = int(_provider_cooldown[name] - time.time())
            cooldown_info = f" [COOLDOWN {remaining}s]"
        print(f"  {name}{cooldown_info}:")
        print(f"    Success Rate : {s['success_rate']}% ({s['success']}/{s['total']})")
        if s["success"] > 0:
            print(f"    Avg Response : {s['avg_ms']}ms")
        print(f"    Last Success : {s['last_success'] or '-'}")
        if s["last_error"]:
            print(f"    Last Error   : {s['last_error'][:80]}")
    print()


# =========================
# COOLDOWN
# =========================

def _is_quota_error(msg: str) -> bool:
    msg_lower = msg.lower()
    return any(p in msg_lower for p in _QUOTA_PATTERNS)


def _is_on_cooldown(name: str) -> bool:
    return time.time() < _provider_cooldown.get(name, 0)


def _set_cooldown(name: str):
    _provider_cooldown[name] = time.time() + COOLDOWN_SECONDS


# =========================
# PROVIDER BUILDER
# =========================

def _build_providers() -> list[SearchProvider]:
    """Bangun daftar provider sesuai urutan dari SEARCH_PROVIDERS env."""
    raw = os.getenv("SEARCH_PROVIDERS", "duckduckgo,brave,bing")
    names = [n.strip().lower() for n in raw.split(",") if n.strip()]

    providers = []
    for name in names:
        cls = _PROVIDER_REGISTRY.get(name)
        if cls is None:
            print(f"[SEARCH] Warning: provider '{name}' tidak dikenal, dilewati")
            continue
        instance = cls()
        if not instance.is_configured():
            print(f"[SEARCH] Skip {instance.name}: belum dikonfigurasi (API key tidak ada)")
            continue
        providers.append(instance)

    return providers


def register_provider(name: str, cls: type[SearchProvider]):
    """
    Daftarkan provider baru ke registry.
    Gunakan ini untuk menambah provider tanpa mengubah file ini.

    Contoh:
        from tools.search.manager import register_provider
        from tools.search.providers.searxng import SearXNGProvider
        register_provider("searxng", SearXNGProvider)
    """
    _PROVIDER_REGISTRY[name.lower()] = cls


# =========================
# MAIN SEARCH
# =========================

def search(query: str, max_results: int = 5) -> str:
    """
    Jalankan pencarian dengan fallback otomatis ke provider berikutnya.
    Return: string hasil pencarian siap pakai oleh Executor/Responder.
    """
    fallback_enabled = os.getenv("SEARCH_FALLBACK", "true").lower() == "true"
    providers = _build_providers()

    if not providers:
        return (
            "Tidak ada search provider yang aktif. "
            "Pastikan curl_cffi terinstall untuk DuckDuckGo, "
            "atau isi BRAVE_API_KEY / TAVILY_API_KEY di .env"
        )

    last_error = ""

    for provider in providers:
        if _is_on_cooldown(provider.name):
            remaining = int(_provider_cooldown[provider.name] - time.time())
            print(f"[SEARCH] Skip {provider.name}: cooldown aktif ({remaining}s lagi)")
            continue

        print(f"[SEARCH] Provider: {provider.name}")
        t_start = time.time()

        try:
            results = provider.search(query, max_results=max_results)
            elapsed_ms = int((time.time() - t_start) * 1000)
            _record_success(provider.name, elapsed_ms, len(results))
            return _format_results(query, results, provider.name)

        except Exception as e:
            elapsed_ms = int((time.time() - t_start) * 1000)
            err_msg = str(e)
            last_error = err_msg
            _record_failure(provider.name, err_msg)

            if _is_quota_error(err_msg):
                print(f"[SEARCH] Failed: quota/rate limit ({elapsed_ms}ms)")
                print(f"[SEARCH] Disabled temporarily: {provider.name} ({COOLDOWN_SECONDS}s)")
                _set_cooldown(provider.name)
            else:
                short_err = err_msg.split(".")[0][:100]
                print(f"[SEARCH] Failed: {short_err} ({elapsed_ms}ms)")

            if not fallback_enabled:
                break

            next_providers = [
                p for p in providers
                if p.name != provider.name and not _is_on_cooldown(p.name)
            ]
            if next_providers:
                print(f"[SEARCH] Fallback -> {next_providers[0].name}")

    return f"Semua search provider gagal. Error terakhir: {last_error}"


def _format_results(query: str, results: list[dict], provider_name: str) -> str:
    lines = [f"Hasil pencarian untuk: '{query}' (via {provider_name})\n"]
    for i, r in enumerate(results, 1):
        title = r.get("title", "Tanpa judul")
        snippet = r.get("snippet", "")
        url = r.get("url", "")
        lines.append(f"{i}. **{title}**")
        if snippet:
            lines.append(f"   {snippet}")
        lines.append(f"   Sumber: {url}\n")
    return "\n".join(lines)
