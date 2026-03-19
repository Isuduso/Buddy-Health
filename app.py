from flask import Flask, request, jsonify
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
import jwt
import spacy
from datetime import datetime, timedelta
from functools import wraps
import os

# Initialize Flask app
app = Flask(__name__)
CORS(app)

# Configuration
app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql://buddy_user:buddy_password@localhost:5432/buddy_health'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['JWT_SECRET_KEY'] = 'Emhibaby05'

# Initialize Database
db = SQLAlchemy(app)

# Load spaCy model
try:
    nlp = spacy.load('en_core_web_sm')
except OSError:
    print("Downloading spaCy model...")
    os.system('python3 -m spacy download en_core_web_sm')
    nlp = spacy.load('en_core_web_sm')

# ==================== DATABASE MODELS ====================

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
        return {
            'id': self.id,
            'username': self.username,
            'name': self.name,
            'language': self.language
        }

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
        return {
            'id': self.id,
            'user_message': self.user_message,
            'bot_response': self.bot_response,
            'language': self.language,
            'detected_symptoms': self.detected_symptoms,
            'created_at': str(self.created_at)
        }

# ==================== HEALTH KNOWLEDGE BASE ====================

HEALTH_DATABASE = {
    'fever': {
        'en': {
            'description': 'High body temperature',
            'symptoms': ['high temperature', 'fever', 'hot', 'temperature don high'],
            'advice': 'Drink plenty of water, rest well, and monitor your temperature. If it persists for more than 3 days or rises above 39°C, please see a doctor immediately.',
            'when_to_see_doctor': 'Fever lasting 3+ days, temperature above 39°C, severe headache, or difficulty breathing'
        },
        'pidgin': {
            'description': 'High body temperature',
            'symptoms': ['high temperature', 'fever', 'hot', 'temperature don high'],
            'advice': 'Drink plenty water, rest well, and check your temperature. If e last pass 3 days or go pass 39°C, go see doctor sharp sharp.',
            'when_to_see_doctor': 'Fever wey don last 3 days, temperature pass 39°C, severe head pain, or difficulty for breathe'
        }
    },
    'cough': {
        'en': {
            'description': 'Persistent cough',
            'symptoms': ['cough', 'coughing', 'chest pain cough', 'persistent cough'],
            'advice': 'Stay hydrated and get adequate rest. If it lasts more than a week or you cough blood, consult a healthcare professional. Avoid self-medication.',
            'when_to_see_doctor': 'Cough lasting 1+ week, coughing blood, severe chest pain, or shortness of breath'
        },
        'pidgin': {
            'description': 'Persistent cough',
            'symptoms': ['cough', 'coughing', 'chest pain cough', 'persistent cough'],
            'advice': 'Drink water well and rest your body. If cough no go after one week or you dey cough blood, run go see doctor.',
            'when_to_see_doctor': 'Cough wey don last one week, coughing blood, severe chest pain, or breathing problem'
        }
    },
    'malaria': {
        'en': {
            'description': 'Malaria infection',
            'symptoms': ['malaria', 'fever chills', 'body pain', 'headache fever', 'mosquito bite'],
            'advice': 'Get tested immediately. Use insecticide-treated nets and avoid mosquito bites. See a doctor for proper diagnosis and treatment. Prevention is key.',
            'when_to_see_doctor': 'Suspected malaria requires immediate testing. High fever with chills, severe weakness, confusion, or unconsciousness'
        },
        'pidgin': {
            'description': 'Malaria infection',
            'symptoms': ['malaria', 'fever chills', 'body pain', 'headache fever', 'mosquito bite'],
            'advice': 'Go for test now. Use mosquito net and avoid mosquito from bite you. Go see doctor for proper check and medicine. Prevention na better pass cure.',
            'when_to_see_doctor': 'Suspected malaria need test now. High fever with shaking, severe weakness, confusion, or person don sleep'
        }
    },
    'headache': {
        'en': {
            'description': 'Head pain',
            'symptoms': ['headache', 'head pain', 'migraine', 'head ache'],
            'advice': 'Rest in a quiet, dark room. Drink water and avoid stress. If headaches are frequent or severe, consult a doctor.',
            'when_to_see_doctor': 'Severe headache with fever, vision changes, stiff neck, or frequent recurring headaches'
        },
        'pidgin': {
            'description': 'Head pain',
            'symptoms': ['headache', 'head pain', 'migraine', 'head ache'],
            'advice': 'Rest for inside quiet room. Drink water and avoid stress. If headache dey come plenty times or very bad, go see doctor.',
            'when_to_see_doctor': 'Severe head pain with fever, eye problem, neck wey stiff, or headache wey dey come always'
        }
    }
}

# ==================== HELPER FUNCTIONS ====================

def create_token(user_id):
    payload = {
        'user_id': user_id,
        'exp': datetime.utcnow() + timedelta(days=7)
    }
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

def extract_symptoms(text, language='en'):
    doc = nlp(text.lower())
    detected_symptoms = []
    
    for condition, data in HEALTH_DATABASE.items():
        for symptom in data[language]['symptoms']:
            if symptom in text.lower():
                detected_symptoms.append(condition)
                break
    
    return detected_symptoms

def generate_response(symptoms, language='en'):
    if not symptoms:
        if language == 'pidgin':
            return 'Tell me more about your sickness so I help you better. Go see doctor for proper check.'
        else:
            return 'Tell me more about your symptoms so I can help better. Remember to consult a doctor for proper diagnosis.'
    
    primary_symptom = symptoms[0]
    symptom_data = HEALTH_DATABASE[primary_symptom][language]
    
    response = f"Based on your symptoms:\n\n"
    response += f"**Condition**: {symptom_data['description']}\n\n"
    response += f"**Advice**: {symptom_data['advice']}\n\n"
    response += f"**When to see a doctor**: {symptom_data['when_to_see_doctor']}\n\n"
    response += "Always consult a healthcare professional for proper diagnosis and treatment."
    
    return response

# ==================== API ROUTES ====================

@app.route('/auth/signup', methods=['POST'])
def signup():
    data = request.get_json()
    
    if not data or not data.get('username') or not data.get('password') or not data.get('name'):
        return jsonify({'error': 'Missing required fields'}), 400
    
    if User.query.filter_by(username=data['username']).first():
        return jsonify({'error': 'Username already exists'}), 409
    
    user = User(
        username=data['username'],
        name=data['name'],
        language=data.get('language', 'en')
    )
    user.set_password(data['password'])
    
    db.session.add(user)
    db.session.commit()
    
    token = create_token(user.id)
    return jsonify({
        'message': 'User created successfully',
        'user': user.to_dict(),
        'token': token
    }), 201

@app.route('/auth/login', methods=['POST'])
def login():
    data = request.get_json()
    
    if not data or not data.get('username') or not data.get('password'):
        return jsonify({'error': 'Missing username or password'}), 400
    
    user = User.query.filter_by(username=data['username']).first()
    
    if not user or not user.check_password(data['password']):
        return jsonify({'error': 'Invalid username or password'}), 401
    
    token = create_token(user.id)
    return jsonify({
        'message': 'Login successful',
        'user': user.to_dict(),
        'token': token
    }), 200

@app.route('/chat/send-message', methods=['POST'])
@token_required
def send_message(user_id):
    data = request.get_json()
    
    if not data or not data.get('message'):
        return jsonify({'error': 'Missing message'}), 400
    
    user = User.query.get(user_id)
    language = user.language
    user_message = data['message']
    
    detected_symptoms = extract_symptoms(user_message, language)
    bot_response = generate_response(detected_symptoms, language)
    
    conversation = Conversation(
        user_id=user_id,
        user_message=user_message,
        bot_response=bot_response,
        language=language,
        detected_symptoms=detected_symptoms
    )
    
    db.session.add(conversation)
    db.session.commit()
    
    return jsonify({
        'message': 'Message processed',
        'user_message': user_message,
        'bot_response': bot_response,
        'detected_symptoms': detected_symptoms,
        'timestamp': str(datetime.utcnow())
    }), 200

@app.route('/health/symptoms', methods=['GET'])
@token_required
def get_symptoms(user_id):
    user = User.query.get(user_id)
    language = user.language
    
    symptoms_list = []
    for condition, data in HEALTH_DATABASE.items():
        symptoms_list.append({
            'condition': condition,
            'description': data[language]['description'],
            'symptoms': data[language]['symptoms']
        })
    
    return jsonify({
        'language': language,
        'symptoms': symptoms_list
    }), 200

@app.route('/chat/history', methods=['GET'])
@token_required
def get_history(user_id):
    conversations = Conversation.query.filter_by(user_id=user_id).order_by(Conversation.created_at.desc()).all()
    
    return jsonify({
        'conversations': [c.to_dict() for c in conversations]
    }), 200

@app.route('/admin/users', methods=['GET'])
def get_all_users():
    admin_key = request.headers.get('X-Admin-Key')
    if admin_key != 'buddy_secure_admin_2024!':
        return jsonify({'error': 'Unauthorized'}), 401
    
    users = User.query.all()
    return jsonify({
        'total_users': len(users),
        'users': [
            {
                'id': u.id,
                'username': u.username,
                'name': u.name,
                'language': u.language,
                'created_at': str(u.created_at),
                'total_conversations': len(u.conversations)
            }
            for u in users
        ]
    }), 200

@app.route('/admin/conversations', methods=['GET'])
def get_all_conversations():
    admin_key = request.headers.get('X-Admin-Key')
    if admin_key != 'buddy_secure_admin_2024!':
        return jsonify({'error': 'Unauthorized'}), 401
    
    conversations = Conversation.query.order_by(Conversation.created_at.desc()).all()
    return jsonify({
        'total_conversations': len(conversations),
        'conversations': [c.to_dict() for c in conversations]
    }), 200

@app.errorhandler(404)
def not_found(error):
    return jsonify({'error': 'Endpoint not found'}), 404

@app.errorhandler(500)
def server_error(error):
    return jsonify({'error': 'Server error'}), 500

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    print("Starting Buddy Health Backend on http://localhost:5000")
    app.run(debug=True, host='localhost', port=5001)
