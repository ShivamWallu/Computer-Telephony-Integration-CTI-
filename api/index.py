import sys
import os

# Add root directory to sys.path for serverless execution
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.app.main import app

# Vercel entrypoint
handler = app
