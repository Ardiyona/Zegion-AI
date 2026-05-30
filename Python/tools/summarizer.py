import os
import json
import hashlib
from ollama import chat
from tools.file_ops import read_file


# =========================
# CACHE HELPERS
# =========================

SUMMARY_CACHE_FILE = "file_summaries.json"


def _load_summary_cache():
    if os.path.exists(SUMMARY_CACHE_FILE):
        try:
            with open(SUMMARY_CACHE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            return {}
    return {}


def _save_summary_cache(cache):
    with open(SUMMARY_CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)


def file_hash(path):
    """Hash isi file untuk deteksi perubahan."""
    try:
        with open(path, "rb") as f:
            return hashlib.md5(f.read()).hexdigest()
    except:
        return None


# =========================
# SUMMARIZATION
# =========================

def summarize_file(path):
    """
    Baca file lalu buat summary singkat pakai AI.
    Hasil di-cache. Kalau file berubah, summary diperbarui.
    """
    cache = _load_summary_cache()
    current_hash = file_hash(path)

    if current_hash is None:
        return f"Error: File {path} tidak ditemukan."

    # Return cache kalau file tidak berubah
    if path in cache and cache[path]["hash"] == current_hash:
        return cache[path]["summary"]

    # Baca file
    content = read_file(path)
    if content.startswith("Error:"):
        return content

    # Generate summary pakai AI lokal
    response = chat(
        model="qwen3:4b",
        messages=[
            {
                "role": "user",
                "content": f"""Buat summary singkat dari file ini dalam 3-5 kalimat.
Jelaskan: apa fungsi file ini, fungsi/class utama yang ada, dan dependensinya.
Jawab langsung tanpa basa-basi.

File: {path}
Isi:
{content[:3000]}"""
            }
        ]
    )

    summary = response["message"]["content"]

    # Simpan ke cache
    cache[path] = {
        "hash": current_hash,
        "summary": summary
    }
    _save_summary_cache(cache)

    return summary


def summarize_project(path="."):
    """Summary semua file dalam project."""
    results = []
    for root, dirs, filenames in os.walk(path):
        # Skip folder yang tidak relevan
        dirs[:] = [d for d in dirs if d not in [
            "__pycache__", ".git", "node_modules", ".venv", "venv"
        ]]
        for filename in filenames:
            if not filename.endswith((".py", ".js", ".ts", ".md", ".txt")):
                continue
            filepath = os.path.join(root, filename)
            print(f"  Summarizing {filepath}...")
            summary = summarize_file(filepath)
            results.append(f"### {filepath}\n{summary}")

    return "\n\n".join(results)


# =========================
# PROJECT INDEX
# =========================

def build_project_index(path="."):
    """
    Build ringkasan project untuk di-inject ke system prompt.
    Menggunakan cache yang sudah ada (tanpa panggil AI baru).
    Kalau belum ada cache, hanya tampilkan daftar file.
    """
    cache = _load_summary_cache()
    skip_dirs = {"__pycache__", ".git", "node_modules", ".venv", "venv"}
    valid_ext = (".py", ".js", ".ts", ".md", ".txt", ".json")
    skip_files = {"memory.json", "file_summaries.json", "project_index.json"}

    lines = ["=== PROJECT INDEX ==="]
    file_count = 0

    for root, dirs, filenames in os.walk(path):
        dirs[:] = [d for d in dirs if d not in skip_dirs]

        for filename in filenames:
            if filename in skip_files:
                continue
            if not filename.endswith(valid_ext):
                continue

            filepath = os.path.join(root, filename)
            file_count += 1

            # Ambil summary dari cache jika ada
            if filepath in cache:
                summary = cache[filepath]["summary"]
                # Ambil baris pertama saja supaya ringkas
                short = summary.split("\n")[0].strip()[:150]
                lines.append(f"- {filepath}: {short}")
            else:
                lines.append(f"- {filepath}: (belum di-summarize)")

    lines.append(f"\nTotal: {file_count} file")
    lines.append("=== END INDEX ===")

    return "\n".join(lines)
