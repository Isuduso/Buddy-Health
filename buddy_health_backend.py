from flask import Flask, request, jsonify
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
import jwt
import json
import re
from datetime import datetime, timedelta
from functools import wraps

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_huggingface import HuggingFaceEndpointEmbeddings
from langchain_community.vectorstores import Chroma
from langchain_classic.chains import RetrievalQA
from langchain_groq import ChatGroq

import os

HEALTH_KEYWORDS = [
    "pain", "fever", "headache", "cough", "malaria", "typhoid", "diabetes",
    "hypertension", "blood", "stomach", "chest", "throat", "skin", "wound",
    "burn", "diarrhea", "vomit", "dizzy", "breathing", "heart", "infection",
    "symptom", "sick", "ill", "doctor", "hospital", "medicine", "treatment",
    "health", "body", "pregnant", "baby", "child", "eye", "ear", "nose",
    "leg", "arm", "head", "back", "joint", "swollen", "rash", "cold", "flu",
    "fatigue", "weak", "tired", "weight", "pressure", "sugar", "urinate",
    "belly", "dey pain", "i get", "fever don", "head dey", "my body"
]

def is_health_related(message):
    message_lower = message.lower().strip()
    if len(message_lower) < 5:
        return False
    return any(keyword in message_lower for keyword in HEALTH_KEYWORDS)
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")

def load_health_data(filepath):
    with open(filepath, "r") as f:
        content = f.read()
    raw_arrays = re.findall(r'\[.*?\]', content, re.DOTALL)
    documents = []
    for array in raw_arrays:
        entries = json.loads(array)
        for entry in entries:
            text = "\n".join([f"{k}: {v}" for k, v in entry.items()])
            doc = Document(page_content=text, metadata={"disease": entry.get("Disease/Condition Name", "Unknown")})
            documents.append(doc)
    return documents

print("Loading health data and AI model...")
docs = load_health_data("health_data.txt")
splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=50)
chunks = splitter.split_documents(docs)
embeddings = HuggingFaceEndpointEmbeddings(model="sentence-transformers/all-MiniLM-L6-v2", huggingfacehub_api_token=os.environ.get("HF_TOKEN"))
vectorstore = Chroma.from_documents(chunks, embeddings)
llm = ChatGroq(model="llama-3.3-70b-versatile", api_key=GROQ_API_KEY, temperature=0.2)
qa_chain = RetrievalQA.from_chain_type(llm=llm, retriever=vectorstore.as_retriever(search_kwargs={"k": 3}), return_source_documents=True)
print("AI model ready!")

app = Flask(__name__)
CORS(app)
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///buddy_health.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['JWT_SECRET_KEY'] = 'your-secret-key-here'
db = SQLAlchemy(app)

class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    name = db.Column(db.String(120), nullable=False)
    password = db.Column(db.String(255), nullable=False)
    language = db.Column(db.String(20), default='en')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    conversations = db.relationship('Conversation', backref='user', lazy=True, cascade='all, delete-orphan')

    def set_password(self, password):
        self.password = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password, password)

    def to_dict(self):
        return {'id': self.id, 'username': self.username, 'name': self.name, 'language': self.language}

class Conversation(db.Model):
    __tablename__ = 'conversations'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    user_message = db.Column(db.Text, nullable=False)
    bot_response = db.Column(db.Text, nullable=False)
    language = db.Column(db.String(20), default='en')
    detected_symptoms = db.Column(db.JSON)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {'id': self.id, 'user_message': self.user_message, 'bot_response': self.bot_response, 'language': self.language, 'detected_symptoms': self.detected_symptoms, 'created_at': str(self.created_at)}

def create_token(user_id):
    payload = {'user_id': user_id, 'exp': datetime.utcnow() + timedelta(days=7)}
    return jwt.encode(payload, app.config['JWT_SECRET_KEY'], algorithm='HS256')

def verify_token(token):
    try:
        data = jwt.decode(token, app.config['JWT_SECRET_KEY'], algorithms=['HS256'])
        return data['user_id']
    except:
        return None

def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get('Authorization')
        if not token:
            return jsonify({'error': 'Missing token'}), 401
        token = token.replace('Bearer ', '')
        user_id = verify_token(token)
        if not user_id:
            return jsonify({'error': 'Invalid token'}), 401
        return f(user_id, *args, **kwargs)
    return decorated

def generate_ai_response(message, language='en'):
    if not is_health_related(message):
        if language == 'pidgin':
            return "I no fit answer dis question. Abeg ask me health question only."
        else:
            return "I can only assist with health-related inquiries. Please ask a health question."
        prompt = f"""Answer in Nigerian Pidgin English using this exact structure:
def ge
WETIN DEY HAPPEN:
[Brief explanation]

SYMPTOMS WEY YOU FIT GET:
[List symptoms]

FIRST AID WEY YOU FIT DO:
[First aid steps]

WHEN TO GO HOSPITAL:
[When to seek care]

REMINDER: Dis na general information only. E no replace real doctor. Always go see doctor for proper check-up.

Question: {message}"""
    else:
        prompt = f"""Answer using this exact structure:

THESE SYMPTOMS COULD BE RELATED TO:
[GENERAL POSSIBLITIES ONLY - THIS IS NOT A DIAGNOSIS]

COMMON SYMPTOMS:
[List the symptoms]

GENERAL WELLNESS TIPS:
[Practical first aid steps]

WHEN TO SEE A DOCTOR:
[Specific warning signs]

DISCLAIMER: This information is for general guidance only and does NOT replace professional medical advice. Always consult a qualified doctor.

Question: {message}"""
    result = qa_chain.invoke(prompt)
    return result['result']

@app.route('/auth/signup', methods=['POST'])
def signup():
    data = request.get_json()
    if not data or not data.get('username') or not data.get('password') or not data.get('name'):
        return jsonify({'error': 'Missing required fields'}), 400
    if User.query.filter_by(username=data['username']).first():
        return jsonify({'error': 'Username already exists'}), 409
    user = User(username=data['username'], name=data['name'], language=data.get('language', 'en'))
    user.set_password(data['password'])
    db.session.add(user)
    db.session.commit()
    token = create_token(user.id)
    return jsonify({'message': 'User created successfully', 'user': user.to_dict(), 'token': token}), 201

@app.route('/auth/login', methods=['POST'])
def login():
    data = request.get_json()
    if not data or not data.get('username') or not data.get('password'):
        return jsonify({'error': 'Missing username or password'}), 400
    user = User.query.filter_by(username=data['username']).first()
    if not user or not user.check_password(data['password']):
        return jsonify({'error': 'Invalid username or password'}), 401
    token = create_token(user.id)
    return jsonify({'message': 'Login successful', 'user': user.to_dict(), 'token': token}), 200

@app.route('/chat/send-message', methods=['POST'])
@token_required
def send_message(user_id):
    data = request.get_json()
    if not data or not data.get('message'):
        return jsonify({'error': 'Missing message'}), 400
    user = User.query.get(user_id)
    language = user.language
    user_message = data['message']
    bot_response = generate_ai_response(user_message, language)
    conversation = Conversation(user_id=user_id, user_message=user_message, bot_response=bot_response, language=language, detected_symptoms=[])
    db.session.add(conversation)
    db.session.commit()
    return jsonify({'message': 'Message processed', 'user_message': user_message, 'bot_response': bot_response, 'timestamp': str(datetime.utcnow())}), 200

@app.route('/chat/guest-message', methods=['POST'])
def guest_message():
    data = request.get_json()
    if not data or not data.get('message'):
        return jsonify({'error': 'Missing message'}), 400
    language = data.get('language', 'en')
    user_message = data['message']
    bot_response = generate_ai_response(user_message, language)
    return jsonify({'message': 'Message processed', 'user_message': user_message, 'bot_response': bot_response, 'timestamp': str(datetime.utcnow())}), 200

@app.route('/chat/history', methods=['GET'])
@token_required
def get_history(user_id):
    conversations = Conversation.query.filter_by(user_id=user_id).order_by(Conversation.created_at.desc()).all()
    return jsonify({'conversations': [c.to_dict() for c in conversations]}), 200

@app.route('/admin/users', methods=['GET'])
def get_all_users():
    admin_key = request.headers.get('X-Admin-Key')
    if admin_key != 'buddy_secure_admin_2024!':
        return jsonify({'error': 'Unauthorized'}), 401
    users = User.query.all()
    return jsonify({'total_users': len(users), 'users': [
        {'id': u.id, 'username': u.username, 'name': u.name, 'language': u.language,
         'created_at': str(u.created_at), 'total_conversations': len(u.conversations)}
        for u in users
    ]}), 200

@app.route('/admin/conversations', methods=['GET'])
def get_all_conversations():
    admin_key = request.headers.get('X-Admin-Key')
    if admin_key != 'buddy_secure_admin_2024!':
        return jsonify({'error': 'Unauthorized'}), 401
    conversations = Conversation.query.order_by(Conversation.created_at.desc()).all()
    return jsonify({'total_conversations': len(conversations), 'conversations': [c.to_dict() for c in conversations]}), 200

@app.errorhandler(404)
def not_found(error):
    return jsonify({'error': 'Endpoint not found'}), 404

@app.errorhandler(500)
def server_error(error):
    return jsonify({'error': 'Server error'}), 500

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True, host='0.0.0.0', port=5001)
