// static/js/exam.js - Enhanced Exam System with AI Face Proctoring
// Features: Timer, Tab Monitoring, Auto-save, AI Face Detection, Violation Tracking

let remainingTime = 0;
let studentExamId = null;
let tabSwitchCount = 0;
let maxTabSwitches = 2;
let timerHandle = null;
let submitting = false;
let showTabSwitches = true;
let examEndTime = null;
let statusCheckInterval = null;

// NEW: Proctoring variables
let proctorEnabled = false;
let calibrationCompleted = false;
let proctorInterval = null;
let video = null;
let canvas = null;
let ctx = null;
let cameraMinimized = false;
let totalViolations = 0;
let maxViolations = 6;

/**
 * Initialize the exam system
 * @param {Object} config - Configuration object
 */
function initExam(config = {}) {
    studentExamId = config.studentExamId || null;
    
    const timeInMinutes = (config.timeRemaining !== undefined && config.timeRemaining !== null)
        ? config.timeRemaining
        : 60;
    remainingTime = timeInMinutes * 60;
    
    tabSwitchCount = Number(config.initialTabSwitchCount) || 0;
    if (tabSwitchCount >= maxTabSwitches) {
        tabSwitchCount = 0;
    }

    maxTabSwitches = parseInt(config.maxTabSwitches || 2, 10) || 2;
    showTabSwitches = config.showTabSwitches ?? true;
    examEndTime = Date.now() + (remainingTime * 1000);
    
    // NEW: Proctoring configuration
    proctorEnabled = config.proctorEnabled ?? true;
    maxViolations = config.maxViolations || 6;
    
    console.log(`📅 Exam initialized:`);
    console.log(`   Time remaining: ${timeInMinutes} minutes (${remainingTime} seconds)`);
    console.log(`   Will end at: ${new Date(examEndTime).toLocaleString()}`);
    console.log(`   Student Exam ID: ${studentExamId}`);
    console.log(`   Proctoring enabled: ${proctorEnabled}`);

    updateTabCountDom();
    attachAnswerHandlers();
    setupSubmitButton();
    monitorUserBehavior();
    startTimer();
    startExamStatusMonitor();
    ensureFullscreenUI();
    tryRequestFullscreen();
    
    // NEW: Initialize proctoring if enabled
    if (proctorEnabled) {
        initProctoring();
    }
}

/* ==========================================
   AI PROCTORING SYSTEM
   ========================================== */

async function initProctoring() {
    console.log("🎯 Initializing AI Proctoring...");
    
    // Show calibration modal
    showCalibrationModal();
}

function showCalibrationModal() {
    const modal = document.createElement('div');
    modal.id = 'calibration-modal';
    modal.className = 'proctor-modal';
    modal.innerHTML = `
        <div class="proctor-modal-content">
            <div class="proctor-header">
                <svg class="proctor-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <path d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"/>
                    <path d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z"/>
                </svg>
                <h2>Camera Calibration</h2>
            </div>
            <div class="proctor-body">
                <p class="proctor-message">
                    We need to calibrate your camera before starting the exam. Please follow the instructions below:
                </p>
                <div class="calibration-instructions">
                    <div class="instruction-item">
                        <span class="instruction-number">1</span>
                        <span>Sit straight and face the screen</span>
                    </div>
                    <div class="instruction-item">
                        <span class="instruction-number">2</span>
                        <span>Ensure your face is visible</span>
                    </div>
                    <div class="instruction-item">
                        <span class="instruction-number">3</span>
                        <span>Stay still for 3 seconds</span>
                    </div>
                </div>
                <div class="calibration-video-container">
                    <video id="calibration-video" autoplay playsinline></video>
                    <div id="calibration-guide-box" class="guide-box"></div>
                </div>
                <canvas id="calibration-canvas" style="display:none;"></canvas>
                <div id="calibration-status" class="calibration-status"></div>
            </div>
            <div class="proctor-footer">
                <button id="btn-calibrate" class="proctor-btn proctor-btn-primary">
                    <svg class="btn-icon" viewBox="0 0 20 20" fill="currentColor">
                        <path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z"/>
                    </svg>
                    Start Calibration
                </button>
            </div>
        </div>
    `;


    
    document.body.appendChild(modal);
    
    // Initialize webcam for calibration
    initCalibrationCamera();
    
    // Setup calibration button
    document.getElementById('btn-calibrate').addEventListener('click', performCalibration);
}

async function initCalibrationCamera() {
    try {
        const stream = await navigator.mediaDevices.getUserMedia({
            video: { width: 640, height: 480 }
        });
        
        const video = document.getElementById('calibration-video');
        video.srcObject = stream;
        
        video.onloadedmetadata = () => {
            video.play();
            updateCalibrationGuideBox();
        };
        
    } catch (err) {
        console.error("Camera access error:", err);
        showCalibrationError("Could not access camera: " + err.message);
    }
}

function updateCalibrationGuideBox() {
    const video = document.getElementById('calibration-video');
    const guideBox = document.getElementById('calibration-guide-box');
    
    if (!video || !guideBox) return;
    
    const w = video.videoWidth || 640;
    const h = video.videoHeight || 480;
    const guideW = w * 0.4;
    const guideH = h * 0.5;
    const left = (w - guideW) / 2;
    const top = (h - guideH) / 2;
    
    guideBox.style.left = left + "px";
    guideBox.style.top = top + "px";
    guideBox.style.width = guideW + "px";
    guideBox.style.height = guideH + "px";
}

async function performCalibration() {
    const statusDiv = document.getElementById('calibration-status');
    const btnCalibrate = document.getElementById('btn-calibrate');
    const video = document.getElementById('calibration-video');
    const canvas = document.getElementById('calibration-canvas');
    
    if (!canvas) {
        console.error("Canvas not found");
        return;
    }
    
    canvas.width = video.videoWidth || 640;
    canvas.height = video.videoHeight || 480;
    const ctx = canvas.getContext('2d');
    
    btnCalibrate.disabled = true;
    statusDiv.textContent = "Calibrating... Please sit straight and look at the screen.";
    statusDiv.className = "calibration-status status-calibrating";
    
    // Collect 20 frames over ~3 seconds
    const frames = [];
    const N = 20;
    
    try {
        for (let i = 0; i < N; i++) {
            ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
            const dataUrl = canvas.toDataURL("image/jpeg", 0.7);
            frames.push(dataUrl);
            await new Promise(res => setTimeout(res, 150));
        }
        
        // Send to backend
        statusDiv.textContent = "Processing calibration data...";
        
        const resp = await fetch(`/api/proctor/calibrate/${studentExamId}`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ frames })
        });
        
        const data = await resp.json();
        
        if (data.status === "ok") {
            calibrationCompleted = true;
            statusDiv.textContent = "✓ Calibration successful!";
            statusDiv.className = "calibration-status status-success";
            
            // Wait 1 second then close modal and start proctoring
            setTimeout(() => {
                closeCalibrationModal();
                startProctoring();
            }, 1500);
            
        } else {
            statusDiv.textContent = "✗ Calibration failed: " + (data.message || "Unknown error");
            statusDiv.className = "calibration-status status-error";
            btnCalibrate.disabled = false;
        }
        
    } catch (err) {
        console.error("Calibration error:", err);
        statusDiv.textContent = "✗ Calibration error: " + err.message;
        statusDiv.className = "calibration-status status-error";
        btnCalibrate.disabled = false;
    }
}

function closeCalibrationModal() {
    const modal = document.getElementById('calibration-modal');
    if (modal) {
        // Stop camera stream
        const video = document.getElementById('calibration-video');
        if (video && video.srcObject) {
            video.srcObject.getTracks().forEach(track => track.stop());
        }
        modal.remove();
    }
}

function showCalibrationError(message) {
    const statusDiv = document.getElementById('calibration-status');
    if (statusDiv) {
        statusDiv.textContent = "✗ " + message;
        statusDiv.className = "calibration-status status-error";
    }
}

async function startProctoring() {
    console.log("📹 Starting AI Proctoring...");
    
    // Create camera preview window
    createCameraPreview();
    
    // Initialize exam webcam
    await initExamCamera();
    
    // Start frame capture every 1 second
    proctorInterval = setInterval(captureAndAnalyzeFrame, 1000);
}

function createCameraPreview() {
    const previewContainer = document.createElement('div');
    previewContainer.id = 'camera-preview-container';
    previewContainer.className = 'camera-preview';
    previewContainer.innerHTML = `
        <div class="camera-header">
            <div class="camera-status">
                <div class="status-dot status-normal"></div>
                <span id="camera-status-text">Monitoring</span>
            </div>
            <div class="camera-controls">
                <button id="btn-minimize-camera" class="camera-control-btn" title="Minimize">
                    <svg viewBox="0 0 20 20" fill="currentColor">
                        <path fill-rule="evenodd" d="M5 10a1 1 0 011-1h8a1 1 0 110 2H6a1 1 0 01-1-1z"/>
                    </svg>
                </button>
            </div>
        </div>
        <div class="camera-body">
            <video id="exam-video" autoplay playsinline></video>
            <canvas id="exam-canvas" style="display:none;"></canvas>
        </div>
        <div class="camera-footer">
            <span id="violation-count">Violations: 0/${maxViolations}</span>
        </div>
    `;
    
    document.body.appendChild(previewContainer);
    
    // Setup minimize button
    document.getElementById('btn-minimize-camera').addEventListener('click', toggleCameraMinimize);
}

function toggleCameraMinimize() {
    const container = document.getElementById('camera-preview-container');
    const btn = document.getElementById('btn-minimize-camera');
    
    cameraMinimized = !cameraMinimized;
    
    if (cameraMinimized) {
        container.classList.add('minimized');
        btn.innerHTML = `
            <svg viewBox="0 0 20 20" fill="currentColor">
                <path fill-rule="evenodd" d="M3 10a1 1 0 011-1h12a1 1 0 110 2H4a1 1 0 01-1-1z"/>
            </svg>
        `;
        btn.title = "Restore";
    } else {
        container.classList.remove('minimized');
        btn.innerHTML = `
            <svg viewBox="0 0 20 20" fill="currentColor">
                <path fill-rule="evenodd" d="M5 10a1 1 0 011-1h8a1 1 0 110 2H6a1 1 0 01-1-1z"/>
            </svg>
        `;
        btn.title = "Minimize";
    }
}

async function initExamCamera() {
    try {
        const stream = await navigator.mediaDevices.getUserMedia({
            video: { width: 640, height: 480 }
        });
        
        video = document.getElementById('exam-video');
        canvas = document.getElementById('exam-canvas');
        
        if (!video || !canvas) {
            console.error("Camera elements not found");
            return;
        }
        
        video.srcObject = stream;
        canvas.width = 640;
        canvas.height = 480;
        ctx = canvas.getContext('2d');
        
        video.onloadedmetadata = () => {
            video.play();
        };
        
    } catch (err) {
        console.error("Exam camera access error:", err);
        showViolationPopup("Camera access required for proctoring. Please enable camera permissions.");
    }
}

async function captureAndAnalyzeFrame() {
    if (!video || !ctx || !calibrationCompleted) return;
    
    try {
        // Capture frame
        ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
        const frameDataUrl = canvas.toDataURL("image/jpeg", 0.7);
        
        // Send to backend for analysis
        const resp = await fetch(`/api/proctor/analyze/${studentExamId}`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                frame: frameDataUrl,
                ts: Date.now()
            })
        });
        
        const data = await resp.json();
        
        // Update UI based on status
        updateCameraStatus(data);
        
        // Handle violations
        if (data.status === "WARNING" || data.status === "NO_FACE") {
            totalViolations = data.total_violations || totalViolations;
            updateViolationCount();
            showViolationPopup(data.message);
            
        } else if (data.status === "TERMINATE" || data.should_terminate) {
            totalViolations = data.total_violations || totalViolations;
            handleTermination(data.message);
        }
        
    } catch (err) {
        console.error("Frame analysis error:", err);
    }
}

function updateCameraStatus(data) {
    const statusDot = document.querySelector('.status-dot');
    const statusText = document.getElementById('camera-status-text');
    
    if (!statusDot || !statusText) return;
    
    statusDot.className = 'status-dot';
    
    if (data.status === "NORMAL") {
        statusDot.classList.add('status-normal');
        statusText.textContent = "Monitoring";
    } else if (data.status === "WARNING" || data.status === "NO_FACE") {
        statusDot.classList.add('status-warning');
        statusText.textContent = "Warning";
    } else if (data.status === "TERMINATE") {
        statusDot.classList.add('status-terminate');
        statusText.textContent = "Terminated";
    }
}

function updateViolationCount() {
    const violationCountEl = document.getElementById('violation-count');
    if (violationCountEl) {
        violationCountEl.textContent = `Violations: ${totalViolations}/${maxViolations}`;
        
        if (totalViolations >= maxViolations - 2) {
            violationCountEl.classList.add('warning');
        }
    }
}

function showViolationPopup(message) {
    // Create popup overlay
    const popup = document.createElement('div');
    popup.className = 'violation-popup';
    popup.innerHTML = `
        <div class="violation-popup-content">
            <div class="violation-icon">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <path d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"/>
                </svg>
            </div>
            <h3>Proctoring Alert</h3>
            <p>${message}</p>
            <p class="violation-warning">Violations: ${totalViolations}/${maxViolations}</p>
            <button class="violation-btn" onclick="this.parentElement.parentElement.remove()">
                I Understand
            </button>
        </div>
    `;
    
    document.body.appendChild(popup);
    
    // Auto-remove after 5 seconds
    setTimeout(() => {
        if (popup.parentElement) {
            popup.remove();
        }
    }, 5000);
}

async function handleTermination(message) {
    console.warn("🚨 Proctoring violation threshold exceeded");
    
    // Stop proctoring
    if (proctorInterval) {
        clearInterval(proctorInterval);
        proctorInterval = null;
    }
    
    // Stop camera
    if (video && video.srcObject) {
        video.srcObject.getTracks().forEach(track => track.stop());
    }
    
    // Show termination message
    showAutoSubmitPopup(message || "Too many proctoring violations detected. Auto-submitting exam...");
    
    // Auto-submit exam
    await autoSubmitExam();
}

/* ==========================================
   TIMER MANAGEMENT
   ========================================== */

function startTimer() {
    const timers = document.querySelectorAll("#header-timer, #exam-timer");
    if (!timers.length) {
        console.warn("⚠️ Timer elements not found");
        return;
    }

    if (timerHandle) clearInterval(timerHandle);

    function updateTimer() {
        const now = Date.now();
        remainingTime = Math.max(0, (examEndTime - now) / 1000);

        if (remainingTime <= 0) {
            timers.forEach(el => el.textContent = "00:00:00");
            clearInterval(timerHandle);
            showAutoSubmitPopup("Time's up! Auto-submitting your exam...");
            autoSubmitExam();
            return;
        }

        const hours = Math.floor(remainingTime / 3600);
        const minutes = Math.floor((remainingTime % 3600) / 60);
        const seconds = Math.floor(remainingTime % 60);
        const formatted = `${String(hours).padStart(2, "0")}:${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;

        timers.forEach(el => {
            el.textContent = formatted;
            el.classList.remove("warning", "danger");
            if (remainingTime <= 300 && remainingTime > 120) el.classList.add("warning");
            if (remainingTime <= 120) el.classList.add("danger");
        });
    }

    updateTimer();
    timerHandle = setInterval(updateTimer, 1000);
}

/* ==========================================
   EXAM STATUS MONITORING
   ========================================== */

function startExamStatusMonitor() {
    if (!studentExamId) {
        console.warn("startExamStatusMonitor: studentExamId not set yet — retrying in 1s");
        setTimeout(startExamStatusMonitor, 1000);
        return;
    }

    if (statusCheckInterval) {
        clearInterval(statusCheckInterval);
        statusCheckInterval = null;
    }

    statusCheckInterval = setInterval(async () => {
        try {
            console.log(`Checking exam status for studentExamId=${studentExamId} ...`);
            const response = await fetch(`/api/check-exam-status/${studentExamId}`, { cache: "no-store" });

            if (!response.ok) {
                console.warn("Exam status check returned non-OK:", response.status);
                return;
            }

            const data = await response.json();
            console.debug("Exam status payload:", data);

            const facultyEnded = data.force_ended === true
                              || data.force_end === true
                              || (data.force_ended_at && new Date(data.force_ended_at).getTime() <= Date.now())
                              || (data.force_ended_time && new Date(data.force_ended_time).getTime() <= Date.now());

            if (facultyEnded) {
                console.warn("Faculty forced exam end detected. Submitting now.");
                if (statusCheckInterval) { clearInterval(statusCheckInterval); statusCheckInterval = null; }
                if (timerHandle) { clearInterval(timerHandle); timerHandle = null; }
                if (proctorInterval) { clearInterval(proctorInterval); proctorInterval = null; }

                try { showFacultyEndPopup(); } catch (e) { console.warn("showFacultyEndPopup error:", e); }

                try {
                    await autoSubmitExam();
                } catch (e) {
                    console.error("autoSubmitExam threw an error after faculty end:", e);
                    try {
                        alert("Exam is being submitted by instructor. If you are not redirected, please contact support.");
                    } catch (_) {}
                }
                return;
            }

            if (data.updated_end_time) {
                const newEndTime = new Date(data.updated_end_time).getTime();
                if (!isNaN(newEndTime) && newEndTime > Date.now()) {
                    if (newEndTime !== examEndTime) {
                        examEndTime = newEndTime;
                        console.log(`⏰ Exam end time updated by server -> ${new Date(examEndTime).toLocaleString()}`);
                        if (timerHandle) { clearInterval(timerHandle); timerHandle = null; }
                        startTimer();
                    }
                } else {
                    console.warn("Ignoring invalid/past updated_end_time from server:", data.updated_end_time);
                }
            }

        } catch (err) {
            console.warn("Status check failed:", err);
        }
    }, 2000);
}

function showFacultyEndPopup() {
    blockNavigation();
    
    const overlay = document.createElement('div');
    overlay.id = 'faculty-end-overlay';
    overlay.innerHTML = `
        <div style="position: fixed; top: 0; left: 0; width: 100%; height: 100%; 
                    background: rgba(0,0,0,0.95); z-index: 99999; 
                    display: flex; align-items: center; justify-content: center;">
            <div style="background: white; padding: 40px; border-radius: 12px; 
                        max-width: 500px; text-align: center; box-shadow: 0 10px 40px rgba(0,0,0,0.3);">
                <div style="width: 80px; height: 80px; margin: 0 auto 20px; 
                            background: #ef4444; border-radius: 50%; 
                            display: flex; align-items: center; justify-content: center;">
                    <svg style="width: 48px; height: 48px; color: white;" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <circle cx="12" cy="12" r="10"/>
                        <line x1="12" y1="8" x2="12" y2="12"/>
                        <line x1="12" y1="16" x2="12.01" y2="16"/>
                    </svg>
                </div>
                <h2 style="font-size: 24px; margin: 0 0 12px; color: #1f2937;">Exam Ended by Instructor</h2>
                <p style="font-size: 16px; color: #6b7280; margin: 0 0 20px;">
                    Your instructor has ended this exam. Your responses are being submitted automatically.
                </p>
                <div style="display: flex; align-items: center; justify-content: center; gap: 8px; color: #3b82f6;">
                    <svg style="width: 20px; height: 20px; animation: spin 1s linear infinite;" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <path d="M21 12a9 9 0 11-6.219-8.56"/>
                    </svg>
                    <span>Submitting...</span>
                </div>
            </div>
        </div>
    `;
    document.body.appendChild(overlay);
}

function blockNavigation() {
    window.onbeforeunload = () => "Exam submission in progress. Please wait.";
}

function showAutoSubmitPopup(message) {
    blockNavigation();
    const overlay = document.createElement('div');
    overlay.style.cssText = `
        position: fixed; top: 0; left: 0; width: 100%; height: 100%;
        background: rgba(0,0,0,0.9); z-index: 999999;
        display: flex; align-items: center; justify-content: center;
    `;
    overlay.innerHTML = `
        <div style="background: white; padding: 30px; border-radius: 8px; text-align: center; max-width: 400px;">
            <h3 style="margin: 0 0 15px; color: #1f2937;">${message}</h3>
            <div style="display: flex; justify-content: center; align-items: center; gap: 8px; color: #3b82f6;">
                <svg style="width: 20px; height: 20px; animation: spin 1s linear infinite;" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <path d="M21 12a9 9 0 11-6.219-8.56"/>
                </svg>
                <span>Submitting...</span>
            </div>
        </div>
    `;
    document.body.appendChild(overlay);
}

/* ==========================================
   ANSWER HANDLING
   ========================================== */

function attachAnswerHandlers() {
    const radios = document.querySelectorAll("[name^='question_']");
    radios.forEach(radio => {
        radio.addEventListener("change", async (e) => {
            const input = e.target;
            const questionId = input.dataset.questionId;
            const answer = input.value;
            
            const label = input.closest("label");
            if (label) {
                const allLabels = document.querySelectorAll(`[name='${input.name}']`).forEach(r => {
                    r.closest("label")?.classList.remove("selected");
                });
                label.classList.add("selected");
            }
            
            await saveAnswer(questionId, answer);
        });
    });
}

async function saveAnswer(questionId, answer) {
    if (!studentExamId || !questionId) return;
    try {
        await fetch(`/api/save-answer/${studentExamId}`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                question_id: questionId,
                selected_answer: answer
            })
        });
    } catch (err) {
        console.warn("Save answer error:", err);
    }
}

/* ==========================================
   USER BEHAVIOR MONITORING
   ========================================== */

function monitorUserBehavior() {
    let outTimer = null;
    let outSeconds = 0;

    document.addEventListener("visibilitychange", async () => {
        if (document.hidden) {
            outSeconds = 0;
            outTimer = setInterval(async () => {
                outSeconds++;
                if (outSeconds >= 5) {
                    clearInterval(outTimer);
                    showAutoSubmitPopup("You were away from the exam window for too long. Auto-submitting...");
                    await autoSubmitExam();
                }
            }, 1000);

            tabSwitchCount = (tabSwitchCount || 0) + 1;
            updateTabCountDom();
            await logActivity("tab_switch", `Tab switched, count=${tabSwitchCount}`, "medium");

            try {
                await fetch(`/api/update-tabcount/${studentExamId}`, {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ tab_switch_count: tabSwitchCount })
                });
            } catch (_) {}

            if (tabSwitchCount >= maxTabSwitches) {
                clearInterval(outTimer);
                showAutoSubmitPopup("Too many tab switches detected. Auto-submitting...");
                await autoSubmitExam();
            }

        } else {
            if (outTimer) clearInterval(outTimer);
            outSeconds = 0;
        }
    });

    document.addEventListener("fullscreenchange", async () => {
        const overlay = document.getElementById("fs-overlay");
        if (document.fullscreenElement) {
            if (overlay) overlay.style.display = "none";
            await logActivity("fullscreen_enter", "Entered fullscreen", "low");
        } else {
            if (overlay) overlay.style.display = "flex";
            await logActivity("fullscreen_exit", "Exited fullscreen", "medium");
            alert("⚠️ You left fullscreen. Re-enter immediately or the exam may be auto-submitted.");
        }
    });

    document.addEventListener("contextmenu", (e) => e.preventDefault());

    ["copy", "paste", "cut", "selectstart"].forEach(evt => {
        document.addEventListener(evt, (e) => e.preventDefault());
    });

    document.addEventListener("keyup", async (e) => {
        if (e.key === "PrintScreen") {
            try { await navigator.clipboard.writeText(""); } catch (_) {}
            alert("⚠️ Screenshot attempt detected!");
            await logActivity("screenshot_attempt", "Pressed PrintScreen", "high");
        }
    });

    document.addEventListener("keydown", async (e) => {
        if ((e.ctrlKey && e.key.toLowerCase() === "p") || 
            (e.metaKey && e.shiftKey && ["3", "4"].includes(e.key))) {
            e.preventDefault();
            alert("Printing/screenshot disabled during the exam.");
            await logActivity("screenshot_hotkey", "Attempted screenshot hotkey", "high");
        }
    });
}

/* ==========================================
   UI HELPERS
   ========================================== */

function updateTabCountDom() {
    if (!showTabSwitches) return;
    const el = document.getElementById("tab-count") || document.getElementById("tab-switch-counter");
    if (!el) return;
    el.textContent = `${tabSwitchCount} / ${maxTabSwitches}`;
    
    if (tabSwitchCount >= maxTabSwitches) {
        el.classList.add("alert");
    } else {
        el.classList.remove("alert");
    }
}

async function logActivity(type, description, severity = "low") {
    if (!studentExamId) return;
    try {
        await fetch(`/api/log-activity/${studentExamId}`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ 
                activity_type: type, 
                description, 
                severity 
            })
        });
    } catch (_) {}
}

/* ==========================================
   SUBMIT LOGIC
   ========================================== */

function setupSubmitButton() {
    const btn = document.getElementById("submit-btn");
    if (!btn) return;
    btn.addEventListener("click", async () => {
        if (!confirm("Are you sure you want to submit the exam?")) return;
        await autoSubmitExam();
    });
}

async function autoSubmitExam() {
    if (submitting) return;
    submitting = true;
    
    if (timerHandle) clearInterval(timerHandle);
    if (statusCheckInterval) clearInterval(statusCheckInterval);
    if (proctorInterval) clearInterval(proctorInterval);
    
    // Stop camera
    if (video && video.srcObject) {
        video.srcObject.getTracks().forEach(track => track.stop());
    }

    try {
        const allInputs = Array.from(document.querySelectorAll("[name^='question_']"));
        const answered = new Set();
        allInputs.forEach(i => { 
            if (i.checked) answered.add(i.name); 
        });

        const questionNames = Array.from(new Set(allInputs.map(i => i.name)));
        const unansweredIds = [];
        for (const qname of questionNames) {
            if (!answered.has(qname)) {
                const el = document.querySelector(`[name='${qname}']`);
                if (!el) continue;
                const qid = el.dataset.questionId;
                if (qid) unansweredIds.push(qid);
            }
        }

        await Promise.all(unansweredIds.map(qid => saveAnswer(qid, "0")));

        const form = document.getElementById("submit-form");
        if (form) {
            form.submit();
        } else if (studentExamId) {
            await fetch(`/submit_exam/${studentExamId}`, { method: "POST" });
            alert("✅ Exam submitted successfully.");
            window.location = "/";
        } else {
            alert("Exam submitted.");
        }
    } catch (err) {
        console.error("Submit error:", err);
        alert("An error occurred while submitting. Please contact support.");
    } finally {
        submitting = false;
    }
}

/* ==========================================
   FULLSCREEN HELPERS
   ========================================== */

function tryRequestFullscreen() {
    try {
        const el = document.documentElement;
        if (el.requestFullscreen) {
            el.requestFullscreen().catch(() => {});
        } else if (el.webkitRequestFullscreen) {
            el.webkitRequestFullscreen();
        }
    } catch (e) {}
}

function ensureFullscreenUI() {
    const overlay = document.getElementById("fs-overlay");
    if (!overlay) return;

    if (!document.fullscreenElement) {
        overlay.style.display = "flex";
        const btn = document.getElementById("fs-enter-btn");
        if (btn) {
            btn.addEventListener("click", async () => {
                tryRequestFullscreen();
            });
        }
    } else {
        overlay.style.display = "none";
    }
}

// Export initExam function
window.initExam = initExam;