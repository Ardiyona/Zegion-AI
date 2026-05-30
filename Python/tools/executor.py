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
from ollama import chat

RESPONDER_MODEL = "qwen3:4b"


def execute_plan(plan):
    """
    Eksekusi setiap langkah dalam plan secara berurutan.

    Return:
    - results: list of (step, action, result) tuples
    - final_response: pesan final untuk user (dari RESPOND action)
    """
    results = []
    final_response = ""

    if not plan:
        return results, "Gagal membuat rencana."

    for task in plan:
        step = task.get("step", "?")
        action = task.get("action", "").upper()
        params = task.get("params", {})

        print(f"\n  ▶ Step {step}: [{action}]")

        result = _execute_step(action, params)

        # Tampilkan hasil singkat
        preview = str(result)[:200]
        print(f"    ✓ {preview}")

        results.append({
            "step": step,
            "action": action,
            "params": params,
            "result": result
        })

        # Jika RESPOND sederhana (tanpa tool lain sebelumnya)
        if action == "RESPOND" and len(results) == 1:
            final_response = params.get("message", result)

        # Jika ada error, stop eksekusi
        if isinstance(result, str) and result.startswith("Error:"):
            print(f"    ✗ Error terdeteksi, menghentikan eksekusi.")
            final_response = f"Terjadi error di step {step}: {result}"
            break

    return results, final_response


def generate_response(user_message, results):
    """
    Phase 3: Responder.
    Generate jawaban final berdasarkan hasil eksekusi yang SEBENARNYA.
    """
    # Kalau hanya RESPOND tanpa tool lain, skip AI call
    if len(results) == 1 and results[0]["action"] == "RESPOND":
        return results[0]["result"]

    # Format hasil eksekusi untuk konteks
    context_parts = []
    for r in results:
        action = r["action"]
        params = r["params"]
        result = str(r["result"])

        if action == "RESPOND":
            continue

        # Batasi panjang result untuk hemat token
        if len(result) > 2000:
            result = result[:2000] + "\n... (terpotong)"

        param_str = ", ".join(f"{k}={v}" for k, v in params.items() if k != "content")
        context_parts.append(f"[{action}({param_str})]:\n{result}")

    context = "\n\n".join(context_parts)

    print("\n  🤖 Generating response...")

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


def _execute_step(action, params):
    """Eksekusi satu langkah berdasarkan action dan params."""

    if action == "READ_FILE":
        path = params.get("path", "")
        return read_file(path)

    elif action == "WRITE_FILE":
        path = params.get("path", "")
        content = params.get("content", "")
        return write_file(path, content)

    elif action == "LIST_FILES":
        path = params.get("path", ".")
        return list_files(path)

    elif action == "SEARCH":
        keyword = params.get("keyword", "")
        path = params.get("path", ".")
        return search_in_files(keyword, path)

    elif action == "EXECUTE":
        path = params.get("path", "")
        return execute_python(path)

    elif action == "SUMMARIZE_FILE":
        path = params.get("path", "")
        return summarize_file(path)

    elif action == "SUMMARIZE_PROJECT":
        path = params.get("path", ".")
        return summarize_project(path)

    elif action == "SEMANTIC_SEARCH":
        query = params.get("query", "")
        return semantic_search(query)

    elif action == "RESPOND":
        return params.get("message", "")

    else:
        return f"Error: Action '{action}' tidak dikenal."
