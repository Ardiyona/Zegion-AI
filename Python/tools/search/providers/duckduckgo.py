import re
import json
from tools.search.base import SearchProvider


class DuckDuckGoProvider(SearchProvider):
    """
    DuckDuckGo provider dengan dua strategi:
    1. JS endpoint (d.js + VQD token) — lebih cepat, tapi bergantung pada internal DDG
    2. HTML endpoint (html.duckduckgo.com) — lebih stabil, tidak butuh VQD

    Jika strategi 1 gagal (VQD tidak ditemukan / parse error), otomatis coba strategi 2.
    Jika keduanya gagal, raise ke SearchManager untuk fallback ke provider lain.
    """

    name = "DuckDuckGo"

    def search(self, query: str, max_results: int = 5) -> list[dict]:
        try:
            return self._search_js(query, max_results)
        except _ParseError as e:
            print(f"[SEARCH] DuckDuckGo JS parse failed ({e}), fallback ke HTML endpoint")
            return self._search_html(query, max_results)

    # =========================
    # Strategi 1: JS endpoint
    # =========================

    def _search_js(self, query: str, max_results: int) -> list[dict]:
        from curl_cffi import requests as curl_requests
        from bs4 import BeautifulSoup

        session = curl_requests.Session(impersonate="chrome120")

        resp = session.get(
            "https://duckduckgo.com/",
            params={"q": query},
            timeout=10,
        )

        vqd = self._extract_vqd(resp.text)
        if not vqd:
            raise _ParseError("VQD token tidak ditemukan")

        resp = session.get(
            "https://links.duckduckgo.com/d.js",
            params={"q": query, "vqd": vqd, "kl": "id-id"},
            timeout=10,
        )

        data = re.search(r"DDG\.pageLayout\.load\('d',(\[.*?\])\)", resp.text, re.DOTALL)
        if not data:
            raise _ParseError("DDG.pageLayout.load tidak ditemukan di respons")

        try:
            items = json.loads(data.group(1))
        except json.JSONDecodeError as e:
            raise _ParseError(f"JSON parse error: {e}")

        results = []
        for r in items:
            if not r.get("u") or r.get("n"):
                continue
            snippet = BeautifulSoup(r.get("a", ""), "html.parser").get_text()[:300]
            results.append({
                "title": r.get("t", ""),
                "snippet": snippet,
                "url": r.get("u", ""),
            })
            if len(results) >= max_results:
                break

        if not results:
            raise _ParseError("Hasil kosong dari JS endpoint")

        return results

    def _extract_vqd(self, html: str) -> str | None:
        for pattern in [r'vqd="([^"]+)"', r"vqd='([^']+)'", r"vqd=([\d-]+)"]:
            m = re.search(pattern, html)
            if m:
                return m.group(1)
        return None

    # =========================
    # Strategi 2: HTML endpoint
    # =========================

    def _search_html(self, query: str, max_results: int) -> list[dict]:
        from curl_cffi import requests as curl_requests
        from bs4 import BeautifulSoup

        session = curl_requests.Session(impersonate="chrome120")

        resp = session.post(
            "https://html.duckduckgo.com/html/",
            data={"q": query, "kl": "id-id"},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=10,
        )

        soup = BeautifulSoup(resp.text, "html.parser")
        result_divs = soup.select(".result__body")

        results = []
        for div in result_divs[:max_results]:
            title_el = div.select_one(".result__title a")
            snippet_el = div.select_one(".result__snippet")
            if not title_el:
                continue
            results.append({
                "title": title_el.get_text(strip=True),
                "snippet": snippet_el.get_text(strip=True)[:300] if snippet_el else "",
                "url": title_el.get("href", ""),
            })

        if not results:
            raise RuntimeError("DuckDuckGo HTML endpoint tidak mengembalikan hasil")

        return results


class _ParseError(Exception):
    """Internal exception — JS parse gagal, coba HTML fallback."""
    pass
