import time

from ollama import chat
from config import DEFAULT_MODEL
from agents.usage import record_usage


# =========================
# CONFIG
# =========================

REFLECTION_PROMPT = """Kamu adalah Reflection AI. Tugasmu mengevaluasi apakah hasil bisa DITINGKATKAN.

Fokusmu: APA YANG BISA LEBIH BAIK?

BUKAN mencari bug (itu tugas Critic). Kamu fokus pada:
1. Kualitas kode: naming, readability, struktur
2. Best practices: error handling, edge cases
3. Efisiensi: apakah ada cara yang lebih baik
4. Dokumentasi: apakah perlu komentar/docstring

ATURAN PENTING:
- Hanya sarankan improvement yang SIGNIFIKAN dan PRAKTIS.
- Jangan sarankan perubahan kosmetik yang tidak penting.
- Jika sudah cukup bagus, katakan GOOD.

Jawab dengan format:
VERDICT: GOOD atau IMPROVE
SUGGESTIONS: (jika IMPROVE) daftar saran perbaikan spesifik, maks 3
"""


def reflect(user_request, results, exec_response, model=None):
    """
    Evaluasi apakah hasil bisa ditingkatkan kualitasnya.
    Fokus pada improvement, bukan bug fixing.

    Return:
    - is_good: bool
    - suggestions: str (saran perbaikan jika IMPROVE)
    """
    # Skip untuk plan sederhana
    if not results or (len(results) == 1 and results[0].get("action") == "RESPOND"):
        return True, ""

    # Hanya aktif jika ada kode yang ditulis
    has_code = any(
        r.get("action") in ("WRITE_FILE", "EXECUTE")
        for r in results
    )
    if not has_code:
        return True, ""

    # Format hasil
    results_text = _format_results(results)

    review_model = model or DEFAULT_MODEL
    messages = [
        {"role": "system", "content": REFLECTION_PROMPT},
        {
            "role": "user",
            "content": f"""Permintaan user: {user_request}

Hasil eksekusi:
{results_text}

Response: {exec_response[:500]}

Apakah ada yang bisa ditingkatkan?"""
        }
    ]
    start = time.time()
    response = chat(model=review_model, messages=messages)
    elapsed = time.time() - start
    record_usage(
        "reflection",
        review_model,
        prompt_tokens=response.get("prompt_eval_count", 0),
        output_tokens=response.get("eval_count", 0),
        prompt_eval_s=response.get("prompt_eval_duration", 0) / 1e9,
        generation_s=response.get("eval_duration", 0) / 1e9,
        duration_s=elapsed,
        prompt_chars=sum(len(m["content"]) for m in messages),
    )

    review = response["message"]["content"]

    # Parse verdict
    is_good = "GOOD" in review.upper() and "IMPROVE" not in review.upper()

    suggestions = ""
    if not is_good:
        import re
        sug_match = re.search(r'SUGGESTIONS:\s*(.*?)$', review, re.DOTALL)
        if sug_match:
            suggestions = sug_match.group(1).strip()
        else:
            suggestions = review

    return is_good, suggestions


def _format_results(results):
    """Format results untuk konteks Reflection."""
    parts = []
    for r in results:
        action = r.get("action", "?")
        result = str(r.get("result", ""))

        if action == "WRITE_FILE":
            target = r.get("target", "?")
            parts.append(f"[WRITE_FILE → {target}]: {result[:500]}")
        elif action == "EXECUTE":
            target = r.get("target", "?")
            parts.append(f"[EXECUTE → {target}]: {result[:500]}")
        elif action not in ("RESPOND", "DONE"):
            parts.append(f"[{action}]: {str(result)[:300]}")

    return "\n\n".join(parts)
