# asgi.py -- tiny shim so "uvicorn asgi:app" works on Render

# Optional local run helper:
if __name__ == "__main__":
    import os
    import uvicorn

    uvicorn.run("asgi:app", host="0.0.0.0", port=int(os.getenv("PORT", "8000")))
