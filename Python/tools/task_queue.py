import json
import os
from datetime import datetime


# =========================
# CONFIG
# =========================

QUEUE_FILE = "task_queue.json"


# =========================
# TASK STATUS
# =========================

STATUS_PENDING = "pending"
STATUS_IN_PROGRESS = "in_progress"
STATUS_COMPLETED = "completed"
STATUS_FAILED = "failed"


# =========================
# QUEUE MANAGEMENT
# =========================

def load_queue():
    """Load task queue dari file."""
    if os.path.exists(QUEUE_FILE):
        try:
            with open(QUEUE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            return []
    return []


def save_queue(queue):
    """Simpan task queue ke file."""
    with open(QUEUE_FILE, "w", encoding="utf-8") as f:
        json.dump(queue, f, ensure_ascii=False, indent=2)


def create_task(user_request, plan):
    """
    Buat task baru dan tambahkan ke queue.
    Return: task dict
    """
    queue = load_queue()

    task = {
        "id": f"task_{len(queue) + 1:03d}",
        "user_request": user_request,
        "created_at": datetime.now().isoformat(),
        "status": STATUS_PENDING,
        "plan": plan,
        "current_step": 0,
        "results": [],
        "final_response": ""
    }

    queue.append(task)
    save_queue(queue)

    return task


def update_task_step(task_id, step_index, result):
    """Update hasil step tertentu dalam task."""
    queue = load_queue()

    for task in queue:
        if task["id"] == task_id:
            task["current_step"] = step_index + 1
            task["results"].append(result)
            task["status"] = STATUS_IN_PROGRESS
            break

    save_queue(queue)


def complete_task(task_id, final_response):
    """Tandai task sebagai selesai."""
    queue = load_queue()

    for task in queue:
        if task["id"] == task_id:
            task["status"] = STATUS_COMPLETED
            task["final_response"] = final_response
            break

    save_queue(queue)


def fail_task(task_id, error_message):
    """Tandai task sebagai gagal."""
    queue = load_queue()

    for task in queue:
        if task["id"] == task_id:
            task["status"] = STATUS_FAILED
            task["final_response"] = f"Error: {error_message}"
            break

    save_queue(queue)


def get_pending_tasks():
    """Ambil semua task yang belum selesai (pending atau in_progress)."""
    queue = load_queue()
    return [
        t for t in queue
        if t["status"] in (STATUS_PENDING, STATUS_IN_PROGRESS)
    ]


def get_remaining_steps(task):
    """Ambil langkah-langkah yang belum dieksekusi dari task."""
    current = task.get("current_step", 0)
    plan = task.get("plan", [])
    return plan[current:]


def format_pending_tasks(tasks):
    """Format daftar pending tasks untuk ditampilkan."""
    if not tasks:
        return None

    lines = [f"📌 Ada {len(tasks)} task yang belum selesai:", ""]

    for t in tasks:
        status_icon = "🔄" if t["status"] == STATUS_IN_PROGRESS else "⏳"
        total = len(t["plan"])
        done = t["current_step"]

        lines.append(f"  {status_icon} [{t['id']}] {t['user_request'][:60]}")
        lines.append(f"     Progress: {done}/{total} langkah | Status: {t['status']}")

    lines.append("")
    lines.append("Ketik 'resume' untuk lanjutkan, atau ketik perintah baru.")

    return "\n".join(lines)


def cleanup_completed(keep=10):
    """Hapus task completed yang lama, simpan N terbaru."""
    queue = load_queue()

    # Pisahkan: yang belum selesai + N completed terbaru
    pending = [t for t in queue if t["status"] in (STATUS_PENDING, STATUS_IN_PROGRESS)]
    completed = [t for t in queue if t["status"] in (STATUS_COMPLETED, STATUS_FAILED)]

    # Keep N terbaru dari completed
    kept = completed[-keep:] if len(completed) > keep else completed

    save_queue(pending + kept)
