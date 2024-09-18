from flask import Flask, render_template, request, redirect, url_for, session, flash, send_from_directory,jsonify
import os
import openai  # For Microsoft Azure OpenAI
from brain import get_index_for_pdf
import streamlit as st
from langchain.chains import RetrievalQA
from langchain.chat_models import ChatOpenAI

app = Flask(__name__)
app.config['SECRET_KEY'] = 'Nikki@25'
# Microsoft Azure OpenAI Configuration
openai.api_type = "azure"
openai.api_base = "https://azurechatbottricon.openai.azure.com/openai/deployments/gpt-35-turbo/chat/completions?api-version=2023-03-15-preview"
openai.api_version = "2024-09-24"
openai.api_key = "ff34c8f7c947948ff83c462f15d091b6f"

# Hardcoded admin credentials
ADMIN_USERNAME = 'admin'
ADMIN_PASSWORD = 'admin123'

# In-memory data storage (Replace with a database in real apps)
users_db = {ADMIN_USERNAME: {'password': ADMIN_PASSWORD, 'role': 'admin', 'id': None, 'name': None, 'email': None}}
files_db = []

# File upload folder
UPLOAD_FOLDER = 'uploads/'
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER


# Chatbot prompt template
prompt_template = """
    You are a helpful Assistant who answers users' questions based on multiple contexts given to you.

    Keep your answer short and to the point.
    
    The evidence is the context of the PDF extract with metadata. 
    
    Carefully focus on the metadata, especially 'filename' and 'page,' whenever answering.
    
    Make sure to add filename and page number at the end of the sentence you are citing.
        
    Reply "Not applicable" if the text is irrelevant.
     
    The PDF content is:
    {pdf_extract}
"""

# Home route
@app.route('/')
def home():
    if 'username' not in session:
        return redirect(url_for('login'))
    elif session['role'] == 'admin':
        return redirect(url_for('admin_dashboard'))
    elif session['role'] == 'user':
        return redirect(url_for('user_dashboard'))
    else:
        return redirect(url_for('login'))

# Route for login page
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        # Check for user in the in-memory users_db
        if username in users_db and users_db[username]['password'] == password:
            session['username'] = username
            session['role'] = users_db[username]['role']
            if users_db[username]['role'] == 'admin':
                return redirect(url_for('admin_dashboard'))
            else:
                return redirect(url_for('user_dashboard'))
        else:
            flash("Invalid credentials!")
            return redirect(url_for('login'))
    return render_template('login.html')

# Logout functionality
@app.route('/logout')
def logout():
    session.pop('username', None)
    session.pop('role', None)
    return redirect(url_for('login'))

# Update user details
@app.route('/update_user_details', methods=['POST'])
def update_user_details():
    if 'username' not in session:
        return redirect(url_for('login'))

    # Fetch details from the form
    user_id = request.form['user_id']
    user_name = request.form['user_name']
    user_email = request.form['user_email']

    # Update the user information in the database (in-memory or use an actual DB)
    users_db[session['username']]['id'] = user_id
    users_db[session['username']]['name'] = user_name
    users_db[session['username']]['email'] = user_email

    session['user_data_saved'] = True
    return redirect(url_for('user_dashboard'))

# Admin Dashboard
@app.route('/admin_dashboard')
def admin_dashboard():
    if 'username' not in session or session['role'] != 'admin':
        return redirect(url_for('login'))
    return render_template('admin_dashboard.html', username=session['username'], files=files_db)

# Add users or admins
@app.route('/add_user', methods=['POST'])
def add_user():
    if 'username' not in session or session['role'] != 'admin':
        return redirect(url_for('login'))

    username = request.form['username']
    password = request.form['password']
    role = request.form['role']  # Either 'user' or 'admin'

    if username in users_db:
        flash(f"Error: {role.capitalize()} '{username}' already exists!")
    else:
        users_db[username] = {'password': password, 'role': role}
        flash(f"{role.capitalize()} '{username}' added successfully!")

    return redirect(url_for('admin_dashboard'))

# Clear the user_data_saved session flag
@app.route('/clear_user_data_saved_flag', methods=['POST'])
def clear_user_data_saved_flag():
    session.pop('user_data_saved', None)
    return '', 204

# Add files to the database
@app.route('/add_file', methods=['POST'])
def add_file():
    if 'username' not in session or session['role'] != 'admin':
        return redirect(url_for('login'))

    if 'file' not in request.files:
        flash('No file selected!')
        return redirect(url_for('admin_dashboard'))

    file = request.files['file']
    
    if file.filename == '':
        flash('No file selected!')
        return redirect(url_for('admin_dashboard'))

    file_path = os.path.join(app.config['UPLOAD_FOLDER'], file.filename)
    file.save(file_path)
    files_db.append(file.filename)  # Storing filenames (you can use a DB)
    
    flash(f"File '{file.filename}' uploaded successfully!")
    return redirect(url_for('admin_dashboard'))

@app.route('/upload_vectordb', methods=['POST'])
def upload_vectordb():
    pdf_files = request.files.getlist("pdf_files")
    pdf_file_names = [file.filename for file in pdf_files]
    vectordb = get_index_for_pdf([file.read() for file in pdf_files], pdf_file_names, openai.api_key)
    session['vectordb'] = vectordb
    flash('PDFs indexed successfully!')
    return redirect(url_for('admin_dashboard'))

# User Dashboard
@app.route('/user_dashboard')
def user_dashboard():
    if 'username' not in session or session['role'] != 'user':
        return redirect(url_for('login'))
    
    chat_history = session.get('chat_history', [])
    user_details = users_db.get(session['username'], {})
    user_data_saved = session.get('user_data_saved', False)

    # Clear the user_data_saved flag after displaying it
    session.pop('user_data_saved', None)
    
    return render_template('user_dashboard.html', 
                           username=session['username'], 
                           files=files_db, 
                           chat_history=chat_history, 
                           user_details=user_details, 
                           user_data_saved=user_data_saved)

# File download
@app.route('/download/<filename>')
def download_file(filename):
    if 'username' not in session or session['role'] != 'user':
        return redirect(url_for('login'))
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

# Chat interface route
@app.route('/chat', methods=['POST'])
def chat():
    if 'username' not in session or session['role'] != 'user':
        return redirect(url_for('login'))
    question = request.form['question']
    
    # Check if vectordb exists in session
    vectordb = st.session.get('vectordb', None)
    if not vectordb:
        flash("No PDF data available.")
        return redirect(url_for('user_dashboard'))
    # Search the vectordb for similar content to the user's question
    search_results = vectordb.similarity_search(question, k=3)
    pdf_extract = "/n ".join([result.page_content for result in search_results])

    # Update the prompt with the pdf extract
    formatted_prompt = prompt_template.format(pdf_extract=pdf_extract)

    response = openai.Completion.create(
        model="gpt-3.5-turbo",  # You can choose a different model like "gpt-3.5-turbo" if available
        messages=[
            {"role": "system", "content": formatted_prompt},
            {"role": "user", "content": question}
        ]
    )
    
    result= response['choices'][0]['message']['content']

    # Store the conversation in the session for continuity
    chat_history = session.get('chat_history', [])
    chat_history.append({'user': question, 'response': result})
    session['chat_history'] = chat_history

    return redirect(url_for('user_dashboard'))


# Test the function
if __name__ == "__main__":
    app.run(debug=True)
