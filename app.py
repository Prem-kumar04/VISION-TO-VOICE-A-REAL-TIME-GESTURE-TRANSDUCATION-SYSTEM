from flask import Flask, render_template, Response, request, redirect, url_for, jsonify, flash, send_file
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from flask_bcrypt import Bcrypt
from camera import VideoCamera, FrameProcessor, state, commit_current_word, data_lock, update_suggestions, perform_backspace
import json
import os
import time
from gtts import gTTS
from datetime import datetime
import io

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///site.db'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max for frame uploads
db = SQLAlchemy(app)
bcrypt = Bcrypt(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

# Ensure audio directory exists
if not os.path.exists('static/audio'):
    os.makedirs('static/audio')

# Create a single FrameProcessor instance (for browser webcam mode)
frame_processor = FrameProcessor()

# --- DATABASE MODELS ---
class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(20), unique=True, nullable=False)
    password = db.Column(db.String(60), nullable=False)
    personal_history = db.Column(db.Text, default='[]') 
    sessions = db.relationship('Session', backref='author', lazy=True)

class Session(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    date_posted = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    english_text = db.Column(db.Text, nullable=False)
    native_text = db.Column(db.Text, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

with app.app_context():
    db.create_all()

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# --- AUTH ROUTES ---
@app.route("/", methods=['GET', 'POST'])
@app.route("/login", methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated: return redirect(url_for('dashboard'))
    if request.method == 'POST':
        user = User.query.filter_by(username=request.form.get('username')).first()
        if user and bcrypt.check_password_hash(user.password, request.form.get('password')):
            login_user(user)
            try: 
                saved_words = json.loads(user.personal_history)
                state.word_history.update(saved_words)
            except: pass
            return redirect(url_for('dashboard'))
        else:
            flash('Login Failed. Check username/password.', 'danger')
    return render_template('login.html')

@app.route("/signup", methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        if User.query.filter_by(username=username).first():
            flash('Username taken', 'danger')
            return redirect(url_for('signup'))
        hashed_pw = bcrypt.generate_password_hash(password).decode('utf-8')
        user = User(username=username, password=hashed_pw)
        db.session.add(user)
        db.session.commit()
        flash('Account Created! Please Login.', 'success')
        return redirect(url_for('login'))
    return render_template('signup.html')

@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

# --- MAIN DASHBOARD & PROFILE ---
@app.route("/dashboard")
@login_required
def dashboard():
    return render_template('dashboard.html', user=current_user)

@app.route("/profile")
@login_required
def profile():
    sessions = Session.query.filter_by(user_id=current_user.id).order_by(Session.date_posted.desc()).all()
    try: learned_words = json.loads(current_user.personal_history)
    except: learned_words = []
    graph_labels = [s.date_posted.strftime('%d-%b') for s in sessions[:5]] 
    graph_data = [len(s.english_text.split()) for s in sessions[:5]]
    return render_template('profile.html', 
                           sessions=sessions, 
                           user=current_user,
                           learned_words=learned_words,
                           graph_labels=graph_labels,
                           graph_data=graph_data)

@app.route('/resume_session/<int:session_id>')
@login_required
def resume_session(session_id):
    session = Session.query.get_or_404(session_id)
    if session.author != current_user:
        flash('Access Denied', 'danger')
        return redirect(url_for('profile'))
    state.current_sentence_en = session.english_text + " "
    state.current_sentence_native = session.native_text + " "
    flash('Session Resumed! You can continue signing.', 'success')
    return redirect(url_for('dashboard'))

# --- VIDEO STREAMING (legacy server-side camera) ---
@app.route('/video_feed')
@login_required
def video_feed():
    def gen(camera):
        while True:
            frame = camera.get_frame()
            if frame: yield (b'--frame\r\nContent-Type: image/jpeg\r\n\r\n' + frame + b'\r\n\r\n')
    return Response(gen(VideoCamera()), mimetype='multipart/x-mixed-replace; boundary=frame')

# ============================================================
# BROWSER WEBCAM ENDPOINT (works on Render!)
# ============================================================
@app.route('/process_frame', methods=['POST'])
@login_required
def process_frame():
    """Receives a base64 frame from browser webcam, processes it, returns results."""
    data = request.get_json()
    if not data or 'frame' not in data:
        return jsonify({'error': 'No frame data'}), 400
    
    annotated_frame, prediction_data = frame_processor.process_browser_frame(data['frame'])
    
    if annotated_frame is None:
        return jsonify({'error': 'Frame processing failed'}), 500
    
    return jsonify({
        'annotated_frame': annotated_frame,
        **prediction_data
    })

# ============================================================
# CAMERA MODE DETECTION
# ============================================================
@app.route('/camera_mode')
def camera_mode():
    """Tell the frontend which camera mode to use."""
    # On Render, use browser camera. Locally, also use browser camera for consistency.
    # The RENDER environment variable is automatically set by Render.
    is_render = os.environ.get('RENDER', '') == 'true'
    return jsonify({
        'mode': 'browser',  # Always use browser camera now
        'is_cloud': is_render
    })

# --- DATA UPDATES (AJAX) ---
@app.route('/get_updates')
def get_updates():
    return jsonify({
        'sentence_en': state.current_sentence_en,
        'sentence_native': state.current_sentence_native,
        'current_word': state.current_word,
        'live_preview': state.live_prediction,
        'suggestion': state.active_suggestion,
        'audio_url': state.last_audio_file,
        'confidence': int(state.confidence_score * 100)
    })

@app.route('/accept_suggestion', methods=['POST'])
def accept_suggestion():
    if state.active_suggestion:
        with data_lock:
            state.current_word = state.active_suggestion
        commit_current_word()
        return jsonify({'status': 'accepted'})
    return jsonify({'status': 'none'})

# --- KEYBOARD HANDLER ---
@app.route('/handle_keypress', methods=['POST'])
def handle_keypress():
    key = request.get_json().get('key')
    
    if key == 'Space':
        commit_current_word()
        
    elif key == 'Backspace':
        perform_backspace()
        
    elif len(key) == 1 and key.isalpha():
        with data_lock:
            state.current_word += key.upper()
        update_suggestions()
        
    return jsonify({'status': 'ok'})

# --- DOWNLOAD TRANSCRIPT ---
@app.route('/download_transcript')
@login_required
def download_transcript():
    content = (
        f"SESSION TRANSCRIPT\n"
        f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"----------------------------\n\n"
        f"ENGLISH:\n{state.current_sentence_en}\n\n"
        f"TRANSLATED:\n{state.current_sentence_native}\n"
    )
    buffer = io.BytesIO()
    buffer.write(content.encode('utf-8'))
    buffer.seek(0)
    
    return send_file(
        buffer,
        as_attachment=True,
        download_name=f"transcript_{int(time.time())}.txt",
        mimetype='text/plain'
    )

# --- SAVE SESSION TO DB ---
@app.route('/save_session', methods=['POST'])
@login_required
def save_session():
    try:
        if state.current_word: commit_current_word()
        
        final_en = state.current_sentence_en.strip()
        final_native = state.current_sentence_native.strip()

        if not final_en: return jsonify({'status': 'empty'})

        new_session = Session(english_text=final_en, native_text=final_native, author=current_user)
        
        try: current_list = set(json.loads(current_user.personal_history))
        except: current_list = set()
        
        words_in_session = set(final_en.upper().split())
        current_list.update(words_in_session)
        current_user.personal_history = json.dumps(list(current_list))
        
        db.session.add(new_session)
        db.session.commit()
        
        state.current_sentence_en = ""
        state.current_sentence_native = ""
        return jsonify({'status': 'saved'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)})

# --- TEXT TO SPEECH ---
@app.route('/speak_sentence', methods=['POST'])
def speak_sentence():
    text = state.current_sentence_native.strip()
    if not text: text = "Please sign some words first." 
    
    ts = str(time.time()).replace('.', '')
    fname = f"full_{ts}.mp3"
    abs_path = os.path.join(os.getcwd(), 'static', 'audio', fname)
    web_path = f"/static/audio/{fname}"
    
    try:
        tts = gTTS(text=text, lang=state.selected_lang, slow=False)
        tts.save(abs_path)
        return jsonify({'status': 'ok', 'audio_url': web_path})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)})

# --- LANGUAGE SETTER ---
@app.route('/set_language', methods=['POST'])
def set_language():
    state.selected_lang = request.get_json()['lang']
    return jsonify({'status': 'ok'})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5001))
    app.run(debug=False, host='0.0.0.0', port=port, threaded=True)