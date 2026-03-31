import json
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
import pickle
import os

SCOPES = [
    'https://www.googleapis.com/auth/drive',
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/forms'
]

print("=" * 60)
print("Google OAuth - Automated Flow")
print("=" * 60)

# Check if credentials file exists
if not os.path.exists('oauth_credentials.json'):
    print("❌ oauth_credentials.json not found!")
    print("Please download OAuth credentials from Google Cloud Console")
    exit(1)

print("✅ Found oauth_credentials.json")

# Create the flow
flow = InstalledAppFlow.from_client_secrets_file(
    'oauth_credentials.json', 
    scopes=SCOPES
)

print("\n📱 Opening browser for authentication...")
print("Please log in and grant permissions when prompted.")
print("=" * 60)

# This will open browser and handle authentication automatically
creds = flow.run_local_server(port=8080)

print("\n✅ Authentication successful!")

# Save credentials
with open('token.pickle', 'wb') as f:
    pickle.dump(creds, f)
print("✅ Credentials saved to token.pickle")

# Test creating a sheet
print("\n📊 Testing Google Sheets API...")
try:
    sheets = build('sheets', 'v4', credentials=creds)
    test_sheet = {'properties': {'title': 'MCQS Test Sheet'}}
    sheet = sheets.spreadsheets().create(body=test_sheet).execute()
    sheet_id = sheet.get('spreadsheetId')
    sheet_url = f'https://docs.google.com/spreadsheets/d/{sheet_id}/edit'
    
    print(f"\n✅ Test sheet created!")
    print(f"📊 URL: {sheet_url}")
    
except Exception as e:
    print(f"\n❌ Error creating sheet: {e}")

print("\n" + "=" * 60)
print("✅ OAuth setup complete!")
print("=" * 60)
