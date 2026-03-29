# Vision-to-Voice — Real-time Gesture Transduction

This project is a local Flask web app that uses MediaPipe and a trained ML model to translate hand-sign letters into words and spoken audio. It supports user accounts, session saving, translation to selected languages via `googletrans`, and TTS via `gTTS`.

Key features
- Live webcam MJPEG stream with landmark overlays
- Per-frame sign prediction (loads `model.p` trained with `train_model.py`)
- Word-building, suggestions/autocomplete, translation, and TTS audio
- User accounts and session history stored in SQLite

Quick start (Windows PowerShell)
```powershell
cd 'c:\Users\lenovo\OneDrive\Desktop\M-project\vision to voice'
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install --upgrade pip
pip install -r requirements.txt
python app.py
# Open http://127.0.0.1:5001 in your browser
```

Data collection & training
- Collect landmark data: `python collect_data.py` (records rows into `data.csv`)
- Train model: `python train_model.py` produces `model.p` (place it in project root)

Security & environment
- Use environment variables for secrets. Copy `.env.example` to `.env` and set `SECRET_KEY`.

Repository updates
- I added `.gitignore`, `.env.example`, and this `README.md`, and updated the app to read `SECRET_KEY` from environment.
