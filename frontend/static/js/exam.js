/**
 * UPDATED exam.js
 * - fixes: visible student camera, reliable violation counting,
 *          immediate termination on fullscreen exit,
 *          debounced tab switch counting, correct API endpoints
 *
 * Keep all previous features; additions are clearly commented.
 */

// GLOBAL STATE MANAGEMENT
const ExamState = {
    studentExamId: null,
    timeRemainingMinutes: 0,
    maxTabSwitches: 3,
    showTabSwitches: true,

    timerInterval: null,
    secondsLeft: 0,

    tabSwitchCount: 0,
    isExamActive: true,

    // Camera & Proctoring
    videoStream: null,
    // visible video for student preview (should be an existing element #student-camera in the template)
    studentCameraElement: null,
    // hidden video used for efficient frame capture and sending (keeps existing behavior)
    videoElement: null,
    sendCanvas: null,
    sendContext: null,
    calibrationComplete: false,
    proctoringInterval: null,

    // Socket.IO
    socket: null,

    // Violation Tracking (local counters)
    violations: {
        no_face: 0,
        multiple_faces: 0,
        looking_away: 0
    },

    // Answer Management
    answers: {},
    lastSaveTime: 0,
    saveDebounceTimer: null,

    // UI Elements
    modal: null,
    calibVideo: null,
    calibStatus: null,
    calibButton: null,
    blockedView: null,
    questionsContainer: null,

    // Tab switch debounce
    lastTabSwitchAt: 0,

    // Heartbeat to detect socket disconnect
    lastSocketHeartbeat: Date.now()
};

// MAIN INITIALIZATION
function initExam(config) {
    console.log("🎯 Initializing Exam System...");
    console.log("Config:", config);

    ExamState.studentExamId = config.studentExamId;
    ExamState.timeRemainingMinutes = config.timeRemaining;
    ExamState.secondsLeft = Math.max(0, Math.floor(config.timeRemaining * 60));
    ExamState.maxTabSwitches = config.maxTabSwitches || 3;
    ExamState.tabSwitchCount = config.initialTabSwitchCount || 0;
    ExamState.showTabSwitches = config.showTabSwitches !== false;

    if (typeof io !== 'undefined') {
        ExamState.socket = io();
        console.log("✅ Socket.IO initialized");
        setupSocketHandlers();
    } else {
        console.error("❌ Socket.IO not available");
    }

    // DOM refs
    ExamState.modal = document.getElementById('proctor-modal');
    ExamState.calibVideo = document.getElementById('calib-video');
    ExamState.calibStatus = document.getElementById('calibration-status');
    ExamState.calibButton = document.getElementById('btn-calibrate');
    ExamState.blockedView = document.getElementById('blocked-view');
    ExamState.questionsContainer = document.getElementById('exam-questions-container');
    ExamState.sendCanvas = document.getElementById('sendCanvas');

    // NEW: student-visible camera element. Ensure your template contains <video id="student-camera" autoplay playsinline></video>
    ExamState.studentCameraElement = document.getElementById('student-camera');

    if (ExamState.sendCanvas) {
        ExamState.sendContext = ExamState.sendCanvas.getContext('2d');
    }

    // ⛔ BLOCK COPY / PASTE / CUT / RIGHT CLICK
    // Disable copy, paste, cut, right-click, selection, and Ctrl+C/V/X/A
    document.addEventListener("copy", (e) => e.preventDefault());
    document.addEventListener("paste", (e) => e.preventDefault());
    document.addEventListener("cut", (e) => e.preventDefault());
    document.addEventListener("contextmenu", (e) => e.preventDefault());
    document.addEventListener("selectstart", (e) => e.preventDefault());

    document.addEventListener("keydown", function (e) {
        if ((e.ctrlKey || e.metaKey) &&
            ["c", "v", "x", "a"].includes(e.key.toLowerCase())) {
            e.preventDefault();
        }
    });

    updateTabSwitchDisplay();
    showCalibrationModal();
    setupEventListeners();
    setupAnswerTracking();
    setupVisibilityMonitoring();
    setupFullscreenMonitoring();

    // small heartbeat to watch socket
    setInterval(() => {
        if (ExamState.socket && ExamState.socket.connected) {
            ExamState.socket.emit('heartbeat', { ts: Date.now(), studentExamId: ExamState.studentExamId });
        } else {
            // if socket down, warn once
            if (!ExamState.socket) return;
            console.warn("⚠️ Socket not connected");
        }
    }, 10000);

    console.log("✅ Exam initialization complete");
}

// SOCKET.IO HANDLERS
function setupSocketHandlers() {
    if (!ExamState.socket) return;

    ExamState.socket.on('calibration_result', (data) => {
        console.log("📸 Calibration result:", data);
        handleCalibrationResult(data);
    });

    ExamState.socket.on('proctor_result', (data) => {
        console.log("👁️ Proctor result:", data);
        handleProctoringResult(data);
    });

    ExamState.socket.on('connect', () => {
        console.log("✅ Socket connected");
    });

    ExamState.socket.on('disconnect', () => {
        console.warn("⚠️ Socket disconnected");
        showNotification("Proctor connection lost. Attempting to reconnect...", "warning");
    });

    // optional server heartbeat ack
    ExamState.socket.on('heartbeat_ack', (d) => {
        ExamState.lastSocketHeartbeat = Date.now();
    });
}

// CALIBRATION MODAL SYSTEM
function showCalibrationModal() {
    console.log("📸 Showing calibration modal");
    if (!ExamState.modal) { console.error("❌ Modal element not found"); return; }
    ExamState.modal.classList.remove('hidden');
    ExamState.modal.style.display = 'flex';
    updateCalibrationStatus("Requesting camera access...", "info");
    startCalibrationCamera();
}
function hideCalibrationModal() {
    console.log("✅ Hiding calibration modal");
    if (ExamState.modal) { ExamState.modal.classList.add('hidden'); ExamState.modal.style.display = 'none'; }
    if (ExamState.calibVideo && ExamState.calibVideo.srcObject) {
        const tracks = ExamState.calibVideo.srcObject.getTracks();
        tracks.forEach(track => track.stop());
        ExamState.calibVideo.srcObject = null;
    }
}

async function startCalibrationCamera() {
    console.log("📸 Starting calibration camera...");
    if (!ExamState.calibVideo) {
        console.error("❌ Calibration video element not found");
        updateCalibrationStatus("Camera initialization failed", "error");
        return;
    }

    try {
        const stream = await navigator.mediaDevices.getUserMedia({
            video: { width: { ideal: 640 }, height: { ideal: 480 }, facingMode: 'user' }
        });

        ExamState.calibVideo.srcObject = stream;
        ExamState.calibVideo.play();

        // Also attach same stream to visible student preview (so student sees themselves during calibration)
        if (ExamState.studentCameraElement) {
            ExamState.studentCameraElement.srcObject = stream;
            ExamState.studentCameraElement.play();
        }

        // Enable calibration button
        if (ExamState.calibButton) {
            ExamState.calibButton.disabled = false;
            ExamState.calibButton.onclick = performCalibration;
        }

        console.log("✅ Calibration camera started");
        updateCalibrationStatus("Camera ready. Click 'Start Calibration' to begin.", "success");

    } catch (error) {
        console.error("❌ Camera access error:", error);
        updateCalibrationStatus("Camera access denied. Please enable camera permissions.", "error");
        if (ExamState.calibButton) {
            ExamState.calibButton.disabled = false;
            ExamState.calibButton.onclick = startCalibrationCamera;
            ExamState.calibButton.innerHTML = 'Retry Camera Access';
        }
    }
}

async function performCalibration() {
    console.log("🔍 Starting calibration...");
    if (!ExamState.calibVideo || !ExamState.calibVideo.srcObject) {
        console.error("❌ No video stream available");
        updateCalibrationStatus("Camera not ready", "error");
        return;
    }

    if (ExamState.calibButton) {
        ExamState.calibButton.disabled = true;
        ExamState.calibButton.innerHTML = 'Calibrating...';
    }
    updateCalibrationStatus("Analyzing your face...", "info");

    try {
        // Use ImageCapture or fallback to canvas
        const track = ExamState.calibVideo.srcObject.getVideoTracks()[0];
        let arrayBuffer = null;

        if (typeof ImageCapture !== 'undefined') {
            const imageCapture = new ImageCapture(track);
            const blob = await imageCapture.takePhoto({ imageWidth: 160, imageHeight: 120 });
            arrayBuffer = await blob.arrayBuffer();
        } else {
            // fallback capture frame to canvas
            const c = document.createElement('canvas');
            c.width = 160; c.height = 120;
            const ctx = c.getContext('2d');
            ctx.drawImage(ExamState.calibVideo, 0, 0, c.width, c.height);
            const blob = await new Promise(res => c.toBlob(res, 'image/jpeg', 0.6));
            arrayBuffer = await blob.arrayBuffer();
        }

        console.log(`📤 Sending calibration frame (${arrayBuffer.byteLength} bytes)`);

        // Send via Socket.IO binary event (keep same event name)
        ExamState.socket.emit('calibrationBinary', {
            studentExamId: ExamState.studentExamId,
            frame: arrayBuffer
        });

    } catch (error) {
        console.error("❌ Calibration capture error:", error);
        updateCalibrationStatus("Failed to capture image. Please try again.", "error");
        if (ExamState.calibButton) {
            ExamState.calibButton.disabled = false;
            ExamState.calibButton.innerHTML = 'Retry Calibration';
        }
    }
}

function handleCalibrationResult(data) {
    console.log("📊 Calibration result:", data);
    if (data.success) {
        ExamState.calibrationComplete = true;
        updateCalibrationStatus("✅ Calibration complete! Starting exam...", "success");
        setTimeout(() => {
            hideCalibrationModal();
            startExam();
        }, 1200);
    } else {
        const message = data.message || "No face detected. Please position yourself clearly in front of the camera.";
        updateCalibrationStatus(message, "error");
        if (ExamState.calibButton) {
            ExamState.calibButton.disabled = false;
            ExamState.calibButton.innerHTML = 'Retry Calibration';
        }
    }
}

function updateCalibrationStatus(message, type = "info") {
    if (!ExamState.calibStatus) return;
    ExamState.calibStatus.textContent = message;
    ExamState.calibStatus.className = 'calibration-status';
    if (type === "success") ExamState.calibStatus.classList.add('success');
    else if (type === "error") ExamState.calibStatus.classList.add('error');
    else ExamState.calibStatus.classList.add('info');
}

// EXAM START
async function startExam() {
    console.log("🎯 Starting exam...");

    if (ExamState.blockedView) ExamState.blockedView.style.display = 'none';
    if (ExamState.questionsContainer) ExamState.questionsContainer.style.display = 'block';

    startTimer();
    await startContinuousProctoring();

    // Enforce fullscreen
    requestFullscreen();

    console.log("✅ Exam started successfully");
}

// CONTINUOUS PROCTORING
async function startContinuousProctoring() {
    console.log("👁️ Starting continuous proctoring...");

    try {
        // Reuse existing stream if calibration produced it
        let stream = null;
        if (ExamState.calibVideo && ExamState.calibVideo.srcObject) {
            stream = ExamState.calibVideo.srcObject;
        } else {
            stream = await navigator.mediaDevices.getUserMedia({
                video: { width: { ideal: 320 }, height: { ideal: 240 }, facingMode: 'user' }
            });
        }

        ExamState.videoStream = stream;

        // Make sure student sees the camera preview
        if (ExamState.studentCameraElement) {
            ExamState.studentCameraElement.srcObject = stream;
            ExamState.studentCameraElement.autoplay = true;
            ExamState.studentCameraElement.playsInline = true;
            try { await ExamState.studentCameraElement.play(); } catch(e) { /* ignore */ }
        }

        // Hidden video element for capture - re-use if exists (prevents multiple elements)
        if (!ExamState.videoElement) {
            ExamState.videoElement = document.createElement('video');
            ExamState.videoElement.autoplay = true;
            ExamState.videoElement.playsInline = true;
            ExamState.videoElement.muted = true;
            ExamState.videoElement.style.display = 'none';
            document.body.appendChild(ExamState.videoElement);
        }
        ExamState.videoElement.srcObject = stream;
        await ExamState.videoElement.play();

        console.log("✅ Proctoring video stream ready");

        // Start frame capture loop (every 3 seconds)
        if (ExamState.proctoringInterval) clearInterval(ExamState.proctoringInterval);
        ExamState.proctoringInterval = setInterval(captureAndSendFrame, 3000);

    } catch (error) {
        console.error("❌ Proctoring camera error:", error);
        showNotification("Warning: Proctoring camera unavailable", "warning");
    }
}

async function captureAndSendFrame() {
    // ensure proctoring runs only when exam active and calibration done
    if (!ExamState.videoElement || !ExamState.socket || !ExamState.calibrationComplete || !ExamState.isExamActive) {
        return;
    }

    try {
        const track = ExamState.videoElement.srcObject.getVideoTracks()[0];
        if (!track) return;

        // ImageCapture preferred
        if (typeof ImageCapture !== 'undefined') {
            const imageCapture = new ImageCapture(track);
            const blob = await imageCapture.takePhoto({ imageWidth: 160, imageHeight: 120 }).catch(() => null);
            if (!blob) return;
            const arrayBuffer = await blob.arrayBuffer();
            ExamState.socket.emit('frameBinary', {
                studentExamId: ExamState.studentExamId,
                frame: arrayBuffer,
                timestamp: Date.now()
            });
        } else {
            // fallback: draw frame to canvas then send
            if (!ExamState.sendCanvas) {
                const c = document.createElement('canvas');
                c.width = 160; c.height = 120;
                ExamState.sendCanvas = c;
                ExamState.sendContext = c.getContext('2d');
            }
            ExamState.sendContext.drawImage(ExamState.videoElement, 0, 0, 160, 120);
            const dataUrl = ExamState.sendCanvas.toDataURL('image/jpeg', 0.6);
            // convert dataURL to ArrayBuffer
            const base64 = dataUrl.split(',')[1];
            const binary = atob(base64);
            const len = binary.length;
            const buffer = new ArrayBuffer(len);
            const view = new Uint8Array(buffer);
            for (let i = 0; i < len; i++) view[i] = binary.charCodeAt(i);
            ExamState.socket.emit('frameBinary', {
                studentExamId: ExamState.studentExamId,
                frame: buffer,
                timestamp: Date.now()
            });
        }

    } catch (error) {
        console.error("❌ Frame capture error:", error);
    }
}

function handleProctoringResult(data) {

    if (data.violation === 'face_out_of_boundary') {
        showViolationPopup(
            "Face Out of Allowed Area",
            "Please keep your face inside the boundary circle."
        );
    }

    if (data.violation === "looking_away") {
        ExamState.violations.looking_away++;
        showViolationPopup("Looking Away", "Keep your face inside the circle.");
    }
    // server sends { success: false, violation: 'no_face', count: x, total_violations: y }
    if (!data) return;

    if (data.success) {
        // face OK; optionally clear local 'no_face' streak? we keep totals persistent
        return;
    }

    console.warn("⚠️ Proctor violation:", data.violation);

    // Map server violation to local counters
    if (data.violation === 'no_face') {
        ExamState.violations.no_face++;
        if (ExamState.violations.no_face % 3 === 0) {
            showViolationPopup("No Face Detected", "Please ensure you are visible in the camera.");
        }
    } else if (data.violation === 'multiple_faces') {
        ExamState.violations.multiple_faces++;
        if (ExamState.violations.multiple_faces % 2 === 0) {
            showViolationPopup("Multiple Faces Detected", "Only the exam taker should be visible.");
        }
    } else if (data.violation === 'looking_away') {
        ExamState.violations.looking_away++;
        if (ExamState.violations.looking_away % 5 === 0) {
            showViolationPopup("Looking Away", "Please keep your eyes on the exam.");
        }
    }

    // unified total (includes server-sent total_violations if available)
    let serverTotal = data.total_violations || 0;
    const localTotal = ExamState.violations.no_face + ExamState.violations.multiple_faces + ExamState.violations.looking_away;

    const totalViolations = Math.max(serverTotal, localTotal);

    // optional: show warning toast with counts
    showNotification(`Violation detected (${data.violation}). Total: ${totalViolations}`, "warning");

    if (totalViolations >= (data.max_threshold || 3)) {
        terminateExamDueToViolations();
    }
}

function terminateExamDueToViolations() {
    console.error("🚨 Too many violations - auto-submitting exam");

    ExamState.isExamActive = false;

    if (ExamState.proctoringInterval) clearInterval(ExamState.proctoringInterval);
    if (ExamState.timerInterval) clearInterval(ExamState.timerInterval);

    // stop video
    if (ExamState.videoStream) ExamState.videoStream.getTracks().forEach(t => t.stop());
    if (ExamState.videoElement && ExamState.videoElement.srcObject) ExamState.videoElement.srcObject.getTracks().forEach(t => t.stop());
    if (ExamState.studentCameraElement && ExamState.studentCameraElement.srcObject) ExamState.studentCameraElement.srcObject.getTracks().forEach(t => t.stop());

    showViolationPopup("Exam Terminated", "Too many proctoring violations detected. Your exam is being submitted automatically.", () => {
        submitExam(true);
    });
}

// TIMER MANAGEMENT
function startTimer() {
    console.log(`⏱️ Starting timer: ${ExamState.secondsLeft} seconds`);
    updateTimerDisplay();

    if (ExamState.timerInterval) clearInterval(ExamState.timerInterval);
    ExamState.timerInterval = setInterval(() => {
        if (ExamState.secondsLeft > 0 && ExamState.isExamActive) {
            ExamState.secondsLeft--;
            updateTimerDisplay();

            if (ExamState.secondsLeft === 0) {
                console.log("⏰ Time's up - auto-submitting");
                clearInterval(ExamState.timerInterval);
                submitExam(true);
            }

            if (ExamState.secondsLeft === 300) showNotification("⚠️ 5 minutes remaining!", "warning");
            if (ExamState.secondsLeft === 60) showNotification("⚠️ 1 minute remaining!", "danger");
        }
    }, 1000);
}

function updateTimerDisplay() {
    const hours = Math.floor(ExamState.secondsLeft / 3600);
    const minutes = Math.floor((ExamState.secondsLeft % 3600) / 60);
    const seconds = ExamState.secondsLeft % 60;
    const timeString = `${pad(hours)}:${pad(minutes)}:${pad(seconds)}`;
    const timerElement = document.getElementById('header-timer');
    if (timerElement) {
        timerElement.textContent = timeString;
        if (ExamState.secondsLeft <= 300) timerElement.classList.add('warning');
        if (ExamState.secondsLeft <= 60) timerElement.classList.add('danger');
    }
}
function pad(num) { return num.toString().padStart(2, '0'); }

// ANSWER TRACKING & AUTOSAVE
function setupAnswerTracking() {
    console.log("📝 Setting up answer tracking...");
    const existingInputs = document.querySelectorAll('input[type="radio"]:checked');
    existingInputs.forEach(input => {
        const questionId = input.dataset.questionId;
        const answer = input.value;
        ExamState.answers[questionId] = answer;
    });
    document.addEventListener('change', (e) => {
        if (e.target.matches('input[type="radio"]')) {
            handleAnswerChange(e.target);
        }
    });
    setInterval(() => {
        if (Object.keys(ExamState.answers).length > 0) saveAnswers();
    }, 10000);
}
function handleAnswerChange(input) {
    const questionId = input.dataset.questionId;
    const answer = input.value;
    ExamState.answers[questionId] = answer;
    const questionCard = input.closest('.question-card');
    if (questionCard) {
        questionCard.querySelectorAll('.option').forEach(opt => opt.classList.remove('selected'));
        const selectedLabel = input.closest('.option');
        if (selectedLabel) selectedLabel.classList.add('selected');
    }
    clearTimeout(ExamState.saveDebounceTimer);
    ExamState.saveDebounceTimer = setTimeout(() => saveAnswers(), 1200);
}

async function saveAnswers() {
    const now = Date.now();
    if (now - ExamState.lastSaveTime < 900) return;
    ExamState.lastSaveTime = now;

    console.log("💾 Saving answers...", ExamState.answers);
    try {
        // UPDATED endpoint to match backend '/api/save-answer' expecting JSON { student_exam_id, answers }
        const response = await fetch('/api/save-answer', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                student_exam_id: ExamState.studentExamId,
                answers: ExamState.answers
            })
        });
        if (response.ok) console.log("✅ Answers saved successfully");
        else console.warn("⚠️ Answer save failed:", response.status);
    } catch (error) {
        console.error("❌ Answer save error:", error);
    }
}

// TAB SWITCH DETECTION (debounced)
function setupVisibilityMonitoring() {
    console.log("👀 Setting up tab switch monitoring...");
    document.addEventListener('visibilitychange', () => {
        if (document.hidden && ExamState.isExamActive && ExamState.calibrationComplete) {
            handleTabSwitch();
        }
    });
    // blur can fire along with visibilitychange; debounce inside handler to avoid double count
    window.addEventListener('blur', () => {
        if (ExamState.isExamActive && ExamState.calibrationComplete) {
            handleTabSwitch();
        }
    });
}

function handleTabSwitch() {
    const now = Date.now();
    // Throttle: only count one tab switch per 2 seconds (prevents double increments)
    if (now - ExamState.lastTabSwitchAt < 2000) {
        console.log("Tab switch debounced");
        return;
    }
    ExamState.lastTabSwitchAt = now;

    ExamState.tabSwitchCount++;
    console.warn(`⚠️ Tab switch detected! Count: ${ExamState.tabSwitchCount}/${ExamState.maxTabSwitches}`);
    updateTabSwitchDisplay();

    // LOG activity using correct API endpoint
    logActivity('tab_switch', { count: ExamState.tabSwitchCount });

    showViolationPopup("Tab Switch Detected", `Warning ${ExamState.tabSwitchCount}/${ExamState.maxTabSwitches}: Stay on this page during the exam.`);

    if (ExamState.tabSwitchCount >= ExamState.maxTabSwitches) {
        console.error("🚨 Max tab switches reached - terminating exam");
        ExamState.isExamActive = false;
        showViolationPopup("Exam Terminated", "Maximum tab switches exceeded. Your exam is being submitted.", () => {
            submitExam(true);
        });
    }
}

function updateTabSwitchDisplay() {
    const tabCountElement = document.getElementById('tab-count');
    if (tabCountElement && ExamState.showTabSwitches) {
        tabCountElement.textContent = `${ExamState.tabSwitchCount} / ${ExamState.maxTabSwitches}`;
        if (ExamState.tabSwitchCount >= ExamState.maxTabSwitches - 1) tabCountElement.classList.add('danger');
        else if (ExamState.tabSwitchCount >= ExamState.maxTabSwitches / 2) tabCountElement.classList.add('warning');
    }
}

// FULLSCREEN ENFORCEMENT
function setupFullscreenMonitoring() {
    console.log("🖥️ Setting up fullscreen monitoring...");
    const fsOverlay = document.getElementById('fs-overlay');
    const fsButton = document.getElementById('fs-enter-btn');

    if (fsButton) fsButton.addEventListener('click', requestFullscreen);

    document.addEventListener('fullscreenchange', () => {
        // If user exits fullscreen while exam active and calibrated -> TERMINATE IMMEDIATELY
        if (!document.fullscreenElement && ExamState.isExamActive && ExamState.calibrationComplete) {
            // show overlay immediately
            if (fsOverlay) fsOverlay.classList.add('active');
            // stop timer
            if (ExamState.timerInterval) clearInterval(ExamState.timerInterval);

            // log activity to backend (correct endpoint)
            logActivity('fullscreen_exit', { ts: Date.now() });

            // NEW: Immediately terminate the exam — strict enforcement
            console.error("🚨 Fullscreen exited - terminating exam.");
            ExamState.isExamActive = false;

            // stop proctoring and media
            if (ExamState.proctoringInterval) clearInterval(ExamState.proctoringInterval);
            if (ExamState.videoStream) ExamState.videoStream.getTracks().forEach(t => t.stop());
            if (ExamState.videoElement && ExamState.videoElement.srcObject) ExamState.videoElement.srcObject.getTracks().forEach(t => t.stop());
            if (ExamState.studentCameraElement && ExamState.studentCameraElement.srcObject) ExamState.studentCameraElement.srcObject.getTracks().forEach(t => t.stop());

            // Auto-submit after showing message
            showViolationPopup("Fullscreen Exit Detected", "You left fullscreen. The exam is being submitted.", () => {
                submitExam(true);
            });

        } else if (document.fullscreenElement) {
            // Entered fullscreen
            if (fsOverlay) fsOverlay.classList.remove('active');
            // resume timer only if calibration complete and exam is active
            if (ExamState.calibrationComplete && ExamState.isExamActive && !ExamState.timerInterval) {
                startTimer();
            }
        }
    });
}

function requestFullscreen() {
    const elem = document.documentElement;
    if (elem.requestFullscreen) elem.requestFullscreen();
    else if (elem.webkitRequestFullscreen) elem.webkitRequestFullscreen();
    else if (elem.msRequestFullscreen) elem.msRequestFullscreen();
}

// EXAM SUBMISSION
function setupEventListeners() {
    const submitButton = document.getElementById('submit-btn');
    if (submitButton) submitButton.addEventListener('click', () => submitExam(false));

    window.addEventListener('beforeunload', (e) => {
        if (ExamState.isExamActive && ExamState.calibrationComplete) {
            e.preventDefault();
            e.returnValue = '';
            return '';
        }
    });
}

function submitExam(autoSubmit = false) {
    console.log("📤 Submitting exam...", autoSubmit ? "(auto)" : "(manual)");
    saveAnswers();
    if (ExamState.timerInterval) clearInterval(ExamState.timerInterval);
    if (ExamState.proctoringInterval) clearInterval(ExamState.proctoringInterval);

    // stop streams
    if (ExamState.videoStream) ExamState.videoStream.getTracks().forEach(track => track.stop());
    if (ExamState.videoElement && ExamState.videoElement.srcObject) ExamState.videoElement.srcObject.getTracks().forEach(track => track.stop());
    if (ExamState.studentCameraElement && ExamState.studentCameraElement.srcObject) ExamState.studentCameraElement.srcObject.getTracks().forEach(track => track.stop());

    ExamState.isExamActive = false;

    const message = autoSubmit ? "Your exam is being submitted automatically..." : "Are you sure you want to submit your exam? This action cannot be undone.";

    if (autoSubmit || confirm(message)) {
        const submitForm = document.getElementById('submit-form');
        if (submitForm) submitForm.submit();
        else window.location.href = `/exam/${ExamState.studentExamId}/submit`;
    } else {
        ExamState.isExamActive = true;
        startTimer();
        if (ExamState.videoStream) ExamState.proctoringInterval = setInterval(captureAndSendFrame, 3000);
    }
}

// ACTIVITY LOGGING - UPDATED endpoint to backend /api/log-activity/<id>
async function logActivity(activityType, details = null) {
    try {
        const payload = {
            activity_type: activityType,
            description: details || '',
            severity: details && details.severity ? details.severity : 'low'
        };
        const url = `/api/log-activity/${ExamState.studentExamId}`; // <<-- FIXED endpoint
        await fetch(url, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
    } catch (error) {
        console.error("❌ Activity log error:", error);
    }
}

// UI NOTIFICATIONS & POPUPS
function showNotification(message, type = "info") {
    const notification = document.createElement('div');
    notification.className = `exam-notification ${type}`;
    notification.textContent = message;
    document.body.appendChild(notification);
    setTimeout(() => notification.classList.add('show'), 100);
    setTimeout(() => { notification.classList.remove('show'); setTimeout(() => notification.remove(), 300); }, 5000);
}
function showViolationPopup(title, message, callback = null) {
    const overlay = document.createElement('div');
    overlay.className = 'violation-overlay';
    overlay.innerHTML = `
        <div class="violation-modal">
            <div class="violation-icon">!</div>
            <h2 class="violation-title">${title}</h2>
            <p class="violation-message">${message}</p>
            <button class="violation-close-btn">I Understand</button>
        </div>
    `;
    document.body.appendChild(overlay);
    setTimeout(() => overlay.classList.add('show'), 100);
    const closeBtn = overlay.querySelector('.violation-close-btn');
    closeBtn.addEventListener('click', () => {
        overlay.classList.remove('show');
        setTimeout(() => { overlay.remove(); if (callback) callback(); }, 300);
    });
}

// CLEANUP ON PAGE UNLOAD
window.addEventListener('unload', () => {
    if (ExamState.videoStream) ExamState.videoStream.getTracks().forEach(track => track.stop());
    if (ExamState.videoElement && ExamState.videoElement.srcObject) ExamState.videoElement.srcObject.getTracks().forEach(track => track.stop());
    if (ExamState.calibVideo && ExamState.calibVideo.srcObject) ExamState.calibVideo.srcObject.getTracks().forEach(track => track.stop());
    if (ExamState.studentCameraElement && ExamState.studentCameraElement.srcObject) ExamState.studentCameraElement.srcObject.getTracks().forEach(track => track.stop());

    if (ExamState.timerInterval) clearInterval(ExamState.timerInterval);
    if (ExamState.proctoringInterval) clearInterval(ExamState.proctoringInterval);

    if (ExamState.socket) ExamState.socket.disconnect();
});

if (typeof module !== 'undefined' && module.exports) {
    module.exports = { initExam };
}
console.log("✅ Exam system module loaded (updated)");
