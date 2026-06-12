"""
api.py — Zegion AI FastAPI Server
Jalankan: python api.py
"""

import asyncio
import json
import os
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from agents.router import mode_label
from config import AGENT_NAME, AGENT_VERSION
from core import handle_message, load_memory


# =========================
# GLOBAL STATE
# =========================

_state = {
    "project_index": "",
    "messages": [],
    "ready": False,
}


# =========================
# LIFESPAN (startup/shutdown)
# =========================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Startup ringan — hanya load memory dari file.
    Build index/embeddings dilakukan lazy saat pesan pertama masuk.
    """
    print(f"\n[Zegion] {AGENT_NAME} v{AGENT_VERSION} API starting...")

    # Load memory dari disk (cepat, tidak butuh Ollama)
    _state["messages"] = load_memory()
    _state["project_index"] = ""
    _state["ready"] = True

    print(f"[Zegion] API ready at http://localhost:8000")
    print(f"[Zegion] Open http://localhost:8000 or React at http://localhost:5173\n")
    yield
    print(f"[Zegion] {AGENT_NAME} shutting down...")


# =========================
# FASTAPI APP
# =========================

app = FastAPI(
    title=f"{AGENT_NAME} AI API",
    version=AGENT_VERSION,
    lifespan=lifespan,
)

# CORS — izinkan React dev server (localhost:5173 / 3000)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000", "http://localhost:8000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# =========================
# REST ENDPOINTS
# =========================

@app.get("/")
async def root():
    return {"name": AGENT_NAME, "version": AGENT_VERSION, "status": "ready" if _state["ready"] else "initializing"}


@app.get("/status")
async def status():
    return {
        "ready": _state["ready"],
        "memory_count": len(_state["messages"]),
    }


@app.get("/history")
async def get_history():
    """Return riwayat percakapan (hanya user + assistant, bukan system)."""
    history = [
        {"role": msg["role"], "content": msg["content"]}
        for msg in _state["messages"]
        if msg["role"] in ("user", "assistant")
    ]
    return {"history": history}


@app.delete("/history")
async def clear_history():
    """Hapus semua riwayat percakapan."""
    _state["messages"] = []
    return {"status": "cleared"}


# =========================
# WEBSOCKET CHAT
# =========================

@app.websocket("/ws")
async def websocket_chat(websocket: WebSocket):
    """
    WebSocket endpoint untuk chat realtime.

    Client kirim: {"message": "halo"}
    Server kirim:
      {"type": "thinking", "mode": "💬 Chat"}
      {"type": "response", "text": "...", "mode": "💬 Chat", "plan": [...]}
      {"type": "error", "text": "..."}
    """
    await websocket.accept()
    print(f"[WS] Client connected")

    try:
        while True:
            # Terima pesan dari React
            raw = await websocket.receive_text()

            try:
                data = json.loads(raw)
                user_input = data.get("message", "").strip()
            except json.JSONDecodeError:
                user_input = raw.strip()

            if not user_input:
                continue

            print(f"[WS] User: {user_input[:80]}")

            # Kirim status "sedang berpikir"
            await websocket.send_json({
                "type": "thinking",
                "text": "Zegion sedang berpikir...",
            })

            # Proses di thread terpisah agar tidak block WebSocket
            loop = asyncio.get_event_loop()
            try:
                response, new_messages, mode, plan = await loop.run_in_executor(
                    None,
                    handle_message,
                    user_input,
                    _state["messages"],
                    _state["project_index"],
                )
                # Update global state
                _state["messages"] = new_messages

            except Exception as e:
                print(f"[WS] Error: {e}")
                await websocket.send_json({
                    "type": "error",
                    "text": f"Terjadi error: {str(e)}",
                })
                continue

            # Kirim response ke React
            await websocket.send_json({
                "type": "response",
                "text": response,
                "mode": mode_label(mode),
                "mode_key": mode,
                "plan": plan,
            })

            print(f"[WS] Response sent ({mode_label(mode)})")

    except WebSocketDisconnect:
        print("[WS] Client disconnected")
    except Exception as e:
        print(f"[WS] Unexpected error: {e}")


# =========================
# ENTRYPOINT
# =========================

if __name__ == "__main__":
    uvicorn.run(
        "api:app",
        host="0.0.0.0",
        port=8000,
        reload=False,
        log_level="info",
    )
