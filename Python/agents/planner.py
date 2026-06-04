import json
from ollama import chat


# =========================
# CONFIG
# =========================

PLANNER_MODEL = "qwen3:4b"


# =========================
# PLANNER PROMPT
# =========================

PLANNER_PROMPT = """Kamu adalah Planner AI. Tugasmu HANYA membuat rencana langkah-langkah, BUKAN mengerjakan.

Berdasarkan permintaan user, buat daftar langkah (task list) dalam format JSON array.

Setiap langkah harus berisi:
- "step": nomor urut
- "action": nama tool yang akan digunakan
- "params": parameter untuk tool tersebut
- "reason": alasan singkat kenapa langkah ini diperlukan

=== FILE TOOLS ===
- READ_FILE(path) → membaca isi file
- WRITE_FILE(path, content) → menulis file
- LIST_FILES(path) → daftar file dalam direktori
- SEARCH(keyword, path) → cari file yang mengandung keyword
- EXECUTE(path) → jalankan file python
- SUMMARIZE_FILE(path) → ringkasan file
- SUMMARIZE_PROJECT(path) → ringkasan project
- SEMANTIC_SEARCH(query) → cari kode berdasarkan makna
- RESPOND(message) → jawab langsung ke user (tanpa tool)

=== CLICKUP TOOLS ===
- CLICKUP_LIST_SPACES() → lihat semua space di workspace
- CLICKUP_LIST_LISTS(space_id) → lihat list di space
- CLICKUP_LIST_TASKS(list_id) → lihat task di list
- CLICKUP_GET_TASK(task_id) → detail 1 task
- CLICKUP_CREATE_TASK(list_id, name, description, priority) → buat task baru
- CLICKUP_UPDATE_TASK(task_id, status, priority) → update task
- CLICKUP_ADD_COMMENT(task_id, comment) → tambah comment ke task

ATURAN:
- Output HANYA JSON array, tanpa penjelasan lain.
- Untuk tugas coding: analisis dulu → tulis kode → execute → verifikasi.
- Untuk ClickUp: gunakan CLICKUP tools yang sesuai.
- Maksimal 10 langkah.
- Akhiri dengan RESPOND untuk konfirmasi ke user.

Contoh output untuk coding:
[
  {"step": 1, "action": "WRITE_FILE", "params": {"path": "hello.py", "content": "print('Hello World')"}, "reason": "Membuat file"},
  {"step": 2, "action": "EXECUTE", "params": {"path": "hello.py"}, "reason": "Verifikasi"},
  {"step": 3, "action": "RESPOND", "params": {"message": "File berhasil dibuat."}, "reason": "Konfirmasi"}
]

Contoh output untuk ClickUp:
[
  {"step": 1, "action": "CLICKUP_LIST_SPACES", "params": {}, "reason": "Lihat space yang tersedia"},
  {"step": 2, "action": "RESPOND", "params": {"message": "Berikut space di workspace Anda."}, "reason": "Konfirmasi"}
]
"""


def create_plan(user_message, project_index=""):
    """
    Buat rencana langkah-langkah berdasarkan permintaan user.
    Return: (plan, raw)
    """
    context = ""
    if project_index:
        context = f"\n\nKonteks project saat ini:\n{project_index}\n"

    response = chat(
        model=PLANNER_MODEL,
        messages=[
            {"role": "system", "content": PLANNER_PROMPT},
            {"role": "user", "content": f"{user_message}{context}"}
        ]
    )

    raw = response["message"]["content"]
    plan = _extract_json(raw)

    return plan, raw


def _extract_json(text):
    """Ekstrak JSON array dari teks AI."""
    import re

    try:
        result = json.loads(text)
        if isinstance(result, list):
            return result
    except:
        pass

    match = re.search(r'\[[\s\S]*\]', text)
    if match:
        try:
            result = json.loads(match.group())
            if isinstance(result, list):
                return result
        except:
            pass

    match = re.search(r'```(?:json)?\s*([\s\S]*?)```', text)
    if match:
        try:
            result = json.loads(match.group(1).strip())
            if isinstance(result, list):
                return result
        except:
            pass

    return None


def format_plan(plan):
    """Format plan menjadi teks yang readable."""
    if not plan:
        return "Tidak bisa membuat rencana."

    lines = ["📋 RENCANA EKSEKUSI:", ""]
    for task in plan:
        step = task.get("step", "?")
        action = task.get("action", "?")
        params = task.get("params", {})
        reason = task.get("reason", "")

        param_str = ", ".join(f"{k}={repr(v)[:50]}" for k, v in params.items())

        lines.append(f"  {step}. [{action}] {param_str}")
        if reason:
            lines.append(f"     └─ {reason}")

    return "\n".join(lines)
