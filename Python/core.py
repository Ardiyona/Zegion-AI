"""
core.py — Zegion AI Core Logic
Berisi semua pipeline logic, bisa dipanggil dari terminal (main.py) maupun API (api.py).
"""

import json
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


# =========================
# STARTUP (dijalankan sekali)
# =========================

def initialize():
    """
    Inisialisasi Zegion: build index, embeddings, load memory.
    Return: (project_index, messages)
    """
    print(f"\n🤖 {AGENT_NAME} v{AGENT_VERSION} memulai...\n")

    print("Membangun project index...")
    project_index = build_project_index(".")
    print("Project index siap!")

    print("Membangun embeddings...")
    embed_result = build_embeddings(".")
    print(f"{embed_result}\n")

    # Load memory
    messages = _load_memory()

    return project_index, messages


def _load_memory():
    """Load memory dari file JSON."""
    if os.path.exists(MEMORY_FILE):
        try:
            with open(MEMORY_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []
    return []

# Public alias untuk diimport api.py
load_memory = _load_memory


def _save_memory(messages):
    """Simpan memory ke file JSON."""
    os.makedirs(os.path.dirname(MEMORY_FILE), exist_ok=True)
    with open(MEMORY_FILE, "w", encoding="utf-8") as f:
        json.dump(messages, f, ensure_ascii=False, indent=2)


# =========================
# PIPELINE MODES
# =========================

def run_chat(user_input, history):
    """
    💬 Chat Mode: Langsung ke model, tanpa Planner/Executor.
    1x AI call. Paling cepat.
    """
    chat_messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    recent = history[-10:] if len(history) > 10 else history
    chat_messages.extend(recent)
    chat_messages.append({"role": "user", "content": user_input})

    response = chat(model=DEFAULT_MODEL, messages=chat_messages)
    return response["message"]["content"]


def run_quick(user_request, plan, task_id, project_index=""):
    """
    ⚡ Quick Mode: Planner → Executor → Responder.
    Tanpa Critic/Reflection.
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
    🔬 Deep Mode: Planner → Executor → Critic → Reflection → Responder.
    Full pipeline.
    """
    results = []
    exec_response = ""

    # ── EXECUTOR + CRITIC LOOP ────────────────────────
    for attempt in range(MAX_CRITIC_RETRIES + 1):
        if attempt > 0:
            print(f"\n🔄 Critic retry {attempt}/{MAX_CRITIC_RETRIES}...")

        results, exec_response = execute_plan(plan, task_id=task_id)
        passed, critic_feedback = critique(user_request, results, exec_response)

        if passed:
            print("  ✅ Critic: PASS!")
            break
        else:
            print(f"  ❌ Critic: FAIL — {critic_feedback[:150]}")
            if attempt < MAX_CRITIC_RETRIES:
                fix_prompt = f"{user_request}\n\n[CRITIC FEEDBACK]: {critic_feedback}"
                new_plan, _ = create_plan(fix_prompt, project_index)
                if new_plan:
                    plan = new_plan
                else:
                    break
            else:
                print("  ⚠️ Max retries tercapai.")

    # ── REFLECTION ────────────────────────────────────
    is_good, suggestions = reflect(user_request, results, exec_response)

    if is_good:
        print("  ✅ Kualitas sudah baik!")
    else:
        print(f"  💡 Saran: {suggestions[:150]}")
        if MAX_REFLECT_RETRIES > 0:
            improve_prompt = f"{user_request}\n\n[REFLECTION]: {suggestions}"
            new_plan, _ = create_plan(improve_prompt, project_index)
            if new_plan:
                results, exec_response = execute_plan(new_plan, task_id=task_id)

    # ── RESPONDER ─────────────────────────────────────
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
# Dipanggil oleh terminal (main.py) dan API (api.py)
# =========================

def handle_message(user_input, messages, project_index=""):
    """
    Handle 1 pesan user — routing ke mode yang tepat.

    Return:
        response (str): jawaban Zegion
        messages (list): memory yang sudah diupdate
        mode (str): mode yang dipakai
        plan (list): plan jika ada
    """
    # ── RESUME ────────────────────────────────────────
    if user_input.strip().lower() == "resume":
        pending = get_pending_tasks()
        if not pending:
            return "Tidak ada task pending.", messages, "chat", []

        responses = []
        for task in pending:
            tid = task["id"]
            req = task["user_request"]
            remaining = get_remaining_steps(task)
            resp = run_quick(req, remaining, tid, project_index)
            messages.append({"role": "user", "content": f"[Resume] {req}"})
            messages.append({"role": "assistant", "content": resp})
            responses.append(resp)

        messages, _ = compress_memory(messages)
        _save_memory(messages)
        cleanup_completed()
        return "\n---\n".join(responses), messages, "resume", []

    # ── DETECT MODE ───────────────────────────────────
    forced_mode, clean_input = parse_override(user_input)
    auto_mode = detect_mode(clean_input)
    mode = forced_mode if forced_mode else auto_mode

    plan = []

    # ── 💬 CHAT MODE ─────────────────────────────────
    if mode == MODE_CHAT:
        final_response = run_chat(clean_input, messages)
        messages.append({"role": "user", "content": clean_input})
        messages.append({"role": "assistant", "content": final_response})
        messages, _ = compress_memory(messages)
        _save_memory(messages)
        return final_response, messages, mode, plan

    # ── ⚡/🔬 AGENT MODE ──────────────────────────────
    messages.append({"role": "user", "content": clean_input})

    plan_result, raw_plan = create_plan(clean_input, project_index)

    if not plan_result:
        messages.append({"role": "assistant", "content": raw_plan})
        messages, _ = compress_memory(messages)
        _save_memory(messages)
        return raw_plan, messages, mode, []

    plan = plan_result
    task = create_task(clean_input, plan)
    task_id = task["id"]

    if mode == MODE_DEEP:
        final_response = run_deep(clean_input, plan, task_id, project_index)
    else:
        final_response = run_quick(clean_input, plan, task_id, project_index)

    # Simpan ke memory dengan tag mode
    plan_summary = ", ".join(
        f"{t['action']}({t.get('params', {}).get('path', t.get('params', {}).get('query', ''))})"
        for t in plan if t.get("action", "").upper() != "RESPOND"
    )
    tag = f"[{mode.upper()}]"
    if plan_summary:
        messages.append({"role": "assistant", "content": f"{tag} [Plan: {plan_summary}]\n\n{final_response}"})
    else:
        messages.append({"role": "assistant", "content": final_response})

    messages, compressed = compress_memory(messages)
    _save_memory(messages)

    if compressed:
        print(f"[MEMORY] Dikompres → {len(messages)} pesan")

    cleanup_completed()
    return final_response, messages, mode, plan
