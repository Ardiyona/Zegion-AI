import os
import json
import math
from ollama import embed
from tools.file_ops import read_file
from tools.summarizer import file_hash


# =========================
# CONFIG
# =========================

EMBEDDING_CACHE_FILE = "data/embeddings_cache.json"
EMBEDDING_MODEL = "nomic-embed-text"


# =========================
# HELPERS
# =========================

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


# =========================
# MAIN FUNCTIONS
# =========================

def build_embeddings(path="."):
    """
    Scan project dan build embedding untuk semua file.
    Menggunakan hash-based cache — skip file yang belum berubah.
    """
    cache = _load_embedding_cache()
    skip_dirs = {"__pycache__", ".git", "node_modules", ".venv", "venv", "data"}
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
            current_hash = file_hash(filepath)

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

    return "\n".join(output_lines) if output_lines else "Tidak ditemukan hasil yang relevan."
