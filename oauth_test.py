from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
import pickle

SCOPES = [
    'https://www.googleapis.com/auth/drive',
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/forms'
]

print("=" * 60)
print("Google OAuth Test")
print("=" * 60)

# Create flow with redirect URI
flow = InstalledAppFlow.from_client_secrets_file(
    'oauth_credentials.json',
    scopes=SCOPES,
    redirect_uri='http://127.0.0.1:5000/oauth2callback'
)

print("\n📱 Opening browser for authentication...")
print("Please log in and grant permissions.")
print("=" * 60)

# Run local server
creds = flow.run_local_server(port=5000)

print("\n✅ Authentication successful!")

# Save credentials
with open('token.pickle', 'wb') as f:
    pickle.dump(creds, f)
print("✅ Credentials saved to token.pickle")

# Test creating a sheet
print("\n📊 Creating test sheet...")
try:
    sheets = build('sheets', 'v4', credentials=creds)
    test_sheet = {'properties': {'title': 'MCQS Test Sheet'}}
    sheet = sheets.spreadsheets().create(body=test_sheet).execute()
    sheet_id = sheet.get('spreadsheetId')
    sheet_url = f'https://docs.google.com/spreadsheets/d/{sheet_id}/edit'
    
    print(f"\n✅ Test sheet created successfully!")
    print(f"📊 URL: {sheet_url}")
    print("\n👉 Click the link above to view your sheet in Google Drive")
    
except Exception as e:
    print(f"\n❌ Error creating sheet: {e}")

print("\n" + "=" * 60)
print("✅ OAuth setup complete!")
print("=" * 60)
