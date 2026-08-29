import uvicorn
import os
import sys

# Ensure project root is in path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

if __name__ == "__main__":
    port = int(os.getenv("PORT", "8000"))
    host = os.getenv("HOST", "127.0.0.1")
    print(f"Starting CTI + Customer Management CRM Server at http://{host}:{port}")
    uvicorn.run("backend.app.main:app", host=host, port=port, reload=True)
