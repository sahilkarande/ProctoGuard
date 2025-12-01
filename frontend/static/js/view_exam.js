// ==========================================
// VIEW EXAM PAGE - JAVASCRIPT
// ==========================================

// Extend Time Modal Functions
function showExtendTimeModal() {
    document.getElementById('extendTimeModal').classList.add('active');
}

function hideExtendTimeModal() {
    document.getElementById('extendTimeModal').classList.remove('active');
}

// Auto-refresh every 5 minutes
setInterval(() => {
    const urlParams = new URLSearchParams(window.location.search);
    if (!urlParams.has('no_refresh')) {
        location.reload();
    }
}, 300000);

// ==========================================
// STUDENT SELECTION MODAL
// ==========================================

document.addEventListener("DOMContentLoaded", () => {

    // Elements
    const radioStopped = document.getElementById("radio-stopped");
    const radioAll = document.getElementById("radio-all");
    const radioSpecific = document.getElementById("radio-specific");
    const selectStudentsBtn = document.getElementById("select-students-btn");
    const modal = document.getElementById("student-selection-modal");
    const modalCloseBtn = document.getElementById("modal-close-btn");
    const modalCancelBtn = document.getElementById("modal-cancel-btn");
    const modalSaveBtn = document.getElementById("modal-save-btn");
    const allowedStudentsInput = document.getElementById("allowed-students-input");
    const selectedDisplay = document.getElementById("selected-students-display");
    const selectedList = document.getElementById("selected-students-list");
    const selectedCount = document.getElementById("selected-count");
    const modalSelectedCount = document.getElementById("modal-selected-count");
    const accessForm = document.getElementById("access-form");

    const batchFilter = document.getElementById("batch-filter");
    const selectBatchBtn = document.getElementById("select-batch-btn");
    const deselectBatchBtn = document.getElementById("deselect-batch-btn");
    const selectAllBtn = document.getElementById("select-all-btn");
    const deselectAllBtn = document.getElementById("deselect-all-btn");
    const studentSearch = document.getElementById("student-search");
    const studentList = document.getElementById("student-list");

    // Range selection elements
    const rangeInput = document.getElementById("range-input");
    const applyRangeBtn = document.getElementById("apply-range-btn");
    const clearRangeBtn = document.getElementById("clear-range-btn");
    const rangeError = document.getElementById("range-error");

    // ==========================================
    // ACCESS MODE TOGGLE
    // ==========================================

    function updateAccessMode() {
        if (radioSpecific && radioSpecific.checked) {
            selectStudentsBtn.disabled = false;
            updateSelectedDisplay();
        } else {
            selectStudentsBtn.disabled = true;
            if (selectedDisplay) selectedDisplay.style.display = "none";
        }
    }

    if (radioStopped) radioStopped.addEventListener("change", updateAccessMode);
    if (radioAll) radioAll.addEventListener("change", updateAccessMode);
    if (radioSpecific) radioSpecific.addEventListener("change", updateAccessMode);

    // Form submit confirmation
    accessForm.addEventListener("submit", (e) => {
        const selectedMode = document.querySelector('input[name="access_mode"]:checked').value;
        if (selectedMode === "stopped") {
            e.preventDefault();
            const confirmed = confirm(
                "⚠️ WARNING: Stop Exam Access?\n\n" +
                "This will immediately prevent ALL students from accessing this exam.\n\n" +
                "Students who are currently attempting the exam will be logged out.\n\n" +
                "Do you really want to stop access to this exam?"
            );
            if (confirmed) {
                accessForm.submit();
            }
        }
    });

    // ==========================================
    // MODAL FUNCTIONS
    // ==========================================

    function openModal() {
        modal.classList.add('active');
        
        // Reset to initial state
        batchFilter.value = "";
        disableControls();
        showAllStudents();
        updateModalCount();
    }

    function closeModal() {
        modal.classList.remove('active');
    }

    if (selectStudentsBtn) selectStudentsBtn.addEventListener("click", openModal);
    modalCloseBtn.addEventListener("click", closeModal);
    modalCancelBtn.addEventListener("click", closeModal);
    modal.addEventListener("click", (e) => {
        if (e.target === modal) closeModal();
    });

    // ==========================================
    // CONTROL STATE MANAGEMENT
    // ==========================================

    function disableControls() {
        rangeInput.disabled = true;
        applyRangeBtn.disabled = true;
        clearRangeBtn.disabled = true;
        selectAllBtn.disabled = true;
        deselectAllBtn.disabled = true;
        studentSearch.disabled = true;
        selectBatchBtn.disabled = true;
        deselectBatchBtn.disabled = true;
        
        // Visual feedback
        rangeInput.style.opacity = "0.5";
        applyRangeBtn.style.opacity = "0.5";
        clearRangeBtn.style.opacity = "0.5";
        selectAllBtn.style.opacity = "0.5";
        deselectAllBtn.style.opacity = "0.5";
        studentSearch.style.opacity = "0.5";
    }

    function enableControls() {
        rangeInput.disabled = false;
        applyRangeBtn.disabled = false;
        clearRangeBtn.disabled = false;
        selectAllBtn.disabled = false;
        deselectAllBtn.disabled = false;
        studentSearch.disabled = false;
        selectBatchBtn.disabled = false;
        deselectBatchBtn.disabled = false;
        
        // Visual feedback
        rangeInput.style.opacity = "1";
        applyRangeBtn.style.opacity = "1";
        clearRangeBtn.style.opacity = "1";
        selectAllBtn.style.opacity = "1";
        deselectAllBtn.style.opacity = "1";
        studentSearch.style.opacity = "1";
    }

    function showAllStudents() {
        const items = document.querySelectorAll(".student-item");
        items.forEach(item => {
            item.style.display = "none";
        });
    }

    // ==========================================
    // SELECTION HELPERS
    // ==========================================

    function getSelectedStudents() {
        const checkboxes = document.querySelectorAll(".student-checkbox:checked");
        return Array.from(checkboxes).map(cb => cb.value);
    }

    function updateModalCount() {
        const count = getSelectedStudents().length;
        modalSelectedCount.textContent = count;
    }

    function updateSelectedDisplay() {
        const selected = getSelectedStudents();
        selectedCount.textContent = selected.length;
        
        if (selected.length > 0 && radioSpecific && radioSpecific.checked) {
            selectedDisplay.style.display = "block";
            selectedList.innerHTML = "";
            
            selected.forEach(id => {
                const item = document.querySelector(`.student-item[data-student-id="${id}"]`);
                if (item) {
                    const nameEl = item.querySelector(".student-name");
                    const name = nameEl ? nameEl.textContent : id;
                    
                    const badge = document.createElement("span");
                    badge.textContent = name;
                    selectedList.appendChild(badge);
                }
            });
        } else {
            selectedDisplay.style.display = "none";
            selectedList.innerHTML = "";
        }
    }

    studentList.addEventListener("change", () => {
        updateModalCount();
    });

    // ==========================================
    // BATCH FILTER (MANDATORY FIRST STEP)
    // ==========================================

    batchFilter.addEventListener("change", () => {
        const selectedBatch = batchFilter.value;
        
        if (!selectedBatch) {
            // No batch selected - hide all and disable controls
            showAllStudents();
            disableControls();
            rangeInput.value = "";
            studentSearch.value = "";
            rangeError.classList.remove('show');
            return;
        }
        
        // Batch selected - show only that batch and enable controls
        const items = document.querySelectorAll(".student-item");
        items.forEach(item => {
            const batch = item.getAttribute("data-batch");
            if (batch === selectedBatch) {
                item.style.display = "flex";
            } else {
                item.style.display = "none";
            }
        });
        
        enableControls();
        
        // Clear previous selections
        rangeInput.value = "";
        studentSearch.value = "";
        rangeError.classList.remove('show');
    });

    // Select/deselect batch
    selectBatchBtn.addEventListener("click", () => {
        const selectedBatch = batchFilter.value;
        if (!selectedBatch) {
            alert("⚠️ Please select a batch first!");
            return;
        }
        
        const items = document.querySelectorAll(`.student-item[data-batch="${selectedBatch}"]`);
        items.forEach(item => {
            if (item.style.display !== "none") {
                const checkbox = item.querySelector(".student-checkbox");
                if (checkbox) checkbox.checked = true;
            }
        });
        updateModalCount();
    });

    deselectBatchBtn.addEventListener("click", () => {
        const selectedBatch = batchFilter.value;
        if (!selectedBatch) {
            alert("⚠️ Please select a batch first!");
            return;
        }
        
        const items = document.querySelectorAll(`.student-item[data-batch="${selectedBatch}"]`);
        items.forEach(item => {
            if (item.style.display !== "none") {
                const checkbox = item.querySelector(".student-checkbox");
                if (checkbox) checkbox.checked = false;
            }
        });
        updateModalCount();
    });

    // ==========================================
    // RANGE SELECTION BY ROLL ID
    // ==========================================

    function showRangeError(message) {
        rangeError.textContent = "❌ " + message;
        rangeError.style.background = "rgba(239, 68, 68, 0.1)";
        rangeError.style.borderLeftColor = "#ef4444";
        rangeError.style.color = "#991b1b";
        rangeError.classList.add('show');
        setTimeout(() => {
            rangeError.classList.remove('show');
        }, 5000);
    }

    function showRangeSuccess(message) {
        rangeError.textContent = "✅ " + message;
        rangeError.style.background = "rgba(16, 185, 129, 0.1)";
        rangeError.style.borderLeftColor = "#10b981";
        rangeError.style.color = "#065f46";
        rangeError.classList.add('show');
        
        setTimeout(() => {
            rangeError.classList.remove('show');
        }, 3000);
    }

    function parseRangeString(rangeStr) {
        // Parse range string like "1-20, 21-40" 
        // IMPORTANT: Comma separates different ranges, NOT a continuous range
        const rollIds = new Set();
        const rangeParts = rangeStr.split(',').map(p => p.trim()).filter(p => p);
        
        console.log("Parsing range string:", rangeStr);
        console.log("Range parts:", rangeParts);
        
        for (const part of rangeParts) {
            if (part.includes('-')) {
                // Handle range like "1-20" or "21-40"
                const [start, end] = part.split('-').map(n => n.trim());
                const startNum = parseInt(start);
                const endNum = parseInt(end);
                
                if (isNaN(startNum) || isNaN(endNum)) {
                    throw new Error(`Invalid range: ${part} - must be numbers`);
                }
                
                if (startNum > endNum) {
                    throw new Error(`Invalid range: ${part} - start must be ≤ end`);
                }
                
                // Add all roll IDs in THIS specific range only
                console.log(`Processing range ${part}: adding ${startNum} to ${endNum}`);
                for (let i = startNum; i <= endNum; i++) {
                    rollIds.add(i.toString());
                }
            } else {
                // Handle single number like "5"
                const num = parseInt(part.trim());
                
                if (isNaN(num)) {
                    throw new Error(`Invalid number: ${part}`);
                }
                
                console.log(`Adding single roll ID: ${num}`);
                rollIds.add(num.toString());
            }
        }
        
        const result = Array.from(rollIds).sort((a, b) => parseInt(a) - parseInt(b));
        console.log("Final roll IDs to select:", result);
        return result;
    }

    function selectStudentsByRollId(rollIds) {
        const selectedBatch = batchFilter.value;
        if (!selectedBatch) {
            throw new Error("No batch selected");
        }
        
        console.log("Selecting students with roll IDs:", rollIds);
        console.log("In batch:", selectedBatch);
        
        // Get all visible students from selected batch
        const visibleItems = Array.from(document.querySelectorAll(".student-item"))
            .filter(item => 
                item.style.display !== "none" && 
                item.getAttribute("data-batch") === selectedBatch
            );
        
        console.log("Total visible students in batch:", visibleItems.length);
        
        let selectedCount = 0;
        
        visibleItems.forEach(item => {
            const checkbox = item.querySelector(".student-checkbox");
            const studentRollId = item.getAttribute("data-roll-id");
            
            console.log("Checking student with roll_id:", studentRollId);
            
            if (checkbox && studentRollId) {
                // Extract just the number from roll_id
                const rollIdNum = studentRollId.trim();
                
                // Check if this roll ID is in our selection
                if (rollIds.includes(rollIdNum)) {
                    checkbox.checked = true;
                    selectedCount++;
                    console.log(`✓ Selected student with roll_id: ${rollIdNum}`);
                }
            }
        });
        
        console.log("Total students selected:", selectedCount);
        return selectedCount;
    }

    // Apply range button
    applyRangeBtn.addEventListener("click", () => {
        const selectedBatch = batchFilter.value;
        
        if (!selectedBatch) {
            showRangeError("Please select a batch first!");
            return;
        }
        
        const rangeStr = rangeInput.value.trim();
        
        if (!rangeStr) {
            showRangeError("Please enter a roll ID range (e.g., 1-20, 21-40)");
            return;
        }
        
        try {
            const rollIds = parseRangeString(rangeStr);
            
            if (rollIds.length === 0) {
                showRangeError("No valid roll IDs found in range");
                return;
            }
            
            console.log("Attempting to select students with roll IDs:", rollIds);
            
            const selectedCount = selectStudentsByRollId(rollIds);
            updateModalCount();
            
            if (selectedCount === 0) {
                showRangeError(`No students found with roll IDs: ${rangeStr} in batch ${selectedBatch}`);
            } else {
                showRangeSuccess(`Selected ${selectedCount} student(s) from roll ID ranges: ${rangeStr}`);
            }
            
        } catch (error) {
            console.error("Range selection error:", error);
            showRangeError(error.message);
        }
    });

    // Clear range button
    clearRangeBtn.addEventListener("click", () => {
        rangeInput.value = "";
        rangeError.classList.remove('show');
    });

    // Enter key support for range input
    rangeInput.addEventListener("keypress", (e) => {
        if (e.key === "Enter") {
            e.preventDefault();
            applyRangeBtn.click();
        }
    });

    // ==========================================
    // SELECT/DESELECT ALL (BATCH FILTERED)
    // ==========================================

    selectAllBtn.addEventListener("click", () => {
        const selectedBatch = batchFilter.value;
        
        if (!selectedBatch) {
            alert("⚠️ Please select a batch first!");
            return;
        }
        
        const visibleCheckboxes = Array.from(document.querySelectorAll(".student-checkbox"))
            .filter(cb => cb.closest(".student-item").style.display !== "none");
        visibleCheckboxes.forEach(cb => cb.checked = true);
        updateModalCount();
    });

    deselectAllBtn.addEventListener("click", () => {
        const selectedBatch = batchFilter.value;
        
        if (!selectedBatch) {
            alert("⚠️ Please select a batch first!");
            return;
        }
        
        const visibleCheckboxes = Array.from(document.querySelectorAll(".student-checkbox"))
            .filter(cb => cb.closest(".student-item").style.display !== "none");
        visibleCheckboxes.forEach(cb => cb.checked = false);
        updateModalCount();
    });

    // ==========================================
    // SEARCH FILTER (BATCH FILTERED)
    // ==========================================

    studentSearch.addEventListener("input", (e) => {
        const selectedBatch = batchFilter.value;
        
        if (!selectedBatch) {
            studentSearch.value = "";
            alert("⚠️ Please select a batch first!");
            return;
        }
        
        const searchTerm = e.target.value.toLowerCase();
        const items = document.querySelectorAll(".student-item");
        
        items.forEach(item => {
            const batch = item.getAttribute("data-batch");
            
            // Only search within selected batch
            if (batch === selectedBatch) {
                const text = item.textContent.toLowerCase();
                if (text.includes(searchTerm)) {
                    item.style.display = "flex";
                } else {
                    item.style.display = "none";
                }
            } else {
                item.style.display = "none";
            }
        });
    });

    // ==========================================
    // SAVE SELECTION
    // ==========================================

    modalSaveBtn.addEventListener("click", () => {
        const selected = getSelectedStudents();
        allowedStudentsInput.value = selected.join(",");
        updateSelectedDisplay();
        closeModal();
    });

    // ==========================================
    // INITIALIZE
    // ==========================================

    updateAccessMode();
    updateSelectedDisplay();
    disableControls(); // Start with controls disabled

});

// ==========================================
// DRAWER TOGGLES
// ==========================================

document.addEventListener("DOMContentLoaded", () => {
    document.querySelectorAll('.drawer-toggle').forEach(btn => {
        btn.addEventListener('click', () => {
            const drawer = btn.parentElement;
            if (drawer.hasAttribute('open')) {
                setTimeout(() => {
                    drawer.scrollIntoView({ behavior: "smooth", block: "center" });
                }, 100);
            }
        });
    });
});