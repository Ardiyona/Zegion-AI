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

print("AI Local Siap 😼")
print("Ketik 'exit' untuk keluar.\n")

# =========================
# MAIN LOOP
# =========================

while True:

    user = input("You: ")

    if user.lower() == "exit":
        break

    # Simpan user message ke memory
    messages.append({
        "role": "user",
        "content": user
    })

    # =========================
    # PHASE 1: PLANNER
    # =========================

    print("\n🧠 Planner sedang menganalisis...")

    plan, raw_plan = create_plan(user, project_index)

    if plan:
        print(format_plan(plan))
    else:
        print(f"\n[WARN] Planner gagal membuat rencana.")
        print(f"[DEBUG] Raw output:\n{raw_plan}\n")

        # Fallback: langsung respond
        messages.append({
            "role": "assistant",
            "content": raw_plan
        })

        print("\n" + "=" * 40)
        print("AI FINAL:")
        print(raw_plan)
        print("=" * 40 + "\n")

        # Save memory
        messages, compressed = compress_memory(messages)
        with open(MEMORY_FILE, "w", encoding="utf-8") as f:
            json.dump(messages, f, ensure_ascii=False, indent=2)
        continue

    # =========================
    # PHASE 2: EXECUTOR
    # =========================

    print("\n⚡ Executor sedang mengerjakan...\n")

    results, final_response = execute_plan(plan)

    # =========================
    # PHASE 3: RESPONDER
    # =========================

    # Jika ada tool yang dipakai (bukan hanya RESPOND),
    # gunakan AI untuk generate jawaban dari hasil aktual
    has_tools = any(r["action"] != "RESPOND" for r in results)

    if has_tools and not final_response:
        final_response = generate_response(user, results)
    elif has_tools and final_response:
        # Ada final_response dari executor tapi mungkin kurang lengkap
        final_response = generate_response(user, results)

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

    # =========================
    # OUTPUT
    # =========================

    print("\n" + "=" * 40)
    print("AI FINAL:")
    print(final_response)
    print("=" * 40 + "\n")

    # =========================
    # SAVE MEMORY
    # =========================

    messages, compressed = compress_memory(messages)

    with open(MEMORY_FILE, "w", encoding="utf-8") as f:
        json.dump(messages, f, ensure_ascii=False, indent=2)

    if compressed:
        print(f"[MEMORY] Memory dikompres → {len(messages)} pesan tersisa")