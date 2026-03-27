// ============================================================
// BROWSER WEBCAM + SERVER ML PROCESSING
// ============================================================

const FRAME_INTERVAL = 150; // Send frame every 150ms (~6-7 FPS)
const UPDATE_INTERVAL = 100;

let browserStream = null;
let isProcessing = false;
let cameraActive = false;

// --- INIT: Start browser webcam ---
async function initBrowserCamera() {
    const video = document.getElementById('browserVideo');
    const canvas = document.getElementById('cameraCanvas');
    const statusBadge = document.getElementById('cameraStatus');
    const prompt = document.getElementById('cameraPrompt');
    
    if (!video || !canvas) return;

    try {
        // Request camera from browser
        browserStream = await navigator.mediaDevices.getUserMedia({
            video: { 
                width: { ideal: 640 },
                height: { ideal: 480 },
                facingMode: 'user'
            },
            audio: false
        });

        video.srcObject = browserStream;
        await video.play();
        
        // Set canvas size to match video
        canvas.width = video.videoWidth || 640;
        canvas.height = video.videoHeight || 480;
        
        // Update UI
        statusBadge.className = 'camera-status live';
        statusBadge.innerHTML = '🟢 Camera Live';
        prompt.style.display = 'none';
        cameraActive = true;

        console.log("✅ Browser camera started successfully");
        
        // Start the frame processing loop
        startFrameLoop();

    } catch (err) {
        console.error("Camera error:", err);
        
        statusBadge.className = 'camera-status error';
        
        if (err.name === 'NotAllowedError') {
            statusBadge.innerHTML = '❌ Camera Denied';
            prompt.innerHTML = `
                <span class="cam-icon">🚫</span>
                <h3>Camera Access Denied</h3>
                <p>Please allow camera access in your browser settings and reload the page.</p>
                <p style="color: #6c5ce7; margin-top: 15px;">You can still use <strong>keyboard input</strong> to type signs!</p>
            `;
        } else if (err.name === 'NotFoundError') {
            statusBadge.innerHTML = '❌ No Camera Found';
            prompt.innerHTML = `
                <span class="cam-icon">📷</span>
                <h3>No Camera Detected</h3>
                <p>Connect a webcam and reload the page.</p>
                <p style="color: #6c5ce7; margin-top: 15px;">You can still use <strong>keyboard input</strong> to type signs!</p>
            `;
        } else {
            statusBadge.innerHTML = '❌ Camera Error';
            prompt.innerHTML = `
                <span class="cam-icon">⚠️</span>
                <h3>Camera Error</h3>
                <p>${err.message}</p>
                <p style="color: #6c5ce7; margin-top: 15px;">You can still use <strong>keyboard input</strong> to type signs!</p>
            `;
        }
    }
}

// --- FRAME PROCESSING LOOP ---
function startFrameLoop() {
    const video = document.getElementById('browserVideo');
    const canvas = document.getElementById('cameraCanvas');
    const ctx = canvas.getContext('2d');
    
    // Temporary canvas for capturing frames to send
    const captureCanvas = document.createElement('canvas');
    captureCanvas.width = 640;
    captureCanvas.height = 480;
    const captureCtx = captureCanvas.getContext('2d');

    async function processFrame() {
        if (!cameraActive) return;

        // Don't queue up requests if one is still processing
        if (!isProcessing) {
            isProcessing = true;
            
            try {
                // Capture frame from video
                captureCtx.drawImage(video, 0, 0, 640, 480);
                const frameData = captureCanvas.toDataURL('image/jpeg', 0.6);
                
                // Send to server for ML processing
                const response = await fetch('/process_frame', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ frame: frameData })
                });
                
                if (response.ok) {
                    const data = await response.json();
                    
                    // Draw the annotated frame on the visible canvas
                    if (data.annotated_frame) {
                        const img = new Image();
                        img.onload = function() {
                            canvas.width = img.width;
                            canvas.height = img.height;
                            ctx.drawImage(img, 0, 0);
                        };
                        img.src = 'data:image/jpeg;base64,' + data.annotated_frame;
                    }
                    
                    // Update UI with prediction data
                    updateUI(data);
                }
            } catch (err) {
                // Network error — just skip this frame
                console.warn("Frame send error:", err.message);
            }
            
            isProcessing = false;
        }

        // Schedule next frame
        setTimeout(processFrame, FRAME_INTERVAL);
    }

    // Start the loop
    processFrame();
}

// --- UPDATE UI FROM SERVER RESPONSE ---
function updateUI(data) {
    const livePreview = document.getElementById('livePreview');
    const liveWord = document.getElementById('liveWord');
    const confScore = document.getElementById('confScore');
    const engOut = document.getElementById('engOut');
    const nativeOut = document.getElementById('nativeOut');
    const suggestionBox = document.getElementById('suggestionText');
    const enterHint = document.getElementById('enterHint');

    if (livePreview) livePreview.innerText = data.live_preview || "_";
    if (liveWord) liveWord.innerText = data.current_word || "";
    if (confScore) confScore.innerText = (data.confidence || 0) + "%";
    if (engOut) engOut.innerText = data.sentence_en || "";
    if (nativeOut) nativeOut.innerText = data.sentence_native || "";

    // Suggestions
    if (suggestionBox && enterHint) {
        if (data.suggestion && data.suggestion.length > (data.current_word || "").length) {
            suggestionBox.innerText = data.suggestion.substring((data.current_word || "").length);
            enterHint.style.display = "block";
        } else {
            suggestionBox.innerText = "";
            enterHint.style.display = "none";
        }
    }
}

// --- FALLBACK: Polling for keyboard-only mode (when camera not available) ---
function startPollingUpdates() {
    setInterval(async () => {
        try {
            const response = await fetch('/get_updates');
            const data = await response.json();
            updateUI(data);
        } catch (error) { console.error(error); }
    }, UPDATE_INTERVAL);
}

// --- KEYBOARD LISTENER ---
if (document.getElementById('liveWord')) {
    document.addEventListener('keydown', async (event) => {
        const key = event.key;
        
        // 1. Enter Key (Autocomplete)
        if (key === 'Enter') {
            await fetch('/accept_suggestion', { method: 'POST' });
            return;
        }

        // 2. Letters, Space, AND BACKSPACE
        if ((key.length === 1 && key.match(/[a-z ]/i)) || key === 'Backspace') {
            await fetch('/handle_keypress', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ key: key === ' ' ? 'Space' : key })
            });
        }
    });

    // Initialize camera on page load
    initBrowserCamera().then(() => {
        // If camera failed, start polling for keyboard-only updates
        if (!cameraActive) {
            console.log("Camera not active, starting polling for keyboard updates...");
            startPollingUpdates();
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