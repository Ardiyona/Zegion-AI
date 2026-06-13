import requests
from bs4 import BeautifulSoup
from duckduckgo_search import DDGS


def web_search(query: str, max_results: int = 5) -> str:
    """
    Cari informasi dari internet menggunakan DuckDuckGo.
    Return: teks berisi judul, snippet, dan link dari hasil teratas.
    """
    try:
        results = []
        with DDGS() as ddgs:
            for r in ddgs.text(query, max_results=max_results):
                results.append(r)

        if not results:
            return f"Tidak ada hasil untuk query: {query}"

        lines = [f"Hasil pencarian untuk: '{query}'\n"]
        for i, r in enumerate(results, 1):
            title = r.get("title", "Tanpa judul")
            body = r.get("body", "")[:300]
            href = r.get("href", "")
            lines.append(f"{i}. **{title}**")
            lines.append(f"   {body}")
            lines.append(f"   Sumber: {href}\n")

        return "\n".join(lines)

    except Exception as e:
        return f"Error saat web search: {e}"


def fetch_url(url: str, max_chars: int = 3000) -> str:
    """
    Ambil dan baca isi halaman web dari URL.
    Return: teks bersih dari halaman tersebut.
    """
    try:
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            )
        }
        resp = requests.get(url, headers=headers, timeout=10)
        resp.raise_for_status()

        soup = BeautifulSoup(resp.text, "html.parser")

        # Hapus elemen yang tidak relevan
        for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
            tag.decompose()

        text = soup.get_text(separator="\n", strip=True)

        # Bersihkan baris kosong berlebih
        lines = [l for l in text.splitlines() if l.strip()]
        clean = "\n".join(lines)

        if len(clean) > max_chars:
            clean = clean[:max_chars] + "\n... (terpotong)"

        return f"Isi halaman {url}:\n\n{clean}"

    except Exception as e:
        return f"Error saat fetch URL '{url}': {e}"
