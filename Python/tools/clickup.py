import time
import requests
from config import CLICKUP_API_KEY, CLICKUP_WORKSPACE_ID, CLICKUP_CACHE_TTL


# =========================
# CONFIG
# =========================

BASE_URL = "https://api.clickup.com/api/v2"
HEADERS = {
    "Authorization": CLICKUP_API_KEY,
    "Content-Type": "application/json",
}


# =========================
# VALIDATION & HTTP
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


# =========================================================
# WORKSPACE STRUCTURE CACHE
# Hanya cache Space, Folder, List (jarang berubah).
# Task SELALU diambil realtime dari API.
# =========================================================

_cache = {
    "spaces": [],
    "lists": [],
    "last_fetched": 0,
    "ttl": CLICKUP_CACHE_TTL,
}


def _is_cache_valid():
    """Cek apakah cache masih fresh."""
    return (
        _cache["last_fetched"] > 0
        and (time.time() - _cache["last_fetched"]) < _cache["ttl"]
        and len(_cache["spaces"]) > 0
    )


def _refresh_cache():
    """Fetch ulang semua spaces & lists dari API, simpan ke cache."""
    # Fetch spaces
    data = _safe_request("GET", f"{BASE_URL}/team/{CLICKUP_WORKSPACE_ID}/space")
    if isinstance(data, str):
        return data

    spaces = data.get("spaces", [])
    _cache["spaces"] = spaces

    # Fetch semua lists dari semua spaces
    all_lists = []
    for space in spaces:
        # Folderless lists
        list_data = _safe_request("GET", f"{BASE_URL}/space/{space['id']}/list")
        if isinstance(list_data, dict):
            for lst in list_data.get("lists", []):
                lst["_space_id"] = space["id"]
                lst["_space_name"] = space["name"]
                lst["_folder"] = "—"
                all_lists.append(lst)

        # Lists inside folders
        folder_data = _safe_request("GET", f"{BASE_URL}/space/{space['id']}/folder")
        if isinstance(folder_data, dict):
            for folder in folder_data.get("folders", []):
                for lst in folder.get("lists", []):
                    lst["_space_id"] = space["id"]
                    lst["_space_name"] = space["name"]
                    lst["_folder"] = folder["name"]
                    all_lists.append(lst)

    _cache["lists"] = all_lists
    _cache["last_fetched"] = time.time()

    return None  # No error


def _invalidate_cache():
    """Paksa refresh cache di panggilan berikutnya."""
    _cache["last_fetched"] = 0


# =========================================================
# INTERNAL HELPERS (menggunakan cache)
# =========================================================

def _get_all_spaces():
    """Return list of space dicts (dari cache jika masih valid)."""
    if not _is_cache_valid():
        err = _refresh_cache()
        if err:
            return err
    return _cache["spaces"]


def _get_all_lists(space_id):
    """Return semua list dari 1 space (dari cache)."""
    if not _is_cache_valid():
        err = _refresh_cache()
        if err:
            return err
    return [l for l in _cache["lists"] if l.get("_space_id") == space_id]


def _get_all_lists_in_workspace():
    """Return semua list dari SEMUA space (dari cache)."""
    if not _is_cache_valid():
        err = _refresh_cache()
        if err:
            return err
    return _cache["lists"]


def _find_list_by_name(list_name):
    """Cari list berdasarkan nama (case-insensitive). Return list dict atau error."""
    all_lists = _get_all_lists_in_workspace()
    if isinstance(all_lists, str):
        return all_lists

    # Exact match dulu
    for lst in all_lists:
        if lst["name"].lower() == list_name.lower():
            return lst

    # Partial match
    for lst in all_lists:
        if list_name.lower() in lst["name"].lower():
            return lst

    names = ", ".join(f"'{l['name']}'" for l in all_lists[:10])
    return f"Error: List '{list_name}' tidak ditemukan. List yang tersedia: {names}"


# =========================================================
# LOW-LEVEL TOOLS (navigasi eksplisit, untuk kasus kompleks)
# =========================================================

def clickup_list_spaces():
    """[LOW-LEVEL] Lihat semua Space di workspace."""
    err = _validate()
    if err:
        return err

    spaces = _get_all_spaces()
    if isinstance(spaces, str):
        return spaces
    if not spaces:
        return "Tidak ada Space ditemukan di workspace ini."

    lines = [f"📂 {len(spaces)} Space ditemukan:\n"]
    for s in spaces:
        lines.append(f"  • {s['name']} (ID: {s['id']})")

    return "\n".join(lines)


def clickup_list_lists(space_id):
    """[LOW-LEVEL] Lihat semua List di sebuah Space."""
    err = _validate()
    if err:
        return err

    lists = _get_all_lists(space_id)
    if isinstance(lists, str):
        return lists
    if not lists:
        return "Tidak ada List ditemukan di Space ini."

    lines = [f"📋 {len(lists)} List ditemukan:\n"]
    for l in lists:
        folder = l.get("_folder", "—")
        task_count = l.get("task_count", "?")
        lines.append(f"  • {l['name']} (ID: {l['id']}) | Folder: {folder} | Tasks: {task_count}")

    return "\n".join(lines)


def clickup_list_tasks(list_id):
    """[LOW-LEVEL] Lihat task di sebuah List (by ID)."""
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

    return _format_task_list(tasks)


# =========================================================
# HIGH-LEVEL TOOLS (intent-based, Planner cukup panggil 1x)
# =========================================================

def clickup_get_tasks(list_name=None, status=None):
    """
    [HIGH-LEVEL] Lihat semua task.
    - Tanpa parameter → semua task di semua list
    - list_name → filter by nama list (auto-resolve ID)
    - status → filter by status (e.g. "open", "in progress")
    """
    err = _validate()
    if err:
        return err

    if list_name:
        # Cari list by nama
        lst = _find_list_by_name(list_name)
        if isinstance(lst, str):
            return lst

        data = _safe_request("GET", f"{BASE_URL}/list/{lst['id']}/task", params={
            "subtasks": "true",
            "include_closed": "true",
        })
        if isinstance(data, str):
            return data

        tasks = data.get("tasks", [])
        source = f"List '{lst['name']}'"
    else:
        # Ambil dari SEMUA list
        all_lists = _get_all_lists_in_workspace()
        if isinstance(all_lists, str):
            return all_lists

        tasks = []
        for lst in all_lists:
            data = _safe_request("GET", f"{BASE_URL}/list/{lst['id']}/task", params={
                "subtasks": "true",
                "include_closed": "true",
            })
            if isinstance(data, dict):
                for t in data.get("tasks", []):
                    t["_list_name"] = lst["name"]
                    tasks.append(t)
        source = "seluruh workspace"

    # Filter by status
    if status and tasks:
        tasks = [
            t for t in tasks
            if t.get("status", {}).get("status", "").lower() == status.lower()
        ]

    if not tasks:
        return f"Tidak ada task ditemukan di {source}."

    return _format_task_list(tasks, show_list=not list_name)


def clickup_get_task_detail(task_id):
    """[HIGH-LEVEL] Lihat detail lengkap 1 task."""
    err = _validate()
    if err:
        return err

    data = _safe_request("GET", f"{BASE_URL}/task/{task_id}")
    if isinstance(data, str):
        return data

    # Validasi workspace
    if str(data.get("team_id", "")) != str(CLICKUP_WORKSPACE_ID):
        return "Error: Task ini bukan milik workspace yang dikonfigurasi."

    status = data.get("status", {}).get("status", "?")
    priority = data.get("priority", {})
    priority_name = priority.get("priority", "none") if priority else "none"
    assignees = ", ".join(a.get("username", "?") for a in data.get("assignees", []))
    description = data.get("description", "Tidak ada deskripsi.")
    due_date = data.get("due_date", None)
    tags = ", ".join(t.get("name", "") for t in data.get("tags", []))
    list_info = data.get("list", {}).get("name", "?")

    lines = [
        f"📌 {data['name']}",
        f"   ID: {data['id']}",
        f"   List: {list_info}",
        f"   Status: {status}",
        f"   Priority: {priority_name}",
        f"   Assignee: {assignees or '—'}",
        f"   Due: {due_date or '—'}",
        f"   Tags: {tags or '—'}",
        f"   Deskripsi: {description[:500]}",
    ]

    return "\n".join(lines)


def clickup_smart_create_task(name, list_name, description="", priority=None):
    """
    [HIGH-LEVEL] Buat task baru — cari list otomatis by nama.
    Tidak perlu tahu list_id.
    """
    err = _validate()
    if err:
        return err

    # Resolve list_name → list_id
    lst = _find_list_by_name(list_name)
    if isinstance(lst, str):
        return lst

    payload = {
        "name": name,
        "description": description,
    }

    if priority:
        priority_map = {"urgent": 1, "high": 2, "normal": 3, "low": 4}
        payload["priority"] = priority_map.get(priority.lower(), 3)

    data = _safe_request("POST", f"{BASE_URL}/list/{lst['id']}/task", json=payload)
    if isinstance(data, str):
        return data

    return f"✅ Task '{data.get('name', name)}' berhasil dibuat di list '{lst['name']}'! (ID: {data.get('id', '?')})"


def clickup_smart_update_task(task_id, status=None, priority=None, name=None):
    """[HIGH-LEVEL] Update task. Validasi workspace otomatis."""
    err = _validate()
    if err:
        return err

    # Validasi workspace
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


def clickup_smart_add_comment(task_id, comment_text):
    """[HIGH-LEVEL] Tambah comment. Validasi workspace otomatis."""
    err = _validate()
    if err:
        return err

    # Validasi workspace
    task_data = _safe_request("GET", f"{BASE_URL}/task/{task_id}")
    if isinstance(task_data, str):
        return task_data
    if str(task_data.get("team_id", "")) != str(CLICKUP_WORKSPACE_ID):
        return "Error: Task ini bukan milik workspace yang dikonfigurasi."

    data = _safe_request("POST", f"{BASE_URL}/task/{task_id}/comment", json={
        "comment_text": comment_text,
    })
    if isinstance(data, str):
        return data

    return f"💬 Comment berhasil ditambahkan ke task {task_id}!"


# =========================================================
# FORMATTING HELPERS
# =========================================================

def _format_task_list(tasks, show_list=False):
    """Format daftar task menjadi teks readable."""
    lines = [f"📝 {len(tasks)} task ditemukan:\n"]
    for t in tasks:
        status = t.get("status", {}).get("status", "?")
        priority = t.get("priority", {})
        priority_name = priority.get("priority", "none") if priority else "none"
        assignees = ", ".join(a.get("username", "?") for a in t.get("assignees", []))

        lines.append(f"  • [{status.upper()}] {t['name']}")
        info = f"    ID: {t['id']} | Priority: {priority_name} | Assignee: {assignees or '—'}"
        if show_list:
            list_name = t.get("_list_name", t.get("list", {}).get("name", "?"))
            info += f" | List: {list_name}"
        lines.append(info)

    return "\n".join(lines)
