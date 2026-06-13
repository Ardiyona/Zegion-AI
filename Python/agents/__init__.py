# agents/__init__.py
# Re-export semua fungsi agent

from agents.router import (
    detect_mode,
    parse_override,
    mode_label,
    MODE_CHAT,
    MODE_QUICK,
    MODE_DEEP,
)

from agents.planner import (
    create_plan,
    format_plan,
)

from agents.executor import (
    execute_plan,
    generate_response,
)

from agents.critic import (
    critique,
)

from agents.reflection import (
    reflect,
)

from agents.memory import (
    compress_memory,
)

from agents.cancel import (
    request_cancel,
    is_cancelled,
    clear_cancel,
    mark_cancelled,
    pop_was_cancelled,
    register_stream,
    unregister_stream,
)

from agents.task_queue import (
    create_task,
    complete_task,
    fail_task,
    get_pending_tasks,
    get_remaining_steps,
    format_pending_tasks,
    cleanup_completed,
)
