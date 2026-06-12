"""
api.py — Zegion AI FastAPI Server
Jalankan: python api.py
"""

import asyncio
import json

import uvicorn
from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from agents.router import mode_label
from config import AGENT_NAME, AGENT_VERSION
from core import handle_message, quick_init
from db import (
    init_db,
    create_conversation,
    get_conversation,
    list_conversations,
    get_messages,
    delete_conversation,
)


# =========================
# GLOBAL STATE
# =========================

_state = {
    "project_index": "",
    "ready": False,
}


# =========================
# LIFESPAN
# =========================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup ringan: init DB + migrasi JSON lama. Tanpa Ollama."""
    print(f"\n[Zegion] {AGENT_NAME} v{AGENT_VERSION} API starting...")
    quick_init()
    _state["ready"] = True
    print(f"[Zegion] API ready at http://localhost:8000")
    print(f"[Zegion] React UI at http://localhost:5173\n")
    yield
    print(f"[Zegion] {AGENT_NAME} shutting down...")


# =========================
# APP
# =========================

app = FastAPI(
    title=f"{AGENT_NAME} AI API",
    version=AGENT_VERSION,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000", "http://localhost:8000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# =========================
# GENERAL ENDPOINTS
# =========================

@app.get("/")
async def root():
    return {
        "name": AGENT_NAME,
        "version": AGENT_VERSION,
        "status": "ready" if _state["ready"] else "initializing",
    }


@app.get("/status")
async def status():
    return {"ready": _state["ready"]}


# =========================
# CONVERSATION ENDPOINTS
# =========================

@app.get("/conversations")
async def get_conversations():
    """List semua conversation, diurutkan dari terbaru."""
    convs = list_conversations(limit=100)
    return {"conversations": convs}


@app.post("/conversations")
async def new_conversation():
    """Buat conversation baru (kosong)."""
    conv = create_conversation()
    return conv


@app.get("/conversations/{conv_id}")
async def get_conversation_detail(conv_id: str):
    """Detail 1 conversation."""
    conv = get_conversation(conv_id)
    if not conv:
        return {"error": "Conversation not found"}, 404
    return conv


@app.get("/conversations/{conv_id}/messages")
async def get_conversation_messages(conv_id: str):
    """Ambil semua messages dari 1 conversation."""
    conv = get_conversation(conv_id)
    if not conv:
        return {"error": "Conversation not found"}
    msgs = get_messages(conv_id)
    return {"messages": msgs}


@app.delete("/conversations/{conv_id}")
async def delete_conv(conv_id: str):
    """Hapus conversation beserta semua messages-nya."""
    ok = delete_conversation(conv_id)
    return {"deleted": ok}


# =========================
# WEBSOCKET CHAT
# =========================

@app.websocket("/ws/{conv_id}")
async def websocket_chat(websocket: WebSocket, conv_id: str):
    """
    WebSocket per conversation.

    Client kirim: {"message": "halo"}
    Server kirim:
      {"type": "thinking"}
      {"type": "response", "text": "...", "mode": "...", "mode_key": "...", "plan": [...], "conv_id": "..."}
      {"type": "error", "text": "..."}
    """
    await websocket.accept()
    print(f"[WS] Client connected → conv: {conv_id[:8]}...")

    try:
        while True:
            raw = await websocket.receive_text()

            try:
                data = json.loads(raw)
                user_input = data.get("message", "").strip()
            except json.JSONDecodeError:
                user_input = raw.strip()

            if not user_input:
                continue

            print(f"[WS] [{conv_id[:8]}] User: {user_input[:60]}")

            await websocket.send_json({"type": "thinking"})

            loop = asyncio.get_event_loop()
            try:
                response, new_conv_id, mode, plan = await loop.run_in_executor(
                    None,
                    handle_message,
                    user_input,
                    conv_id,
                    _state["project_index"],
                )
            except Exception as e:
                print(f"[WS] Error: {e}")
                await websocket.send_json({"type": "error", "text": str(e)})
                continue

            await websocket.send_json({
                "type": "response",
                "text": response,
                "mode": mode_label(mode),
                "mode_key": mode,
                "plan": plan,
                "conv_id": new_conv_id,
            })

            print(f"[WS] [{conv_id[:8]}] Done ({mode_label(mode)})")

    except WebSocketDisconnect:
        print(f"[WS] Client disconnected → conv: {conv_id[:8]}")
    except Exception as e:
        print(f"[WS] Error: {e}")


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
