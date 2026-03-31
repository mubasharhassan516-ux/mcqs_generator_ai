from flask import Flask, render_template_string, request, redirect, url_for, flash, session
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
import json
import pickle
import os

app = Flask(__name__)
app.secret_key = 'your-secret-key-12345'

# Load OAuth config
if os.path.exists('oauth_credentials.json'):
    with open('oauth_credentials.json', 'r') as f:
        client_config = json.load(f)
else:
    print("⚠️ oauth_credentials.json not found!")

SCOPES = [
    'https://www.googleapis.com/auth/drive',
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/forms'
]

# HTML Templates
HOME_PAGE = '''
<!DOCTYPE html>
<html>
<head>
    <title>MCQS Application</title>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 20px;
        }
        .container {
            max-width: 1200px;
            margin: 0 auto;
            background: white;
            border-radius: 10px;
            box-shadow: 0 10px 40px rgba(0,0,0,0.1);
            overflow: hidden;
        }
        header {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 30px;
            text-align: center;
        }
        header h1 {
            font-size: 2.5em;
            margin-bottom: 10px;
        }
        nav {
            background: #f8f9fa;
            padding: 15px;
            border-bottom: 1px solid #e0e0e0;
        }
        nav a {
            color: #667eea;
            text-decoration: none;
            padding: 10px 20px;
            margin: 0 5px;
            border-radius: 5px;
            transition: background 0.3s;
            display: inline-block;
        }
        nav a:hover {
            background: #e0e0e0;
        }
        .content {
            padding: 40px;
        }
        .status-card {
            background: #e8f5e9;
            border-left: 4px solid #4caf50;
            padding: 15px;
            margin-bottom: 20px;
            border-radius: 5px;
        }
        .feature-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
            gap: 20px;
            margin-top: 30px;
        }
        .feature-card {
            background: #f8f9fa;
            padding: 25px;
            border-radius: 8px;
            text-align: center;
            transition: transform 0.3s;
        }
        .feature-card:hover {
            transform: translateY(-5px);
            box-shadow: 0 5px 20px rgba(0,0,0,0.1);
        }
        .feature-card h3 {
            color: #667eea;
            margin-bottom: 15px;
        }
        .btn {
            display: inline-block;
            background: #667eea;
            color: white;
            padding: 10px 20px;
            text-decoration: none;
            border-radius: 5px;
            margin-top: 15px;
            transition: background 0.3s;
        }
        .btn:hover {
            background: #764ba2;
        }
        .btn-success {
            background: #4caf50;
        }
        .btn-success:hover {
            background: #45a049;
        }
        footer {
            background: #f8f9fa;
            text-align: center;
            padding: 20px;
            color: #666;
            border-top: 1px solid #e0e0e0;
        }
        .flash-message {
            padding: 10px;
            margin: 10px 0;
            border-radius: 5px;
        }
        .flash-success {
            background: #d4edda;
            color: #155724;
            border: 1px solid #c3e6cb;
        }
        .flash-error {
            background: #f8d7da;
            color: #721c24;
            border: 1px solid #f5c6cb;
        }
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>📚 MCQS Application</h1>
            <p>Multiple Choice Question Generator & Management System</p>
        </header>
        <nav>
            <a href="/">Home</a>
            <a href="/upload">Upload Document</a>
            <a href="/generate">Generate MCQs</a>
            <a href="/google">Google Integration</a>
        </nav>
        <div class="content">
            {% with messages = get_flashed_messages(with_categories=true) %}
                {% if messages %}
                    {% for category, message in messages %}
                        <div class="flash-message flash-{{ category }}">{{ message }}</div>
                    {% endfor %}
                {% endif %}
            {% endwith %}
            
            <h2>Welcome to MCQS Application!</h2>
            <p>Your complete solution for generating and managing multiple choice questions.</p>
            
            <div class="status-card">
                <strong>✅ System Status:</strong> Ready
                {% if google_connected %}
                <br><strong>✅ Google Integration:</strong> Connected
                {% else %}
                <br><strong>⚠️ Google Integration:</strong> Not connected - <a href="/google/login">Connect Now</a>
                {% endif %}
            </div>
            
            <div class="feature-grid">
                <div class="feature-card">
                    <h3>📄 Upload Document</h3>
                    <p>Upload PDF, DOCX, or TXT files to extract content for MCQ generation.</p>
                    <a href="/upload" class="btn">Upload Now</a>
                </div>
                <div class="feature-card">
                    <h3>🤖 Generate MCQs</h3>
                    <p>Automatically generate multiple choice questions from your documents.</p>
                    <a href="/generate" class="btn">Generate MCQs</a>
                </div>
                <div class="feature-card">
                    <h3>📊 Google Sheets Export</h3>
                    <p>Export your MCQs directly to Google Sheets for easy sharing.</p>
                    <a href="/google/export" class="btn btn-success">Export to Sheets</a>
                </div>
                <div class="feature-card">
                    <h3>📝 Google Forms</h3>
                    <p>Create interactive quizzes in Google Forms from your MCQs.</p>
                    <a href="/google/create-form" class="btn btn-success">Create Form</a>
                </div>
            </div>
        </div>
        <footer>
            <p>&copy; 2026 MCQS Application | Built with Flask & Google APIs</p>
        </footer>
    </div>
</body>
</html>
'''

@app.route('/')
def home():
    google_connected = os.path.exists('token.pickle')
    return render_template_string(HOME_PAGE, google_connected=google_connected)

@app.route('/upload')
def upload():
    return '''
    <h1>Upload Document</h1>
    <p>Upload PDF, DOCX, or TXT files to generate MCQs</p>
    <form method="POST" action="/upload-file" enctype="multipart/form-data">
        <input type="file" name="file" accept=".pdf,.docx,.txt">
        <button type="submit">Upload</button>
    </form>
    <p><a href="/">Back to Home</a></p>
    '''

@app.route('/upload-file', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        flash('No file uploaded', 'error')
        return redirect(url_for('upload'))
    
    file = request.files['file']
    if file.filename == '':
        flash('No file selected', 'error')
        return redirect(url_for('upload'))
    
    # Save file
    filepath = os.path.join('uploads', file.filename)
    os.makedirs('uploads', exist_ok=True)
    file.save(filepath)
    
    flash(f'File {file.filename} uploaded successfully!', 'success')
    return redirect(url_for('home'))

@app.route('/generate')
def generate():
    return '''
    <h1>Generate MCQs</h1>
    <p>Select a document to generate multiple choice questions</p>
    <p><a href="/">Back to Home</a></p>
    '''

@app.route('/google')
def google():
    google_connected = os.path.exists('token.pickle')
    return f'''
    <h1>Google Integration</h1>
    <p>Status: {"✅ Connected" if google_connected else "❌ Not Connected"}</p>
    <p><a href="/google/login">Connect Google Account</a></p>
    <p><a href="/google/export">Export to Sheets</a></p>
    <p><a href="/google/create-form">Create Google Form</a></p>
    <p><a href="/">Back to Home</a></p>
    '''

@app.route('/google/login')
def google_login():
    if not os.path.exists('oauth_credentials.json'):
        return '<h1>Error: oauth_credentials.json not found!</h1>'
    
    flow = Flow.from_client_config(
        client_config,
        scopes=SCOPES,
        redirect_uri='http://127.0.0.1:5000/google/callback'
    )
    
    auth_url, state = flow.authorization_url(
        access_type='offline',
        include_granted_scopes='true',
        prompt='consent'
    )
    
    session['oauth_state'] = state
    return redirect(auth_url)

@app.route('/google/callback')
def google_callback():
    state = session.get('oauth_state')
    
    flow = Flow.from_client_config(
        client_config,
        scopes=SCOPES,
        state=state,
        redirect_uri='http://127.0.0.1:5000/google/callback'
    )
    
    flow.fetch_token(authorization_response=request.url)
    credentials = flow.credentials
    
    with open('token.pickle', 'wb') as f:
        pickle.dump(credentials, f)
    
    flash('Google account connected successfully!', 'success')
    return redirect(url_for('home'))

@app.route('/google/export')
def google_export():
    if not os.path.exists('token.pickle'):
        flash('Please connect your Google account first', 'error')
        return redirect(url_for('google_login'))
    
    try:
        with open('token.pickle', 'rb') as f:
            creds = pickle.load(f)
        
        sheets = build('sheets', 'v4', credentials=creds)
        
        # Create a test sheet
        spreadsheet = {
            'properties': {
                'title': 'MCQS Generated Questions'
            }
        }
        sheet = sheets.spreadsheets().create(body=spreadsheet).execute()
        sheet_id = sheet.get('spreadsheetId')
        sheet_url = f'https://docs.google.com/spreadsheets/d/{sheet_id}/edit'
        
        return f'''
        <h1>✅ Sheet Created!</h1>
        <p><a href="{sheet_url}" target="_blank">Click here to open your Google Sheet</a></p>
        <p><a href="/">Back to Home</a></p>
        '''
    except Exception as e:
        return f'<h1>Error: {e}</h1><p><a href="/">Back</a></p>'

@app.route('/google/create-form')
def google_create_form():
    if not os.path.exists('token.pickle'):
        flash('Please connect your Google account first', 'error')
        return redirect(url_for('google_login'))
    
    try:
        with open('token.pickle', 'rb') as f:
            creds = pickle.load(f)
        
        forms = build('forms', 'v1', credentials=creds)
        
        # Create a test form
        form = {
            'info': {
                'title': 'MCQS Quiz',
                'description': 'Generated by MCQS Application'
            }
        }
        result = forms.forms().create(body=form).execute()
        form_id = result.get('formId')
        form_url = f'https://docs.google.com/forms/d/{form_id}/edit'
        
        return f'''
        <h1>✅ Form Created!</h1>
        <p><a href="{form_url}" target="_blank">Click here to edit your Google Form</a></p>
        <p><a href="/">Back to Home</a></p>
        '''
    except Exception as e:
        return f'<h1>Error: {e}</h1><p><a href="/">Back</a></p>'

if __name__ == '__main__':
    print("=" * 50)
    print("MCQS Flask Application")
    print("=" * 50)
    print("🌐 Open: http://127.0.0.1:5000")
    print("=" * 50)
    app.run(debug=True, host='127.0.0.1', port=5000)
