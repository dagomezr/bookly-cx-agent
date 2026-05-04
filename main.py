import base64 as b64lib
import json
import os
import shutil
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from dotenv import load_dotenv
from agent.chat import chat
from agent.sms import sms_chat
from agent.guardrails import is_prompt_injection, flag_security_event, INJECTION_RESPONSE

load_dotenv()

app = FastAPI()

app.mount("/static", StaticFiles(directory="frontend"), name="static")

# Clear images, inbox, memory, and SMS sessions on every startup (demo mode)
if os.path.exists("images"):
    shutil.rmtree("images")
os.makedirs("images")
with open("tasks.json", "w") as _f:
    _f.write("[]")
with open("memory.json", "w") as _f:
    _f.write("{}")
with open("sms_sessions.json", "w") as _f:
    _f.write("{}")

# Serve locally saved customer photos for the operator inbox
app.mount("/images", StaticFiles(directory="images"), name="images")

TASKS_PATH       = "tasks.json"
MEMORY_PATH      = "memory.json"
SMS_SESSIONS_PATH = "sms_sessions.json"


# --- Helpers ---

def load_tasks() -> list:
    if not os.path.exists(TASKS_PATH):
        return []
    with open(TASKS_PATH, "r") as f:
        return json.load(f)


def save_tasks(tasks: list):
    with open(TASKS_PATH, "w") as f:
        json.dump(tasks, f, indent=2)


def load_memory() -> dict:
    if not os.path.exists(MEMORY_PATH):
        return {}
    with open(MEMORY_PATH, "r") as f:
        return json.load(f)


def load_sms_sessions() -> dict:
    if not os.path.exists(SMS_SESSIONS_PATH):
        return {}
    with open(SMS_SESSIONS_PATH, "r") as f:
        return json.load(f)


def save_sms_sessions(sessions: dict):
    with open(SMS_SESSIONS_PATH, "w") as f:
        json.dump(sessions, f, indent=2)


# --- Routes ---

@app.get("/")
def root():
    return FileResponse("frontend/index.html")


@app.get("/inbox")
def inbox():
    return FileResponse("frontend/inbox.html")


@app.get("/sms")
def sms_page():
    return FileResponse("frontend/sms.html")


@app.get("/api/tasks")
def get_tasks():
    return load_tasks()


@app.post("/api/tasks/{ticket_id}/decision")
async def decide_task(ticket_id: str, body: dict, background_tasks: BackgroundTasks):
    tasks = load_tasks()
    for task in tasks:
        if task["ticket_id"] == ticket_id:
            decision = body.get("decision")
            if decision not in ("approved", "rejected"):
                raise HTTPException(status_code=400, detail="decision must be 'approved' or 'rejected'")
            task["status"] = decision
            task["procedure"] = body.get("procedure", None)
            save_tasks(tasks)

            # If approved, generate the SMS opening message in the background
            # so the inbox response returns immediately
            if decision == "approved":
                background_tasks.add_task(start_sms_session, task)

            return {"ok": True, "ticket_id": ticket_id, "status": decision}
    raise HTTPException(status_code=404, detail="Task not found")


async def start_sms_session(task: dict):
    """Generate the opening proactive message and create the SMS session."""
    # Load customer memory by contact (try email then phone from order mock)
    memory = load_memory()
    contact = task.get("order_id", "")  # fallback
    # Search memory for any key related to this task
    customer_memory = {}
    for key, val in memory.items():
        customer_memory = val
        contact = key
        break  # demo: one customer at a time

    # Generate opening message from the SMS agent
    opening_message = await sms_chat(
        user_message=None,
        history=[],
        task=task,
        memory=customer_memory
    )

    sessions = load_sms_sessions()
    sessions["active"] = {
        "ticket_id": task["ticket_id"],
        "contact": contact,
        "history": [
            {"role": "assistant", "content": opening_message}
        ],
        "task": task,
        "memory": customer_memory
    }
    save_sms_sessions(sessions)


@app.get("/api/sms/active")
def get_active_sms():
    sessions = load_sms_sessions()
    if "active" not in sessions:
        return {"active": False}
    return {"active": True, **sessions["active"]}


@app.post("/api/sms/reply")
async def sms_reply(body: dict):
    user_message = body.get("message", "").strip()
    if not user_message:
        raise HTTPException(status_code=400, detail="Message is required")

    sessions = load_sms_sessions()
    if "active" not in sessions:
        raise HTTPException(status_code=404, detail="No active SMS session")

    session = sessions["active"]
    history = session["history"]

    # Call the SMS agent with full history + context
    agent_response = await sms_chat(
        user_message=user_message,
        history=history,
        task=session["task"],
        memory=session["memory"]
    )

    # Update history server-side
    history.append({"role": "user", "content": user_message})
    history.append({"role": "assistant", "content": agent_response})
    session["history"] = history
    sessions["active"] = session
    save_sms_sessions(sessions)

    return {"response": agent_response}


@app.post("/chat")
async def chat_endpoint(body: dict):
    user_message = body.get("message", "") or ""
    conversation_history = body.get("history", [])
    image = body.get("image")

    # --- Guardrail: prompt injection check ---
    if user_message and is_prompt_injection(user_message):
        flag_security_event(user_message, conversation_history)
        return {"response": INJECTION_RESPONSE}

    if image:
        media_type = image.get("media_type", "image/jpeg")
        ext = media_type.split("/")[-1].replace("jpeg", "jpg")
        filepath = os.path.join("images", f"pending.{ext}")
        with open(filepath, "wb") as f:
            f.write(b64lib.b64decode(image["base64"]))

    response = await chat(user_message, conversation_history, image)
    return {"response": response}