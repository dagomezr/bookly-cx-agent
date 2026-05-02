import base64 as b64lib
import json
import os
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from dotenv import load_dotenv
from agent.chat import chat

load_dotenv()

app = FastAPI()

app.mount("/static", StaticFiles(directory="frontend"), name="static")

# Clear images folder and inbox on every startup (demo mode)
import shutil
if os.path.exists("images"):
    shutil.rmtree("images")
os.makedirs("images")
with open("tasks.json", "w") as _f:
    _f.write("[]")

# Serve locally saved customer photos for the operator inbox
app.mount("/images", StaticFiles(directory="images"), name="images")

TASKS_PATH = "tasks.json"


def load_tasks() -> list:
    if not os.path.exists(TASKS_PATH):
        return []
    with open(TASKS_PATH, "r") as f:
        return json.load(f)


def save_tasks(tasks: list):
    with open(TASKS_PATH, "w") as f:
        json.dump(tasks, f, indent=2)


@app.get("/")
def root():
    return FileResponse("frontend/index.html")


@app.get("/inbox")
def inbox():
    return FileResponse("frontend/inbox.html")


@app.get("/api/tasks")
def get_tasks():
    return load_tasks()


@app.post("/api/tasks/{ticket_id}/decision")
async def decide_task(ticket_id: str, body: dict):
    tasks = load_tasks()
    for task in tasks:
        if task["ticket_id"] == ticket_id:
            decision = body.get("decision")
            if decision not in ("approved", "rejected"):
                raise HTTPException(status_code=400, detail="decision must be 'approved' or 'rejected'")
            task["status"] = decision
            task["procedure"] = body.get("procedure", None)
            save_tasks(tasks)
            return {"ok": True, "ticket_id": ticket_id, "status": decision}
    raise HTTPException(status_code=404, detail="Task not found")


@app.post("/chat")
async def chat_endpoint(body: dict):
    user_message = body.get("message", "") or ""
    conversation_history = body.get("history", [])
    image = body.get("image")  # optional: { base64, media_type }

    # Save image to disk as soon as it arrives.
    # The MCP tool will pick it up automatically — no need to tell Claude about the path.
    if image:
        media_type = image.get("media_type", "image/jpeg")
        ext = media_type.split("/")[-1].replace("jpeg", "jpg")
        filepath = os.path.join("images", f"pending.{ext}")
        with open(filepath, "wb") as f:
            f.write(b64lib.b64decode(image["base64"]))

    response = await chat(user_message, conversation_history, image)
    return {"response": response}