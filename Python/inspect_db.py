"""Script untuk lihat isi database Zegion."""
from db import get_connection

conn = get_connection()

print("=== CONVERSATIONS ===")
rows = conn.execute("""
    SELECT c.id, c.title, COUNT(m.id) as msg_count
    FROM conversations c
    LEFT JOIN messages m ON m.conversation_id = c.id
    GROUP BY c.id
    ORDER BY c.updated_at DESC
""").fetchall()

for row in rows:
    print(f"  [{row['id'][:8]}...] {row['title']!r} - {row['msg_count']} pesan")

print()
total_conv = conn.execute("SELECT COUNT(*) FROM conversations").fetchone()[0]
total_msg  = conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
print(f"Total: {total_conv} conversations, {total_msg} messages")
print(f"File DB: data/zegion.db")
conn.close()
