from tools.search.manager import search as _search
from tools.search.providers.duckduckgo import DuckDuckGoProvider


def web_search(query: str, max_results: int = 5) -> str:
    """Cari informasi dari internet. Provider dipilih otomatis oleh Search Manager."""
    return _search(query, max_results=max_results)


def fetch_url(url: str, max_chars: int = 3000) -> str:
    """Ambil dan baca isi halaman web dari URL."""
    try:
        from curl_cffi import requests as curl_requests
        from bs4 import BeautifulSoup

        session = curl_requests.Session(impersonate="chrome120")
        resp = session.get(url, timeout=10)
        resp.raise_for_status()

        soup = BeautifulSoup(resp.text, "html.parser")
        for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
            tag.decompose()

        text = soup.get_text(separator="\n", strip=True)
        lines = [l for l in text.splitlines() if l.strip()]
        clean = "\n".join(lines)

        if len(clean) > max_chars:
            clean = clean[:max_chars] + "\n... (terpotong)"

        return f"Isi halaman {url}:\n\n{clean}"

    except Exception as e:
        return f"Error saat fetch URL '{url}': {e}"
