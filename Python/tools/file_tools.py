import os
import subprocess
import json
import hashlib
import math
from ollama import chat, embed

def list_files(path="."):

    files = []

    for root, dirs, filenames in os.walk(path):

        for filename in filenames:

            full_path = os.path.join(root, filename)

            files.append(full_path)

    return "\n".join(files)

def search_in_files(keyword, path="."):

    import os

    results = []

    for root, dirs, filenames in os.walk(path):

        for filename in filenames:

            filepath = os.path.join(root, filename)

            try:
                with open(filepath, "r", encoding="utf-8") as f:

                    content = f.read()

                    if keyword.lower() in content.lower():

                        results.append(filepath)

            except:
                pass

    if results:
        return "\n".join(results)

    return "Tidak ditemukan"

def read_file(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        return f"Error: {str(e)}"

def write_file(path, content):
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)

        return f"Berhasil menulis ke {path}"

    except Exception as e:
        return f"Error: {str(e)}"
    
def execute_python(path):

    try:

        result = subprocess.run(
            ["py", path],
            capture_output=True,
            text=True,
            timeout=10
        )

        if result.returncode == 0:

            return f"""
STATUS: SUCCESS

OUTPUT:
{result.stdout}
"""

        else:

            return f"""
STATUS: ERROR

ERROR:
{result.stderr}
"""

    except Exception as e:

        return f"""
STATUS: ERROR

ERROR:
{str(e)}
"""
    
# File Sumarization
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

def _file_hash(path):
    """Hash isi file untuk deteksi perubahan."""
    try:
        with open(path, "rb") as f:
            return hashlib.md5(f.read()).hexdigest()
    except:
        return None

def summarize_file(path):
    """
    Baca file lalu buat summary singkat pakai AI.
    Hasil di-cache. Kalau file berubah, summary diperbarui.
    """
    cache = _load_summary_cache()
    current_hash = _file_hash(path)

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

# =========================
# SEMANTIC RETRIEVAL
# =========================

EMBEDDING_CACHE_FILE = "embeddings_cache.json"
EMBEDDING_MODEL = "nomic-embed-text"

def _chunk_text(text, chunk_size=500, overlap=100):
    """Pecah teks menjadi chunk-chunk dengan overlap."""
    lines = text.split("\n")
    chunks = []
    current = []
    current_len = 0

    for line in lines:
        current.append(line)
        current_len += len(line) + 1

        if current_len >= chunk_size:
            chunks.append("\n".join(current))
            # Overlap: simpan beberapa baris terakhir
            overlap_lines = []
            overlap_len = 0
            for l in reversed(current):
                if overlap_len + len(l) > overlap:
                    break
                overlap_lines.insert(0, l)
                overlap_len += len(l) + 1
            current = overlap_lines
            current_len = overlap_len

    if current:
        chunks.append("\n".join(current))

    return chunks

def _cosine_similarity(a, b):
    """Hitung cosine similarity antara 2 vector."""
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)

def _load_embedding_cache():
    if os.path.exists(EMBEDDING_CACHE_FILE):
        try:
            with open(EMBEDDING_CACHE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            return {}
    return {}

def _save_embedding_cache(cache):
    with open(EMBEDDING_CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False)

def _embed_text(text):
    """Generate embedding vector menggunakan Ollama."""
    response = embed(model=EMBEDDING_MODEL, input=text)
    return response["embeddings"][0]

def build_embeddings(path="."):
    """
    Scan project dan build embedding untuk semua file.
    Menggunakan hash-based cache — skip file yang belum berubah.
    """
    cache = _load_embedding_cache()
    skip_dirs = {"__pycache__", ".git", "node_modules", ".venv", "venv"}
    valid_ext = (".py", ".js", ".ts", ".md", ".txt")
    skip_files = {"memory.json", "file_summaries.json", "embeddings_cache.json"}

    updated = 0

    for root, dirs, filenames in os.walk(path):
        dirs[:] = [d for d in dirs if d not in skip_dirs]

        for filename in filenames:
            if filename in skip_files:
                continue
            if not filename.endswith(valid_ext):
                continue

            filepath = os.path.join(root, filename)
            current_hash = _file_hash(filepath)

            if current_hash is None:
                continue

            # Skip kalau file belum berubah
            if filepath in cache and cache[filepath].get("hash") == current_hash:
                continue

            # Baca dan chunk file
            content = read_file(filepath)
            if content.startswith("Error:"):
                continue

            chunks = _chunk_text(content)
            chunk_embeddings = []

            print(f"  Embedding {filepath} ({len(chunks)} chunks)...")

            for i, chunk in enumerate(chunks):
                # Prefix chunk dengan info file untuk konteks
                labeled = f"File: {filepath}\n\n{chunk}"
                vec = _embed_text(labeled)
                chunk_embeddings.append({
                    "chunk_index": i,
                    "text": chunk[:1000],  # Simpan sebagian teks untuk preview
                    "embedding": vec
                })

            cache[filepath] = {
                "hash": current_hash,
                "chunks": chunk_embeddings
            }
            updated += 1

    _save_embedding_cache(cache)
    return f"Embedding selesai. {updated} file diperbarui."

def semantic_search(query, path=".", top_k=5):
    """
    Cari file/chunk yang paling relevan dengan query.
    Return top-k hasil berdasarkan cosine similarity.
    """
    cache = _load_embedding_cache()

    if not cache:
        return "Error: Belum ada embedding. Jalankan build_embeddings dulu."

    # Embed query
    query_vec = _embed_text(query)

    # Hitung similarity untuk semua chunks
    results = []
    for filepath, data in cache.items():
        if not isinstance(data, dict) or "chunks" not in data:
            continue
        for chunk_data in data["chunks"]:
            sim = _cosine_similarity(query_vec, chunk_data["embedding"])
            results.append({
                "file": filepath,
                "chunk": chunk_data["chunk_index"],
                "similarity": sim,
                "preview": chunk_data["text"][:300]
            })

    # Sort by similarity
    results.sort(key=lambda x: x["similarity"], reverse=True)
    top = results[:top_k]

    # Format output
    output_lines = []
    for i, r in enumerate(top, 1):
        output_lines.append(
            f"{i}. [{r['similarity']:.3f}] {r['file']} (chunk {r['chunk']})\n"
            f"   {r['preview'][:200]}..."
        )

    return "\n\n".join(output_lines) if output_lines else "Tidak ditemukan hasil yang relevan."