# 🤖 Zegion AI

**AI Agent lokal yang berjalan 100% di komputer Anda.** Tidak perlu API cloud, tidak ada biaya bulanan. Cukup Ollama + GPU.

Zegion adalah multi-agent AI assistant yang bisa membaca, menulis, dan menjalankan kode — serta terintegrasi dengan ClickUp untuk manajemen task.

> Dibuat oleh **Ardiyona**

---

## ✨ Fitur

- 🧠 **Multi-Agent Pipeline** — Planner → Executor → Critic → Reflection → Responder
- 🔀 **3 Mode Otomatis** — Chat / Quick / Deep, dipilih otomatis oleh Router
- 🌐 **Web UI Modern** — Antarmuka chat interaktif (React) dengan Conversation History
- 📚 **Knowledge Base** — Ingatan jangka panjang (Episodic Memory) berbasis SQLite
- 🔎 **Semantic Search** — Cari kode berdasarkan makna, bukan keyword
- 💾 **Task Queue** — Task disimpan, bisa dilanjutkan setelah restart
- 📋 **ClickUp Integration** — Manajemen task dari chat dengan cache super cepat
- 🔒 **Workspace Lock** — Hanya akses 1 workspace ClickUp yang dikonfigurasi
- ⚡ **100% Lokal** — Semua diproses di komputer Anda via Ollama

## 🏗️ Arsitektur

```
User Input
    │
    ▼
┌─────────────────────────┐
│ 🔀 ROUTER (rule-based)  │  ← Instan, tanpa AI
└────┬───────┬───────┬────┘
     │       │       │
     ▼       ▼       ▼
  💬 Chat  ⚡ Quick  🔬 Deep
  1x AI    2-3x AI   5-7x AI
     │       │       │
     │       │       ├→ Planner
     │       ├→ Plan ├→ Executor
     │       ├→ Exec ├→ Critic (fix loop)
     │       ├→ Resp ├→ Reflection (improve)
     │       │       ├→ Responder
     ▼       ▼       ▼
         AI Response
```

| Mode | Pipeline | Cocok Untuk |
|---|---|---|
| 💬 **Chat** | Langsung ke model | Sapaan, tanya jawab, diskusi |
| ⚡ **Quick** | Planner → Executor → Responder | Buat file, baca file, task simpel |
| 🔬 **Deep** | Full pipeline + Critic + Reflection | Coding, debugging, refactoring |

## 📋 Prasyarat

- **Python** 3.10+
- **Ollama** — [Download di sini](https://ollama.com/download)
- **GPU** — Minimal 4GB VRAM (direkomendasikan)

## 🚀 Instalasi

### 1. Clone repository

```bash
git clone https://github.com/Ardiyona/Zegion-AI.git
cd Zegion-AI/Python
```

### 2. Install Ollama & model

```bash
# Install Ollama dari https://ollama.com/download
# Lalu download model:
ollama pull qwen3:4b
ollama pull nomic-embed-text
```

### 3. Install dependencies Python

```bash
pip install -r requirements.txt
```

### 4. Setup environment

```bash
# Copy template environment
cp .env.example .env

# Edit .env sesuai kebutuhan (opsional)
```

### 5. Jalankan Web UI (Direkomendasikan)

Buka 2 terminal terpisah.

**Terminal 1 (Backend API):**
```bash
cd Zegion-AI/Python
python api.py
```

**Terminal 2 (Frontend React):**
```bash
cd Zegion-AI/web
npm install
npm run dev
```

Buka browser dan akses **`http://localhost:5173`**.

### 6. Jalankan Terminal UI (Alternatif CLI)

Jika hanya ingin versi terminal (tanpa Web UI):
```bash
cd Zegion-AI/Python
python main.py
```

## ⚙️ Konfigurasi

Edit file `.env` untuk mengubah pengaturan:

```env
# Model (ganti jika punya GPU lebih besar)
DEFAULT_MODEL=qwen3:4b
EMBEDDING_MODEL=nomic-embed-text

# Pipeline tuning
MAX_CRITIC_RETRIES=2
MAX_REFLECT_RETRIES=1

# ClickUp (opsional)
CLICKUP_API_KEY=pk_your_api_key
CLICKUP_WORKSPACE_ID=your_workspace_id
```

### Mendapatkan ClickUp API Key (Opsional)

1. Buka https://app.clickup.com/settings/apps
2. Klik **Generate** untuk membuat Personal API Token
3. Copy token, paste ke `CLICKUP_API_KEY` di `.env`
4. Untuk Workspace ID, jalankan Zegion lalu ketik: `lihat space di clickup`

## 💬 Cara Penggunaan

### Perintah Dasar

```
You: halo                          → 💬 Chat Mode
You: buatkan file calculator.py    → ⚡ Quick Mode
You: refactor seluruh project      → 🔬 Deep Mode
```

### Override Mode Manual

```
You: /chat jelaskan apa itu python   → Paksa Chat Mode
You: /quick buat file test.py        → Paksa Quick Mode
You: /deep buatkan calculator.py     → Paksa Deep Mode
```

### Perintah Sistem

| Perintah | Fungsi |
|---|---|
| `exit` | Keluar dari program |
| `resume` | Lanjutkan task yang tertunda |

### Contoh ClickUp

```
You: lihat space di clickup
You: lihat task di list ID 12345
You: buat task "Fix bug login" di list 12345 priority high
You: update task abc123 status "in progress"
```

## 📁 Struktur Project

```
├── Python/
│   ├── api.py               # FastAPI Server (WebSocket + REST)
│   ├── main.py              # Terminal UI (CLI)
│   ├── core.py              # Logika inti pipeline AI
│   ├── db.py                # Database layer (SQLite) & Knowledge Base
│   ├── config.py            # Konfigurasi
│   ├── requirements.txt     
│   │
│   ├── agents/              # 🤖 AI Agents (Router, Planner, Executor, Critic, dll)
│   ├── tools/               # 🔧 Tool functions (File Ops, ClickUp, Semantic)
│   │
│   └── data/                # 💾 Auto-generated data
│       └── zegion.db        # SQLite database (History & Knowledge Base)
│
└── web/                     # 🌐 Frontend React (Vite)
    ├── src/
    │   ├── components/      # UI (Sidebar, ChatInput, MessageList)
    │   ├── hooks/           # useChat (WebSocket state manager)
    │   └── index.css        # Premium Dark Theme
    ├── package.json
    └── index.html
```

## 🔧 Tools yang Tersedia

### File Tools
| Tool | Fungsi |
|---|---|
| `READ_FILE` | Membaca isi file |
| `WRITE_FILE` | Menulis/membuat file |
| `LIST_FILES` | Daftar file di direktori |
| `SEARCH` | Cari keyword dalam file |
| `EXECUTE` | Jalankan script Python |
| `SUMMARIZE_FILE` | Ringkasan file dengan AI |
| `SEMANTIC_SEARCH` | Cari kode berdasarkan makna |

### ClickUp Tools
| Tool | Fungsi |
|---|---|
| `CLICKUP_LIST_SPACES` | Lihat semua Space |
| `CLICKUP_LIST_LISTS` | Lihat List di Space |
| `CLICKUP_LIST_TASKS` | Lihat task di List |
| `CLICKUP_GET_TASK` | Detail 1 task |
| `CLICKUP_CREATE_TASK` | Buat task baru |
| `CLICKUP_UPDATE_TASK` | Update status/priority task |
| `CLICKUP_ADD_COMMENT` | Tambah comment ke task |

## 🔒 Keamanan

- API key disimpan di `.env` yang di-gitignore
- ClickUp hanya bisa akses **1 workspace** yang dikonfigurasi
- **Tidak ada fungsi delete** — by design, untuk mencegah kerusakan data
- Semua proses berjalan lokal, tidak ada data yang dikirim ke cloud (kecuali ClickUp API)

## 🖥️ Spesifikasi Minimum

| Komponen | Minimum | Rekomendasi |
|---|---|---|
| GPU VRAM | 4 GB | 6+ GB |
| RAM | 8 GB | 16 GB |
| Storage | 5 GB | 10 GB |
| Python | 3.10 | 3.12+ |
| OS | Windows / Linux / macOS | — |

## 📝 Lisensi

MIT License — Bebas digunakan dan dimodifikasi.

## 🙏 Credit

- **Model**: [Qwen3:4b](https://ollama.com/library/qwen3) by Alibaba
- **Embeddings**: [nomic-embed-text](https://ollama.com/library/nomic-embed-text) by Nomic AI
- **Runtime**: [Ollama](https://ollama.com/)

---

<p align="center">
  <b>Zegion AI</b> — Your local AI agent, by Ardiyona 🚀
</p>
