from ollama import chat


# =========================
# CONFIG
# =========================

CRITIC_MODEL = "qwen3:4b"
MAX_CRITIC_LOOPS = 2  # Maksimal loop Critic → Executor

CRITIC_PROMPT = """Kamu adalah Critic AI. Tugasmu mengevaluasi apakah hasil eksekusi BENAR dan SESUAI dengan permintaan user.

Fokusmu: APA YANG SALAH?

Evaluasi berdasarkan:
1. Apakah kode/output memenuhi SEMUA requirement user?
2. Apakah ada bug, error, atau logic yang salah?
3. Apakah ada parameter/fitur yang hilang?
4. Apakah kode bisa berjalan tanpa error?

Jawab dengan format:
VERDICT: PASS atau FAIL
ISSUES: (jika FAIL) daftar masalah yang ditemukan
FIX: (jika FAIL) instruksi perbaikan yang spesifik
"""


def critique(user_request, results, exec_response):
    """
    Evaluasi apakah hasil eksekusi BENAR dan LENGKAP.
    Fokus pada kesalahan dan kekurangan.

    Return:
    - passed: bool
    - feedback: str (instruksi perbaikan jika FAIL)
    """
    # Skip untuk plan sederhana
    if not results or (len(results) == 1 and results[0].get("action") == "RESPOND"):
        return True, ""

    # Cek apakah ada WRITE_FILE atau EXECUTE di results (barulah perlu critique)
    has_code = any(
        r.get("action") in ("WRITE_FILE", "EXECUTE")
        for r in results
    )
    if not has_code:
        return True, ""

    # Format hasil untuk review
    results_text = _format_results(results)

    response = chat(
        model=CRITIC_MODEL,
        messages=[
            {"role": "system", "content": CRITIC_PROMPT},
            {
                "role": "user",
                "content": f"""Permintaan user: {user_request}

Hasil eksekusi:
{results_text}

Response executor: {exec_response[:500]}

Apakah hasilnya BENAR dan SESUAI requirement?"""
            }
        ]
    )

    review = response["message"]["content"]

    # Parse verdict
    passed = "PASS" in review.upper() and "FAIL" not in review.upper()

    feedback = ""
    if not passed:
        import re
        # Coba extract FIX
        fix_match = re.search(r'FIX:\s*(.*?)(?:\n\n|$)', review, re.DOTALL)
        if fix_match:
            feedback = fix_match.group(1).strip()
        else:
            # Coba extract ISSUES
            issues_match = re.search(r'ISSUES:\s*(.*?)(?:FIX:|$)', review, re.DOTALL)
            if issues_match:
                feedback = issues_match.group(1).strip()
            else:
                feedback = review

    return passed, feedback


def _format_results(results):
    """Format results untuk konteks Critic."""
    parts = []
    for r in results:
        action = r.get("action", "?")
        result = str(r.get("result", ""))

        if action == "WRITE_FILE":
            target = r.get("target", "?")
            parts.append(f"[WRITE_FILE → {target}]: {result[:300]}")
        elif action == "EXECUTE":
            target = r.get("target", "?")
            parts.append(f"[EXECUTE → {target}]: {result[:500]}")
        elif action == "READ_FILE":
            target = r.get("target", "?")
            parts.append(f"[READ_FILE → {target}]: {result[:500]}")
        elif action not in ("RESPOND", "DONE"):
            parts.append(f"[{action}]: {str(result)[:300]}")

    return "\n\n".join(parts)
