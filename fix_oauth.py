from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
import json
import pickle
import os

# Load client config
with open('oauth_credentials.json', 'r') as f:
    client_config = json.load(f)

SCOPES = [
    'https://www.googleapis.com/auth/drive',
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/forms'
]

# Update the redirect URIs in the config
client_config['web']['redirect_uris'] = [
    'http://127.0.0.1:5000/google/callback',
    'http://localhost:5000/google/callback'
]

# Save the updated config
with open('oauth_credentials.json', 'w') as f:
    json.dump(client_config, f, indent=2)

print("✅ Updated oauth_credentials.json with correct redirect URIs")

# Test with the correct redirect URI
flow = Flow.from_client_config(
    client_config,
    scopes=SCOPES,
    redirect_uri='http://127.0.0.1:5000/google/callback'
)

print("\n📱 Opening browser for authentication...")
print("Please log in and grant permissions.")
print("=" * 50)

# Run the flow
creds = flow.run_local_server(port=5000)

print("\n✅ Authentication successful!")

# Save credentials
with open('token.pickle', 'wb') as f:
    pickle.dump(creds, f)
print("✅ Credentials saved to token.pickle")

# Test creating a sheet
try:
    sheets = build('sheets', 'v4', credentials=creds)
    test_sheet = {'properties': {'title': 'MCQS Test'}}
    sheet = sheets.spreadsheets().create(body=test_sheet).execute()
    sheet_id = sheet.get('spreadsheetId')
    print(f"\n✅ Sheet created: https://docs.google.com/spreadsheets/d/{sheet_id}/edit")
except Exception as e:
    print(f"\n❌ Error: {e}")

print("\n" + "=" * 50)
print("✅ Setup complete! You can now use your MCQS app.")
print("=" * 50)
