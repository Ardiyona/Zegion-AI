import json
import os
import re

from ollama import chat
from tools.file_tools import (
    read_file,
    write_file,
    list_files,
    search_in_files
)

MEMORY_FILE = "memory.json"

# =========================
# SYSTEM PROMPT
# =========================

system_prompt = {
    "role": "system",
    "content": """
Kamu adalah AI assistant lokal.

Kamu memiliki tools:

1. read_file(path)
Untuk membaca file.

2. write_file(path, content)
Untuk membuat atau mengubah file.

Jika perlu membaca file gunakan format:

[READ_FILE path="main.py"]

Jika perlu membuat atau mengubah file gunakan format:

[WRITE_FILE path="hello.py"]
print("Hello World")
[/WRITE_FILE]

Gunakan nama file yang sesuai.

Jangan jelaskan penggunaan tools.
Gunakan tools jika diperlukan.

3. list_files(path)
Untuk melihat struktur file project.
[LIST_FILES path="."]

4. search_in_files(keyword, path)
Untuk mencari keyword dalam project.

Jika perlu mencari keyword gunakan format:

[SEARCH keyword="login" path="."]
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

    MAX_ITERATIONS = 5

    ai = ""

    for _ in range(MAX_ITERATIONS):

        response = chat(
            model="qwen3:4b",
            messages=messages
        )

        ai = response["message"]["content"]

        print("\nAI THINKING:")
        print(ai)
        print()

        tool_used = False

        # =========================
        # READ FILE TOOL
        # =========================

        read_match = re.search(
            r'\[READ_FILE path="(.*?)"\]',
            ai
        )

        if read_match:

            tool_used = True

            filepath = read_match.group(1)

            result = read_file(filepath)

            print(f"\nSYSTEM: Membaca file {filepath}\n")

            messages.append({
                "role": "assistant",
                "content": ai
            })

            messages.append({
                "role": "user",
                "content": f"""
                Isi file {filepath}:

                {result}
                """
            })

            continue

        # =========================
        # LIST FILES TOOL
        # =========================

        list_match = re.search(
            r'\[LIST_FILES path="(.*?)"\]',
            ai
        )

        if list_match:

            tool_used = True

            path = list_match.group(1)

            result = list_files(path)

            print(f"\nSYSTEM: Melihat struktur folder {path}\n")

            messages.append({
                "role": "assistant",
                "content": ai
            })

            messages.append({
                "role": "user",
                "content": f"""
        Struktur file:

        {result[:5000]}
        """
            })

            continue

        # =========================
        # SEARCH TOOL
        # =========================

        search_match = re.search(
            r'\[SEARCH keyword="(.*?)" path="(.*?)"\]',
            ai
        )

        if search_match:

            tool_used = True

            keyword = search_match.group(1)
            path = search_match.group(2)

            result = search_in_files(keyword, path)

            print(f"\nSYSTEM: Mencari '{keyword}' di {path}\n")

            messages.append({
                "role": "assistant",
                "content": ai
            })

            messages.append({
                "role": "user",
                "content": f"""
        Hasil pencarian keyword '{keyword}':

        {result}
        """
            })

            continue

        # =========================
        # WRITE FILE TOOL
        # =========================

        write_match = re.search(
            r'\[WRITE_FILE path="(.*?)"\](.*?)\[/WRITE_FILE\]',
            ai,
            re.DOTALL
        )

        if write_match:

            tool_used = True

            filepath = write_match.group(1)
            content = write_match.group(2).strip()

            result = write_file(filepath, content)

            print(f"\nSYSTEM: {result}\n")

            messages.append({
                "role": "assistant",
                "content": ai
            })

            messages.append({
                "role": "user",
                "content": result
            })

            continue

        # Kalau tidak ada tool dipakai
        if not tool_used:
            break

    # =========================
    # SIMPAN FINAL RESPONSE
    # =========================

    messages.append({
        "role": "assistant",
        "content": ai
    })

    # =========================
    # FINAL OUTPUT
    # =========================

    print("\nAI FINAL:")
    print(ai)
    print()

    # =========================
    # SAVE MEMORY
    # =========================

    with open(MEMORY_FILE, "w", encoding="utf-8") as f:
        json.dump(messages, f, ensure_ascii=False, indent=2)