import json
import os

from tools import (
    build_project_index,
    build_embeddings,
    compress_memory,
    create_plan,
    format_plan,
    execute_plan,
    generate_response,
    create_task,
    complete_task,
    fail_task,
    get_pending_tasks,
    get_remaining_steps,
    format_pending_tasks,
    cleanup_completed,
)

MEMORY_FILE = "memory.json"

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

print("Ketik 'exit' untuk keluar.\n")

# =========================
# HELPER: EXECUTE & RESPOND
# =========================

def run_task(user_request, plan, task_id):
    """Jalankan plan dan generate response."""

    # Phase 2: Executor
    print("\n⚡ Executor sedang mengerjakan...\n")
    results, final_response = execute_plan(plan, task_id=task_id)

    # Phase 3: Responder
    has_tools = any(r["action"] != "RESPOND" for r in results)

    if has_tools:
        final_response = generate_response(user_request, results)

    # Cek error
    has_error = any(
        isinstance(r["result"], str) and r["result"].startswith("Error:")
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

    # =========================
    # RESUME PENDING TASKS
    # =========================

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

            final_response = run_task(user_request, remaining, task_id)

            # Simpan ke memory
            messages.append({
                "role": "user",
                "content": f"[Resume {task_id}] {user_request}"
            })
            messages.append({
                "role": "assistant",
                "content": final_response
            })

            print("\n" + "=" * 40)
            print("AI FINAL:")
            print(final_response)
            print("=" * 40 + "\n")

        # Save memory
        messages, compressed = compress_memory(messages)
        with open(MEMORY_FILE, "w", encoding="utf-8") as f:
            json.dump(messages, f, ensure_ascii=False, indent=2)

        cleanup_completed()
        continue

    # =========================
    # NORMAL FLOW
    # =========================

    # Simpan user message ke memory
    messages.append({
        "role": "user",
        "content": user
    })

    # Phase 1: Planner
    print("\n🧠 Planner sedang menganalisis...")

    plan, raw_plan = create_plan(user, project_index)

    if plan:
        print(format_plan(plan))
    else:
        print(f"\n[WARN] Planner gagal membuat rencana.")
        print(f"[DEBUG] Raw output:\n{raw_plan}\n")

        messages.append({
            "role": "assistant",
            "content": raw_plan
        })

        print("\n" + "=" * 40)
        print("AI FINAL:")
        print(raw_plan)
        print("=" * 40 + "\n")

        messages, compressed = compress_memory(messages)
        with open(MEMORY_FILE, "w", encoding="utf-8") as f:
            json.dump(messages, f, ensure_ascii=False, indent=2)
        continue

    # Simpan ke Task Queue
    task = create_task(user, plan)
    task_id = task["id"]
    print(f"\n📌 Task disimpan: {task_id}")

    # Execute
    final_response = run_task(user, plan, task_id)

    # Simpan ke memory
    plan_summary = ", ".join(
        f"{t['action']}({t.get('params', {}).get('path', t.get('params', {}).get('query', ''))})"
        for t in plan if t["action"] != "RESPOND"
    )

    if plan_summary:
        messages.append({
            "role": "assistant",
            "content": f"[Plan: {plan_summary}]\n\n{final_response}"
        })
    else:
        messages.append({
            "role": "assistant",
            "content": final_response
        })

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

    # Cleanup old tasks
    cleanup_completed()