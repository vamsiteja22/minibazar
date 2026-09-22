import os
import sys

# Add project root directory to sys.path so modules can be imported by Vercel
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from wsgi import app

# Vercel serverless function entrypoint
app = app
