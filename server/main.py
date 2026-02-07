import os
import uuid
from typing import List, Optional
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from langchain_core.messages import HumanMessage, AIMessage

from server.agent import app as agent_app

app = FastAPI(title="GenTab Intelligence API")

# Enable CORS for Chrome Extension
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify extension ID
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Ensure static directory exists
STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
os.makedirs(STATIC_DIR, exist_ok=True)

# Mount static files
app.mount("/dashboard", StaticFiles(directory=STATIC_DIR), name="static")

class TabInfo(BaseModel):
    id: int
    title: str
    url: str

class ChatRequest(BaseModel):
    message: str
    tabs: List[TabInfo]

class ChatResponse(BaseModel):
    response: str
    action: Optional[str] = None
    dashboard_url: Optional[str] = None

@app.post("/chat", response_model=ChatResponse)
async def chat_endpoint(request: ChatRequest):
    try:
        # Format tab context
        tab_context = "\n".join([f"- {t.title} ({t.url})" for t in request.tabs])
        
        # Prepare input state
        initial_state = {
            "messages": [HumanMessage(content=request.message)],
            "tab_context": tab_context
        }
        
        # Invoke Agent
        result = agent_app.invoke(initial_state)
        
        messages = result["messages"]
        last_message = messages[-1].content if messages else "No response."
        
        response_data = {"response": last_message}
        
        # Check if dashboard was generated
        code = result.get("generated_dashboard_code")
        if code:
             project_id = uuid.uuid4().hex[:8]
             dashboard_id = f"dashboard_{project_id}.html"
             file_path = os.path.join(STATIC_DIR, dashboard_id)
             
             with open(file_path, "w", encoding="utf-8") as f:
                 f.write(code)
             
             # CRITICAL FIX: Use /dashboard/ (mounted path) instead of /static/
             dashboard_url = f"http://localhost:8000/dashboard/{dashboard_id}"
             
             response_data["action"] = "open_dashboard"
             response_data["dashboard_url"] = dashboard_url
             response_data["response"] += " I've created your dashboard. Opening it now..."

        return response_data

    except Exception as e:
        print(f"Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
