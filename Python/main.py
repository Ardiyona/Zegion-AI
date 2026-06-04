import json
import os
from ollama import chat

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

MEMORY_FILE = "data/memory.json"
CHAT_MODEL = "qwen3:4b"
MAX_CRITIC_RETRIES = 2
MAX_REFLECT_RETRIES = 1

# =========================
# STARTUP
# =========================

print("Membangun project index...")
project_index = build_project_index(".")
print("Project index siap!")

print("Membangun embeddings...")
embed_result = build_embeddings(".")
print(f"{embed_result}\n")

# =========================
# LOAD MEMORY
# =========================

if os.path.exists(MEMORY_FILE):
    try:
        with open(MEMORY_FILE, "r", encoding="utf-8") as f:
            messages = json.load(f)
    except:
        messages = []
else:
    messages = []

# =========================
# CEK PENDING TASKS
# =========================

pending = get_pending_tasks()
if pending:
    print(format_pending_tasks(pending))
else:
    print("AI Local Siap 😼")

print("Commands: exit | resume | /chat | /quick | /deep\n")

# =========================
# CHAT MODE
# =========================

CHAT_PROMPT = """Kamu adalah AI assistant lokal yang ramah dan helpful.
Jawab dalam bahasa Indonesia dengan jelas dan ringkas."""

def run_chat(user_input, history):
    """
    💬 Chat Mode: Langsung ke model, tanpa Planner/Executor.
    Hanya 1x panggilan AI. Paling cepat.
    """
    print("\n💬 Chat Mode")

    # Bangun pesan dengan sedikit history untuk konteks
    chat_messages = [{"role": "system", "content": CHAT_PROMPT}]

    # Ambil 10 pesan terakhir untuk konteks
    recent = history[-10:] if len(history) > 10 else history
    chat_messages.extend(recent)

    chat_messages.append({"role": "user", "content": user_input})

    response = chat(model=CHAT_MODEL, messages=chat_messages)
    return response["message"]["content"]

# =========================
# QUICK MODE
# =========================

def run_quick(user_request, plan, task_id):
    """
    ⚡ Quick Mode: Planner → Executor → Responder.
    Tanpa Critic/Reflection. 2-3x panggilan AI.
    """
    print("\n⚡ Quick Mode — Executor mengerjakan...")
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

# =========================
# DEEP MODE
# =========================

def run_deep(user_request, plan, task_id):
    """
    🔬 Deep Mode: Planner → Executor → Critic → Reflection → Responder.
    Full pipeline. 5-7x panggilan AI.
    """
    results = []
    exec_response = ""

    # ── EXECUTOR + CRITIC LOOP ────────────────────────
    for attempt in range(MAX_CRITIC_RETRIES + 1):

        if attempt > 0:
            print(f"\n🔄 Critic retry {attempt}/{MAX_CRITIC_RETRIES}...")

        print("\n🔬 Deep Mode — Executor AI mengerjakan...")
        results, exec_response = execute_plan(plan, task_id=task_id)

        print("\n🔎 Critic mengevaluasi...")
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
    print("\n💡 Reflection menganalisis...")
    is_good, suggestions = reflect(user_request, results, exec_response)

    if is_good:
        print("  ✅ Kualitas sudah baik!")
    else:
        print(f"  💡 Saran: {suggestions[:150]}")

        if MAX_REFLECT_RETRIES > 0:
            improve_prompt = f"{user_request}\n\n[REFLECTION]: {suggestions}"
            new_plan, _ = create_plan(improve_prompt, project_index)
            if new_plan:
                print(f"\n⚡ Executor improvement...")
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
# MAIN LOOP
# =========================

while True:

    user = input("You: ")

    if user.lower() == "exit":
        break

    # ── RESUME ────────────────────────────────────────
    if user.lower() == "resume":
        pending = get_pending_tasks()
        if not pending:
            print("\n✅ Tidak ada task pending.\n")
            continue

        for task in pending:
            tid = task["id"]
            req = task["user_request"]
            remaining = get_remaining_steps(task)
            print(f"\n🔄 Resume [{tid}]: {req[:50]}...")
            resp = run_quick(req, remaining, tid)
            messages.append({"role": "user", "content": f"[Resume] {req}"})
            messages.append({"role": "assistant", "content": resp})
            print("\n" + "=" * 40)
            print("AI FINAL:")
            print(resp)
            print("=" * 40 + "\n")

        messages, _ = compress_memory(messages)
        with open(MEMORY_FILE, "w", encoding="utf-8") as f:
            json.dump(messages, f, ensure_ascii=False, indent=2)
        cleanup_completed()
        continue

    # ── DETECT MODE ───────────────────────────────────
    forced_mode, clean_input = parse_override(user)
    auto_mode = detect_mode(clean_input)
    mode = forced_mode if forced_mode else auto_mode

    print(f"\n[{mode_label(mode)}]")

    # ── 💬 CHAT MODE ─────────────────────────────────
    if mode == MODE_CHAT:
        final_response = run_chat(clean_input, messages)

        messages.append({"role": "user", "content": clean_input})
        messages.append({"role": "assistant", "content": final_response})

        print("\n" + "=" * 40)
        print("AI:")
        print(final_response)
        print("=" * 40 + "\n")

        messages, compressed = compress_memory(messages)
        with open(MEMORY_FILE, "w", encoding="utf-8") as f:
            json.dump(messages, f, ensure_ascii=False, indent=2)
        continue

    # ── ⚡/🔬 AGENT MODE (QUICK/DEEP) ────────────────
    messages.append({"role": "user", "content": clean_input})

    # Phase 1: Planner
    print("🧠 Planner menganalisis...")
    plan, raw_plan = create_plan(clean_input, project_index)

    if plan:
        print(format_plan(plan))
    else:
        print("[WARN] Planner gagal.")
        messages.append({"role": "assistant", "content": raw_plan})
        print("\n" + "=" * 40)
        print("AI FINAL:")
        print(raw_plan)
        print("=" * 40 + "\n")
        messages, _ = compress_memory(messages)
        with open(MEMORY_FILE, "w", encoding="utf-8") as f:
            json.dump(messages, f, ensure_ascii=False, indent=2)
        continue

    # Task Queue
    task = create_task(clean_input, plan)
    task_id = task["id"]
    print(f"📌 Task: {task_id}")

    # Run pipeline berdasarkan mode
    if mode == MODE_DEEP:
        final_response = run_deep(clean_input, plan, task_id)
    else:
        final_response = run_quick(clean_input, plan, task_id)

    # Simpan ke memory
    plan_summary = ", ".join(
        f"{t['action']}({t.get('params', {}).get('path', t.get('params', {}).get('query', ''))})"
        for t in plan if t.get("action", "").upper() != "RESPOND"
    )
    tag = f"[{mode.upper()}]"
    if plan_summary:
        messages.append({"role": "assistant", "content": f"{tag} [Plan: {plan_summary}]\n\n{final_response}"})
    else:
        messages.append({"role": "assistant", "content": final_response})

    print("\n" + "=" * 40)
    print("AI FINAL:")
    print(final_response)
    print("=" * 40 + "\n")

    messages, compressed = compress_memory(messages)
    with open(MEMORY_FILE, "w", encoding="utf-8") as f:
        json.dump(messages, f, ensure_ascii=False, indent=2)

    if compressed:
        print(f"[MEMORY] Dikompres → {len(messages)} pesan")

    cleanup_completed()