import cv2
import mediapipe as mp
import numpy as np
import pickle
import os
import time
import threading
from collections import Counter
from googletrans import Translator
from gtts import gTTS

# --- GLOBAL STATE ---
class GlobalState:
    def __init__(self):
        self.current_sentence_en = ""
        self.current_sentence_native = ""
        self.current_word = ""       
        self.live_prediction = "_"   
        self.active_suggestion = "" 
        self.selected_lang = 'te' 
        self.last_audio_file = ""
        self.confidence_score = 0.0 
        self.word_history = set(["HELLO", "WORLD", "THANKS", "WELCOME"])
        
        # TIMERS
        self.last_delete_time = 0
        self.two_hand_frame_count = 0

state = GlobalState()
translator = Translator()
data_lock = threading.Lock() 

# --- SHARED BACKSPACE LOGIC ---
def perform_backspace():
    """Deletes last char of current word OR picks up previous word."""
    with data_lock:
        # 1. If currently typing a word, delete its last letter
        if len(state.current_word) > 0:
            state.current_word = state.current_word[:-1]
            
        # 2. If NO active word, "pick up" the previous word
        else:
            en_words = state.current_sentence_en.strip().split()
            native_words = state.current_sentence_native.strip().split()
            
            if en_words:
                last_word = en_words.pop()
                # Update sentences
                state.current_sentence_en = " ".join(en_words) + " " if en_words else ""
                
                if native_words: 
                    native_words.pop()
                    state.current_sentence_native = " ".join(native_words) + " " if native_words else ""

                # Move word back to editing
                state.current_word = last_word[:-1]

    update_suggestions()

def update_suggestions():
    state.active_suggestion = ""
    if len(state.current_word) >= 2:
        for saved_word in sorted(list(state.word_history)):
            if saved_word.startswith(state.current_word):
                state.active_suggestion = saved_word
                break

def commit_current_word():
    with data_lock:
        word = state.current_word.strip()
        if not word: return
        
        print(f"✅ COMMITTING WORD: '{word}'")

        try:
            if state.selected_lang == 'en': trans = word
            else: trans = translator.translate(word, dest=state.selected_lang).text
        except: trans = word

        state.current_sentence_en += word + " "
        state.current_sentence_native += trans + " "
        state.word_history.add(word)
        
        state.current_word = ""
        state.active_suggestion = ""

    # Audio
    ts = str(time.time()).replace('.', '')
    fname = f"audio_{ts}.mp3"
    abs_path = os.path.join(os.getcwd(), 'static', 'audio', fname)
    web_path = f"/static/audio/{fname}"
    try:
        tts = gTTS(text=trans, lang=state.selected_lang, slow=False)
        tts.save(abs_path)
        state.last_audio_file = web_path
    except: pass

# --- VIDEO CAMERA ---
model_path = os.path.join(os.path.dirname(__file__), 'model.p')
try:
    with open(model_path, 'rb') as f:
        model = pickle.load(f)
except FileNotFoundError:
    model = None

class VideoCamera(object):
    def __init__(self):
        self.video = cv2.VideoCapture(0, cv2.CAP_DSHOW)

        
        # Add this check
        if not self.video.isOpened():
            print("❌ Camera failed to open! Trying index 1...")
            self.video = cv2.VideoCapture(1)
        
        if not self.video.isOpened():
            print("❌ Camera index 1 also failed. Check camera permissions.")
        else:
            print("✅ Camera opened successfully")
        
        self.mp_hands = mp.solutions.hands
        self.hands = self.mp_hands.Hands(static_image_mode=False, max_num_hands=2, min_detection_confidence=0.5)
        self.mp_draw = mp.solutions.drawing_utils
        self.hand_history = []
        self.hand_was_visible = False

    def __del__(self):
        self.video.release()

    def predict_sign(self, frame):
        h, w, c = frame.shape
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        results = self.hands.process(rgb)
        
        current_time = time.time()

        # --- TWO HANDS (DELETE GESTURE) ---
        if results.multi_hand_landmarks and len(results.multi_hand_landmarks) == 2:
            state.two_hand_frame_count += 1
            
            # Require 5 stable frames to prevent glitches
            if state.two_hand_frame_count > 5:
                # Cooldown (0.8 seconds)
                if current_time - state.last_delete_time > 0.8:
                    print("✌️ TWO HANDS -> SMART BACKSPACE")
                    
                    perform_backspace() # <--- CALL SHARED LOGIC
                    
                    state.last_delete_time = current_time
                    state.two_hand_frame_count = 0 
                    
                    # Red Flash
                    cv2.rectangle(frame, (0,0), (w,h), (0,0,255), 15)

            for hand_landmarks in results.multi_hand_landmarks:
                self.mp_draw.draw_landmarks(frame, hand_landmarks, self.mp_hands.HAND_CONNECTIONS)
            
            return frame
        else:
            state.two_hand_frame_count = 0

        # --- SINGLE HAND (PREDICT) ---
        if results.multi_hand_landmarks and len(results.multi_hand_landmarks) == 1:
            self.hand_was_visible = True
            for hand_landmarks in results.multi_hand_landmarks:
                self.mp_draw.draw_landmarks(frame, hand_landmarks, self.mp_hands.HAND_CONNECTIONS)
                
                x_min, y_min = w, h
                x_max, y_max = 0, 0
                data_aux = []
                for lm in hand_landmarks.landmark:
                    x, y = int(lm.x * w), int(lm.y * h)
                    if x < x_min: x_min = x
                    if x > x_max: x_max = x
                    if y < y_min: y_min = y
                    if y > y_max: y_max = y
                    data_aux.append(lm.x); data_aux.append(lm.y); data_aux.append(lm.z)
                cv2.rectangle(frame, (x_min-20, y_min-20), (x_max+20, y_max+20), (0, 255, 0), 2)

                if model:
                    prediction = model.predict([data_aux])[0]
                    probs = model.predict_proba([data_aux])[0]
                    conf = np.max(probs)
                    state.confidence_score = float(conf)
                    
                    if conf > 0.4:
                        state.live_prediction = prediction 
                        self.hand_history.append(prediction)
                    else:
                        state.live_prediction = "?"
        else:
            state.live_prediction = "_"
            state.confidence_score = 0.0
            
            if self.hand_was_visible and len(self.hand_history) > 5:
                most_common, _ = Counter(self.hand_history).most_common(1)[0]
                self.process_locked_sign(most_common)
                
            self.hand_history = []
            self.hand_was_visible = False

        return frame

    def process_locked_sign(self, sign):
        if sign == " " or sign == "SPACE":
            commit_current_word()
            return

        clean_sign = str(sign).strip().upper()

        with data_lock:
            state.current_word += sign
            
        update_suggestions()

    def get_frame(self):
        success, frame = self.video.read()
        if not success: return None
        frame = cv2.flip(frame, 1)
        frame = self.predict_sign(frame)
        ret, jpeg = cv2.imencode('.jpg', frame)
        return jpeg.tobytes()