import re
from ollama import chat
from tools.file_ops import (
    read_file,
    write_file,
    list_files,
    search_in_files,
    execute_python,
)
from tools.summarizer import (
    summarize_file,
    summarize_project,
)
from tools.semantic import (
    semantic_search,
)
from tools.clickup import (
    # Low-level
    clickup_list_spaces,
    clickup_list_lists,
    clickup_list_tasks,
    # High-level
    clickup_get_tasks,
    clickup_get_task_detail,
    clickup_smart_create_task,
    clickup_smart_update_task,
    clickup_smart_add_comment,
)


# =========================
# CONFIG
# =========================

EXECUTOR_MODEL = "qwen3:4b"
RESPONDER_MODEL = "qwen3:4b"
MAX_EXECUTOR_STEPS = 10

EXECUTOR_PROMPT = """Kamu adalah Executor AI. Tugasmu MENGERJAKAN rencana yang diberikan.

Kamu punya tools berikut. WAJIB gunakan format PERSIS:

=== FILE TOOLS ===
1. [READ_FILE path="file.py"]
2. [WRITE_FILE path="file.py"]
isi file
[/WRITE_FILE]
3. [LIST_FILES path="."]
4. [SEARCH keyword="kata" path="."]
5. [EXECUTE path="file.py"]
6. [SUMMARIZE_FILE path="file.py"]
7. [SEMANTIC_SEARCH query="deskripsi"]

=== CLICKUP TOOLS (utama) ===
8. [CLICKUP_GET_TASKS] → semua task di workspace
9. [CLICKUP_GET_TASKS list_name="nama list"] → task di list tertentu
10. [CLICKUP_GET_TASKS status="open"] → filter by status
11. [CLICKUP_GET_TASK_DETAIL task_id="id"] → detail 1 task
12. [CLICKUP_CREATE_TASK list_name="nama list" name="nama task" description="desc" priority="normal"]
13. [CLICKUP_UPDATE_TASK task_id="id" status="done" priority="high"]
14. [CLICKUP_ADD_COMMENT task_id="id" comment="teks"]

=== CLICKUP LOW-LEVEL (untuk navigasi) ===
15. [CLICKUP_LIST_SPACES]
16. [CLICKUP_LIST_LISTS space_id="id"]
17. [CLICKUP_LIST_TASKS list_id="id"]

ATURAN:
- Lakukan SATU tool per respons.
- Gunakan CLICKUP tools utama (8-14) untuk operasi ClickUp. Low-level (15-17) hanya jika perlu navigasi detail.
- Jika hasil EXECUTE menunjukkan error, PERBAIKI file lalu EXECUTE lagi.
- Jika semua langkah selesai, tulis [DONE] diikuti ringkasan hasil.
- Jika tidak perlu tool, langsung tulis [DONE] diikuti jawaban.
"""


# =========================
# TOOL HANDLERS
# =========================

def _handle_tools(ai_response):
    """
    Parse response AI dan jalankan tool jika ada.
    Return: (tool_used, tool_name, tool_target, result)
    """

    # READ FILE
    m = re.search(r'\[READ_FILE path="(.*?)"\]', ai_response)
    if m:
        path = m.group(1)
        result = read_file(path)
        return True, "READ_FILE", path, f"Isi file {path}:\n\n{result}"

    # LIST FILES
    m = re.search(r'\[LIST_FILES path="(.*?)"\]', ai_response)
    if m:
        path = m.group(1)
        result = list_files(path)
        return True, "LIST_FILES", path, f"Struktur file:\n\n{result[:5000]}"

    # SEARCH
    m = re.search(r'\[SEARCH keyword="(.*?)" path="(.*?)"\]', ai_response)
    if m:
        keyword, path = m.group(1), m.group(2)
        result = search_in_files(keyword, path)
        return True, "SEARCH", keyword, f"Hasil pencarian '{keyword}':\n\n{result}"

    # SEMANTIC SEARCH
    m = re.search(r'\[SEMANTIC_SEARCH query="(.*?)"\]', ai_response)
    if m:
        query = m.group(1)
        result = semantic_search(query)
        return True, "SEMANTIC_SEARCH", query, f"Hasil semantic search:\n\n{result}"

    # EXECUTE
    m = re.search(r'\[EXECUTE path="(.*?)"\]', ai_response)
    if m:
        path = m.group(1)
        result = execute_python(path)
        return True, "EXECUTE", path, f"Hasil eksekusi {path}:\n\n{result}"

    # SUMMARIZE FILE
    m = re.search(r'\[SUMMARIZE_FILE path="(.*?)"\]', ai_response)
    if m:
        path = m.group(1)
        result = summarize_file(path)
        return True, "SUMMARIZE_FILE", path, f"Summary {path}:\n\n{result}"

    # WRITE FILE (block format)
    write_matches = re.findall(
        r'\[WRITE_FILE path="(.*?)"\](.*?)\[/WRITE_FILE\]',
        ai_response, re.DOTALL
    )
    if write_matches:
        results = []
        for path, content in write_matches:
            content = content.strip()
            r = write_file(path, content)
            results.append(f"{path}: {r}")
        return True, "WRITE_FILE", write_matches[0][0], "\n".join(results)

    # WRITE FILE (inline format)
    m = re.search(r'\[WRITE_FILE path="(.*?)" content="(.*?)"\]', ai_response, re.DOTALL)
    if m:
        path = m.group(1)
        content = m.group(2).replace("\\n", "\n").replace('\\"', '"')
        result = write_file(path, content)
        return True, "WRITE_FILE", path, result

    # =========================
    # CLICKUP HIGH-LEVEL TOOLS
    # =========================

    # CLICKUP GET TASKS (high-level — auto-resolve)
    m = re.search(r'\[CLICKUP_GET_TASKS(?:\s+list_name="(.*?)")?(?:\s+status="(.*?)")?\]', ai_response)
    if m:
        list_name = m.group(1)
        status = m.group(2)
        result = clickup_get_tasks(list_name=list_name, status=status)
        label = list_name or status or "all"
        return True, "CLICKUP_GET_TASKS", label, result

    # CLICKUP GET TASK DETAIL (high-level)
    m = re.search(r'\[CLICKUP_GET_TASK_DETAIL task_id="(.*?)"\]', ai_response)
    if m:
        task_id = m.group(1)
        result = clickup_get_task_detail(task_id)
        return True, "CLICKUP_GET_TASK_DETAIL", task_id, result

    # CLICKUP CREATE TASK (high-level — by list name)
    m = re.search(r'\[CLICKUP_CREATE_TASK list_name="(.*?)" name="(.*?)"(?:\s+description="(.*?)")?(?:\s+priority="(.*?)")?\]', ai_response)
    if m:
        list_name = m.group(1)
        name = m.group(2)
        desc = m.group(3) or ""
        priority = m.group(4)
        result = clickup_smart_create_task(name, list_name, desc, priority=priority)
        return True, "CLICKUP_CREATE_TASK", name, result

    # CLICKUP UPDATE TASK (high-level)
    m = re.search(r'\[CLICKUP_UPDATE_TASK task_id="(.*?)"(?:\s+status="(.*?)")?(?:\s+priority="(.*?)")?(?:\s+name="(.*?)")?\]', ai_response)
    if m:
        task_id = m.group(1)
        status = m.group(2)
        priority = m.group(3)
        name = m.group(4)
        result = clickup_smart_update_task(task_id, status=status, priority=priority, name=name)
        return True, "CLICKUP_UPDATE_TASK", task_id, result

    # CLICKUP ADD COMMENT (high-level)
    m = re.search(r'\[CLICKUP_ADD_COMMENT task_id="(.*?)" comment="(.*?)"\]', ai_response, re.DOTALL)
    if m:
        task_id = m.group(1)
        comment = m.group(2)
        result = clickup_smart_add_comment(task_id, comment)
        return True, "CLICKUP_ADD_COMMENT", task_id, result

    # =========================
    # CLICKUP LOW-LEVEL TOOLS (navigasi)
    # =========================

    # CLICKUP LIST SPACES
    if '[CLICKUP_LIST_SPACES]' in ai_response:
        result = clickup_list_spaces()
        return True, "CLICKUP_LIST_SPACES", "spaces", result

    # CLICKUP LIST LISTS
    m = re.search(r'\[CLICKUP_LIST_LISTS space_id="(.*?)"\]', ai_response)
    if m:
        space_id = m.group(1)
        result = clickup_list_lists(space_id)
        return True, "CLICKUP_LIST_LISTS", space_id, result

    # CLICKUP LIST TASKS (low-level by ID)
    m = re.search(r'\[CLICKUP_LIST_TASKS list_id="(.*?)"\]', ai_response)
    if m:
        list_id = m.group(1)
        result = clickup_list_tasks(list_id)
        return True, "CLICKUP_LIST_TASKS", list_id, result

    return False, None, None, None


# =========================
# EXECUTOR AGENT
# =========================

def execute_plan(plan, task_id=None):
    """
    Executor AI Agent — mengerjakan plan dengan kemampuan berpikir.
    Bisa adaptasi, retry error, dan ambil keputusan sendiri.
    """
    from agents.task_queue import update_task_step

    # Format plan sebagai instruksi
    plan_text = "\n".join(
        f"{t.get('step', i+1)}. {t.get('action', '?')}: {t.get('reason', '')} "
        f"(params: {t.get('params', {})})"
        for i, t in enumerate(plan)
    )

    # Cek apakah ini plan sederhana (RESPOND saja)
    if len(plan) == 1 and plan[0].get("action", "").upper() == "RESPOND":
        msg = plan[0].get("params", {}).get("message", "")
        return [{"step": 1, "action": "RESPOND", "result": msg}], msg

    # Build executor messages
    exec_messages = [
        {"role": "system", "content": EXECUTOR_PROMPT},
        {"role": "user", "content": f"Rencana yang harus dikerjakan:\n{plan_text}\n\nMulai kerjakan dari langkah pertama."}
    ]

    results = []
    final_response = ""

    for step in range(MAX_EXECUTOR_STEPS):

        # Call AI
        response = chat(model=EXECUTOR_MODEL, messages=exec_messages)
        ai = response["message"]["content"]

        print(f"\n  🤖 Executor (step {step + 1}):")

        # Cek apakah sudah selesai
        if "[DONE]" in ai:
            done_idx = ai.index("[DONE]")
            final_response = ai[done_idx + 6:].strip()
            print(f"    ✅ DONE: {final_response[:150]}...")

            if task_id:
                update_task_step(task_id, step, {
                    "step": step + 1,
                    "action": "DONE",
                    "result": final_response
                })
            break

        # Coba handle tools
        tool_used, tool_name, tool_target, tool_result = _handle_tools(ai)

        if tool_used:
            print(f"    🔧 [{tool_name}] → {tool_target}")
            preview = str(tool_result)[:150]
            print(f"    📄 {preview}...")

            results.append({
                "step": step + 1,
                "action": tool_name,
                "target": tool_target,
                "result": tool_result
            })

            if task_id:
                update_task_step(task_id, step, results[-1])

            exec_messages.append({"role": "assistant", "content": ai})
            exec_messages.append({"role": "user", "content": tool_result})
        else:
            print(f"    💭 {ai[:150]}...")
            exec_messages.append({"role": "assistant", "content": ai})
            exec_messages.append({"role": "user", "content": "Lanjutkan. Gunakan tool yang sesuai atau tulis [DONE] jika sudah selesai."})

    return results, final_response


# =========================
# RESPONDER
# =========================

def generate_response(user_message, results):
    """
    Phase 4: Responder.
    Generate jawaban final berdasarkan hasil eksekusi yang SEBENARNYA.
    """
    if not results:
        return "Semua langkah selesai."

    if len(results) == 1 and results[0].get("action") == "RESPOND":
        return results[0]["result"]

    # Format hasil eksekusi untuk konteks
    context_parts = []
    for r in results:
        action = r.get("action", "?")
        result = str(r.get("result", ""))

        if action in ("RESPOND", "DONE"):
            continue

        if len(result) > 2000:
            result = result[:2000] + "\n... (terpotong)"

        target = r.get("target", "")
        context_parts.append(f"[{action}({target})]:\n{result}")

    if not context_parts:
        return results[-1].get("result", "Selesai.")

    context = "\n\n".join(context_parts)

    print("\n  🤖 Responder generating answer...")

    response = chat(
        model=RESPONDER_MODEL,
        messages=[
            {
                "role": "system",
                "content": "Kamu adalah AI assistant. Berdasarkan hasil tool yang sudah dijalankan, jawab pertanyaan user secara lengkap dan jelas. Jawab dalam bahasa Indonesia."
            },
            {
                "role": "user",
                "content": f"Pertanyaan user: {user_message}\n\nHasil eksekusi:\n{context}\n\nBerikan jawaban lengkap berdasarkan hasil di atas."
            }
        ]
    )

    return response["message"]["content"]
