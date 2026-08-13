from unittest.mock import patch

from agents.usage import start_usage, get_usage, clear_usage
from core import try_clickup_fast_path


with patch("core.clickup_get_tasks", return_value="tasks") as get_tasks:
    start_usage("test-model")
    plan, results, response = try_clickup_fast_path("bisa list semua task yang ada di clickup?")
    usage = get_usage()
    clear_usage()

    assert plan == [{
        "step": 1,
        "action": "CLICKUP_GET_TASKS",
        "params": {},
        "reason": "Direct read-only intent match",
    }]
    assert results == [{"step": 1, "action": "CLICKUP_GET_TASKS", "target": "all", "result": "tasks"}]
    assert response == "tasks"
    assert usage["total_prompt_tokens"] == 0
    assert usage["total_output_tokens"] == 0
    assert usage["events"] == []
    get_tasks.assert_called_once_with(status=None)

with patch("core.clickup_get_tasks") as get_tasks:
    assert try_clickup_fast_path("buat task baru di clickup") is None
    get_tasks.assert_not_called()

with patch("core.clickup_get_tasks", return_value="done tasks") as get_tasks:
    plan, results, response = try_clickup_fast_path("list task done di clickup")
    assert plan[0]["params"] == {"status": "complete"}
    assert results[0]["target"] == "complete"
    assert response == "done tasks"
    get_tasks.assert_called_once_with(status="complete")

with patch("core.clickup_get_tasks") as get_tasks:
    assert try_clickup_fast_path("lihat task yang tadi") is None
    get_tasks.assert_not_called()

with patch("core.clickup_get_task_detail", return_value="detail") as get_detail:
    plan, results, response = try_clickup_fast_path("lihat detail task 86exy7dku")
    assert plan[0]["action"] == "CLICKUP_GET_TASK_DETAIL"
    assert results[0]["target"] == "86exy7dku"
    assert response == "detail"
    get_detail.assert_called_once_with("86exy7dku")
