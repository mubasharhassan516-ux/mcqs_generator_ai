import os
from dotenv import load_dotenv

# Load .env file
load_dotenv()

api_key = os.environ.get('ANTHROPIC_API_KEY')
if api_key:
    print(f"✅ API Key loaded: {api_key[:30]}...")
else:
    print("❌ API Key NOT loaded")
    print("Current directory:", os.getcwd())
    print(".env exists:", os.path.exists('.env'))
