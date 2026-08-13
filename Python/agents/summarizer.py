"""
summarizer.py — Event-based conversation summarization.

Triggers:
  - executor_success(conv_id, results): after significant tool writes/mutations
  - message_count(conv_id): every 5 messages with tools, 20 messages for chat-only
  - on_close(conv_id): when conversation closes

All triggers run async (background thread) and persist JSON summaries to SQLite KB.
"""

import json
import logging
import threading
import time
from typing import Optional

from ollama import chat as _ollama_chat
from config import SUMMARY_MODEL, SUMMARY_NUM_CTX
from db import (
    get_conversation,
    get_messages,
    kb_add,
    kb_list,
)

logger = logging.getLogger(__name__)

# Significant tool actions that warrant summarization
_SIGNIFICANT_TOOLS = {
    "CLICKUP_UPDATE_TASK",
    "CLICKUP_CREATE_TASK",
    "CLICKUP_ADD_COMMENT",
    "WRITE_FILE",
    "EXECUTE",
}

# Track per-conv last-summarized message count to avoid redundant summaries
_last_summarized: dict[str, int] = {}

# Semaphore: hanya 1 summarization boleh jalan sekaligus
_summary_semaphore = threading.Semaphore(1)

# Flag: sedang ada request user aktif — summarizer defer sampai selesai
_active_request = threading.Event()


def mark_request_start() -> None:
    """Panggil saat request user mulai diproses."""
    _active_request.set()


def mark_request_done() -> None:
    """Panggil saat request user selesai."""
    _active_request.clear()

# Track whether a conv has ever used an agent tool (QUICK/DEEP)
_has_used_agent_tool: dict[str, bool] = {}

_MESSAGE_THRESHOLD_WITH_TOOLS = 5
_MESSAGE_THRESHOLD_CHAT_ONLY  = 20

_WORK_SUMMARY_SYSTEM_PROMPT = """You are a conversation summarizer. Output ONLY valid JSON. No explanation, no markdown.

Extract durable project/work memory from the conversation:
- tasks_touched: list of ClickUp task IDs mentioned or acted on
- actions: list of concrete actions taken (e.g. "updated status of 86abc to in progress")
- key_decisions: list of technical/product decisions or conclusions reached

Exclude user preferences, identity, communication style, temporary chat, guesses, and duplicates.

Output format (strict JSON, no extra text):
{"tasks_touched": [], "actions": [], "key_decisions": []}"""

_USER_INFO_SYSTEM_PROMPT = """You are a user profile extractor. Output ONLY valid JSON. No explanation, no markdown.

Extract only durable facts about the user:
- stable preferences
- identity or role
- long-term instructions

Exclude project decisions, code actions, temporary requests, assistant actions, guesses, and duplicates. If unsure, return an empty list.

Output format (strict JSON, no extra text):
{"user_info_detected": []}"""


def _parse_summary_json(raw: str) -> Optional[dict]:
    decoder = json.JSONDecoder()
    for i, char in enumerate(raw):
        if char != "{":
            continue
        try:
            obj, _ = decoder.raw_decode(raw[i:])
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            return obj
    return None


def _ensure_list_of_strings(value, *, max_items: int = 20, max_len: int = 300) -> list[str]:
    if not isinstance(value, list):
        return []

    result = []
    seen = set()
    for item in value:
        if not isinstance(item, str):
            continue
        text = " ".join(item.split())[:max_len]
        if not text:
            continue
        key = text.lower()
        if key in seen:
            continue
        result.append(text)
        seen.add(key)
        if len(result) >= max_items:
            break
    return result


def _normalize_work_summary(summary: dict) -> dict:
    return {
        "tasks_touched": _ensure_list_of_strings(summary.get("tasks_touched")),
        "actions": _ensure_list_of_strings(summary.get("actions")),
        "key_decisions": _ensure_list_of_strings(summary.get("key_decisions")),
        "user_info_detected": [],
    }


_PROJECT_WORK_TERMS = (
    "updated",
    "fixed",
    "implemented",
    "created task",
    "added comment",
    "changed status",
    "refactored",
    "deployed",
    "clickup",
    "middleware",
    "sudah mengubah",
    "sudah memperbaiki",
    "menambahkan komentar",
)


def _normalize_user_info(summary: dict) -> list[str]:
    items = _ensure_list_of_strings(summary.get("user_info_detected"), max_items=10)
    result = []
    for item in items:
        item_lower = item.lower()
        if any(term in item_lower for term in _PROJECT_WORK_TERMS):
            continue
        result.append(item)
    return result


_USER_INFO_SIGNALS = (
    "remember",
    "ingat",
    "prefer",
    "saya lebih suka",
    "jangan",
    "selalu",
    "panggil saya",
    "my role",
    "i work as",
    "gunakan bahasa",
    "jawab dengan",
)


def _should_extract_user_info(conv_text: str) -> bool:
    text = conv_text.lower()
    return any(signal in text for signal in _USER_INFO_SIGNALS)


def _chat_json(system_prompt: str, user_prompt: str) -> Optional[dict]:
    response = _ollama_chat(
        model=SUMMARY_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        options={"temperature": 0, "num_ctx": SUMMARY_NUM_CTX},
    )
    raw = response["message"]["content"].strip()
    summary = _parse_summary_json(raw)
    if summary is None:
        logger.warning("[summarizer] invalid JSON summary, retrying once: %s", raw[:100])
        response = _ollama_chat(
            model=SUMMARY_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": (
                    "Your previous response was not valid JSON. "
                    "Respond with the JSON object only, starting with { and ending with }. "
                    "Do not add new content.\n\n"
                    f"Input:\n{user_prompt}"
                )},
            ],
            options={"temperature": 0, "num_ctx": SUMMARY_NUM_CTX},
        )
        raw = response["message"]["content"].strip()
        summary = _parse_summary_json(raw)
    return summary


def _build_conversation_text(conv_id: str, limit: int = 30) -> str:
    messages = get_messages(conv_id, limit=limit)
    if not messages:
        return ""
    lines = []
    for m in messages:
        role = m["role"].upper()
        content = m["content"][:500]
        lines.append(f"[{role}]: {content}")
    return "\n".join(lines)


def _run_summary(conv_id: str, reason: str) -> Optional[dict]:
    conv = get_conversation(conv_id)
    if not conv:
        return None

    messages = get_messages(conv_id)
    if len(messages) < 2:
        return None

    conv_text = _build_conversation_text(conv_id)
    if not conv_text:
        return None

    try:
        work_raw = _chat_json(
            _WORK_SUMMARY_SYSTEM_PROMPT,
            f"Summarize project/work memory from this conversation:\n\n{conv_text}",
        )
        if work_raw is None:
            logger.warning("[summarizer] failed to parse work summary after retry")
            return None

        summary = _normalize_work_summary(work_raw)

        if _should_extract_user_info(conv_text):
            user_raw = _chat_json(
                _USER_INFO_SYSTEM_PROMPT,
                f"Extract durable user facts from this conversation:\n\n{conv_text}",
            )
            if user_raw is None:
                logger.warning("[summarizer] failed to parse user_info summary after retry")
            else:
                summary["user_info_detected"] = _normalize_user_info(user_raw)

    except Exception as e:
        logger.error("[summarizer] model error: %s", e)
        return None

    _persist_summary(conv_id, conv.get("title", conv_id), summary, reason)
    return summary


def _persist_summary(conv_id: str, title: str, summary: dict, reason: str) -> None:
    """Upsert per-conversation summary into KB."""
    content = json.dumps(summary, ensure_ascii=False)

    # Check if entry for this conv already exists — update it
    existing = [e for e in kb_list(limit=500) if e.get("source_conv_id") == conv_id]
    if existing:
        from db import kb_update
        kb_update(existing[0]["id"], content=content)
        logger.info("[summarizer] updated KB entry for conv %s (trigger: %s)", conv_id[:8], reason)
    else:
        importance = "high" if summary.get("actions") or summary.get("tasks_touched") else "medium"
        kb_add(content, source_conv_id=conv_id, source_title=title, importance=importance)
        logger.info("[summarizer] added KB entry for conv %s (trigger: %s)", conv_id[:8], reason)

    _last_summarized[conv_id] = _get_message_count(conv_id)

    # Phase 3 hook — process user_info_detected
    user_info = summary.get("user_info_detected", [])
    if user_info:
        _update_global_user_profile(user_info)


def _get_message_count(conv_id: str) -> int:
    return len(get_messages(conv_id))


def mark_agent_tool_used(conv_id: str) -> None:
    """Flag bahwa conversation ini pernah pakai agent tool (QUICK/DEEP)."""
    _has_used_agent_tool[conv_id] = True


def _should_summarize_by_count(conv_id: str) -> bool:
    """Dual threshold: 5 pesan kalau pernah pakai agent tool, 20 kalau pure chat."""
    current = _get_message_count(conv_id)
    last = _last_summarized.get(conv_id, 0)
    has_tools = _has_used_agent_tool.get(conv_id, False)
    threshold = _MESSAGE_THRESHOLD_WITH_TOOLS if has_tools else _MESSAGE_THRESHOLD_CHAT_ONLY
    return (current - last) >= threshold


# =========================
# PUBLIC TRIGGER API
# =========================

def _deferred_summary(conv_id: str, reason: str) -> None:
    """Tunggu sampai tidak ada request aktif, lalu run summary dengan semaphore."""
    # Tunggu request user selesai dulu (max 60s)
    deadline = time.time() + 60
    while _active_request.is_set() and time.time() < deadline:
        time.sleep(0.5)

    if not _summary_semaphore.acquire(blocking=False):
        logger.info("[summarizer] skipped (another summary running): %s", reason)
        return
    try:
        _run_summary(conv_id, reason)
    finally:
        _summary_semaphore.release()


def trigger_executor_success(conv_id: str, results: list[dict]) -> None:
    """Call after executor completes — runs async if significant tool was used."""
    if not conv_id:
        return
    used_tools = {r.get("action", "").upper() for r in results}
    if not used_tools.intersection(_SIGNIFICANT_TOOLS):
        return
    threading.Thread(
        target=_deferred_summary, args=(conv_id, "executor_success"), daemon=True
    ).start()


def trigger_message_count(conv_id: str) -> None:
    """Call after each message save — summarizes every 5 messages."""
    if not conv_id:
        return
    if _should_summarize_by_count(conv_id):
        threading.Thread(
            target=_deferred_summary, args=(conv_id, "message_count"), daemon=True
        ).start()


def trigger_on_close(conv_id: str) -> None:
    """Call when conversation closes — always summarize if >= 2 messages."""
    if not conv_id:
        return
    threading.Thread(
        target=_deferred_summary, args=(conv_id, "on_close"), daemon=True
    ).start()


# =========================
# PHASE 3 — GLOBAL USER PROFILE
# Persists user facts across all conversations.
# key: stored as source_title = "global:user_profile"
# =========================

_GLOBAL_PROFILE_KEY = "global:user_profile"

_EMPTY_PROFILE = {
    "user_profile": {
        "name": "",
        "role": "",
        "preferences": [],
        "projects": [],
        "tech_stack": [],
    },
    "long_term_context": [],
}


def _load_global_profile() -> dict:
    entries = [e for e in kb_list(limit=500) if e.get("source_title") == _GLOBAL_PROFILE_KEY]
    if not entries:
        return json.loads(json.dumps(_EMPTY_PROFILE))
    try:
        return json.loads(entries[0]["content"])
    except Exception:
        return json.loads(json.dumps(_EMPTY_PROFILE))


def _save_global_profile(profile: dict) -> None:
    content = json.dumps(profile, ensure_ascii=False)
    existing = [e for e in kb_list(limit=500) if e.get("source_title") == _GLOBAL_PROFILE_KEY]
    if existing:
        from db import kb_update
        kb_update(existing[0]["id"], content=content, importance="high")
    else:
        kb_add(content, source_title=_GLOBAL_PROFILE_KEY, importance="high")


def _merge_list(existing: list, incoming: list) -> list:
    """Deduplicate — case-insensitive, keep existing order, append new."""
    existing_lower = {s.lower() for s in existing}
    result = list(existing)
    for item in incoming:
        if item.lower() not in existing_lower:
            result.append(item)
            existing_lower.add(item.lower())
    return result


def _update_global_user_profile(user_info: list[str]) -> None:
    """Merge durable user facts conservatively; keep full text to avoid keyword misclassification."""
    if not user_info:
        return

    profile = _load_global_profile()
    profile["long_term_context"] = _merge_list(profile["long_term_context"], user_info)
    _save_global_profile(profile)
    logger.info("[summarizer] global user profile updated")


def reset_global_profile() -> bool:
    """Hapus global user profile dari KB. Return True jika ada yang dihapus."""
    from db import kb_delete
    entries = [e for e in kb_list(limit=500) if e.get("source_title") == _GLOBAL_PROFILE_KEY]
    if not entries:
        return False
    kb_delete(entries[0]["id"])
    logger.info("[summarizer] global user profile reset")
    return True


def get_global_profile_context() -> str:
    """Return global user profile as inject-ready string for planner/executor."""
    profile = _load_global_profile()
    up = profile["user_profile"]
    ltc = profile["long_term_context"]

    lines = []
    if up.get("name"):
        lines.append(f"User name: {up['name']}")
    if up.get("role"):
        lines.append(f"User role: {up['role']}")
    if up.get("preferences"):
        lines.append(f"Preferences: {', '.join(up['preferences'])}")
    if up.get("tech_stack"):
        lines.append(f"Tech stack: {', '.join(up['tech_stack'])}")
    if up.get("projects"):
        lines.append(f"Active projects: {', '.join(up['projects'])}")
    if ltc:
        lines.append(f"Additional context: {'; '.join(ltc[:5])}")

    if not lines:
        return ""

    return "[USER PROFILE]\n" + "\n".join(lines) + "\n[/USER PROFILE]"
