from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
import os

SCOPES = [
    'https://www.googleapis.com/auth/drive',
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/forms'
]

print("=" * 60)
print("Testing OAuth 2.0 with your Google Account")
print("=" * 60)

# Check if credentials file exists
if not os.path.exists('oauth_credentials.json'):
    print("❌ oauth_credentials.json not found!")
    print("Please download OAuth credentials from Google Cloud Console")
    exit(1)

print("✅ Found oauth_credentials.json")

# Run OAuth flow
flow = InstalledAppFlow.from_client_secrets_file(
    'oauth_credentials.json', SCOPES)
creds = flow.run_local_server(port=0)

print(f"✅ Authenticated as: {creds.id_token['email'] if hasattr(creds, 'id_token') else 'Your Google Account'}")

try:
    # Test Sheets API
    sheets = build('sheets', 'v4', credentials=creds)
    test_sheet = {'properties': {'title': 'MCQS Test Sheet'}}
    sheet = sheets.spreadsheets().create(body=test_sheet).execute()
    sheet_id = sheet.get('spreadsheetId')
    sheet_url = f'https://docs.google.com/spreadsheets/d/{sheet_id}/edit'
    
    print(f"\n✅ Sheets API is working!")
    print(f"📊 Sheet created successfully!")
    print(f"🔗 URL: {sheet_url}")
    
    # Test Forms API
    forms = build('forms', 'v1', credentials=creds)
    test_form = {'info': {'title': 'MCQS Test Form'}}
    form = forms.forms().create(body=test_form).execute()
    form_id = form.get('formId')
    form_url = f'https://docs.google.com/forms/d/{form_id}/edit'
    
    print(f"\n✅ Forms API is working!")
    print(f"📝 Form created successfully!")
    print(f"🔗 URL: {form_url}")
    
    print("\n" + "=" * 60)
    print("✅ All APIs are working with your Google Account!")
    print("=" * 60)
    
except Exception as e:
    print(f"❌ Error: {e}")
