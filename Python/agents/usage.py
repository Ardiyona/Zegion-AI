"""Request-local token usage collector."""

import threading

_state = threading.local()


def start_usage(model: str) -> None:
    _state.data = {
        "model": model,
        "total_prompt_tokens": 0,
        "total_output_tokens": 0,
        "total_time_s": 0.0,
        "events": [],
    }


def record_usage(
    phase: str,
    model: str,
    prompt_tokens: int = 0,
    output_tokens: int = 0,
    prompt_eval_s: float = 0.0,
    generation_s: float = 0.0,
    duration_s: float = 0.0,
    prompt_chars: int = 0,
) -> None:
    data = getattr(_state, "data", None)
    if data is None:
        return

    event = {
        "phase": phase,
        "model": model,
        "prompt_tokens": int(prompt_tokens or 0),
        "output_tokens": int(output_tokens or 0),
        "prompt_eval_s": round(float(prompt_eval_s or 0), 3),
        "generation_s": round(float(generation_s or 0), 3),
        "duration_s": round(float(duration_s or prompt_eval_s + generation_s or 0), 3),
        "prompt_chars": int(prompt_chars or 0),
    }
    data["events"].append(event)
    data["total_prompt_tokens"] += event["prompt_tokens"]
    data["total_output_tokens"] += event["output_tokens"]
    data["total_time_s"] = round(data["total_time_s"] + event["duration_s"], 3)


def get_usage() -> dict:
    data = getattr(_state, "data", None)
    if data is None:
        return {}
    return {
        "model": data.get("model", ""),
        "total_prompt_tokens": data.get("total_prompt_tokens", 0),
        "total_output_tokens": data.get("total_output_tokens", 0),
        "total_time_s": data.get("total_time_s", 0.0),
        "events": list(data.get("events", [])),
    }


def clear_usage() -> None:
    if hasattr(_state, "data"):
        del _state.data
