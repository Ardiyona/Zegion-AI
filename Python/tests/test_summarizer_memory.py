from agents import summarizer as summarizer_module
from agents.summarizer import (
    _ensure_list_of_strings,
    _normalize_user_info,
    _normalize_work_summary,
    _parse_summary_json,
    _should_extract_user_info,
    _update_global_user_profile,
)


assert _parse_summary_json('Here is JSON: {"tasks_touched": ["86abc12"], "actions": []}') == {
    "tasks_touched": ["86abc12"],
    "actions": [],
}

assert _ensure_list_of_strings(["  A   B  ", "a b", "", 1, None, "C"]) == ["A B", "C"]

assert _normalize_work_summary({
    "tasks_touched": ["86abc12", "86ABC12"],
    "actions": ["fixed parser"],
    "key_decisions": ["use raw_decode"],
    "user_info_detected": ["should be ignored"],
}) == {
    "tasks_touched": ["86abc12"],
    "actions": ["fixed parser"],
    "key_decisions": ["use raw_decode"],
    "user_info_detected": [],
}

assert _normalize_user_info({
    "user_info_detected": [
        "User prefers concise Indonesian answers",
        "Assistant fixed middleware",
        "User prefers concise Indonesian answers",
    ]
}) == ["User prefers concise Indonesian answers"]

assert _should_extract_user_info("[USER]: saya prefer jawaban singkat") is True
assert _should_extract_user_info("[USER]: pakai JWT untuk auth\n[ASSISTANT]: sudah saya ubah middleware") is False

saved_profiles = []
summarizer_module._load_global_profile = lambda: {
    "user_profile": {"name": "", "role": "", "preferences": [], "projects": [], "tech_stack": []},
    "long_term_context": [],
}
summarizer_module._save_global_profile = saved_profiles.append

_update_global_user_profile(["User tidak suka Python", "User prefers concise answers"])

assert saved_profiles == [{
    "user_profile": {"name": "", "role": "", "preferences": [], "projects": [], "tech_stack": []},
    "long_term_context": ["User tidak suka Python", "User prefers concise answers"],
}]
