"""
summarizer.py — Event-based conversation summarization.

Triggers:
  - executor_success(conv_id, results): called after executor tool success
  - message_count(conv_id): called every 5 messages (fallback)
  - on_close(conv_id): called when conversation closes

All triggers run async (background thread) — never blocks user response.
"""

import json
import logging
import re
import threading
import time
from typing import Optional

from ollama import chat as _ollama_chat
from config import SUMMARY_MODEL
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

_SUMMARY_SYSTEM_PROMPT = """You are a conversation summarizer. Output ONLY valid JSON. No explanation, no markdown.

Extract from the conversation:
- tasks_touched: list of ClickUp task IDs mentioned or acted on
- actions: list of concrete actions taken (e.g. "updated status of 86abc to in progress")
- key_decisions: list of decisions or conclusions reached
- user_info_detected: list of facts about the user (preferences, tech stack, role, projects) — empty list if none detected

Output format (strict JSON, no extra text):
{"tasks_touched": [], "actions": [], "key_decisions": [], "user_info_detected": []}"""


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
        response = _ollama_chat(
            model=SUMMARY_MODEL,
            messages=[
                {"role": "system", "content": _SUMMARY_SYSTEM_PROMPT},
                {"role": "user", "content": f"Summarize this conversation:\n\n{conv_text}"},
            ],
            options={"temperature": 0},
        )
        raw = response["message"]["content"].strip()

        # Extract JSON — handle model wrapping in markdown
        m = re.search(r'\{[\s\S]*\}', raw)
        if not m:
            logger.warning("[summarizer] no JSON in response: %s", raw[:100])
            return None
        summary = json.loads(m.group())

    except Exception as e:
        logger.error("[summarizer] model error: %s", e)
        return None

    # Validate expected keys
    for key in ("tasks_touched", "actions", "key_decisions", "user_info_detected"):
        if key not in summary:
            summary[key] = []

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


# Simple keyword patterns to categorize user_info_detected entries
_PROFILE_PATTERNS = [
    (r'\b(name|nama)\b.*?[:\-]\s*(.+)', "name"),
    (r'\b(role|jabatan|posisi|pekerjaan)\b.*?[:\-]\s*(.+)', "role"),
    (r'\bprefer.+?([\w\+#\.]+)', "preferences"),
    (r'\bproject.+?([\w\s]+)', "projects"),
    (r'\b(uses?|pakai|menggunakan)\b.+?([\w\+#\.]+)', "tech_stack"),
]


def _update_global_user_profile(user_info: list[str]) -> None:
    """Merge user_info_detected into global KB user profile. Rule-based, no model call."""
    if not user_info:
        return

    profile = _load_global_profile()
    up = profile["user_profile"]
    ltc = profile["long_term_context"]

    for info in user_info:
        info_lower = info.lower()
        categorized = False

        # Try to categorize into structured fields
        if any(kw in info_lower for kw in ["prefer", "suka", "favorite", "pakai", "use"]):
            up["preferences"] = _merge_list(up["preferences"], [info])
            categorized = True
        if any(kw in info_lower for kw in ["project", "proyek", "working on", "sedang"]):
            up["projects"] = _merge_list(up["projects"], [info])
            categorized = True
        if any(kw in info_lower for kw in ["python", "go", "javascript", "typescript", "rust",
                                             "java", "kotlin", "swift", "react", "vue", "django",
                                             "fastapi", "ollama", "docker", "linux"]):
            up["tech_stack"] = _merge_list(up["tech_stack"], [info])
            categorized = True
        if any(kw in info_lower for kw in ["name", "nama", "saya adalah", "i am", "my name"]):
            if not up["name"]:
                up["name"] = info
            categorized = True
        if any(kw in info_lower for kw in ["role", "jabatan", "developer", "engineer",
                                             "designer", "manager", "analyst"]):
            if not up["role"]:
                up["role"] = info
            categorized = True

        # Fallback — store in long_term_context if uncategorized
        if not categorized:
            ltc = _merge_list(ltc, [info])

    profile["user_profile"] = up
    profile["long_term_context"] = ltc
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
