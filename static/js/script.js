// ============================================================
// BROWSER WEBCAM + SERVER ML PROCESSING
// ============================================================

// --- SIGN LANGUAGE REFERENCE ---
function openSignReference() {
    const modal = new bootstrap.Modal(document.getElementById('signChartModal'), {});
    modal.show();
}

// --- POLLING LOOP ---
if (document.getElementById('liveWord')) {
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