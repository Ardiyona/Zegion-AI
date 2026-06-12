"""
main.py — Zegion AI Terminal Interface
Jalankan: python main.py
"""

from agents import (
    get_pending_tasks,
    format_pending_tasks,
)
from agents.router import mode_label
from config import AGENT_NAME

from core import initialize, handle_message


# =========================
# STARTUP
# =========================

project_index, messages = initialize()

pending = get_pending_tasks()
if pending:
    print(format_pending_tasks(pending))
else:
    print(f"{AGENT_NAME} Siap! 😼")

print("Commands: exit | resume | /chat | /quick | /deep\n")


# =========================
# MAIN LOOP (Terminal UI)
# =========================

while True:
    try:
        user = input("You: ")
    except (KeyboardInterrupt, EOFError):
        print("\nSampai jumpa! 👋")
        break

    if not user.strip():
        continue

    if user.lower() == "exit":
        print("Sampai jumpa! 👋")
        break

    # Delegate semua logic ke core
    response, messages, mode, plan = handle_message(user, messages, project_index)

    print(f"\n[{mode_label(mode)}]")
    print("\n" + "=" * 40)
    print("AI:")
    print(response)
    print("=" * 40 + "\n")