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

Berdasarkan permintaan user, buat daftar langkah (task list) dalam format JSON.

Setiap langkah harus berisi:
- "step": nomor urut
- "action": nama tool yang akan digunakan
- "params": parameter untuk tool tersebut
- "reason": alasan singkat kenapa langkah ini diperlukan

Tools yang tersedia:
- READ_FILE(path) → membaca isi file
- WRITE_FILE(path, content) → menulis file
- LIST_FILES(path) → daftar file dalam direktori
- SEARCH(keyword, path) → cari file yang mengandung keyword
- EXECUTE(path) → jalankan file python
- SUMMARIZE_FILE(path) → ringkasan file
- SUMMARIZE_PROJECT(path) → ringkasan project
- SEMANTIC_SEARCH(query) → cari kode berdasarkan makna
- RESPOND(message) → jawab langsung ke user (tanpa tool)

ATURAN:
- Output HANYA JSON array, tanpa penjelasan lain.
- Jika pertanyaan sederhana (sapaan, tanya info), gunakan RESPOND saja.
- Untuk tugas coding: analisis dulu → tulis kode → execute → verifikasi.
- Maksimal 10 langkah.

Contoh output untuk "buatkan file hello.py yang print hello world":
[
  {"step": 1, "action": "WRITE_FILE", "params": {"path": "hello.py", "content": "print('Hello World')"}, "reason": "Membuat file sesuai permintaan"},
  {"step": 2, "action": "EXECUTE", "params": {"path": "hello.py"}, "reason": "Verifikasi file berjalan"},
  {"step": 3, "action": "RESPOND", "params": {"message": "File hello.py berhasil dibuat dan dijalankan."}, "reason": "Konfirmasi ke user"}
]

Contoh output untuk "halo":
[
  {"step": 1, "action": "RESPOND", "params": {"message": "Halo! Ada yang bisa saya bantu?"}, "reason": "Sapaan sederhana"}
]
"""


def create_plan(user_message, project_index=""):
    """
    Buat rencana langkah-langkah berdasarkan permintaan user.
    Return: list of task dicts, atau None jika gagal parse.
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

    # Parse JSON dari response
    plan = _extract_json(raw)

    return plan, raw


def _extract_json(text):
    """Ekstrak JSON array dari teks AI (yang mungkin mengandung markdown dll)."""
    import re

    # Coba parse langsung
    try:
        return json.loads(text)
    except:
        pass

    # Coba cari JSON array dalam teks
    match = re.search(r'\[[\s\S]*\]', text)
    if match:
        try:
            return json.loads(match.group())
        except:
            pass

    # Coba bersihkan markdown code block
    match = re.search(r'```(?:json)?\s*([\s\S]*?)```', text)
    if match:
        try:
            return json.loads(match.group(1).strip())
        except:
            pass

    return None


def format_plan(plan):
    """Format plan menjadi teks yang readable untuk ditampilkan."""
    if not plan:
        return "Tidak bisa membuat rencana."

    lines = ["📋 RENCANA EKSEKUSI:", ""]
    for task in plan:
        step = task.get("step", "?")
        action = task.get("action", "?")
        params = task.get("params", {})
        reason = task.get("reason", "")

        # Format params singkat
        param_str = ", ".join(f"{k}={repr(v)[:50]}" for k, v in params.items())

        lines.append(f"  {step}. [{action}] {param_str}")
        if reason:
            lines.append(f"     └─ {reason}")

    return "\n".join(lines)
