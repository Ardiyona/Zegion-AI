from abc import ABC, abstractmethod


class SearchProvider(ABC):
    """Base class untuk semua search provider."""

    name: str = "unknown"

    @abstractmethod
    def search(self, query: str, max_results: int = 5) -> list[dict]:
        """
        Jalankan pencarian.
        Return: list of {"title": str, "snippet": str, "url": str}
        Raise: Exception jika gagal (timeout, bot detection, quota, dll)
        """
        ...

    def is_configured(self) -> bool:
        """Return True jika provider sudah terkonfigurasi (misal: API key ada)."""
        return True
