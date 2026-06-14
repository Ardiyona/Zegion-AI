import logging
import re
import time
from typing import Optional
from ollama import chat as _ollama_chat

from tools.file_ops import (
    read_file,
    write_file,
    list_files,
    search_in_files,
    execute_python,
)
from tools.summarizer import (
    summarize_file,
    summarize_project,
)
from tools.semantic import (
    semantic_search,
)
from tools.web_search import (
    web_search,
    fetch_url,
)
from tools.clickup import (
    # Low-level
    clickup_list_spaces,
    clickup_list_lists,
    clickup_list_tasks,
    # High-level
    clickup_get_tasks,
    clickup_get_task_detail,
    clickup_smart_create_task,
    clickup_smart_update_task,
    clickup_smart_add_comment,
)
from config import DEFAULT_MODEL

logger = logging.getLogger(__name__)


# =========================
# CONFIG
# =========================

MAX_EXECUTOR_STEPS = 10

EXECUTOR_PROMPT = """Kamu adalah Executor AI. Kerjakan rencana menggunakan tools.

ATURAN:
1. Output HANYA satu tool command atau [DONE]. JANGAN tulis penjelasan lain.
2. Parameter harus NYATA, bukan placeholder. Jika tidak tahu, pakai tool tanpa parameter.
3. Setelah hasil tool diterima dan cukup untuk menjawab user, LANGSUNG tulis [DONE] diikuti jawaban.
4. JANGAN buat file untuk menyimpan jawaban, ringkasan, atau hasil pencarian. Gunakan [DONE] saja.
5. WRITE_FILE dan EXECUTE HANYA jika user meminta membuat/menulis file atau menjalankan kode.
6. CLICKUP_UPDATE_TASK: HANYA sertakan field yang user minta. Jangan ubah status/priority/name/description jika user tidak meminta.
7. Jika tool gagal/error, coba pendekatan LAIN. Jika 2x gagal, tulis [DONE] dengan penjelasan error.

FORMAT TOOL:
[READ_FILE path="file.py"]
[WRITE_FILE path="file.py"]
isi
[/WRITE_FILE]
[LIST_FILES path="."]
[SEARCH keyword="kata" path="."]
[EXECUTE path="file.py"]
[SUMMARIZE_FILE path="file.py"]
[SEMANTIC_SEARCH query="deskripsi"]
[WEB_SEARCH query="kata kunci"]
[FETCH_URL url="https://..."]
[CLICKUP_GET_TASKS] atau [CLICKUP_GET_TASKS list_name="Zegion" status="open"]
[CLICKUP_GET_TASK_DETAIL task_id="86exy7dku"]
[CLICKUP_CREATE_TASK list_name="Zegion" name="nama task" description="desc" priority="normal"]
[CLICKUP_UPDATE_TASK task_id="86exy7dku" status="done" priority="high"]
[CLICKUP_ADD_COMMENT task_id="86exy7dku" comment="teks"]
[CLICKUP_LIST_SPACES]
[CLICKUP_LIST_LISTS space_id="id"]
[CLICKUP_LIST_TASKS list_id="id"]

CONTOH BENAR:
User: "list task saya" → [CLICKUP_GET_TASKS] → (terima hasil) → [DONE] Berikut task Anda: ...
User: "baca file main.py" → [READ_FILE path="main.py"] → (terima isi) → [DONE] Isi file main.py: ...
User: "cari info bitcoin" → [WEB_SEARCH query="harga bitcoin"] → (terima hasil) → [DONE] Harga bitcoin saat ini: ...
User: "tambah deskripsi task X" → [CLICKUP_UPDATE_TASK task_id="X" description="..."] → [DONE]
User: "ubah status task X jadi done" → [CLICKUP_UPDATE_TASK task_id="X" status="done"] → [DONE]
"""


# =========================
# STREAMING CHAT HELPER
# =========================

class _CancelledError(Exception):
    """Raised when streaming is interrupted by user cancel."""
    pass


class _ChatResult(str):
    """String subclass that also carries Ollama telemetry metadata."""
    prompt_eval_count: int = 0
    eval_count: int = 0
    prompt_eval_ns: int = 0
    eval_ns: int = 0

    @property
    def prompt_eval_s(self) -> float:
        return self.prompt_eval_ns / 1e9 if self.prompt_eval_ns else 0.0

    @property
    def eval_s(self) -> float:
        return self.eval_ns / 1e9 if self.eval_ns else 0.0

    @property
    def tps(self) -> float:
        return self.eval_count / self.eval_s if self.eval_s > 0 else 0.0


def _print_telemetry(label: str, model: str, prompt_chars: int, result: '_ChatResult'):
    """Print standardized telemetry block for an agent phase."""
    print(f"\n  [{label}]")
    print(f"  Model: {model}")
    print(f"  Prompt chars: {prompt_chars:,}")
    print(f"  Prompt tokens: {result.prompt_eval_count:,}")
    print(f"  Output tokens: {result.eval_count:,}")
    print(f"  Prompt eval: {result.prompt_eval_s:.1f}s")
    print(f"  Generation: {result.eval_s:.1f}s")
    if result.tps > 0:
        print(f"  TPS: {result.tps:.2f}")
    print()


def _stream_chat(
    model: str,
    messages: list[dict],
    conv_id: Optional[str] = None,
) -> _ChatResult:
    """
    Streaming wrapper around ollama.chat().

    - Registers the stream so request_cancel() can close it from another thread.
    - Checks is_cancelled() on every token — breaks immediately if set.
    - Calls unregister_stream() in finally on ALL exit paths.
    - Never passes a partial buffer to caller on cancel or error.

    Returns:
        Full accumulated response string on success.

    Raises:
        _CancelledError: if cancelled mid-stream (or before stream starts).
        Exception: re-raises network/generation errors after cleanup.
    """
    from agents.cancel import (
        is_cancelled, mark_cancelled, register_stream, unregister_stream,
    )

    # Check before even opening stream
    if is_cancelled(conv_id):
        mark_cancelled(conv_id)
        raise _CancelledError()

    stream = _ollama_chat(model=model, messages=messages, stream=True)
    register_stream(conv_id, stream)

    buffer = ""
    cancelled = False
    error: Optional[Exception] = None
    last_chunk: dict = {}

    try:
        for chunk in stream:
            if is_cancelled(conv_id):
                cancelled = True
                break
            try:
                buffer += chunk.get("message", {}).get("content", "")
                last_chunk = chunk  # simpan chunk terakhir untuk metadata
            except Exception as e:
                logger.warning("[executor] chunk parse error: %s", e)
    except Exception as e:
        # Network drop or generation error — not a cancel
        logger.warning("[executor] stream error: %s", e)
        error = e
    finally:
        unregister_stream(conv_id)

    if cancelled:
        mark_cancelled(conv_id)
        raise _CancelledError()

    if error is not None:
        raise error

    # Wrap buffer in _ChatResult dengan metadata dari chunk terakhir
    result = _ChatResult(buffer)
    result.prompt_eval_count = last_chunk.get("prompt_eval_count", 0)
    result.eval_count = last_chunk.get("eval_count", 0)
    result.prompt_eval_ns = last_chunk.get("prompt_eval_duration", 0)
    result.eval_ns = last_chunk.get("eval_duration", 0)
    return result


# =========================
# TOOL HANDLERS
# =========================

def _is_placeholder(value: str) -> bool:
    """Cek apakah nilai parameter adalah placeholder, bukan nilai nyata."""
    if not value:
        return False
    placeholders = [
        "nama list", "nama file", "kata kunci", "kata", "deskripsi",
        "id", "nama task", "nama", "desc", "teks", "path",
        "nama baru", "deskripsi baru", "list", "query",
        "file.py", "nama list", "nama",
    ]
    v = value.strip().lower()
    return v in placeholders or v.startswith("nama") or v == "list_name"


def _find_last(pattern: str, text: str, flags=0):
    """Cari match TERAKHIR dari pattern di text (bukan pertama)."""
    matches = list(re.finditer(pattern, text, flags))
    return matches[-1] if matches else None


def _handle_tools(
    ai_response: str,
) -> tuple[bool, Optional[str], Optional[str], Optional[str]]:
    """
    Parse full (non-partial) AI response and execute the LAST matching tool.

    Must only be called after _stream_chat() completes without cancel/error.
    Returns: (tool_used, tool_name, tool_target, result)
    """

    # READ FILE
    m = _find_last(r'\[READ_FILE path="(.*?)"\]', ai_response)
    if m:
        path = m.group(1)
        if _is_placeholder(path):
            return True, "READ_FILE", path, f"Error: parameter '{path}' adalah placeholder. Gunakan nama file yang nyata."
        result = read_file(path)
        return True, "READ_FILE", path, f"Isi file {path}:\n\n{result}"

    # LIST FILES
    m = _find_last(r'\[LIST_FILES path="(.*?)"\]', ai_response)
    if m:
        path = m.group(1)
        result = list_files(path)
        return True, "LIST_FILES", path, f"Struktur file:\n\n{result[:5000]}"

    # SEARCH
    m = _find_last(r'\[SEARCH keyword="(.*?)" path="(.*?)"\]', ai_response)
    if m:
        keyword, path = m.group(1), m.group(2)
        result = search_in_files(keyword, path)
        return True, "SEARCH", keyword, f"Hasil pencarian '{keyword}':\n\n{result}"

    # SEMANTIC SEARCH
    m = _find_last(r'\[SEMANTIC_SEARCH query="(.*?)"\]', ai_response)
    if m:
        query = m.group(1)
        result = semantic_search(query)
        return True, "SEMANTIC_SEARCH", query, f"Hasil semantic search:\n\n{result}"

    # EXECUTE
    m = _find_last(r'\[EXECUTE path="(.*?)"\]', ai_response)
    if m:
        path = m.group(1)
        result = execute_python(path)
        return True, "EXECUTE", path, f"Hasil eksekusi {path}:\n\n{result}"

    # SUMMARIZE FILE
    m = _find_last(r'\[SUMMARIZE_FILE path="(.*?)"\]', ai_response)
    if m:
        path = m.group(1)
        result = summarize_file(path)
        return True, "SUMMARIZE_FILE", path, f"Summary {path}:\n\n{result}"

    # WRITE FILE (block format) — ambil match terakhir
    write_matches = list(re.finditer(
        r'\[WRITE_FILE path="(.*?)"\](.*?)\[/WRITE_FILE\]',
        ai_response, re.DOTALL
    ))
    if write_matches:
        last_write = write_matches[-1]
        path, content = last_write.group(1), last_write.group(2).strip()
        if _is_placeholder(path):
            return True, "WRITE_FILE", path, f"Error: parameter '{path}' adalah placeholder. Gunakan nama file yang nyata."
        r = write_file(path, content)
        return True, "WRITE_FILE", path, r

    # WRITE FILE (inline format)
    m = _find_last(r'\[WRITE_FILE path="(.*?)" content="(.*?)"\]', ai_response, re.DOTALL)
    if m:
        path = m.group(1)
        content = m.group(2).replace("\\n", "\n").replace('\\"', '"')
        result = write_file(path, content)
        return True, "WRITE_FILE", path, result

    # WEB SEARCH
    m = _find_last(r'\[WEB_SEARCH query="(.*?)"\]', ai_response)
    if m:
        query = m.group(1)
        result = web_search(query)
        return True, "WEB_SEARCH", query, result

    # FETCH URL
    m = _find_last(r'\[FETCH_URL url="(.*?)"\]', ai_response)
    if m:
        url = m.group(1)
        result = fetch_url(url)
        return True, "FETCH_URL", url, result

    # CLICKUP GET TASKS
    m = _find_last(r'\[CLICKUP_GET_TASKS(?:\s+list_name="(.*?)")?(?:\s+status="(.*?)")?\]', ai_response)
    if m:
        list_name = m.group(1)
        status = m.group(2)
        # Tolak placeholder
        if _is_placeholder(list_name):
            return True, "CLICKUP_GET_TASKS", list_name, f"Error: parameter list_name='{list_name}' adalah placeholder. Gunakan nama list yang nyata, atau hapus parameter untuk semua task."
        result = clickup_get_tasks(list_name=list_name, status=status)
        label = list_name or status or "all"
        return True, "CLICKUP_GET_TASKS", label, result

    # CLICKUP GET TASK DETAIL
    m = _find_last(r'\[CLICKUP_GET_TASK_DETAIL task_id="(.*?)"\]', ai_response)
    if m:
        task_id = m.group(1)
        result = clickup_get_task_detail(task_id)
        return True, "CLICKUP_GET_TASK_DETAIL", task_id, result

    # CLICKUP CREATE TASK
    m = _find_last(r'\[CLICKUP_CREATE_TASK list_name="(.*?)" name="(.*?)"(?:\s+description="(.*?)")?(?:\s+priority="(.*?)")?\]', ai_response)
    if m:
        list_name, name = m.group(1), m.group(2)
        desc = m.group(3) or ""
        priority = m.group(4)
        result = clickup_smart_create_task(name, list_name, desc, priority=priority)
        return True, "CLICKUP_CREATE_TASK", name, result

    # CLICKUP UPDATE TASK
    m = _find_last(r'\[CLICKUP_UPDATE_TASK task_id="(.*?)"(?:\s+status="(.*?)")?(?:\s+priority="(.*?)")?(?:\s+name="(.*?)")?(?:\s+description="(.*?)")?\]', ai_response, re.DOTALL)
    if m:
        task_id = m.group(1)
        status, priority, name, description = m.group(2), m.group(3), m.group(4), m.group(5)
        result = clickup_smart_update_task(task_id, status=status, priority=priority, name=name, description=description)
        return True, "CLICKUP_UPDATE_TASK", task_id, result

    # CLICKUP ADD COMMENT
    m = _find_last(r'\[CLICKUP_ADD_COMMENT task_id="(.*?)" comment="(.*?)"\]', ai_response, re.DOTALL)
    if m:
        task_id, comment = m.group(1), m.group(2)
        result = clickup_smart_add_comment(task_id, comment)
        return True, "CLICKUP_ADD_COMMENT", task_id, result

    # CLICKUP LIST SPACES
    if '[CLICKUP_LIST_SPACES]' in ai_response:
        result = clickup_list_spaces()
        return True, "CLICKUP_LIST_SPACES", "spaces", result

    # CLICKUP LIST LISTS
    m = _find_last(r'\[CLICKUP_LIST_LISTS space_id="(.*?)"\]', ai_response)
    if m:
        space_id = m.group(1)
        result = clickup_list_lists(space_id)
        return True, "CLICKUP_LIST_LISTS", space_id, result

    # CLICKUP LIST TASKS (low-level)
    m = _find_last(r'\[CLICKUP_LIST_TASKS list_id="(.*?)"\]', ai_response)
    if m:
        list_id = m.group(1)
        result = clickup_list_tasks(list_id)
        return True, "CLICKUP_LIST_TASKS", list_id, result

    return False, None, None, None


# =========================
# EXECUTOR AGENT
# =========================

# Tools yang hasilnya bisa langsung dikembalikan tanpa Responder
_DIRECT_RESPONSE_TOOLS = {
    "CLICKUP_GET_TASKS",
    "CLICKUP_GET_TASK_DETAIL",
    "LIST_FILES",
    "READ_FILE",
    "LIST_SPACES",
    "CLICKUP_LIST_SPACES",
    "CLICKUP_LIST_LISTS",
    "CLICKUP_LIST_TASKS",
    "WEB_SEARCH",
    "FETCH_URL",
    "SEMANTIC_SEARCH",
    "SEARCH",
    "SUMMARIZE_FILE",
    "CLICKUP_UPDATE_TASK",
    "CLICKUP_ADD_COMMENT",
    "CLICKUP_CREATE_TASK",
}

# Keywords yang menandakan user memang ingin membuat/menulis file
_FILE_REQUEST_KEYWORDS = [
    "buat file", "tulis file", "buatkan file", "save", "simpan ke file",
    "export", "ekspor", "generate file", "buat dokumen", "tulis dokumen",
    "create file", "write file", "write to", "save to", "output file",
    "buat script", "buat kode", "tulis kode", "buat program",
    "buat laporan", "generate report",
]


def _user_wants_file(user_request: str) -> bool:
    """Cek apakah user secara eksplisit meminta pembuatan/penulisan file."""
    if not user_request:
        return False
    req = user_request.lower()
    return any(kw in req for kw in _FILE_REQUEST_KEYWORDS)


def _user_wants_execute(user_request: str) -> bool:
    """Cek apakah user secara eksplisit meminta eksekusi kode."""
    if not user_request:
        return False
    keywords = [
        "jalankan", "execute", "run", "eksekusi", "test", "coba jalan",
        "debug", "fix error", "perbaiki error", "buat script",
    ]
    req = user_request.lower()
    return any(kw in req for kw in keywords)


def _user_wants_update(user_request: str) -> bool:
    """Cek apakah user secara eksplisit meminta update/perubahan pada sesuatu."""
    if not user_request:
        return False
    keywords = [
        "update", "ubah", "perbarui", "edit", "ganti", "tambah",
        "tambahkan", "modify", "change", "set", "atur", "assign",
    ]
    req = user_request.lower()
    return any(kw in req for kw in keywords)


def execute_plan(
    plan: list[dict],
    task_id: Optional[str] = None,
    conv_id: Optional[str] = None,
    model: Optional[str] = None,
    user_request: str = "",
) -> tuple[list[dict], str]:
    """
    Executor AI Agent — mengerjakan plan dengan kemampuan berpikir.

    Returns: (results, final_response)
    final_response is "" when cancelled — caller must check pop_was_cancelled().
    """
    from agents.task_queue import update_task_step

    exec_model = model or DEFAULT_MODEL

    # Extract expected tool actions from plan (for completion tracking)
    plan_actions = [
        t.get("action", "").upper()
        for t in plan
        if t.get("action", "").upper() not in ("RESPOND", "DONE")
    ]

    plan_text = "\n".join(
        f"{t.get('step', i+1)}. {t.get('action', '?')}: {t.get('reason', '')} "
        f"(params: {t.get('params', {})})"
        for i, t in enumerate(plan)
    )

    # Fast path: plan is just a single RESPOND — no streaming needed
    if len(plan) == 1 and plan[0].get("action", "").upper() == "RESPOND":
        msg = plan[0].get("params", {}).get("message", "")
        return [{"step": 1, "action": "RESPOND", "result": msg}], msg

    exec_messages: list[dict] = [
        {"role": "system", "content": EXECUTOR_PROMPT},
        {"role": "user", "content": f"Rencana yang harus dikerjakan:\n{plan_text}\n\nMulai kerjakan dari langkah pertama."}
    ]

    # Log initial context size
    init_chars = sum(len(m["content"]) for m in exec_messages)
    print(f"\n  [EXECUTOR CONTEXT]")
    print(f"  Initial prompt chars: {init_chars:,}")
    print(f"  Messages: {len(exec_messages)}")

    results: list[dict] = []
    final_response = ""
    total_start = time.time()
    total_prompt_tokens = 0
    total_output_tokens = 0
    total_prompt_eval_s = 0.0
    total_gen_s = 0.0
    consecutive_errors = 0  # Circuit breaker: track consecutive tool errors

    for step in range(MAX_EXECUTOR_STEPS):

        print(f"\n  🤖 Executor (step {step + 1}):")

        # Log context size before each step
        ctx_chars = sum(len(m["content"]) for m in exec_messages)
        print(f"    Context size: {ctx_chars:,} chars ({len(exec_messages)} messages)")

        step_start = time.time()
        try:
            ai = _stream_chat(model=exec_model, messages=exec_messages, conv_id=conv_id)
        except _CancelledError:
            print(f"    ⛔ Dibatalkan user (step {step + 1})")
            break
        except Exception as e:
            elapsed = time.time() - step_start
            print(f"    ❌ Stream error: {e}  ({elapsed:.2f}s)")
            final_response = f"Error: {e}"
            break

        elapsed = time.time() - step_start

        # Accumulate telemetry
        total_prompt_tokens += ai.prompt_eval_count
        total_output_tokens += ai.eval_count
        total_prompt_eval_s += ai.prompt_eval_s
        total_gen_s += ai.eval_s

        # Tampilkan raw response dari AI untuk debugging
        print(f"    🧠 Raw AI response ({elapsed:.2f}s):")
        for line in ai.splitlines():
            print(f"       | {line}")

        # Print per-step telemetry
        _print_telemetry(f"EXECUTOR step {step + 1}", exec_model, ctx_chars, ai)

        # Tool parsing hanya setelah stream SELESAI penuh — tidak pada partial buffer
        if "[DONE]" in ai:
            done_idx = ai.index("[DONE]")
            final_response = ai[done_idx + 6:].strip()
        
            # If [DONE] is empty, synthesize from tool results
            if not final_response and results:
                success_results = [
                    r for r in results
                    if not str(r.get("result", "")).startswith("Error")
                    and r.get("action") not in ("RESPOND", "DONE")
                ]
                if success_results:
                    parts = []
                    for r in success_results[-3:]:  # last 3 successful results
                        action = r.get("action", "")
                        result = str(r.get("result", ""))[:300]
                        target = r.get("target", "")
                        parts.append(f"[{action}] {target}: {result}")
                    final_response = "\n".join(parts)
                    print(f"    \u26a0\ufe0f  Empty [DONE] — synthesized response from {len(success_results)} tool results")
        
            print(f"    \u2705 DONE: {final_response[:2000]}{'...' if len(final_response) > 2000 else ''}")
            if task_id:
                update_task_step(task_id, step, {
                    "step": step + 1, "action": "DONE", "result": final_response,
                })
            break

        # ── PRE-PARSE: detect intended tool BEFORE executing ──
        exec_text = ai  # may be modified by guards below

        # ── FIELD MUTATION GUARD: strip unintended params from CLICKUP_UPDATE_TASK ──
        update_match = _find_last(
            r'\[CLICKUP_UPDATE_TASK task_id="(.*?)"(?:\s+status="(.*?)")?(?:\s+priority="(.*?)")?(?:\s+name="(.*?)")?(?:\s+description="(.*?)")?\]',
            exec_text, re.DOTALL
        )
        if update_match:
            ai_status = update_match.group(2)
            ai_priority = update_match.group(3)
            ai_name = update_match.group(4)
            ai_description = update_match.group(5)
            included_fields = {k for k, v in {
                'status': ai_status, 'priority': ai_priority,
                'name': ai_name, 'description': ai_description,
            }.items() if v}

            # Determine which fields user explicitly asked to change
            req = user_request.lower()
            allowed_fields = set()
            if any(kw in req for kw in ['deskripsi', 'description', 'desc', 'keterangan', 'detail']):
                allowed_fields.add('description')
            if any(kw in req for kw in ['status', 'keadaan', 'progress']):
                allowed_fields.add('status')
            if any(kw in req for kw in ['priority', 'prioritas']):
                allowed_fields.add('priority')
            if any(kw in req for kw in ['nama', 'judul', 'title', 'rename']):
                allowed_fields.add('name')

            if allowed_fields and included_fields:
                extra_fields = included_fields - allowed_fields
                if extra_fields:
                    # Execute update DIRECTLY with only allowed fields (bypass f-string reconstruction)
                    tid = update_match.group(1)
                    print(f"    ⚠️  FIELD GUARD: stripped fields {extra_fields}, keeping {allowed_fields & included_fields}")
                    tool_result = clickup_smart_update_task(
                        tid,
                        status=ai_status if 'status' in allowed_fields else None,
                        priority=ai_priority if 'priority' in allowed_fields else None,
                        name=ai_name if 'name' in allowed_fields else None,
                        description=ai_description if 'description' in allowed_fields else None,
                    )
                    result_str = str(tool_result)
                    is_error = result_str.startswith("Error")
                    limit = 2000 if is_error else 1000
                    print(f"    🔧 [CLICKUP_UPDATE_TASK] → {tid} (filtered)")
                    print(f"    📄 {result_str[:limit]}{'...' if len(result_str) > limit else ''}")
                    results.append({
                        "step": step + 1,
                        "action": "CLICKUP_UPDATE_TASK",
                        "target": tid,
                        "result": tool_result,
                    })
                    if task_id:
                        update_task_step(task_id, step, results[-1])
                    exec_messages.append({"role": "assistant", "content": ai})
                    if is_error:
                        consecutive_errors += 1
                        if consecutive_errors >= 2:
                            print(f"    ⚠️  CIRCUIT BREAKER: {consecutive_errors} consecutive errors — forcing DONE")
                            exec_messages.append({"role": "user", "content": (
                                "Tool sudah gagal 2x berturut-turut. JANGAN coba lagi. "
                                "Tulis [DONE] dan jelaskan error yang terjadi beserta saran untuk user."
                            )})
                            consecutive_errors = 0
                        else:
                            exec_messages.append({"role": "user", "content": (
                                f"Error: {result_str}\n\n"
                                "Coba pendekatan LAIN. Jangan ulangi parameter yang sama. "
                                "Jika bingung, tulis [DONE] dengan penjelasan."
                            )})
                    else:
                        consecutive_errors = 0
                        exec_messages.append({"role": "user", "content": tool_result})
                    continue  # Skip normal _handle_tools flow

        # ── Now execute with (possibly cleaned) text ──
        tool_used, tool_name, tool_target, tool_result = _handle_tools(exec_text)

        # ── GUARD: Tolak WRITE_FILE jika user tidak minta file ──
        if tool_used and tool_name == "WRITE_FILE" and not _user_wants_file(user_request):
            print(f"    ⛔ GUARD: WRITE_FILE ditolak (user tidak meminta pembuatan file)")
            tool_used = False
            exec_messages.append({"role": "assistant", "content": ai})
            exec_messages.append({"role": "user", "content": "JANGAN buat file. Langsung tulis [DONE] diikuti jawaban Anda."})
            consecutive_errors = 0
            continue

        # ── GUARD: Tolak EXECUTE jika user tidak minta run code ──
        if tool_used and tool_name == "EXECUTE" and not _user_wants_execute(user_request):
            print(f"    ⛔ GUARD: EXECUTE ditolak (user tidak meminta eksekusi kode)")
            tool_used = False
            exec_messages.append({"role": "assistant", "content": ai})
            exec_messages.append({"role": "user", "content": "JANGAN jalankan file. Langsung tulis [DONE] diikuti jawaban Anda."})
            consecutive_errors = 0
            continue

        # ── GUARD: Tolak CLICKUP_CREATE_TASK jika user tidak minta buat task baru ──
        if tool_used and tool_name == "CLICKUP_CREATE_TASK" and not any(
            kw in user_request.lower()
            for kw in ['buat task', 'create task', 'tambah task', 'new task', 'task baru', 'buatkan task', 'add task']
        ):
            print(f"    ⛔ GUARD: CLICKUP_CREATE_TASK ditolak (user tidak meminta pembuatan task baru)")
            tool_used = False
            exec_messages.append({"role": "assistant", "content": ai})
            exec_messages.append({"role": "user", "content": "JANGAN buat task baru. Selesaikan permintaan awal atau tulis [DONE] dengan penjelasan."})
            consecutive_errors = 0
            continue

        if tool_used:
            print(f"    🔧 [{tool_name}] → {tool_target}")
            result_str = str(tool_result)
            is_error = result_str.startswith("Error")
            limit = 2000 if is_error else 1000
            print(f"    📄 {result_str[:limit]}{'...' if len(result_str) > limit else ''}")
            results.append({
                "step": step + 1,
                "action": tool_name,
                "target": tool_target,
                "result": tool_result,
            })
            if task_id:
                update_task_step(task_id, step, results[-1])
            exec_messages.append({"role": "assistant", "content": exec_text})

            # ── ERROR CIRCUIT BREAKER ──
            if is_error:
                consecutive_errors += 1
                if consecutive_errors >= 2:
                    print(f"    ⚠️  CIRCUIT BREAKER: {consecutive_errors} consecutive errors — forcing DONE")
                    exec_messages.append({"role": "user", "content": (
                        "Tool sudah gagal 2x berturut-turut. JANGAN coba lagi. "
                        "Tulis [DONE] dan jelaskan error yang terjadi beserta saran untuk user."
                    )})
                    consecutive_errors = 0
                else:
                    exec_messages.append({"role": "user", "content": (
                        f"Error: {result_str}\n\n"
                        "Coba pendekatan LAIN. Jangan ulangi parameter yang sama. "
                        "Jika bingung, tulis [DONE] dengan penjelasan."
                    )})
            else:
                consecutive_errors = 0
                exec_messages.append({"role": "user", "content": tool_result})

            # Check if all planned actions are done → hint model to write [DONE]
            done_actions = [r.get("action", "").upper() for r in results]
            if plan_actions and all(a in done_actions for a in plan_actions):
                exec_messages.append({"role": "user", "content": "Semua langkah rencana sudah selesai. Tulis [DONE] diikuti ringkasan hasil."})
                plan_actions = []  # prevent re-triggering
        else:
            print(f"    💭 (no tool used, asking AI to continue)")
            exec_messages.append({"role": "assistant", "content": ai})
            exec_messages.append({"role": "user", "content": "Lanjutkan. Gunakan tool yang sesuai, atau tulis [DONE] diikuti jawaban jika sudah selesai. JANGAN buat file."})

    total_elapsed = time.time() - total_start
    total_tps = total_output_tokens / total_gen_s if total_gen_s > 0 else 0

    print(f"\n  [EXECUTOR SUMMARY]")
    print(f"  Total time: {total_elapsed:.2f}s")
    print(f"  Tool calls: {len(results)}")
    print(f"  Total prompt tokens: {total_prompt_tokens:,}")
    print(f"  Total output tokens: {total_output_tokens:,}")
    print(f"  Total prompt eval: {total_prompt_eval_s:.1f}s")
    print(f"  Total generation: {total_gen_s:.1f}s")
    if total_tps > 0:
        print(f"  Avg TPS: {total_tps:.2f}")

    return results, final_response


# =========================
# RESPONDER
# =========================

def generate_response(
    user_message: str,
    results: list[dict],
    conv_id: Optional[str] = None,
    model: Optional[str] = None,
) -> str:
    """
    Phase 4: Responder — generate final answer from execution results.
    """
    if not results:
        return "Semua langkah selesai."

    if len(results) == 1 and results[0].get("action") == "RESPOND":
        return results[0]["result"]

    context_parts = []
    for r in results:
        action = r.get("action", "?")
        if action in ("RESPOND", "DONE"):
            continue
        result = str(r.get("result", ""))
        if len(result) > 2000:
            result = result[:2000] + "\n... (terpotong)"
        target = r.get("target", "")
        context_parts.append(f"[{action}({target})]:\n{result}")

    if not context_parts:
        return results[-1].get("result", "Selesai.")

    context = "\n\n".join(context_parts)
    resp_model = model or DEFAULT_MODEL
    print("\n  🤖 Responder generating answer...")

    resp_messages = [
        {
            "role": "system",
            "content": "You are an AI assistant. Based on the tool results, answer the user's question thoroughly and clearly. Respond in the same language the user used."
        },
        {
            "role": "user",
            "content": f"Pertanyaan user: {user_message}\n\nHasil eksekusi:\n{context}\n\nBerikan jawaban lengkap berdasarkan hasil di atas."
        }
    ]

    # Log context size
    resp_chars = sum(len(m["content"]) for m in resp_messages)
    print(f"  [RESPONDER CONTEXT]")
    print(f"  Prompt chars: {resp_chars:,}")
    print(f"  Tool results: {len(context_parts)}")

    resp_start = time.time()
    try:
        ai = _stream_chat(
            model=resp_model,
            messages=resp_messages,
            conv_id=conv_id,
        )
    except _CancelledError:
        return ""
    except Exception as e:
        logger.error("[responder] stream error: %s", e)
        return f"Error saat generate response: {e}"

    resp_elapsed = time.time() - resp_start

    # Print telemetry
    _print_telemetry("RESPONDER", resp_model, resp_chars, ai)

    # Tampilkan raw response Responder
    print(f"  🧠 Responder raw response:")
    for line in ai.splitlines():
        print(f"       | {line}")
    print()

    return ai
