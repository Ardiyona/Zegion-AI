from tools.search.base import SearchProvider


# =============================================================
# Brave Search API (opsional — butuh BRAVE_API_KEY di .env)
# Uncomment kode di bawah dan update providers/__init__.py
# serta registry di manager.py untuk mengaktifkan.
# =============================================================

# import os
#
# class BraveProvider(SearchProvider):
#     name = "Brave"
#
#     def is_configured(self) -> bool:
#         return bool(os.getenv("BRAVE_API_KEY"))
#
#     def search(self, query: str, max_results: int = 5) -> list[dict]:
#         import requests
#
#         api_key = os.getenv("BRAVE_API_KEY")
#         if not api_key:
#             raise RuntimeError("BRAVE_API_KEY tidak ditemukan di .env")
#
#         resp = requests.get(
#             "https://api.search.brave.com/res/v1/web/search",
#             headers={
#                 "Accept": "application/json",
#                 "Accept-Encoding": "gzip",
#                 "X-Subscription-Token": api_key,
#             },
#             params={"q": query, "count": max_results, "search_lang": "id"},
#             timeout=10,
#         )
#
#         if resp.status_code == 429:
#             raise RuntimeError("quota exceeded: Brave rate limit tercapai")
#         if resp.status_code == 401:
#             raise RuntimeError("quota exceeded: BRAVE_API_KEY tidak valid")
#         resp.raise_for_status()
#
#         data = resp.json()
#         results = []
#         for r in data.get("web", {}).get("results", [])[:max_results]:
#             results.append({
#                 "title": r.get("title", ""),
#                 "snippet": r.get("description", "")[:300],
#                 "url": r.get("url", ""),
#             })
#
#         if not results:
#             raise RuntimeError("Brave mengembalikan hasil kosong")
#
#         return results


class BraveHTMLProvider(SearchProvider):
    """Scraping search.brave.com — tidak butuh API key."""

    name = "Brave"

    def search(self, query: str, max_results: int = 5) -> list[dict]:
        import requests
        from bs4 import BeautifulSoup

        resp = requests.get(
            "https://search.brave.com/search",
            params={"q": query, "source": "web"},
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "id-ID,id;q=0.9,en;q=0.8",
                "Accept-Encoding": "gzip, deflate",  # tolak brotli — requests tidak bisa decode br
            },
            timeout=10,
        )
        resp.raise_for_status()

        soup = BeautifulSoup(resp.text, "html.parser")
        results = []

        for el in soup.select(".snippet")[:max_results]:
            url_el = el.select_one("a[href]")
            if not url_el:
                continue
            url = url_el.get("href", "")
            if not url.startswith("http"):
                continue

            title_el = el.select_one(".snippet-title") or url_el
            snippet_el = el.select_one(".snippet-description")

            results.append({
                "title": title_el.get_text(strip=True),
                "snippet": snippet_el.get_text(strip=True)[:300] if snippet_el else "",
                "url": url,
            })

        if not results:
            raise RuntimeError("Brave HTML tidak mengembalikan hasil (struktur halaman mungkin berubah)")

        return results
