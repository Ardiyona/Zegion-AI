"""
core.py — Zegion AI Core Logic
Pipeline logic yang bisa dipanggil dari terminal (main.py) maupun API (api.py).
Storage: SQLite via db.py
"""

import logging
import os
from typing import Optional

from agents.executor import _stream_chat, _CancelledError

from config import (
    AGENT_NAME,
    AGENT_VERSION,
    DEFAULT_MODEL,
    MEMORY_FILE,
    MAX_CRITIC_RETRIES,
    MAX_REFLECT_RETRIES,
    SYSTEM_PROMPT,
)

from tools import (
    build_project_index,
    build_embeddings,
)

from agents import (
    detect_mode,
    parse_override,
    mode_label,
    MODE_CHAT,
    MODE_QUICK,
    MODE_DEEP,
    create_plan,
    format_plan,
    execute_plan,
    generate_response,
    critique,
    reflect,
    compress_memory,
    create_task,
    complete_task,
    fail_task,
    get_pending_tasks,
    get_remaining_steps,
    format_pending_tasks,
    cleanup_completed,
    request_cancel,
    is_cancelled,
    clear_cancel,
    pop_was_cancelled,

)

from db import (
    init_db,
    create_conversation,
    get_conversation,
    list_conversations,
    update_conversation_title,
    add_message,
    get_messages,
    get_messages_as_ollama_format,
    generate_title_from_message,
    migrate_from_json,
    delete_conversation,
    kb_add,
    kb_get_context,
    is_conversation_worth_summarizing,
)

logger = logging.getLogger(__name__)


# =========================
# STARTUP
# =========================

def initialize() -> str:
    """
    Inisialisasi Zegion: init DB, migrate data lama, build index & embeddings.
    Return: project_index (str)
    """
    print(f"\n{AGENT_NAME} v{AGENT_VERSION} memulai...\n")

    init_db()
    print("[DB] Database ready.")

    if os.path.exists(MEMORY_FILE):
        migrated = migrate_from_json(MEMORY_FILE)
        if migrated:
            print("[DB] Migrasi memory.json selesai.")

    print("Membangun project index...")
    project_index = build_project_index(".")
    print("Project index siap!")

    print("Membangun embeddings...")
    embed_result = build_embeddings(".")
    print(f"{embed_result}\n")

    return project_index


def quick_init() -> None:
    """Startup cepat: hanya init DB (termasuk KB table) dan migrasi."""
    init_db()
    if os.path.exists(MEMORY_FILE):
        migrate_from_json(MEMORY_FILE)


# =========================
# OLLAMA HISTORY BUILDER
# =========================

def _build_ollama_history(conv_id: str, limit: int = 20) -> list[dict]:
    """
    Ambil pesan terakhir dari DB dan format untuk Ollama.
    Inject: system prompt + long-term knowledge + recent messages.
    """
    kb_context = kb_get_context(max_entries=8)
    system_content = SYSTEM_PROMPT
    if kb_context:
        system_content = f"{SYSTEM_PROMPT}\n\n{kb_context}"

    messages = [{"role": "system", "content": system_content}]
    history = get_messages_as_ollama_format(conv_id, limit=limit)
    messages.extend(history)
    return messages


# =========================
# PIPELINE MODES
# =========================

def run_chat(user_input: str, conv_id: str) -> Optional[str]:
    """
    Chat Mode: Langsung ke model, tanpa Planner/Executor.

    Returns None if cancelled, otherwise the response string.
    """
    chat_messages = _build_ollama_history(conv_id, limit=20)
    chat_messages.append({"role": "user", "content": user_input})

    try:
        return _stream_chat(model=DEFAULT_MODEL, messages=chat_messages, conv_id=conv_id)
    except _CancelledError:
        return None
    except Exception as e:
        logger.error("[run_chat] error: %s", e)
        return f"Error: {e}"


def run_quick(
    user_request: str,
    plan: list[dict],
    task_id: str,
    project_index: str = "",
    conv_id: Optional[str] = None,
) -> str:
    """Quick Mode: Planner → Executor → Responder."""
    results, exec_response = execute_plan(plan, task_id=task_id, conv_id=conv_id)

    if pop_was_cancelled(conv_id):
        return ""

    has_tools = any(r.get("action") not in ("RESPOND", "DONE") for r in results)

    if has_tools:
        final_response = generate_response(user_request, results, conv_id=conv_id)
        if pop_was_cancelled(conv_id):
            return ""
    elif exec_response:
        final_response = exec_response
    else:
        final_response = "Selesai."

    complete_task(task_id, final_response)
    return final_response


def run_deep(
    user_request: str,
    plan: list[dict],
    task_id: str,
    project_index: str = "",
    conv_id: Optional[str] = None,
) -> str:
    """Deep Mode: Planner → Executor → Critic → Reflection → Responder."""
    results: list[dict] = []
    exec_response = ""

    for attempt in range(MAX_CRITIC_RETRIES + 1):
        if attempt > 0:
            print(f"\nCritic retry {attempt}/{MAX_CRITIC_RETRIES}...")

        results, exec_response = execute_plan(plan, task_id=task_id, conv_id=conv_id)

        if pop_was_cancelled(conv_id):
            return ""

        passed, critic_feedback = critique(user_request, results, exec_response)

        if passed:
            print("  Critic: PASS!")
            break
        else:
            print(f"  Critic: FAIL — {critic_feedback[:150]}")
            if attempt < MAX_CRITIC_RETRIES:
                fix_prompt = f"{user_request}\n\n[CRITIC FEEDBACK]: {critic_feedback}"
                new_plan, _ = create_plan(fix_prompt, project_index)
                if new_plan:
                    plan = new_plan
                else:
                    break
            else:
                print("  Max retries tercapai.")

    is_good, suggestions = reflect(user_request, results, exec_response)

    if not is_good:
        print(f"  Saran: {suggestions[:150]}")
        if MAX_REFLECT_RETRIES > 0:
            improve_prompt = f"{user_request}\n\n[REFLECTION]: {suggestions}"
            new_plan, _ = create_plan(improve_prompt, project_index)
            if new_plan:
                results, exec_response = execute_plan(new_plan, task_id=task_id, conv_id=conv_id)
                if pop_was_cancelled(conv_id):
                    return ""

    has_tools = any(r.get("action") not in ("RESPOND", "DONE") for r in results)

    if has_tools:
        final_response = generate_response(user_request, results, conv_id=conv_id)
        if pop_was_cancelled(conv_id):
            return ""
    elif exec_response:
        final_response = exec_response
    else:
        final_response = "Semua langkah selesai."

    has_error = any(
        isinstance(r.get("result", ""), str) and r["result"].startswith("Error:")
        for r in results
    )
    if has_error:
        fail_task(task_id, final_response)
    else:
        complete_task(task_id, final_response)

    return final_response


# =========================
# MAIN HANDLER
# =========================

def handle_message(
    user_input: str,
    conv_id: str,
    project_index: str = "",
) -> tuple[Optional[str], str, str, list]:
    """
    Handle 1 pesan user — routing ke mode yang tepat.
    Simpan user + assistant message ke DB.

    Returns: (response, conv_id, mode, plan)
    response is None when cancelled — caller must NOT send a response to client.
    """
    if not conv_id or not get_conversation(conv_id):
        conv = create_conversation()
        conv_id = conv["id"]

    # ── RESUME ────────────────────────────────────────
    if user_input.strip().lower() == "resume":
        pending = get_pending_tasks()
        if not pending:
            add_message(conv_id, "assistant", "Tidak ada task pending.")
            return "Tidak ada task pending.", conv_id, "chat", []

        responses = []
        for task in pending:
            tid = task["id"]
            req = task["user_request"]
            remaining = get_remaining_steps(task)
            resp = run_quick(req, remaining, tid, project_index)
            add_message(conv_id, "user", f"[Resume] {req}")
            add_message(conv_id, "assistant", resp)
            responses.append(resp)

        cleanup_completed()
        result = "\n---\n".join(responses)
        return result, conv_id, "resume", []

    # ── DETECT MODE ───────────────────────────────────
    forced_mode, clean_input = parse_override(user_input)
    auto_mode = detect_mode(clean_input)
    mode = forced_mode if forced_mode else auto_mode
    plan: list = []

    add_message(conv_id, "user", clean_input)

    conv = get_conversation(conv_id)
    if conv and conv["title"] == "New Chat":
        title = generate_title_from_message(clean_input)
        update_conversation_title(conv_id, title)

    # ── CHAT MODE ─────────────────────────────────────
    if mode == MODE_CHAT:
        clear_cancel(conv_id)
        final_response = run_chat(clean_input, conv_id)
        if final_response is None or pop_was_cancelled(conv_id) or is_cancelled(conv_id):
            clear_cancel(conv_id)
            return None, conv_id, mode, plan
        add_message(conv_id, "assistant", final_response, mode="Chat", mode_key="chat")
        return final_response, conv_id, mode, plan

    # ── AGENT MODE (QUICK / DEEP) ─────────────────────
    plan_result, raw_plan = create_plan(clean_input, project_index)

    if not plan_result:
        add_message(conv_id, "assistant", raw_plan, mode_key=mode)
        return raw_plan, conv_id, mode, []

    plan = plan_result
    task = create_task(clean_input, plan)
    task_id = task["id"]

    clear_cancel(conv_id)

    if mode == MODE_DEEP:
        final_response = run_deep(clean_input, plan, task_id, project_index, conv_id=conv_id)
    else:
        final_response = run_quick(clean_input, plan, task_id, project_index, conv_id=conv_id)

    # Cancelled — jangan simpan ke DB
    if pop_was_cancelled(conv_id) or is_cancelled(conv_id) or not final_response:
        clear_cancel(conv_id)
        return None, conv_id, mode, plan

    mode_name = mode_label(mode)
    add_message(
        conv_id, "assistant", final_response,
        mode=mode_name, mode_key=mode, plan=plan
    )

    cleanup_completed()
    return final_response, conv_id, mode, plan


# =========================
# SMART DELETE
# =========================

def smart_delete_conversation(conv_id: str) -> dict:
    """
    Hapus conversation dengan safety check:
    1. Cek apakah conversation penting (rule-based, cepat)
    2. Jika penting → AI summarize → simpan ke knowledge base
    3. Hapus conversation dari DB
    """
    from db import get_messages as _get_messages

    conv = get_conversation(conv_id)
    if not conv:
        return {"deleted": False, "summarized": False, "kb_entry": None,
                "reason": "Conversation tidak ditemukan"}

    worth_summarizing = is_conversation_worth_summarizing(conv_id)
    kb_entry = None

    if worth_summarizing:
        messages = _get_messages(conv_id)
        conversation_text = "\n".join(
            f"[{m['role'].upper()}]: {m['content'][:400]}"
            for m in messages
            if m["role"] in ("user", "assistant")
        )

        has_deep = any(m.get("mode_key") == "deep" for m in messages)
        importance = "high" if has_deep else "medium"

        try:
            summary = _stream_chat(
                model=DEFAULT_MODEL,
                messages=[{
                    "role": "user",
                    "content": (
                        "Buat ringkasan singkat dari percakapan ini.\n"
                        "Fokus pada:\n"
                        "1. Apa yang dikerjakan/diputuskan\n"
                        "2. File atau konfigurasi yang berubah\n"
                        "3. Konteks penting yang perlu diingat ke depan\n\n"
                        "Format: bullet points singkat, maksimal 5 poin.\n"
                        "Jawab langsung dalam bahasa Indonesia.\n\n"
                        f"Percakapan:\n{conversation_text[:4000]}"
                    )
                }],
                conv_id=None,  # summarize tidak boleh di-cancel
            )
        except Exception as e:
            summary = f"[Gagal generate summary: {e}]"
            importance = "low"

        kb_entry = kb_add(
            content=summary,
            source_conv_id=conv_id,
            source_title=conv.get("title", "Unknown"),
            importance=importance,
        )
        print(f"[KB] Saved summary from '{conv.get('title')}' (importance: {importance})")

    delete_conversation(conv_id)

    return {
        "deleted": True,
        "summarized": worth_summarizing,
        "kb_entry": kb_entry,
        "reason": "Summarized & deleted" if worth_summarizing else "Deleted (not worth summarizing)",
    }
