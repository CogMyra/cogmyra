from typing import List
from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel
import os

# If these aren't already in your file, keep them. If they are, don't duplicate.
from openai import OpenAI

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

router = APIRouter()


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    session_id: str
    messages: List[ChatMessage]


class ChatResponse(BaseModel):
    reply: str


@router.post("/api/chat", response_model=ChatResponse)
async def chat(req: ChatRequest, request: Request):
    """
    OpenAI-backed chat. Returns assistant text content.
    """
    if not os.getenv("OPENAI_API_KEY"):
        # Hard fail if key missing (so we don't silently echo again)
        raise HTTPException(
            status_code=500, detail="OPENAI_API_KEY is not set on the server."
        )

    try:
        completion = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": m.role, "content": m.content} for m in req.messages],
            max_tokens=300,
            temperature=0.7,
        )
        reply = completion.choices[0].message.content or ""
        reply = reply.strip()
        if not reply:
            reply = "I'm here and ready to help!"
        return ChatResponse(reply=reply)
    except Exception as e:
        # Surface a clear server error so the UI shows “Load failed” instead of echoing.
        raise HTTPException(status_code=502, detail=f"OpenAI call failed: {e}")
