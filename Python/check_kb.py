from db import get_connection, kb_list
conn = get_connection()
tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
print("Tables:", tables)
print("KB entries:", conn.execute("SELECT COUNT(*) FROM knowledge_base").fetchone()[0])
conn.close()
