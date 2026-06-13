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

=== WEB TOOLS ===
- WEB_SEARCH(query) → cari informasi dari internet jika kamu tidak tahu jawabannya atau butuh data terbaru (harga, berita, error code, dokumentasi, dll)
- FETCH_URL(url) → baca isi halaman web dari URL tertentu (gunakan setelah WEB_SEARCH jika perlu detail lebih lanjut)

=== CLICKUP TOOLS (utama — gunakan ini dulu) ===
- CLICKUP_GET_TASKS() → lihat semua task di workspace
- CLICKUP_GET_TASKS(list_name) → lihat task di list tertentu (by nama)
- CLICKUP_GET_TASKS(status) → filter task by status
- CLICKUP_GET_TASK_DETAIL(task_id) → detail lengkap 1 task
- CLICKUP_CREATE_TASK(list_name, name, description, priority) → buat task (by nama list)
- CLICKUP_UPDATE_TASK(task_id, status, priority) → update task
- CLICKUP_ADD_COMMENT(task_id, comment) → tambah comment

=== CLICKUP LOW-LEVEL (hanya untuk navigasi/eksplorasi) ===
- CLICKUP_LIST_SPACES() → lihat semua space di workspace
- CLICKUP_LIST_LISTS(space_id) → lihat list di space
- CLICKUP_LIST_TASKS(list_id) → lihat task di list (by ID)

ATURAN:
- Output HANYA JSON array, tanpa penjelasan lain.
- Untuk tugas coding: analisis dulu → tulis kode → execute → verifikasi.
- Untuk pertanyaan tentang info terkini / data real-time / error dari internet: gunakan WEB_SEARCH terlebih dulu. Jika perlu membaca detail halaman, lanjutkan dengan FETCH_URL.
- Untuk ClickUp: gunakan tools UTAMA. TIDAK perlu memanggil LIST_SPACES → LIST_LISTS → LIST_TASKS secara manual.
- Maksimal 10 langkah.
- Akhiri dengan RESPOND untuk konfirmasi ke user.

Contoh output untuk "berapa harga bitcoin hari ini":
[
  {"step": 1, "action": "WEB_SEARCH", "params": {"query": "harga bitcoin hari ini"}, "reason": "Cari data harga terkini dari internet"},
  {"step": 2, "action": "RESPOND", "params": {"message": "Berikut informasi harga Bitcoin."}, "reason": "Konfirmasi ke user"}
]

Contoh output untuk "cari solusi error 0x80070005 windows":
[
  {"step": 1, "action": "WEB_SEARCH", "params": {"query": "error code 0x80070005 windows solution"}, "reason": "Cari solusi dari internet"},
  {"step": 2, "action": "RESPOND", "params": {"message": "Berikut solusi yang ditemukan."}, "reason": "Konfirmasi ke user"}
]

Contoh output untuk "lihat task saya":
[
  {"step": 1, "action": "CLICKUP_GET_TASKS", "params": {}, "reason": "Ambil semua task dari workspace"},
  {"step": 2, "action": "RESPOND", "params": {"message": "Berikut task Anda."}, "reason": "Konfirmasi"}
]

Contoh output untuk "buat task Fix Login di list Development":
[
  {"step": 1, "action": "CLICKUP_CREATE_TASK", "params": {"list_name": "Development", "name": "Fix Login", "priority": "high"}, "reason": "Buat task baru"},
  {"step": 2, "action": "RESPOND", "params": {"message": "Task berhasil dibuat."}, "reason": "Konfirmasi"}
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
