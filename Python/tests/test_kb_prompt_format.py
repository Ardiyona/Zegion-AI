from db import _format_kb_content_for_prompt


assert _format_kb_content_for_prompt('{"tasks_touched":["86abc123"],"actions":["updated status to in progress"],"key_decisions":["keep JSON storage"],"user_info_detected":[]}') == [
    "Task terkait: 86abc123",
    "Aksi sebelumnya: updated status to in progress",
    "Keputusan: keep JSON storage",
]

assert _format_kb_content_for_prompt('{"user_profile":{"name":"User name: Dhiya","role":"Developer","preferences":["prefers concise answers"],"projects":["Zegion-AI"],"tech_stack":["Python"]},"long_term_context":["uses Ollama"]}') == [
    "Nama user: User name: Dhiya",
    "Role user: Developer",
    "Preferensi user: prefers concise answers",
    "Project aktif: Zegion-AI",
    "Tech stack user: Python",
    "Konteks jangka panjang: uses Ollama",
]

assert _format_kb_content_for_prompt('plain remembered fact') == ["plain remembered fact"]
assert _format_kb_content_for_prompt('{"tasks_touched": ["86abc123", 1, ""]}') == ["Task terkait: 86abc123"]
