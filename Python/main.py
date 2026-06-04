import json
import os

from tools import (
    build_project_index,
    build_embeddings,
)

from agents import (
    create_plan,
    format_plan,
    execute_plan,
    generate_response,
    review_results,
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
MAX_RETRIES = 2  # Maksimal retry jika Reviewer reject

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

print("Ketik 'exit' untuk keluar.")
print("Ketik 'resume' untuk lanjutkan task pending.\n")

# =========================
# 4-AGENT PIPELINE
# =========================

def run_pipeline(user_request, plan, task_id):
    """
    Sequential Multi-Agent Pipeline:
    Planner → Executor (AI) → Reviewer (AI) → Responder (AI)
    """
    plan_summary = ", ".join(
        f"{t['action']}({t.get('params', {}).get('path', t.get('params', {}).get('query', ''))})"
        for t in plan if t.get("action", "").upper() != "RESPOND"
    )

    for attempt in range(MAX_RETRIES + 1):

        if attempt > 0:
            print(f"\n🔄 Retry {attempt}/{MAX_RETRIES}...")

        # ── PHASE 2: EXECUTOR (AI Agent) ──────────────────
        print("\n⚡ Executor AI sedang mengerjakan...")
        results, exec_response = execute_plan(plan, task_id=task_id)

        # ── PHASE 3: REVIEWER (AI Agent) ──────────────────
        print("\n🔍 Reviewer sedang mengevaluasi...")
        approved, feedback = review_results(
            user_request, plan_summary, results, exec_response
        )

        if approved:
            print("  ✅ Reviewer: APPROVED!")
            break
        else:
            print(f"  ❌ Reviewer: NEEDS REVISION")
            print(f"  📝 Feedback: {feedback[:200]}")

            if attempt < MAX_RETRIES:
                from agents.planner import create_plan as replan
                revision_prompt = f"{user_request}\n\n[FEEDBACK REVIEWER]: {feedback}"
                plan, _ = replan(revision_prompt, project_index)

                if not plan:
                    break
            else:
                print("  ⚠️ Max retries tercapai, lanjut dengan hasil terakhir.")

    # ── PHASE 4: RESPONDER (AI Agent) ─────────────────
    has_tools = any(r.get("action") not in ("RESPOND", "DONE") for r in results)

    if has_tools:
        final_response = generate_response(user_request, results)
    elif exec_response:
        final_response = exec_response
    else:
        final_response = "Semua langkah selesai."

    # Update task queue
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
            print("\n✅ Tidak ada task yang perlu dilanjutkan.\n")
            continue

        for task in pending:
            task_id = task["id"]
            user_request = task["user_request"]
            remaining = get_remaining_steps(task)

            print(f"\n🔄 Melanjutkan [{task_id}]: {user_request[:50]}...")
            print(f"   Sisa {len(remaining)} langkah\n")

            final_response = run_pipeline(user_request, remaining, task_id)

            messages.append({"role": "user", "content": f"[Resume {task_id}] {user_request}"})
            messages.append({"role": "assistant", "content": final_response})

            print("\n" + "=" * 40)
            print("AI FINAL:")
            print(final_response)
            print("=" * 40 + "\n")

        messages, _ = compress_memory(messages)
        with open(MEMORY_FILE, "w", encoding="utf-8") as f:
            json.dump(messages, f, ensure_ascii=False, indent=2)

        cleanup_completed()
        continue

    # ── NORMAL FLOW ───────────────────────────────────
    messages.append({"role": "user", "content": user})

    # Phase 1: Planner
    print("\n🧠 Planner sedang menganalisis...")
    plan, raw_plan = create_plan(user, project_index)

    if plan:
        print(format_plan(plan))
    else:
        print(f"\n[WARN] Planner gagal membuat rencana.")
        messages.append({"role": "assistant", "content": raw_plan})
        print("\n" + "=" * 40)
        print("AI FINAL:")
        print(raw_plan)
        print("=" * 40 + "\n")
        messages, _ = compress_memory(messages)
        with open(MEMORY_FILE, "w", encoding="utf-8") as f:
            json.dump(messages, f, ensure_ascii=False, indent=2)
        continue

    # Simpan ke Task Queue
    task = create_task(user, plan)
    task_id = task["id"]
    print(f"📌 Task disimpan: {task_id}")

    # Run 4-Agent Pipeline
    final_response = run_pipeline(user, plan, task_id)

    # Simpan ke memory
    plan_summary = ", ".join(
        f"{t['action']}({t.get('params', {}).get('path', t.get('params', {}).get('query', ''))})"
        for t in plan if t.get("action", "").upper() != "RESPOND"
    )
    if plan_summary:
        messages.append({"role": "assistant", "content": f"[Plan: {plan_summary}]\n\n{final_response}"})
    else:
        messages.append({"role": "assistant", "content": final_response})

    # Output
    print("\n" + "=" * 40)
    print("AI FINAL:")
    print(final_response)
    print("=" * 40 + "\n")

    # Save memory
    messages, compressed = compress_memory(messages)
    with open(MEMORY_FILE, "w", encoding="utf-8") as f:
        json.dump(messages, f, ensure_ascii=False, indent=2)

    if compressed:
        print(f"[MEMORY] Memory dikompres → {len(messages)} pesan tersisa")

    cleanup_completed()