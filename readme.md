# Bookly CX AI Agent

A conversational AI customer support agent prototype for **Bookly**, a fictional online bookstore. Built as part of a Solutions Engineering assignment for Decagon AI.

The agent handles order status inquiries, return/refund requests, and proactive post-resolution outreach — with a human-in-the-loop operator inbox for high-value cases.

---

## Features

- Multi-turn web chat with photo upload support
- MCP tool integration (orders, returns, knowledge base, procedures, memory)
- Human-in-the-loop operator inbox for orders over $300
- Curated Exceptional Procedures — operators inject one-time resolutions at review time
- Cross-session memory per customer contact
- Proactive WhatsApp outreach via Twilio on case approval
- Prompt injection guardrails (pre-LLM interception)

---

## Prerequisites

- Python 3.11+
- Node.js (for docx generation only, optional)
- A Twilio account with WhatsApp sandbox enabled (optional — app runs without it)

---

## Setup

### 1. Clone the repo

```bash
git clone <repo-url>
cd bookly-cx-agent
```

### 2. Create and activate a virtual environment

```bash
python -m venv .venv
source .venv/bin/activate        # Mac/Linux
.venv\Scripts\activate           # Windows
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure environment variables

Create a `.env` file in the project root:

```env
# Required
ANTHROPIC_API_KEY=sk-ant-...

# Optional — WhatsApp outreach via Twilio
TWILIO_ACCOUNT_SID=ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
TWILIO_AUTH_TOKEN=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
TWILIO_WHATSAPP_FROM=whatsapp:+14155238886
TWILIO_TO_NUMBER=+1XXXXXXXXXX
```

> If Twilio variables are not set, the app runs in simulated mode — the outreach message appears in the `/sms` page but no real message is sent.

---

## Run

```bash
uvicorn main:app --reload
```

The app starts at `http://127.0.0.1:8000`.

---

## Pages

| URL | Description |
|-----|-------------|
| `/` | Customer web chat |
| `/inbox` | Operator inbox — human-in-loop review |
| `/sms` | Simulated WhatsApp outreach thread |

---

## Demo scenario

1. Go to `/` and start a chat as a customer
2. Use contact `test@example.com` or phone `5551234567`
3. Request a return for order **BK-1003** ($389.95) — this triggers human review
4. Upload a photo of the item when prompted
5. Go to `/inbox` — approve the case and optionally add a Curated Exceptional Procedure
6. The WhatsApp outreach message fires (real if Twilio is configured, simulated at `/sms` otherwise)

---

## Project structure

```
bookly-cx-agent/
├── main.py                  # FastAPI app — routes and background tasks
├── agent/
│   ├── chat.py              # Main chat agent — agentic loop + system prompt
│   ├── sms.py               # Outreach agent — proactive WhatsApp follow-up
│   └── guardrails.py        # Input guardrails — prompt injection detection
├── mcp_server/
│   ├── tools.py             # MCP tool server (orders, returns, memory, etc.)
│   ├── procedures.md        # Operational procedure library
│   └── knowledge_base.md   # Policy knowledge base
├── frontend/
│   ├── index.html           # Customer chat UI
│   ├── inbox.html           # Operator inbox
│   └── sms.html             # Simulated SMS thread
├── requirements.txt
└── .env                     # Not committed — see setup above
```

---

## Notes

- All data (tasks, memory, images, sessions) is reset on every server restart — intentional for demo purposes
- Mock customer data: `test@example.com` / `5551234567`
- The agent uses `claude-opus-4-6` by default — update `model` in `chat.py` and `sms.py` to switch