import json
import os
import re

from ollama import chat
from tools.file_tools import (
    read_file,
    write_file,
    list_files,
    search_in_files,
    execute_python
)

MEMORY_FILE = "memory.json"

# =========================
# SYSTEM PROMPT
# =========================

system_prompt = {
    "role": "system",
    "content": """
Kamu adalah AI assistant lokal.

Kamu memiliki tools berikut. WAJIB gunakan format PERSIS seperti di bawah:

1. READ FILE:
[READ_FILE path="nama_file.py"]

2. WRITE FILE:
[WRITE_FILE path="nama_file.py"]
isi konten file di sini
[/WRITE_FILE]

3. LIST FILES:
[LIST_FILES path="."]

4. SEARCH:
[SEARCH keyword="kata" path="."]

5. EXECUTE PYTHON:
[EXECUTE path="nama_file.py"]

ATURAN:
- Lakukan SATU langkah per respons. Jangan gabungkan beberapa tool.
- Setelah WRITE_FILE → wajib EXECUTE di respons berikutnya.
- Jika STATUS: ERROR → perbaiki file lalu EXECUTE lagi.
- Gunakan [TASK_COMPLETE] hanya jika STATUS: SUCCESS.
- JANGAN gunakan format lain selain yang tertulis di atas.
"""
}

# =========================
# LOAD MEMORY
# =========================

if os.path.exists(MEMORY_FILE):

    try:
        with open(MEMORY_FILE, "r", encoding="utf-8") as f:
            messages = json.load(f)

    except:
        messages = [system_prompt]

else:
    messages = [system_prompt]

print("AI Local Siap 😼")
print("Ketik 'exit' untuk keluar.\n")

# =========================
# MAIN LOOP
# =========================

while True:

    user = input("You: ")

    if user.lower() == "exit":
        break

    # Tambahkan user message
    messages.append({
        "role": "user",
        "content": user
    })

    # =========================
    # MULTI STEP AGENT LOOP
    # =========================

    MAX_ITERATIONS = 10  # naikin sedikit biar cukup

    ai = ""
    last_thinking = ""  # ← tracking AI THINKING terakhir

    for step in range(MAX_ITERATIONS):

        response = chat(
            model="qwen3:4b",
            messages=messages
        )

        ai = response["message"]["content"]
        print(f"\n[DEBUG] Raw AI response:\n{ai}\n")

        tool_used = False

        # ── READ FILE ──────────────────────────────────────────
        read_match = re.search(r'\[READ_FILE path="(.*?)"\]', ai)
        if read_match:
            tool_used = True
            filepath = read_match.group(1)
            result = read_file(filepath)
            print(f"\n[TOOL] READ_FILE → {filepath}")
            print(f"AI THINKING:\n{ai}\n")
            messages.append({"role": "assistant", "content": ai})
            messages.append({"role": "user", "content": f"Isi file {filepath}:\n\n{result}"})
            continue

        # ── LIST FILES ─────────────────────────────────────────
        list_match = re.search(r'\[LIST_FILES path="(.*?)"\]', ai)
        if list_match:
            tool_used = True
            path = list_match.group(1)
            result = list_files(path)
            print(f"\n[TOOL] LIST_FILES → {path}")
            print(f"AI THINKING:\n{ai}\n")
            messages.append({"role": "assistant", "content": ai})
            messages.append({"role": "user", "content": f"Struktur file:\n\n{result[:5000]}"})
            continue

        # ── SEARCH ────────────────────────────────────────────
        search_match = re.search(r'\[SEARCH keyword="(.*?)" path="(.*?)"\]', ai)
        if search_match:
            tool_used = True
            keyword = search_match.group(1)
            path = search_match.group(2)
            result = search_in_files(keyword, path)
            print(f"\n[TOOL] SEARCH → '{keyword}' di {path}")
            print(f"AI THINKING:\n{ai}\n")
            messages.append({"role": "assistant", "content": ai})
            messages.append({"role": "user", "content": f"Hasil pencarian '{keyword}':\n\n{result}"})
            continue

        # ── EXECUTE ───────────────────────────────────────────
        execute_match = re.search(r'\[EXECUTE path="(.*?)"\]', ai)
        if execute_match:
            tool_used = True
            filepath = execute_match.group(1)
            result = execute_python(filepath)
            print(f"\n[TOOL] EXECUTE → {filepath}")
            print(f"AI THINKING:\n{ai}\n")
            print(f"Hasil:\n{result}\n")
            messages.append({"role": "assistant", "content": ai})
            messages.append({"role": "user", "content": f"Hasil eksekusi {filepath}:\n\n{result}"})
            continue

        # ── WRITE FILE ────────────────────────────────────────
        # Proses SEMUA blok WRITE_FILE dalam satu response
        write_matches = re.findall(
            r'\[WRITE_FILE path="(.*?)"\](.*?)\[/WRITE_FILE\]',
            ai,
            re.DOTALL
        )

        # Handle format inline: [WRITE_FILE path="..." content="..."]
        if not write_matches:
            inline_matches = re.findall(
                r'\[WRITE_FILE path="(.*?)" content="(.*?)"\]',
                ai,
                re.DOTALL
            )
            # Unescape \n dan \" dari inline format
            write_matches = [
                (path, content.replace("\\n", "\n").replace('\\"', '"'))
                for path, content in inline_matches
            ]

        if write_matches:
            tool_used = True
            print(f"\nAI THINKING:\n{ai}\n")
            feedback_parts = []
            for filepath, content in write_matches:
                content = content.strip()
                result = write_file(filepath, content)
                print(f"[TOOL] WRITE_FILE → {filepath}: {result}")
                feedback_parts.append(f"{filepath}: {result}")
            messages.append({"role": "assistant", "content": ai})
            messages.append({"role": "user", "content": "\n".join(feedback_parts)})
            continue

        # ── TASK COMPLETE ─────────────────────────────────────
        if "[TASK_COMPLETE]" in ai:
            print(f"\nAI THINKING:\n{ai}\n")
            break

        # Tidak ada tool → ini jawaban final
        if not tool_used:
            break

    # =========================
    # SIMPAN FINAL RESPONSE
    # =========================

    messages.append({"role": "assistant", "content": ai})

    print("\n" + "="*40)
    print("AI FINAL:")
    print(ai)
    print("="*40 + "\n")

    # =========================
    # SAVE MEMORY
    # =========================

    with open(MEMORY_FILE, "w", encoding="utf-8") as f:
        json.dump(messages, f, ensure_ascii=False, indent=2)