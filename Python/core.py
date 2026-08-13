"""
core.py — Zegion AI Core Logic
Pipeline logic yang bisa dipanggil dari terminal (main.py) maupun API (api.py).
Storage: SQLite via db.py
"""

import logging
import os
import re
from typing import Optional

from agents.executor import _stream_chat, _CancelledError, _DIRECT_RESPONSE_TOOLS, _print_telemetry
from agents.summarizer import trigger_executor_success, trigger_message_count, trigger_on_close, mark_agent_tool_used, mark_request_start, mark_request_done
from agents.usage import clear_usage, get_usage, start_usage
from agents.task_queue import update_task_step

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
    clickup_get_tasks,
    clickup_get_task_detail,
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
    delete_message,
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


def _emit_status(status_callback, text: str) -> None:
    if not status_callback:
        return
    try:
        status_callback(text)
    except Exception as e:
        logger.debug("[status] callback failed: %s", e)


# =========================
# SESSION CONTEXT
# Tracks last tool-touched entity per conv_id — in-memory, resets on restart.
# Used to resolve references like "task yang tadi", "kembalikan yang itu", etc.
# =========================

_session_context: dict[str, dict] = {}


def get_session_context(conv_id: str) -> dict:
    return _session_context.get(conv_id, {})


def update_session_context(conv_id: str, results: list[dict]) -> None:
    """Extract last touched entity from executor results and store per conv_id."""
    for r in reversed(results):
        action = r.get("action", "")
        target = r.get("target", "")
        if not target:
            continue
        if "CLICKUP" in action and target:
            _session_context[conv_id] = {
                "task_id": target,
                "action": action,
                "source": "clickup",
            }
            return


def _inject_session_context(user_input: str, conv_id: str) -> str:
    """
    If user refers to a previous entity without an ID, inject the last known
    context so the planner and executor can resolve it.
    """
    ctx = get_session_context(conv_id)
    if not ctx:
        return user_input

    ref_keywords = [
        "sebelumnya", "tadi", "yang itu", "yang tadi", "yang sama",
        "itu", "tersebut", "barusan", "previously", "that task", "the task",
    ]
    inp_lower = user_input.lower()

    # Only inject if user refers to something without already specifying an ID
    has_id = bool(re.search(r'\b86[a-z0-9]{5,}\b', user_input, re.IGNORECASE))
    has_ref = any(kw in inp_lower for kw in ref_keywords)

    if has_ref and not has_id and ctx.get("task_id"):
        task_id = ctx["task_id"]
        injected = f"{user_input} (task id: {task_id})"
        logger.info("[session_context] injected task_id=%s into: %s", task_id, user_input[:60])
        return injected

    return user_input


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

def _build_ollama_history(conv_id: str, limit: int = 20, model: str = DEFAULT_MODEL) -> list[dict]:
    """
    Ambil pesan terakhir dari DB dan format untuk Ollama.
    Inject: system prompt + long-term knowledge + recent messages.
    """
    kb_context = kb_get_context(max_entries=8)
    system_content = f"{SYSTEM_PROMPT}\nModel yang kamu gunakan saat ini: {model}."
    if kb_context:
        system_content = f"{system_content}\n\n{kb_context}"

    messages = [{"role": "system", "content": system_content}]
    history = get_messages_as_ollama_format(conv_id, limit=limit)
    messages.extend(history)
    return messages


# =========================
# PIPELINE MODES
# =========================

def run_chat(user_input: str, conv_id: str, model: str = DEFAULT_MODEL) -> Optional[str]:
    """
    Chat Mode: Langsung ke model, tanpa Planner/Executor.

    Returns None if cancelled, otherwise the response string.
    """
    chat_messages = _build_ollama_history(conv_id, limit=20, model=model)
    chat_messages.append({"role": "user", "content": user_input})

    try:
        result = _stream_chat(model=model, messages=chat_messages, conv_id=conv_id)
        _print_telemetry("CHAT", model, sum(len(m["content"]) for m in chat_messages), result)
        return result
    except _CancelledError:
        return None
    except Exception as e:
        logger.error("[run_chat] error: %s", e)
        return f"Error: {e}"


def _should_skip_responder(results: list[dict], exec_response: str) -> bool:
    """
    Tentukan apakah Responder bisa di-skip.

    Skip jika:
    - Executor sudah punya jawaban [DONE] yang tidak kosong
    - Semua tool yang dipakai adalah simple read-only tools (direct response)
    - ATAU exec_response sudah cukup panjang dan informatif (>100 char)
    """
    if not exec_response:
        return False

    tool_actions = {r.get("action") for r in results if r.get("action") not in ("RESPOND", "DONE")}
    if not tool_actions:
        return True  # tidak ada tool, langsung pakai exec_response

    # Semua tool adalah direct-response tools
    if tool_actions.issubset(_DIRECT_RESPONSE_TOOLS):
        return True

    # Jika DONE sudah cukup panjang/informatif, skip juga
    if len(exec_response) > 100:
        return True

    return False


_CLICKUP_FAST_MUTATION_WORDS = [
    "buat", "bikin", "create", "add", "tambah", "tambahkan",
    "ubah", "update", "isi", "ganti", "edit", "set", "rename",
    "tandai", "selesaikan", "hapus", "delete",
    "komentar", "comment", "komen",
]

_CLICKUP_FAST_REFERENCE_WORDS = [
    "sebelumnya", "tadi", "yang itu", "yang tadi", "yang sama",
    "itu", "tersebut", "barusan", "previously", "that task", "the task",
]


def _clickup_status_from_text(text: str) -> Optional[str]:
    if re.search(r"\bin\s*progress\b", text):
        return "in progress"
    if re.search(r"\b(to\s*do|todo)\b", text):
        return "to do"
    if re.search(r"\b(done|complete|completed|selesai)\b", text):
        return "complete"
    return None


def try_clickup_fast_path(user_input: str) -> Optional[tuple[list[dict], list[dict], str]]:
    """Direct ClickUp read-only intents; no Planner/Executor LLM."""
    text = user_input.lower().strip()
    if not text or any(word in text for word in _CLICKUP_FAST_MUTATION_WORDS):
        return None

    task_id_match = re.search(r"\b86[a-z0-9]{5,}\b", text, re.IGNORECASE)
    if not task_id_match and any(word in text for word in _CLICKUP_FAST_REFERENCE_WORDS):
        return None

    wants_read = any(word in text for word in [
        "list", "lihat", "tampilkan", "cek", "ambil", "show", "get", "detail", "info",
        "apa saja", "semua", "task saya",
    ])
    mentions_task = "task" in text or "clickup" in text

    if task_id_match and wants_read:
        task_id = task_id_match.group(0)
        plan = [{"step": 1, "action": "CLICKUP_GET_TASK_DETAIL", "params": {"task_id": task_id}, "reason": "Direct read-only intent match"}]
        result = clickup_get_task_detail(task_id)
        results = [{"step": 1, "action": "CLICKUP_GET_TASK_DETAIL", "target": task_id, "result": result}]
        return plan, results, result

    if mentions_task and wants_read:
        status = _clickup_status_from_text(text)
        params = {"status": status} if status else {}
        plan = [{"step": 1, "action": "CLICKUP_GET_TASKS", "params": params, "reason": "Direct read-only intent match"}]
        result = clickup_get_tasks(status=status)
        results = [{"step": 1, "action": "CLICKUP_GET_TASKS", "target": status or "all", "result": result}]
        return plan, results, result

    return None


def run_quick(
    user_request: str,
    plan: list[dict],
    task_id: str,
    project_index: str = "",
    conv_id: Optional[str] = None,
    model: str = DEFAULT_MODEL,
    status_callback=None,
) -> str:
    """Quick Mode: Planner → Executor → (Responder jika perlu)."""
    results, exec_response = execute_plan(
        plan, task_id=task_id, conv_id=conv_id, model=model,
        user_request=user_request, status_callback=status_callback,
    )
    if conv_id:
        update_session_context(conv_id, results)
        trigger_executor_success(conv_id, results)

    if pop_was_cancelled(conv_id):
        return ""

    # Optimasi: skip Responder jika DONE sudah cukup
    if _should_skip_responder(results, exec_response):
        print("\n  ⚡ Skipping Responder (direct response mode)")
        final_response = exec_response
    else:
        has_tools = any(r.get("action") not in ("RESPOND", "DONE") for r in results)
        if has_tools:
            _emit_status(status_callback, "Menyusun jawaban...")
            final_response = generate_response(user_request, results, conv_id=conv_id, model=model, status_callback=status_callback)
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
    model: str = DEFAULT_MODEL,
    status_callback=None,
) -> str:
    """Deep Mode: Planner → Executor → Critic → Reflection → Responder."""
    results: list[dict] = []
    exec_response = ""

    for attempt in range(MAX_CRITIC_RETRIES + 1):
        if attempt > 0:
            print(f"\nCritic retry {attempt}/{MAX_CRITIC_RETRIES}...")

        results, exec_response = execute_plan(
            plan, task_id=task_id, conv_id=conv_id, model=model,
            user_request=user_request, status_callback=status_callback,
        )
        if conv_id:
            update_session_context(conv_id, results)
            trigger_executor_success(conv_id, results)

        if pop_was_cancelled(conv_id):
            return ""

        passed, critic_feedback = critique(user_request, results, exec_response, model=model)

        if passed:
            print("  Critic: PASS!")
            break
        else:
            print(f"  Critic: FAIL — {critic_feedback[:150]}")
            if attempt < MAX_CRITIC_RETRIES:
                fix_prompt = f"{user_request}\n\n[CRITIC FEEDBACK]: {critic_feedback}"
                new_plan, _ = create_plan(fix_prompt, project_index, model=model)
                if new_plan:
                    plan = new_plan
                    _emit_status(status_callback, "Menyusun rencana perbaikan...")
                else:
                    break
            else:
                print("  Max retries tercapai.")

    is_good, suggestions = reflect(user_request, results, exec_response, model=model)

    if not is_good:
        print(f"  Saran: {suggestions[:150]}")
        if MAX_REFLECT_RETRIES > 0:
            improve_prompt = f"{user_request}\n\n[REFLECTION]: {suggestions}"
            new_plan, _ = create_plan(improve_prompt, project_index, model=model)
            if new_plan:
                _emit_status(status_callback, "Menjalankan rencana perbaikan...")
                results, exec_response = execute_plan(
                    new_plan, task_id=task_id, conv_id=conv_id, model=model,
                    user_request=user_request, status_callback=status_callback,
                )
                if pop_was_cancelled(conv_id):
                    return ""

    has_tools = any(r.get("action") not in ("RESPOND", "DONE") for r in results)

    # Optimasi: skip Responder jika DONE sudah cukup
    if _should_skip_responder(results, exec_response):
        print("\n  ⚡ Skipping Responder (direct response mode)")
        final_response = exec_response
    elif has_tools:
        _emit_status(status_callback, "Menyusun jawaban...")
        final_response = generate_response(user_request, results, conv_id=conv_id, model=model, status_callback=status_callback)
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
    model: str = DEFAULT_MODEL,
    status_callback=None,
) -> tuple[Optional[str], str, str, list, dict]:
    """
    Handle 1 pesan user — routing ke mode yang tepat.
    Simpan user + assistant message ke DB.

    Returns: (response, conv_id, mode, plan, usage)
    response is None when cancelled — caller must NOT send a response to client.
    """
    start_usage(model)
    mark_request_start()
    try:
        return _handle_message_inner(user_input, conv_id, project_index, model, status_callback)
    finally:
        mark_request_done()
        clear_usage()


def _handle_message_inner(
    user_input: str,
    conv_id: str,
    project_index: str = "",
    model: str = DEFAULT_MODEL,
    status_callback=None,
) -> tuple[Optional[str], str, str, list, dict]:
    if not conv_id or not get_conversation(conv_id):
        conv = create_conversation()
        conv_id = conv["id"]

    # ── RESUME ────────────────────────────────────────
    if user_input.strip().lower() == "resume":
        pending = get_pending_tasks()
        if not pending:
            usage = get_usage()
            add_message(conv_id, "assistant", "Tidak ada task pending.", usage=usage)
            return "Tidak ada task pending.", conv_id, "chat", [], usage

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
        usage = get_usage()
        return result, conv_id, "resume", [], usage

    # ── DETECT MODE ───────────────────────────────────
    forced_mode, clean_input = parse_override(user_input)
    auto_mode = detect_mode(clean_input)
    mode = forced_mode if forced_mode else auto_mode
    _emit_status(status_callback, f"Mode {mode_label(mode)} aktif...")
    plan: list = []

    user_msg = add_message(conv_id, "user", clean_input)
    user_msg_id = user_msg["id"]

    conv = get_conversation(conv_id)
    if conv and conv["title"] == "New Chat":
        title = generate_title_from_message(clean_input)
        update_conversation_title(conv_id, title)

    # ── CHAT MODE ─────────────────────────────────────
    if mode == MODE_CHAT:
        clear_cancel(conv_id)
        _emit_status(status_callback, "Menyusun jawaban...")
        final_response = run_chat(clean_input, conv_id, model=model)
        if final_response is None or pop_was_cancelled(conv_id) or is_cancelled(conv_id):
            clear_cancel(conv_id)
            delete_message(user_msg_id)
            return None, conv_id, mode, plan, get_usage()
        usage = get_usage()
        add_message(conv_id, "assistant", final_response, mode="Chat", mode_key="chat", usage=usage)
        return final_response, conv_id, mode, plan, usage

    # ── AGENT MODE (QUICK / DEEP) ─────────────────────
    if mode == MODE_QUICK:
        fast = try_clickup_fast_path(clean_input)
        if fast:
            plan, results, final_response = fast
            _emit_status(status_callback, "Mengambil data ClickUp...")
            print("\n  [CLICKUP FAST-PATH]")
            print("  Intent: direct read-only match")
            print("  Planner/Executor tokens: 0")
            print(f"  Tool calls: {len(results)}")

            task = create_task(clean_input, plan)
            task_id = task["id"]
            for i, result in enumerate(results):
                update_task_step(task_id, i, result)
            complete_task(task_id, final_response)
            update_session_context(conv_id, results)
            mark_agent_tool_used(conv_id)

            usage = get_usage()
            add_message(
                conv_id, "assistant", final_response,
                mode=mode_label(mode), mode_key=mode, plan=plan, usage=usage
            )
            trigger_message_count(conv_id)
            cleanup_completed()
            return final_response, conv_id, mode, plan, usage

    plan_input = _inject_session_context(clean_input, conv_id)
    _emit_status(status_callback, "Menyusun rencana...")
    plan_result, raw_plan = create_plan(plan_input, project_index, model=model)

    if not plan_result:
        usage = get_usage()
        add_message(conv_id, "assistant", raw_plan, mode_key=mode, usage=usage)
        return raw_plan, conv_id, mode, [], usage

    plan = plan_result
    task = create_task(clean_input, plan)
    task_id = task["id"]

    clear_cancel(conv_id)
    mark_agent_tool_used(conv_id)

    _emit_status(status_callback, "Menjalankan rencana...")
    if mode == MODE_DEEP:
        final_response = run_deep(clean_input, plan, task_id, project_index, conv_id=conv_id, model=model, status_callback=status_callback)
    else:
        final_response = run_quick(clean_input, plan, task_id, project_index, conv_id=conv_id, model=model, status_callback=status_callback)

    # Cancelled — jangan simpan ke DB, hapus user message yang sudah tersimpan
    if pop_was_cancelled(conv_id) or is_cancelled(conv_id) or not final_response:
        clear_cancel(conv_id)
        delete_message(user_msg_id)
        return None, conv_id, mode, plan, get_usage()

    usage = get_usage()
    mode_name = mode_label(mode)
    add_message(
        conv_id, "assistant", final_response,
        mode=mode_name, mode_key=mode, plan=plan, usage=usage
    )
    trigger_message_count(conv_id)

    cleanup_completed()
    return final_response, conv_id, mode, plan, usage


# =========================
# SMART DELETE
# =========================

def smart_delete_conversation(conv_id: str) -> dict:
    """
    Hapus conversation dari DB.
    (AI summarize dinonaktifkan)
    """
    conv = get_conversation(conv_id)
    if not conv:
        return {"deleted": False, "summarized": False, "kb_entry": None,
                "reason": "Conversation tidak ditemukan"}

    # ── AI Summarize (DISABLED) ──────────────────────────
    # worth_summarizing = is_conversation_worth_summarizing(conv_id)
    # kb_entry = None
    #
    # if worth_summarizing:
    #     from db import get_messages as _get_messages
    #     messages = _get_messages(conv_id)
    #     conversation_text = "\n".join(
    #         f"[{m['role'].upper()}]: {m['content'][:400]}"
    #         for m in messages
    #         if m["role"] in ("user", "assistant")
    #     )
    #
    #     has_deep = any(m.get("mode_key") == "deep" for m in messages)
    #     importance = "high" if has_deep else "medium"
    #
    #     try:
    #         summary = _stream_chat(
    #             model=DEFAULT_MODEL,
    #             messages=[{
    #                 "role": "user",
    #                 "content": (
    #                     "Buat ringkasan singkat dari percakapan ini.\n"
    #                     "Fokus pada:\n"
    #                     "1. Apa yang dikerjakan/diputuskan\n"
    #                     "2. File atau konfigurasi yang berubah\n"
    #                     "3. Konteks penting yang perlu diingat ke depan\n\n"
    #                     "Format: bullet points singkat, maksimal 5 poin.\n"
    #                     "Jawab langsung dalam bahasa Indonesia.\n\n"
    #                     f"Percakapan:\n{conversation_text[:4000]}"
    #                 )
    #             }],
    #             conv_id=None,  # summarize tidak boleh di-cancel
    #         )
    #     except Exception as e:
    #         summary = f"[Gagal generate summary: {e}]"
    #         importance = "low"
    #
    #     kb_entry = kb_add(
    #         content=summary,
    #         source_conv_id=conv_id,
    #         source_title=conv.get("title", "Unknown"),
    #         importance=importance,
    #     )
    #     print(f"[KB] Saved summary from '{conv.get('title')}' (importance: {importance})")
    # ─────────────────────────────────────────────────────

    trigger_on_close(conv_id)
    delete_conversation(conv_id)

    return {
        "deleted": True,
        "summarized": True,
        "kb_entry": None,
        "reason": "Deleted",
    }
