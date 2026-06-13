"""
Registry cancel flag + active stream per conversation.
Thread-safe: semua mutasi state lewat _lock.
"""

import logging
import threading
from typing import Optional

logger = logging.getLogger(__name__)

_cancel_flags: dict[str, bool] = {}
_was_cancelled: set[str] = set()
_active_streams: dict[str, object] = {}
_lock = threading.Lock()


def request_cancel(conv_id: str) -> None:
    """
    Dipanggil dari API thread saat user klik stop.
    Atomically: set flag + ambil stream, lalu close di luar lock.
    """
    with _lock:
        _cancel_flags[conv_id] = True
        stream = _active_streams.pop(conv_id, None)

    # Close di luar lock — hindari deadlock jika close() blocking
    if stream is not None:
        try:
            stream.close()
        except Exception as e:
            logger.debug("[cancel] stream.close() error (ignored): %s", e)


def is_cancelled(conv_id: Optional[str]) -> bool:
    if not conv_id:
        return False
    return _cancel_flags.get(conv_id, False)


def register_stream(conv_id: str, stream: object) -> None:
    """
    Simpan referensi stream aktif.
    Jika conv_id sudah di-cancel sebelum stream terdaftar, langsung close.
    """
    if not conv_id:
        return
    with _lock:
        if _cancel_flags.get(conv_id):
            # Cancel datang lebih dulu — close langsung, jangan simpan
            pass
        else:
            _active_streams[conv_id] = stream
            return

    # Di sini berarti sudah di-cancel — close di luar lock
    try:
        stream.close()
    except Exception as e:
        logger.debug("[cancel] stream.close() on late-register (ignored): %s", e)


def unregister_stream(conv_id: Optional[str]) -> None:
    if not conv_id:
        return
    with _lock:
        _active_streams.pop(conv_id, None)


def mark_cancelled(conv_id: Optional[str]) -> None:
    """
    Tandai conv_id sebagai was_cancelled.
    Dipanggil oleh streaming loop setelah deteksi cancel — JANGAN pop stream
    di sini karena request_cancel sudah melakukannya, dan unregister_stream
    di finally akan membersihkan sisanya.
    """
    if not conv_id:
        return
    with _lock:
        _cancel_flags.pop(conv_id, None)
        _was_cancelled.add(conv_id)


def clear_cancel(conv_id: Optional[str]) -> None:
    """Bersihkan semua flag sebelum eksekusi baru dimulai."""
    if not conv_id:
        return
    with _lock:
        _cancel_flags.pop(conv_id, None)
        _active_streams.pop(conv_id, None)
        _was_cancelled.discard(conv_id)


def pop_was_cancelled(conv_id: Optional[str]) -> bool:
    """Cek dan bersihkan was_cancelled. Return True jika eksekusi dibatalkan."""
    if not conv_id:
        return False
    with _lock:
        if conv_id in _was_cancelled:
            _was_cancelled.discard(conv_id)
            return True
        return False
