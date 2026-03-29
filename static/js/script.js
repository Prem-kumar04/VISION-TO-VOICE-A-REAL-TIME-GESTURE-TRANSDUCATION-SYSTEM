// ============================================================
// BROWSER WEBCAM + SERVER ML PROCESSING
// ============================================================
const UPDATE_INTERVAL = 150;
let cameraActive = false;

// --- SIGN LANGUAGE REFERENCE ---
function openSignReference() {
    const modal = new bootstrap.Modal(document.getElementById('signChartModal'), {});
    modal.show();
}

// --- WEBRTC SETUP ---
async function initBrowserCamera() {
    const videoElement = document.getElementById('browserVideo');
    const canvasElement = document.getElementById('cameraCanvas');
    const statusEl = document.getElementById('cameraStatus');
    const promptEl = document.getElementById('cameraPrompt');
    
    if (!videoElement || !canvasElement) return;

    try {
        const stream = await navigator.mediaDevices.getUserMedia({ video: { width: 640, height: 480 } });
        videoElement.srcObject = stream;
        
        videoElement.onloadedmetadata = () => {
            cameraActive = true;
            if (promptEl) promptEl.style.display = 'none';
            if (statusEl) {
                statusEl.className = 'camera-status live';
                statusEl.innerText = '🔴 LIVE';
            }
            startWebRTCStream(videoElement, canvasElement);
        };
    } catch(err) {
        console.error("Camera access denied:", err);
        if (statusEl) {
            statusEl.className = 'camera-status error';
            statusEl.innerText = '⚠️ Error Accessing Camera';
        }
    }
}

function startWebRTCStream(video, canvas) {
    const context = canvas.getContext('2d', { willReadFrequently: true });
    
    setInterval(async () => {
        if (!cameraActive) return;
        
        canvas.width = video.videoWidth;
        canvas.height = video.videoHeight;
        context.drawImage(video, 0, 0, canvas.width, canvas.height);
        
        const b64 = canvas.toDataURL('image/jpeg', 0.6); 
        
        try {
            const response = await fetch('/process_frame', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ frame: b64 })
            });
            const data = await response.json();
            
            if (data.annotated_frame) {
                const img = new Image();
                img.onload = () => {
                    context.clearRect(0,0, canvas.width, canvas.height);
                    context.drawImage(img, 0, 0, canvas.width, canvas.height);
                };
                img.src = "data:image/jpeg;base64," + data.annotated_frame;
            }
            updateUI(data);
        } catch(e) {}
    }, UPDATE_INTERVAL); 
}

function startPollingUpdates() {
    setInterval(async () => {
        try {
            const response = await fetch('/get_updates');
            const data = await response.json();
            updateUI(data);
        } catch (error) { console.error(error); }
    }, UPDATE_INTERVAL);
}

function updateUI(data) {
    if(data.live_preview !== undefined) document.getElementById('livePreview').innerText = data.live_preview || "_";
    if(data.current_word !== undefined) document.getElementById('liveWord').innerText = data.current_word;
    if(data.confidence !== undefined) document.getElementById('confScore').innerText = data.confidence + "%";
    if(data.sentence_en !== undefined) document.getElementById('engOut').innerText = data.sentence_en;
    if(data.sentence_native !== undefined) document.getElementById('nativeOut').innerText = data.sentence_native;

    const suggestionBox = document.getElementById('suggestionText');
    if (data.suggestion && data.suggestion.length > (data.current_word || "").length) {
        suggestionBox.innerText = data.suggestion.substring((data.current_word || "").length);
        document.getElementById('enterHint').style.display = "block";
    } else {
        if (suggestionBox) suggestionBox.innerText = "";
        if (document.getElementById('enterHint')) document.getElementById('enterHint').style.display = "none";
    }
}

// --- INITIALIZATION & EVENTS ---
if (document.getElementById('liveWord')) {
    initBrowserCamera().then(() => {
        if (!cameraActive) {
            console.log("No camera detected, falling back to basic polling.");
            startPollingUpdates();
        }
    });

    document.addEventListener('keydown', async (event) => {
        const key = event.key;
        if (key === 'Enter') {
            await fetch('/accept_suggestion', { method: 'POST' });
            return;
        }
        if ((key.length === 1 && key.match(/[a-z ]/i)) || key === 'Backspace') {
            await fetch('/handle_keypress', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ key: key === ' ' ? 'Space' : key })
            });
        }
    });
}

// --- AUDIO FUNCTION ---
async function playFullSentence() {
    console.log("🖱️ Button Clicked");
    const btn = document.querySelector('.speak-btn');
    btn.style.transform = "scale(0.9)";
    setTimeout(() => btn.style.transform = "scale(1)", 100);

    try {
        const response = await fetch('/speak_sentence', { method: 'POST' });
        const data = await response.json();
        
        if (data.status === 'ok') {
            let audio = new Audio(data.audio_url);
            audio.play().catch(e => alert("Browser blocked audio. Click page background."));
        } else {
            alert(data.message || "Audio Error");
        }
    } catch (e) {
        console.error("Audio Fetch Error:", e);
    }
}

async function setLanguage(langCode) {
    await fetch('/set_language', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ lang: langCode })
    });
}

async function saveSession() {
    const response = await fetch('/save_session', { method: 'POST' });
    const result = await response.json();
    if (result.status === 'saved') {
        alert("Saved!");
        window.location.reload();
    } else {
        alert("Nothing to save!");
    }
}