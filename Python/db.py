"""
db.py — Zegion AI Database Layer
SQLite-based storage untuk conversation history.
Zero dependency: pakai sqlite3 bawaan Python.
"""

import json
import sqlite3
import time
import uuid
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "data", "zegion.db")


# =========================
# CONNECTION
# =========================

def get_connection():
    """Return SQLite connection dengan WAL mode untuk concurrency."""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row  # Akses kolom by name
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


# =========================
# SCHEMA INIT
# =========================

def init_db():
    """Buat tabel jika belum ada. Dipanggil saat startup."""
    conn = get_connection()
    try:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS conversations (
                id          TEXT    PRIMARY KEY,
                title       TEXT    NOT NULL DEFAULT 'New Chat',
                created_at  INTEGER NOT NULL,
                updated_at  INTEGER NOT NULL
            );

            CREATE TABLE IF NOT EXISTS messages (
                id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                conversation_id     TEXT    NOT NULL,
                role                TEXT    NOT NULL,
                content             TEXT    NOT NULL,
                mode                TEXT,
                mode_key            TEXT,
                plan                TEXT    DEFAULT '[]',
                created_at          INTEGER NOT NULL,
                FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_messages_conv
                ON messages(conversation_id, created_at);

            CREATE INDEX IF NOT EXISTS idx_conversations_updated
                ON conversations(updated_at DESC);
        """)
        conn.commit()
    finally:
        conn.close()


# =========================
# CONVERSATION CRUD
# =========================

def create_conversation(title="New Chat"):
    """Buat conversation baru. Return conversation dict."""
    now = int(time.time())
    conv_id = str(uuid.uuid4())

    conn = get_connection()
    try:
        conn.execute(
            "INSERT INTO conversations (id, title, created_at, updated_at) VALUES (?, ?, ?, ?)",
            (conv_id, title, now, now)
        )
        conn.commit()
    finally:
        conn.close()

    return {"id": conv_id, "title": title, "created_at": now, "updated_at": now}


def get_conversation(conv_id):
    """Ambil 1 conversation by ID. Return dict atau None."""
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM conversations WHERE id = ?", (conv_id,)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def list_conversations(limit=50):
    """List semua conversations, diurutkan dari terbaru. Return list of dicts."""
    conn = get_connection()
    try:
        rows = conn.execute(
            """SELECT c.id, c.title, c.created_at, c.updated_at,
                      COUNT(m.id) as message_count
               FROM conversations c
               LEFT JOIN messages m ON m.conversation_id = c.id
               GROUP BY c.id
               ORDER BY c.updated_at DESC
               LIMIT ?""",
            (limit,)
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def update_conversation_title(conv_id, title):
    """Update judul conversation."""
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE conversations SET title = ?, updated_at = ? WHERE id = ?",
            (title[:100], int(time.time()), conv_id)
        )
        conn.commit()
    finally:
        conn.close()


def touch_conversation(conv_id):
    """Update updated_at saat ada pesan baru."""
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE conversations SET updated_at = ? WHERE id = ?",
            (int(time.time()), conv_id)
        )
        conn.commit()
    finally:
        conn.close()


def delete_conversation(conv_id):
    """Hapus conversation dan semua message-nya (CASCADE)."""
    conn = get_connection()
    try:
        conn.execute("DELETE FROM conversations WHERE id = ?", (conv_id,))
        conn.commit()
        return True
    finally:
        conn.close()


# =========================
# MESSAGE CRUD
# =========================

def add_message(conv_id, role, content, mode=None, mode_key=None, plan=None):
    """Tambah 1 pesan ke conversation. Return message dict."""
    now = int(time.time())
    plan_json = json.dumps(plan or [])

    conn = get_connection()
    try:
        cursor = conn.execute(
            """INSERT INTO messages
               (conversation_id, role, content, mode, mode_key, plan, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (conv_id, role, content, mode, mode_key, plan_json, now)
        )
        msg_id = cursor.lastrowid
        conn.commit()
    finally:
        conn.close()

    touch_conversation(conv_id)

    return {
        "id": msg_id,
        "conversation_id": conv_id,
        "role": role,
        "content": content,
        "mode": mode,
        "mode_key": mode_key,
        "plan": plan or [],
        "created_at": now,
    }


def get_messages(conv_id, limit=200):
    """Ambil semua pesan dari 1 conversation. Return list of dicts."""
    conn = get_connection()
    try:
        rows = conn.execute(
            """SELECT id, conversation_id, role, content, mode, mode_key, plan, created_at
               FROM messages
               WHERE conversation_id = ?
               ORDER BY created_at ASC
               LIMIT ?""",
            (conv_id, limit)
        ).fetchall()

        result = []
        for row in rows:
            d = dict(row)
            try:
                d["plan"] = json.loads(d["plan"] or "[]")
            except Exception:
                d["plan"] = []
            result.append(d)

        return result
    finally:
        conn.close()


def get_messages_as_ollama_format(conv_id, limit=50):
    """
    Ambil messages dalam format {role, content} untuk dikirim ke Ollama.
    Hanya ambil N pesan terakhir untuk efisiensi.
    """
    conn = get_connection()
    try:
        rows = conn.execute(
            """SELECT role, content FROM messages
               WHERE conversation_id = ? AND role IN ('user', 'assistant', 'system')
               ORDER BY created_at DESC
               LIMIT ?""",
            (conv_id, limit)
        ).fetchall()

        # Balik urutan (DESC → ASC)
        return [{"role": row["role"], "content": row["content"]} for row in reversed(rows)]
    finally:
        conn.close()


# =========================
# AUTO-TITLE GENERATION
# =========================

def generate_title_from_message(text, max_len=50):
    """
    Buat judul conversation dari pesan pertama user.
    Potong di kata yang wajar, tambahkan ... jika perlu.
    """
    text = text.strip()
    if len(text) <= max_len:
        return text

    # Potong di spasi terakhir sebelum max_len
    truncated = text[:max_len]
    last_space = truncated.rfind(" ")
    if last_space > 20:
        truncated = truncated[:last_space]

    return truncated + "..."


# =========================
# MIGRATION: JSON → SQLite
# =========================

def migrate_from_json(json_path):
    """
    Migrasi data lama dari memory.json ke SQLite.
    Dipanggil sekali jika file JSON lama masih ada.
    """
    if not os.path.exists(json_path):
        return False

    try:
        with open(json_path, "r", encoding="utf-8") as f:
            messages = json.load(f)
    except Exception:
        return False

    # Filter hanya user + assistant (skip system prompt)
    chat_messages = [m for m in messages if m.get("role") in ("user", "assistant")]

    if not chat_messages:
        return False

    # Buat 1 conversation untuk data lama
    conv = create_conversation("Imported History")

    for msg in chat_messages:
        add_message(
            conv_id=conv["id"],
            role=msg["role"],
            content=msg.get("content", ""),
        )

    # Rename file JSON lama agar tidak migrate lagi
    os.rename(json_path, json_path + ".migrated")
    print(f"[DB] Migrated {len(chat_messages)} messages from {json_path}")
    return True
