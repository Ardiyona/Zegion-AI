"""
core.py — Zegion AI Core Logic
Pipeline logic yang bisa dipanggil dari terminal (main.py) maupun API (api.py).
Storage: SQLite via db.py
"""

import os
from ollama import chat

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
)


# =========================
# STARTUP
# =========================

def initialize():
    """
    Inisialisasi Zegion: init DB, migrate data lama, build index & embeddings.
    Return: project_index (str)
    """
    print(f"\n{AGENT_NAME} v{AGENT_VERSION} memulai...\n")

    # Init SQLite DB
    init_db()
    print("[DB] Database ready.")

    # Migrasi data JSON lama jika ada
    if os.path.exists(MEMORY_FILE):
        migrated = migrate_from_json(MEMORY_FILE)
        if migrated:
            print("[DB] Migrasi memory.json selesai.")

    # Build project index & embeddings
    print("Membangun project index...")
    project_index = build_project_index(".")
    print("Project index siap!")

    print("Membangun embeddings...")
    embed_result = build_embeddings(".")
    print(f"{embed_result}\n")

    return project_index


# Public alias untuk startup ringan di api.py (tanpa Ollama)
def quick_init():
    """Startup cepat: hanya init DB dan migrasi. Tanpa Ollama."""
    init_db()
    if os.path.exists(MEMORY_FILE):
        migrate_from_json(MEMORY_FILE)


# =========================
# OLLAMA HISTORY BUILDER
# =========================

def _build_ollama_history(conv_id, limit=20):
    """
    Ambil pesan terakhir dari DB dan format untuk Ollama.
    System prompt selalu di depan.
    """
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    history = get_messages_as_ollama_format(conv_id, limit=limit)
    messages.extend(history)
    return messages


# =========================
# PIPELINE MODES
# =========================

def run_chat(user_input, conv_id):
    """
    Chat Mode: Langsung ke model, tanpa Planner/Executor.
    """
    chat_messages = _build_ollama_history(conv_id, limit=20)
    chat_messages.append({"role": "user", "content": user_input})

    response = chat(model=DEFAULT_MODEL, messages=chat_messages)
    return response["message"]["content"]


def run_quick(user_request, plan, task_id, project_index=""):
    """
    Quick Mode: Planner → Executor → Responder.
    """
    results, exec_response = execute_plan(plan, task_id=task_id)

    has_tools = any(r.get("action") not in ("RESPOND", "DONE") for r in results)

    if has_tools:
        final_response = generate_response(user_request, results)
    elif exec_response:
        final_response = exec_response
    else:
        final_response = "Selesai."

    complete_task(task_id, final_response)
    return final_response


def run_deep(user_request, plan, task_id, project_index=""):
    """
    Deep Mode: Planner → Executor → Critic → Reflection → Responder.
    """
    results = []
    exec_response = ""

    for attempt in range(MAX_CRITIC_RETRIES + 1):
        if attempt > 0:
            print(f"\nCritic retry {attempt}/{MAX_CRITIC_RETRIES}...")

        results, exec_response = execute_plan(plan, task_id=task_id)
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
                results, exec_response = execute_plan(new_plan, task_id=task_id)

    has_tools = any(r.get("action") not in ("RESPOND", "DONE") for r in results)

    if has_tools:
        final_response = generate_response(user_request, results)
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

def handle_message(user_input, conv_id, project_index=""):
    """
    Handle 1 pesan user — routing ke mode yang tepat.
    Simpan user + assistant message ke DB.

    Return:
        response   (str)
        conv_id    (str)   — sama atau baru jika conv_id kosong
        mode       (str)
        plan       (list)
    """
    # Buat conversation baru jika belum ada
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

    plan = []

    # Simpan pesan user ke DB
    add_message(conv_id, "user", clean_input)

    # Auto-set title dari pesan pertama user
    conv = get_conversation(conv_id)
    if conv and conv["title"] == "New Chat":
        title = generate_title_from_message(clean_input)
        update_conversation_title(conv_id, title)

    # ── CHAT MODE ─────────────────────────────────────
    if mode == MODE_CHAT:
        # Hapus pesan user yang baru saja ditambah dari history
        # agar tidak double — run_chat akan query ulang dari DB
        final_response = run_chat(clean_input, conv_id)
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

    if mode == MODE_DEEP:
        final_response = run_deep(clean_input, plan, task_id, project_index)
    else:
        final_response = run_quick(clean_input, plan, task_id, project_index)

    # Simpan response ke DB dengan metadata mode & plan
    mode_name = mode_label(mode)
    add_message(
        conv_id, "assistant", final_response,
        mode=mode_name, mode_key=mode, plan=plan
    )

    cleanup_completed()
    return final_response, conv_id, mode, plan
