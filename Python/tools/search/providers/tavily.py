from tools.search.base import SearchProvider


# =============================================================
# Tavily API (opsional — butuh TAVILY_API_KEY di .env)
# Uncomment kode di bawah dan update providers/__init__.py
# serta registry di manager.py untuk mengaktifkan.
# =============================================================

# import os
#
# class TavilyProvider(SearchProvider):
#     name = "Tavily"
#
#     def is_configured(self) -> bool:
#         return bool(os.getenv("TAVILY_API_KEY"))
#
#     def search(self, query: str, max_results: int = 5) -> list[dict]:
#         import requests
#
#         api_key = os.getenv("TAVILY_API_KEY")
#         if not api_key:
#             raise RuntimeError("TAVILY_API_KEY tidak ditemukan di .env")
#
#         resp = requests.post(
#             "https://api.tavily.com/search",
#             json={
#                 "api_key": api_key,
#                 "query": query,
#                 "max_results": max_results,
#                 "search_depth": "basic",
#             },
#             timeout=15,
#         )
#
#         if resp.status_code == 429:
#             raise RuntimeError("quota exceeded: Tavily rate limit tercapai")
#         if resp.status_code == 401:
#             raise RuntimeError("quota exceeded: TAVILY_API_KEY tidak valid")
#         resp.raise_for_status()
#
#         data = resp.json()
#         results = []
#         for r in data.get("results", [])[:max_results]:
#             results.append({
#                 "title": r.get("title", ""),
#                 "snippet": r.get("content", "")[:300],
#                 "url": r.get("url", ""),
#             })
#
#         if not results:
#             raise RuntimeError("Tavily mengembalikan hasil kosong")
#
#         return results


class BingHTMLProvider(SearchProvider):
    """
    Scraping Bing Search — tidak butuh API key.
    Dipakai sebagai fallback terakhir setelah DuckDuckGo dan Brave.
    """

    name = "Bing"

    def search(self, query: str, max_results: int = 5) -> list[dict]:
        from curl_cffi import requests as curl_requests
        from bs4 import BeautifulSoup

        session = curl_requests.Session(impersonate="chrome120")
        resp = session.get(
            "https://www.bing.com/search",
            params={"q": query, "setlang": "id", "cc": "ID"},
            timeout=10,
        )
        resp.raise_for_status()

        soup = BeautifulSoup(resp.text, "html.parser")
        results = []

        for el in soup.select("li.b_algo")[:max_results]:
            title_el = el.select_one("h2 a")
            snippet_el = el.select_one(".b_caption p") or el.select_one(".b_snippet")

            if not title_el:
                continue

            url = title_el.get("href", "")
            if not url.startswith("http"):
                continue

            # Bing kadang bungkus URL dengan redirect internal — ambil URL asli dari param 'u'
            if "bing.com/ck/" in url:
                import re, urllib.parse
                m = re.search(r"[?&]u=a1([A-Za-z0-9_-]+)", url)
                if m:
                    try:
                        import base64
                        url = base64.urlsafe_b64decode(m.group(1) + "==").decode("utf-8", errors="ignore")
                    except Exception:
                        pass

            results.append({
                "title": title_el.get_text(strip=True),
                "snippet": snippet_el.get_text(strip=True)[:300] if snippet_el else "",
                "url": url,
            })

        if not results:
            raise RuntimeError("Bing tidak mengembalikan hasil (struktur halaman mungkin berubah)")

        return results
