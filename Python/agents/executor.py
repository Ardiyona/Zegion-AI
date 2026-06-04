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


# =========================
# CONFIG
# =========================

EXECUTOR_MODEL = "qwen3:4b"
RESPONDER_MODEL = "qwen3:4b"
MAX_EXECUTOR_STEPS = 10

EXECUTOR_PROMPT = """Kamu adalah Executor AI. Tugasmu MENGERJAKAN rencana yang diberikan.

Kamu punya tools berikut. WAJIB gunakan format PERSIS:

1. [READ_FILE path="file.py"]
2. [WRITE_FILE path="file.py"]
isi file
[/WRITE_FILE]
3. [LIST_FILES path="."]
4. [SEARCH keyword="kata" path="."]
5. [EXECUTE path="file.py"]
6. [SUMMARIZE_FILE path="file.py"]
7. [SEMANTIC_SEARCH query="deskripsi"]

ATURAN:
- Lakukan SATU tool per respons.
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
