import cv2
import mediapipe as mp
import numpy as np
import pickle
import os
import time
import threading
import base64
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

        state.current_sentence_en += word + " "
        state.word_history.add(word)
        
        state.current_word = ""
        state.active_suggestion = ""

    # Translation & Audio (Async) - Run in background thread to avoid blocking
    def translate_and_speak():
        try:
            if state.selected_lang == 'en': 
                trans = word
            else: 
                trans = translator.translate(word, dest=state.selected_lang).text
        except: 
            trans = word
        
        # Update native translation
        with data_lock:
            state.current_sentence_native += trans + " "
        
        # Generate audio
        try:
            ts = str(time.time()).replace('.', '')
            fname = f"audio_{ts}.mp3"
            abs_path = os.path.join(os.getcwd(), 'static', 'audio', fname)
            web_path = f"/static/audio/{fname}"
            tts = gTTS(text=trans, lang=state.selected_lang, slow=False)
            tts.save(abs_path)
            state.last_audio_file = web_path
        except: pass
    
    async_thread = threading.Thread(target=translate_and_speak, daemon=True)
    async_thread.start()

# --- LOAD ML MODEL ---
model_path = os.path.join(os.path.dirname(__file__), 'model.p')
try:
    with open(model_path, 'rb') as f:
        model = pickle.load(f)
except FileNotFoundError:
    model = None

class VideoCamera(object):
    def __init__(self):
        # Try multiple camera indices silently
        self.video = None
        for camera_index in [0, 1, -1]:  # -1 tries any available camera
            try:
                if camera_index == 0:
                    self.video = cv2.VideoCapture(0, cv2.CAP_DSHOW)
                else:
                    self.video = cv2.VideoCapture(camera_index)
                
                if self.video.isOpened():
                    print(f"✅ Camera opened successfully at index {camera_index}")
                    break
                else:
                    self.video.release()
                    self.video = None
            except:
                self.video = None
        
        if self.video is None:
            print("⚠️ Warning: No camera detected. App will run in demo mode.")
            self.video = cv2.VideoCapture(0)  # Keep placeholder
        
        self.mp_hands = mp.solutions.hands
        self.hands = self.mp_hands.Hands(
            static_image_mode=False, 
            max_num_hands=2, 
            min_detection_confidence=0.5
        )
        self.mp_draw = mp.solutions.drawing_utils
        self.hand_history = []
        self.hand_was_visible = False

    def process_browser_frame(self, base64_data):
        """
        Receives a base64-encoded JPEG from the browser,
        runs hand detection + sign prediction,
        returns annotated frame (base64) + prediction data.
        """
        try:
            # Decode base64 → numpy array
            # Handle data URL format: "data:image/jpeg;base64,/9j/4AAQ..."
            if ',' in base64_data:
                base64_data = base64_data.split(',')[1]
            
            img_bytes = base64.b64decode(base64_data)
            nparr = np.frombuffer(img_bytes, np.uint8)
            frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            
            if frame is None:
                return None, {}

            # Run prediction (same logic as VideoCamera.predict_sign)
            frame = self._predict_sign(frame)
            
            # Encode annotated frame back to base64 JPEG
            ret, jpeg = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 70])
            if not ret:
                return None, {}
            
            annotated_b64 = base64.b64encode(jpeg.tobytes()).decode('utf-8')
            
            return annotated_b64, {
                'live_preview': state.live_prediction,
                'current_word': state.current_word,
                'confidence': int(state.confidence_score * 100),
                'sentence_en': state.current_sentence_en,
                'sentence_native': state.current_sentence_native,
                'suggestion': state.active_suggestion,
                'audio_url': state.last_audio_file,
            }
            
        except Exception as e:
            print(f"Frame processing error: {e}")
            return None, {}

    def _predict_sign(self, frame):
        """Run hand detection + sign prediction on a single frame."""
        h, w, c = frame.shape
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        results = self.hands.process(rgb)
        
        current_time = time.time()

        # --- TWO HANDS (DELETE GESTURE) ---
        if results.multi_hand_landmarks and len(results.multi_hand_landmarks) == 2:
            state.two_hand_frame_count += 1
            
            if state.two_hand_frame_count > 5:
                if current_time - state.last_delete_time > 0.8:
                    print("TWO HANDS -> SMART BACKSPACE")
                    perform_backspace()
                    state.last_delete_time = current_time
                    state.two_hand_frame_count = 0 
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
                self._process_locked_sign(most_common)
                
            self.hand_history = []
            self.hand_was_visible = False

        return frame

    def _process_locked_sign(self, sign):
        if sign == " " or sign == "SPACE":
            commit_current_word()
            return

        clean_sign = str(sign).strip().upper()

        with data_lock:
            state.current_word += sign
            
        update_suggestions()


# ============================================================
# VIDEO CAMERA (legacy - for LOCAL use only, needs hardware cam)
# ============================================================
class VideoCamera(object):
    def __init__(self):
        self.camera_available = False
        self.video = None
        
        try:
            self.video = cv2.VideoCapture(0, cv2.CAP_DSHOW)
            if not self.video.isOpened():
                print("Camera index 0 failed. Trying index 1...")
                self.video = cv2.VideoCapture(1)
            
            if not self.video.isOpened():
                self.video = cv2.VideoCapture(0)
            
            if self.video.isOpened():
                self.camera_available = True
                print("Camera opened successfully")
            else:
                print("No camera available - running in demo mode")
        except Exception as e:
            print(f"Camera init error: {e} - running in demo mode")
        
        self.mp_hands = mp.solutions.hands
        self.hands = self.mp_hands.Hands(static_image_mode=False, max_num_hands=2, min_detection_confidence=0.5)
        self.mp_draw = mp.solutions.drawing_utils
        self.hand_history = []
        self.hand_was_visible = False

    def __del__(self):
        if self.video and self.video.isOpened():
            self.video.release()

    def _placeholder_frame(self):
        """Return a placeholder frame when no camera is available."""
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        for i in range(480):
            frame[i, :] = [int(30 + i * 0.05), int(20 + i * 0.03), int(40 + i * 0.06)]
        
        cv2.putText(frame, "No Camera Available", (120, 220),
                    cv2.FONT_HERSHEY_SIMPLEX, 1.2, (200, 200, 200), 2)
        cv2.putText(frame, "Running in Demo Mode", (150, 270),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (150, 150, 150), 1)
        cv2.putText(frame, "Use keyboard to type signs", (130, 320),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (100, 180, 255), 1)
        
        ret, jpeg = cv2.imencode('.jpg', frame)
        return jpeg.tobytes()

    def predict_sign(self, frame):
        h, w, c = frame.shape
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        results = self.hands.process(rgb)
        
        current_time = time.time()

        if results.multi_hand_landmarks and len(results.multi_hand_landmarks) == 2:
            state.two_hand_frame_count += 1
            if state.two_hand_frame_count > 5:
                if current_time - state.last_delete_time > 0.8:
                    print("TWO HANDS -> SMART BACKSPACE")
                    perform_backspace()
                    state.last_delete_time = current_time
                    state.two_hand_frame_count = 0 
                    cv2.rectangle(frame, (0,0), (w,h), (0,0,255), 15)

            for hand_landmarks in results.multi_hand_landmarks:
                self.mp_draw.draw_landmarks(frame, hand_landmarks, self.mp_hands.HAND_CONNECTIONS)
            
            return frame
        else:
            state.two_hand_frame_count = 0

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
        if not self.camera_available:
            return self._placeholder_frame()
        success, frame = self.video.read()
        if not success: 
            return self._placeholder_frame()
        frame = cv2.flip(frame, 1)
        frame = self.predict_sign(frame)
        ret, jpeg = cv2.imencode('.jpg', frame)
        return jpeg.tobytes()