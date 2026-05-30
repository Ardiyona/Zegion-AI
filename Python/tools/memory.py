from ollama import chat

# =========================
# CONFIG
# =========================

# Compress jika jumlah pesan melebihi threshold
COMPRESS_THRESHOLD = 50

# Jumlah pesan terbaru yang dipertahankan
KEEP_RECENT = 20

# Model untuk membuat summary
SUMMARY_MODEL = "qwen3:4b"


# =========================
# MEMORY COMPRESSION
# =========================

def compress_memory(messages):
    """
    Kompres memory jika terlalu banyak pesan.

    Strategi:
    1. Simpan system prompt (messages[0])
    2. Summary pesan lama menjadi 1 pesan ringkasan
    3. Pertahankan N pesan terbaru

    Return:
    - messages yang sudah dikompres (atau original jika belum perlu)
    - boolean apakah kompresi terjadi
    """
    if len(messages) <= COMPRESS_THRESHOLD:
        return messages, False

    print(f"\n[MEMORY] Kompres: {len(messages)} pesan → ", end="")

    # Pisahkan bagian-bagian memory
    system = messages[0]                    # System prompt
    old_messages = messages[1:-KEEP_RECENT]  # Pesan lama (akan di-compress)
    recent = messages[-KEEP_RECENT:]         # Pesan terbaru (dipertahankan)

    # Cek apakah sudah ada summary sebelumnya
    existing_summary = ""
    if old_messages and old_messages[0]["role"] == "system" and \
       old_messages[0]["content"].startswith("[MEMORY SUMMARY]"):
        existing_summary = old_messages[0]["content"]
        old_messages = old_messages[1:]  # Skip summary lama dari pesan yang di-compress

    # Format pesan lama untuk di-summarize
    conversation_text = _format_messages(old_messages)

    # Buat summary
    summary = _generate_summary(conversation_text, existing_summary)

    # Rakit memory baru
    summary_message = {
        "role": "system",
        "content": f"[MEMORY SUMMARY]\n{summary}"
    }

    compressed = [system, summary_message] + recent

    print(f"{len(compressed)} pesan")
    print(f"[MEMORY] Summary: {summary[:200]}...\n")

    return compressed, True


def _format_messages(messages):
    """Format daftar pesan menjadi teks percakapan."""
    lines = []
    for msg in messages:
        role = msg["role"].upper()
        content = msg["content"]

        # Truncate pesan yang terlalu panjang
        if len(content) > 500:
            content = content[:500] + "..."

        lines.append(f"[{role}]: {content}")

    return "\n\n".join(lines)


def _generate_summary(conversation, existing_summary=""):
    """Buat ringkasan percakapan menggunakan AI."""
    context = ""
    if existing_summary:
        context = f"""
Summary sebelumnya:
{existing_summary}

Gabungkan dengan percakapan baru di bawah.
"""

    prompt = f"""{context}
Buat ringkasan singkat dari percakapan berikut. Fokus pada:
1. Apa yang sudah dikerjakan/dibahas
2. Keputusan penting yang dibuat
3. Konteks yang perlu diingat untuk percakapan selanjutnya

Format ringkasan sebagai bullet points.
Jawab langsung tanpa basa-basi, dalam bahasa Indonesia.

Percakapan:
{conversation[:5000]}"""

    response = chat(
        model=SUMMARY_MODEL,
        messages=[
            {
                "role": "user",
                "content": prompt
            }
        ]
    )

    return response["message"]["content"]
