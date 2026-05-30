from ollama import chat


# =========================
# CONFIG
# =========================

REVIEWER_MODEL = "qwen3:4b"

REVIEWER_PROMPT = """Kamu adalah Reviewer AI. Tugasmu mengevaluasi apakah hasil eksekusi sudah memenuhi permintaan user.

Evaluasi berdasarkan:
1. Apakah semua langkah berhasil?
2. Apakah hasilnya sesuai dengan yang diminta user?
3. Apakah ada error yang belum ditangani?

Jawab dengan format:
VERDICT: APPROVED atau NEEDS_REVISION
REASON: alasan singkat
FEEDBACK: (jika NEEDS_REVISION) apa yang perlu diperbaiki
"""


def review_results(user_request, plan_summary, results, final_response):
    """
    Review apakah hasil eksekusi sudah memuaskan.

    Return:
    - approved: bool
    - feedback: str (kosong jika approved)
    """
    # Skip review untuk plan sederhana (RESPOND saja)
    if not results or (len(results) == 1 and results[0].get("action") == "RESPOND"):
        return True, ""

    # Format hasil untuk review
    results_text = ""
    for r in results:
        action = r.get("action", "?")
        result = str(r.get("result", ""))[:500]
        results_text += f"- [{action}]: {result}\n"

    response = chat(
        model=REVIEWER_MODEL,
        messages=[
            {"role": "system", "content": REVIEWER_PROMPT},
            {
                "role": "user",
                "content": f"""Permintaan user: {user_request}

Rencana: {plan_summary}

Hasil eksekusi:
{results_text}

Jawaban final: {final_response[:500]}

Evaluasi apakah hasilnya sudah benar dan lengkap."""
            }
        ]
    )

    review = response["message"]["content"]

    print(f"\n  🔍 Reviewer: {review[:200]}...")

    # Parse verdict
    approved = "APPROVED" in review.upper()

    # Extract feedback jika NEEDS_REVISION
    feedback = ""
    if not approved:
        import re
        fb_match = re.search(r'FEEDBACK:\s*(.*?)(?:\n|$)', review, re.DOTALL)
        if fb_match:
            feedback = fb_match.group(1).strip()
        else:
            feedback = review

    return approved, feedback
