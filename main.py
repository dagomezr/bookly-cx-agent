from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from dotenv import load_dotenv
from agent.chat import chat

load_dotenv()

app = FastAPI()

app.mount("/static", StaticFiles(directory="frontend"), name="static")

@app.get("/")
def root():
    return FileResponse("frontend/index.html")

@app.post("/chat")
async def chat_endpoint(body: dict):
    user_message = body.get("message")
    conversation_history = body.get("history", [])
    response = await chat(user_message, conversation_history)
    return {"response": response}