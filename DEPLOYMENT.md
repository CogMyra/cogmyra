# CogMyra — Deployment & Usage

This doc captures how to run the **API** and **web** locally, and how to
smoke-test the **hosted** API on Render.

---

## 1) Local API (FastAPI + Uvicorn)

### Env (set once per terminal)
```bash
export OPENAI_API_KEY="YOUR_REAL_KEY"
export OPENAI_MODEL="gpt-4.1"

cd ~/cogmyra-dev
python3 -m uvicorn server.main:app --reload --port 8000
curl -sS http://127.0.0.1:8000/api/health
curl -sS -X POST http://127.0.0.1:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{
    "sessionId":"local-dev",
    "messages":[
      {"role":"system","content":"You are CogMyra Guide (CMG)."},
      {"role":"user","content":"Explain gravity in one short sentence."}
    ]
  }'
curl -sS "http://127.0.0.1:8000/api/admin/logs?limit=10" | jq .
tail -n 50 ~/cogmyra-dev/server/logs/events.jsonl
