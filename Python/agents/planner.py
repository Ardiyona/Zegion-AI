import re
import json
import time
from ollama import chat
from config import DEFAULT_MODEL


# =========================
# PLANNER BASE PROMPT
# Tool definitions + rules only — no examples
# =========================

PLANNER_BASE = """Kamu adalah Planner AI. Tugasmu HANYA membuat rencana langkah-langkah, BUKAN mengerjakan.

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
- WEB_SEARCH(query) → HANYA untuk data eksternal real-time: harga saham/kripto, berita terkini, cuaca, error code dari internet, dokumentasi library, versi terbaru software. JANGAN gunakan untuk pertanyaan percakapan, identitas, opini, atau hal yang bisa dijawab langsung.
- FETCH_URL(url) → baca isi halaman web dari URL tertentu (gunakan setelah WEB_SEARCH jika perlu detail lebih lanjut)

=== CLICKUP TOOLS (utama — gunakan ini dulu) ===
- CLICKUP_GET_TASKS() → lihat semua task di workspace
- CLICKUP_GET_TASKS(list_name) → lihat task di list tertentu (by nama)
- CLICKUP_GET_TASKS(status) → filter task by status
- CLICKUP_GET_TASK_DETAIL(task_id) → detail lengkap 1 task
- CLICKUP_CREATE_TASK(list_name, name, description, priority) → buat task (by nama list)
- CLICKUP_UPDATE_TASK(task_id, status, priority, name, description) → update task
- CLICKUP_ADD_COMMENT(task_id, comment) → tambah comment

=== CLICKUP LOW-LEVEL (hanya untuk navigasi/eksplorasi) ===
- CLICKUP_LIST_SPACES() → lihat semua space di workspace
- CLICKUP_LIST_LISTS(space_id) → lihat list di space
- CLICKUP_LIST_TASKS(list_id) → lihat task di list (by ID)

ATURAN:
- Output HANYA JSON array, tanpa penjelasan lain.
- Untuk tugas coding: analisis dulu → tulis kode → execute → verifikasi.
- Untuk pertanyaan percakapan, identitas, status, opini, atau penjelasan konsep: gunakan RESPOND langsung, JANGAN WEB_SEARCH.
- Untuk pertanyaan tentang info terkini / data real-time / error dari internet: gunakan WEB_SEARCH terlebih dulu. Jika perlu membaca detail halaman, lanjutkan dengan FETCH_URL.
- Untuk ClickUp: gunakan tools UTAMA. TIDAK perlu memanggil LIST_SPACES → LIST_LISTS → LIST_TASKS secara manual.
- Nilai params description/name/comment harus COPY PERSIS dari teks user. JANGAN parafrase atau terjemahkan.
- Maksimal 10 langkah.
- Akhiri dengan RESPOND untuk konfirmasi ke user."""


# =========================
# INTENT EXAMPLES
# 1-2 focused few-shot examples per intent
# Injected only when intent is detected — keeps prompt short for small models
# =========================

INTENT_EXAMPLES = {
    "clickup_update": """\
Contoh output untuk "isi deskripsi task id abc123 menjadi 'Refactor auth module'":
[
  {"step": 1, "action": "CLICKUP_UPDATE_TASK", "params": {"task_id": "abc123", "description": "Refactor auth module"}, "reason": "Update deskripsi task"},
  {"step": 2, "action": "RESPOND", "params": {"message": "Deskripsi task berhasil diperbarui."}, "reason": "Konfirmasi"}
]

Contoh output untuk "ubah status task 86xyz99 menjadi done":
[
  {"step": 1, "action": "CLICKUP_UPDATE_TASK", "params": {"task_id": "86xyz99", "status": "done"}, "reason": "Update status task"},
  {"step": 2, "action": "RESPOND", "params": {"message": "Status task berhasil diubah."}, "reason": "Konfirmasi"}
]""",

    "clickup_comment": """\
Contoh output untuk "tambah komentar di task 86abc12: sudah selesai review":
[
  {"step": 1, "action": "CLICKUP_ADD_COMMENT", "params": {"task_id": "86abc12", "comment": "sudah selesai review"}, "reason": "Tambah komentar pada task"},
  {"step": 2, "action": "RESPOND", "params": {"message": "Komentar berhasil ditambahkan."}, "reason": "Konfirmasi"}
]""",

    "clickup_create": """\
Contoh output untuk "buat task Fix Login di list Development":
[
  {"step": 1, "action": "CLICKUP_CREATE_TASK", "params": {"list_name": "Development", "name": "Fix Login", "priority": "high"}, "reason": "Buat task baru"},
  {"step": 2, "action": "RESPOND", "params": {"message": "Task berhasil dibuat."}, "reason": "Konfirmasi"}
]""",

    "clickup_detail": """\
Contoh output untuk "lihat detail task 86abc12":
[
  {"step": 1, "action": "CLICKUP_GET_TASK_DETAIL", "params": {"task_id": "86abc12"}, "reason": "Ambil detail lengkap task"},
  {"step": 2, "action": "RESPOND", "params": {"message": "Berikut detail task."}, "reason": "Konfirmasi"}
]""",

    "clickup_get": """\
Contoh output untuk "lihat task saya":
[
  {"step": 1, "action": "CLICKUP_GET_TASKS", "params": {}, "reason": "Ambil semua task dari workspace"},
  {"step": 2, "action": "RESPOND", "params": {"message": "Berikut task Anda."}, "reason": "Konfirmasi"}
]""",

    "web_search": """\
Contoh output untuk "berapa harga bitcoin hari ini":
[
  {"step": 1, "action": "WEB_SEARCH", "params": {"query": "harga bitcoin hari ini"}, "reason": "Cari data harga terkini dari internet"},
  {"step": 2, "action": "RESPOND", "params": {"message": "Berikut informasi harga Bitcoin."}, "reason": "Konfirmasi ke user"}
]

Contoh output untuk "cari solusi error 0x80070005 windows":
[
  {"step": 1, "action": "WEB_SEARCH", "params": {"query": "error code 0x80070005 windows solution"}, "reason": "Cari solusi dari internet"},
  {"step": 2, "action": "RESPOND", "params": {"message": "Berikut solusi yang ditemukan."}, "reason": "Konfirmasi ke user"}
]""",
}

_ALL_EXAMPLES = "\n\n".join(INTENT_EXAMPLES.values())


# =========================
# INTENT PATTERNS
# Ordered most-specific first to avoid false positives
# verb + entity must BOTH match
# =========================

INTENT_PATTERNS = [
    {
        "intent": "clickup_update",
        "verbs":    ["ubah", "update", "isi", "ganti", "edit", "set", "rename", "tandai", "selesaikan", "complete", "finish", "tambah", "tambahkan", "add"],
        "entities": ["task", "deskripsi", "status", "prioritas", "nama", "judul", "title", "selesai", "done"],
    },
    # comment before create — both share verb "tambah"; entity "komentar/comment" is unambiguous
    {
        "intent": "clickup_comment",
        "verbs":    ["tambah", "tulis", "kirim", "add"],
        "entities": ["komentar", "comment"],
    },
    {
        "intent": "clickup_create",
        "verbs":    ["buat", "tambah", "bikin", "create", "add"],
        "entities": ["task"],
    },
    # detail before get — "lihat detail task" must match detail, not get
    {
        "intent": "clickup_detail",
        "verbs":    ["lihat", "cek", "tampilkan", "info", "detail", "show"],
        "entities": ["detail"],
    },
    {
        "intent": "clickup_get",
        "verbs":    ["lihat", "tampilkan", "list", "cek", "ambil", "show", "get"],
        "entities": ["task"],
    },
    {
        "intent": "web_search",
        "verbs":    ["cari", "carikan", "search", "cek"],
        "entities": ["harga", "berita", "cuaca", "error", "dokumentasi", "versi", "terbaru", "hari ini"],
    },
]


def _detect_intent(user_message):
    msg = user_message.lower()
    for pattern in INTENT_PATTERNS:
        verb_hit   = any(v in msg for v in pattern["verbs"])
        entity_hit = any(e in msg for e in pattern["entities"])
        if verb_hit and entity_hit:
            return pattern["intent"]
    return None


def build_prompt(user_message):
    intent = _detect_intent(user_message)
    examples = INTENT_EXAMPLES.get(intent, _ALL_EXAMPLES) if intent else _ALL_EXAMPLES
    return f"{PLANNER_BASE}\n\n{examples}", intent


# =========================
# PLAN CREATION
# =========================


def create_plan(user_message, project_index="", model=None):
    """
    Buat rencana langkah-langkah berdasarkan permintaan user.
    Return: (plan, raw)
    """
    plan_model = model or DEFAULT_MODEL
    context = ""
    if project_index:
        context = f"\n\nKonteks project saat ini:\n{project_index}\n"

    system_prompt, intent = build_prompt(user_message)

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": f"{user_message}{context}"}
    ]

    prompt_chars = sum(len(m["content"]) for m in messages)

    start = time.time()
    response = chat(
        model=plan_model,
        messages=messages
    )
    elapsed = time.time() - start

    raw = response["message"]["content"]
    plan = _extract_json(raw)

    # Telemetry
    p_eval_count = response.get("prompt_eval_count", 0)
    eval_count = response.get("eval_count", 0)
    p_eval_s = response.get("prompt_eval_duration", 0) / 1e9
    gen_s = response.get("eval_duration", 0) / 1e9
    tps = eval_count / gen_s if gen_s > 0 else 0

    print(f"\n  [PLANNER]")
    print(f"  Intent: {intent or 'fallback'}")
    print(f"  Model: {plan_model}")
    print(f"  Prompt chars: {prompt_chars:,}")
    print(f"  Prompt tokens: {p_eval_count:,}")
    print(f"  Output tokens: {eval_count:,}")
    print(f"  Prompt eval: {p_eval_s:.1f}s")
    print(f"  Generation: {gen_s:.1f}s")
    print(f"  Total: {elapsed:.1f}s")
    if tps > 0:
        print(f"  TPS: {tps:.2f}")
    print()

    return plan, raw


def _extract_json(text):
    """Ekstrak JSON array dari teks AI."""
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
