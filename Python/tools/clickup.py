import requests
from config import CLICKUP_API_KEY, CLICKUP_WORKSPACE_ID


# =========================
# CONFIG
# =========================

BASE_URL = "https://api.clickup.com/api/v2"
HEADERS = {
    "Authorization": CLICKUP_API_KEY,
    "Content-Type": "application/json",
}


# =========================
# VALIDATION
# =========================

def _validate():
    """Validasi API key dan workspace ID sudah diset."""
    if not CLICKUP_API_KEY:
        return "Error: CLICKUP_API_KEY belum diset di .env"
    if not CLICKUP_WORKSPACE_ID:
        return "Error: CLICKUP_WORKSPACE_ID belum diset di .env"
    return None


def _safe_request(method, url, **kwargs):
    """Wrapper request dengan error handling."""
    try:
        resp = requests.request(method, url, headers=HEADERS, timeout=15, **kwargs)

        if resp.status_code == 429:
            return "Error: Rate limit tercapai. Coba lagi nanti."
        if resp.status_code == 401:
            return "Error: API key tidak valid."
        if resp.status_code == 403:
            return "Error: Akses ditolak. Cek permission API key."
        if resp.status_code >= 400:
            return f"Error: HTTP {resp.status_code} — {resp.text[:200]}"

        return resp.json()
    except requests.exceptions.Timeout:
        return "Error: Request timeout. Cek koneksi internet."
    except requests.exceptions.ConnectionError:
        return "Error: Tidak bisa terhubung ke ClickUp API."
    except Exception as e:
        return f"Error: {str(e)}"


# =========================
# CLICKUP TOOLS
# =========================

def clickup_list_spaces():
    """Lihat semua Space di workspace yang dikonfigurasi."""
    err = _validate()
    if err:
        return err

    data = _safe_request("GET", f"{BASE_URL}/team/{CLICKUP_WORKSPACE_ID}/space")

    if isinstance(data, str):  # Error string
        return data

    spaces = data.get("spaces", [])
    if not spaces:
        return "Tidak ada Space ditemukan di workspace ini."

    lines = [f"📂 {len(spaces)} Space ditemukan:\n"]
    for s in spaces:
        lines.append(f"  • {s['name']} (ID: {s['id']})")

    return "\n".join(lines)


def clickup_list_lists(space_id):
    """Lihat semua List di sebuah Space."""
    err = _validate()
    if err:
        return err

    # Ambil folderless lists
    data = _safe_request("GET", f"{BASE_URL}/space/{space_id}/list")

    if isinstance(data, str):
        return data

    lists = data.get("lists", [])

    # Juga ambil lists di dalam folders
    folder_data = _safe_request("GET", f"{BASE_URL}/space/{space_id}/folder")
    if isinstance(folder_data, dict):
        for folder in folder_data.get("folders", []):
            for lst in folder.get("lists", []):
                lst["_folder"] = folder["name"]
                lists.append(lst)

    if not lists:
        return "Tidak ada List ditemukan di Space ini."

    lines = [f"📋 {len(lists)} List ditemukan:\n"]
    for l in lists:
        folder = l.get("_folder", "—")
        task_count = l.get("task_count", "?")
        lines.append(f"  • {l['name']} (ID: {l['id']}) | Folder: {folder} | Tasks: {task_count}")

    return "\n".join(lines)


def clickup_list_tasks(list_id):
    """Lihat task di sebuah List."""
    err = _validate()
    if err:
        return err

    data = _safe_request("GET", f"{BASE_URL}/list/{list_id}/task", params={
        "subtasks": "true",
        "include_closed": "true",
    })

    if isinstance(data, str):
        return data

    tasks = data.get("tasks", [])
    if not tasks:
        return "Tidak ada task di List ini."

    lines = [f"📝 {len(tasks)} task ditemukan:\n"]
    for t in tasks:
        status = t.get("status", {}).get("status", "?")
        priority = t.get("priority", {})
        priority_name = priority.get("priority", "none") if priority else "none"
        assignees = ", ".join(a.get("username", "?") for a in t.get("assignees", []))

        lines.append(f"  • [{status.upper()}] {t['name']}")
        lines.append(f"    ID: {t['id']} | Priority: {priority_name} | Assignee: {assignees or '—'}")

    return "\n".join(lines)


def clickup_get_task(task_id):
    """Lihat detail 1 task."""
    err = _validate()
    if err:
        return err

    data = _safe_request("GET", f"{BASE_URL}/task/{task_id}")

    if isinstance(data, str):
        return data

    # Validasi workspace — pastikan task milik workspace yang benar
    team_id = data.get("team_id", "")
    if str(team_id) != str(CLICKUP_WORKSPACE_ID):
        return "Error: Task ini bukan milik workspace yang dikonfigurasi."

    status = data.get("status", {}).get("status", "?")
    priority = data.get("priority", {})
    priority_name = priority.get("priority", "none") if priority else "none"
    assignees = ", ".join(a.get("username", "?") for a in data.get("assignees", []))
    description = data.get("description", "Tidak ada deskripsi.")
    due_date = data.get("due_date", None)
    tags = ", ".join(t.get("name", "") for t in data.get("tags", []))

    lines = [
        f"📌 {data['name']}",
        f"   ID: {data['id']}",
        f"   Status: {status}",
        f"   Priority: {priority_name}",
        f"   Assignee: {assignees or '—'}",
        f"   Due: {due_date or '—'}",
        f"   Tags: {tags or '—'}",
        f"   Deskripsi: {description[:500]}",
    ]

    return "\n".join(lines)


def clickup_create_task(list_id, name, description="", status=None, priority=None):
    """Buat task baru di List tertentu."""
    err = _validate()
    if err:
        return err

    payload = {
        "name": name,
        "description": description,
    }

    if status:
        payload["status"] = status
    if priority:
        # ClickUp priority: 1=urgent, 2=high, 3=normal, 4=low
        priority_map = {
            "urgent": 1, "high": 2, "normal": 3, "low": 4
        }
        payload["priority"] = priority_map.get(priority.lower(), 3)

    data = _safe_request("POST", f"{BASE_URL}/list/{list_id}/task", json=payload)

    if isinstance(data, str):
        return data

    return f"✅ Task '{data.get('name', name)}' berhasil dibuat! (ID: {data.get('id', '?')})"


def clickup_update_task(task_id, status=None, priority=None, name=None):
    """Update task yang sudah ada."""
    err = _validate()
    if err:
        return err

    # Validasi workspace dulu
    task_data = _safe_request("GET", f"{BASE_URL}/task/{task_id}")
    if isinstance(task_data, str):
        return task_data
    if str(task_data.get("team_id", "")) != str(CLICKUP_WORKSPACE_ID):
        return "Error: Task ini bukan milik workspace yang dikonfigurasi."

    payload = {}
    if status:
        payload["status"] = status
    if priority:
        priority_map = {"urgent": 1, "high": 2, "normal": 3, "low": 4}
        payload["priority"] = priority_map.get(priority.lower(), 3)
    if name:
        payload["name"] = name

    if not payload:
        return "Error: Tidak ada yang diupdate. Berikan status, priority, atau name."

    data = _safe_request("PUT", f"{BASE_URL}/task/{task_id}", json=payload)

    if isinstance(data, str):
        return data

    return f"✅ Task '{data.get('name', task_id)}' berhasil diupdate!"


def clickup_add_comment(task_id, comment_text):
    """Tambah comment ke task."""
    err = _validate()
    if err:
        return err

    # Validasi workspace
    task_data = _safe_request("GET", f"{BASE_URL}/task/{task_id}")
    if isinstance(task_data, str):
        return task_data
    if str(task_data.get("team_id", "")) != str(CLICKUP_WORKSPACE_ID):
        return "Error: Task ini bukan milik workspace yang dikonfigurasi."

    payload = {
        "comment_text": comment_text,
    }

    data = _safe_request("POST", f"{BASE_URL}/task/{task_id}/comment", json=payload)

    if isinstance(data, str):
        return data

    return f"💬 Comment berhasil ditambahkan ke task {task_id}!"
