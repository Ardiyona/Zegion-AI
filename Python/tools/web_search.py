import ipaddress
import socket
from urllib.parse import urljoin, urlparse

from tools.search.manager import search as _search
from tools.search.providers.duckduckgo import DuckDuckGoProvider


MAX_REDIRECTS = 5


def web_search(query: str, max_results: int = 5) -> str:
    """Cari informasi dari internet. Provider dipilih otomatis oleh Search Manager."""
    return _search(query, max_results=max_results)


def _is_public_ip(host: str) -> bool:
    try:
        ip = ipaddress.ip_address(host)
        return ip.is_global
    except ValueError:
        return False


def _validate_public_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("hanya URL http/https yang diizinkan")
    if not parsed.hostname:
        raise ValueError("hostname wajib ada")
    if parsed.username or parsed.password:
        raise ValueError("credential di URL tidak diizinkan")

    host = parsed.hostname.rstrip(".").lower()
    if host in {"localhost", "localhost.localdomain"} or host.endswith(".local"):
        raise ValueError("hostname lokal tidak diizinkan")

    if _is_public_ip(host):
        return parsed.geturl()

    try:
        infos = socket.getaddrinfo(host, parsed.port, type=socket.SOCK_STREAM)
    except socket.gaierror as e:
        raise ValueError(f"hostname tidak bisa di-resolve: {e}") from e

    ips = {item[4][0] for item in infos}
    if not ips or any(not _is_public_ip(ip) for ip in ips):
        raise ValueError("URL mengarah ke alamat non-publik")

    return parsed.geturl()


def _fetch_public(session, url: str):
    current_url = _validate_public_url(url)
    for _ in range(MAX_REDIRECTS + 1):
        resp = session.get(current_url, timeout=10, allow_redirects=False)
        if resp.status_code not in {301, 302, 303, 307, 308}:
            return resp, current_url

        location = resp.headers.get("location")
        if not location:
            return resp, current_url
        current_url = _validate_public_url(urljoin(current_url, location))

    raise ValueError("redirect terlalu banyak")


def fetch_url(url: str, max_chars: int = 3000) -> str:
    """Ambil dan baca isi halaman web publik dari URL."""
    try:
        from curl_cffi import requests as curl_requests
        from bs4 import BeautifulSoup

        session = curl_requests.Session(impersonate="chrome120")
        resp, final_url = _fetch_public(session, url)
        resp.raise_for_status()

        soup = BeautifulSoup(resp.text, "html.parser")
        for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
            tag.decompose()

        text = soup.get_text(separator="\n", strip=True)
        lines = [l for l in text.splitlines() if l.strip()]
        clean = "\n".join(lines)

        if len(clean) > max_chars:
            clean = clean[:max_chars] + "\n... (terpotong)"

        return f"Isi halaman {final_url}:\n\n{clean}"

    except Exception as e:
        return f"Error saat fetch URL '{url}': {e}"
