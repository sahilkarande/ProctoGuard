// ===============================================================
// VIEW EXAM JS - Updated for LIST layout + 3-Column Modal
// ===============================================================

// Extend Time Modal
function showExtendTimeModal() {
    document.getElementById("extendTimeModal").classList.add("active");
}

function hideExtendTimeModal() {
    document.getElementById("extendTimeModal").classList.remove("active");
}

// Auto-refresh page every 5 minutes
setInterval(() => {
    const p = new URLSearchParams(window.location.search);
    if (!p.has("no_refresh")) location.reload();
}, 300000);


// ===============================================================
// STUDENT SELECTION MODAL (3-COLUMN)
// ===============================================================
document.addEventListener("DOMContentLoaded", () => {

    // ----------------------------------------------------
    // ELEMENTS
    // ----------------------------------------------------
    const modal = document.getElementById("student-selection-modal");
    const selectBtn = document.getElementById("select-students-btn");
    const closeBtn = document.getElementById("modal-close-btn");
    const cancelBtn = document.getElementById("modal-cancel-btn");
    const saveBtn = document.getElementById("modal-save-btn");

    const batchFilter = document.getElementById("batch-filter");
    const studentSearch = document.getElementById("student-search");
    const rangeInput = document.getElementById("range-input");
    const applyRangeBtn = document.getElementById("apply-range-btn");
    const clearRangeBtn = document.getElementById("clear-range-btn");

    const studentList = document.querySelector(".student-list");

    const selectAllBtn = document.getElementById("select-all-btn");
    const deselectAllBtn = document.getElementById("deselect-all-btn");
    const selectEvensBtn = document.getElementById("select-evens-btn");
    const selectOddsBtn = document.getElementById("select-odds-btn");

    const modalSelectedCount = document.getElementById("modal-selected-count");

    const selectedDisplay = document.getElementById("selected-students-display");
    const selectedList = document.getElementById("selected-students-list");
    const selectedCount = document.getElementById("selected-count");
    const allowedStudentsInput = document.getElementById("allowed-students-input");

    const radioSpecific = document.getElementById("radio-specific");
    const radioAll = document.getElementById("radio-all");
    const radioStopped = document.getElementById("radio-stopped");


    // ----------------------------------------------------
    // ACCESS MODE LOGIC
    // ----------------------------------------------------
    function updateAccessMode() {
        if (!radioSpecific) return;

        if (radioSpecific.checked) {
            selectBtn.disabled = false;
            updateSelectedDisplay();
        } else {
            selectBtn.disabled = true;
            selectedDisplay.style.display = "none";
        }
    }

    [radioSpecific, radioAll, radioStopped].forEach(r => {
        if (r) r.addEventListener("change", updateAccessMode);
    });


    // ----------------------------------------------------
    // MODAL OPEN / CLOSE
    // ----------------------------------------------------
    function openModal() {
        modal.classList.add("active");
        batchFilter.value = "";
        studentSearch.value = "";
        rangeInput.value = "";

        hideAllStudents(); // until batch is chosen
        disableControls();
        updateModalCount();
    }

    function closeModal() {
        modal.classList.remove("active");
    }

    selectBtn?.addEventListener("click", openModal);
    closeBtn?.addEventListener("click", closeModal);
    cancelBtn?.addEventListener("click", closeModal);

    modal.addEventListener("click", e => {
        if (e.target === modal) closeModal();
    });


    // ----------------------------------------------------
    // UTILITY HELPERS
    // ----------------------------------------------------
    function hideAllStudents() {
        document.querySelectorAll(".student-row").forEach(row => {
            row.style.display = "none";
        });
    }

    function showRows(rows) {
        rows.forEach(row => (row.style.display = "grid"));
    }

    function disableControls() {
        [
            studentSearch, rangeInput, applyRangeBtn, clearRangeBtn,
            selectAllBtn, deselectAllBtn, selectEvensBtn, selectOddsBtn
        ].forEach(el => {
            el.disabled = true;
            el.style.opacity = 0.5;
        });
    }

    function enableControls() {
        [
            studentSearch, rangeInput, applyRangeBtn, clearRangeBtn,
            selectAllBtn, deselectAllBtn, selectEvensBtn, selectOddsBtn
        ].forEach(el => {
            el.disabled = false;
            el.style.opacity = 1;
        });
    }


    // ----------------------------------------------------
    // SELECTION FUNCTIONS
    // ----------------------------------------------------
    function getVisibleRows() {
        return [...document.querySelectorAll(".student-row")]
            .filter(row => row.style.display !== "none");
    }

    function getSelectedStudents() {
        return [...document.querySelectorAll(".student-checkbox:checked")].map(cb => cb.value);
    }

    function updateModalCount() {
        modalSelectedCount.textContent = getSelectedStudents().length;
    }

    function updateSelectedDisplay() {
        const selectedIDs = getSelectedStudents();
        selectedCount.textContent = selectedIDs.length;

        if (!radioSpecific || !radioSpecific.checked) {
            selectedDisplay.style.display = "none";
            return;
        }

        if (selectedIDs.length > 0) {
            selectedDisplay.style.display = "block";
            selectedList.innerHTML = "";
            selectedIDs.forEach(id => {
                const row = document.querySelector(`.student-row[data-student-id="${id}"]`);
                if (!row) return;

                const name = row.querySelector(".student-name")?.textContent || id;
                const tag = document.createElement("span");
                tag.className = "selected-tag";
                tag.textContent = name;
                selectedList.appendChild(tag);
            });
        } else {
            selectedDisplay.style.display = "none";
        }
    }


    // ----------------------------------------------------
    // BATCH FILTER
    // ----------------------------------------------------
    batchFilter.addEventListener("change", () => {
        const batch = batchFilter.value;
        const rows = document.querySelectorAll(".student-row");

        if (!batch) {
            hideAllStudents();
            disableControls();
            updateModalCount();
            return;
        }

        rows.forEach(row => {
            row.style.display = row.dataset.batch === batch ? "grid" : "none";
        });

        enableControls();
        updateModalCount();
    });


    // ----------------------------------------------------
    // SEARCH (Within selected batch)
    // ----------------------------------------------------
    studentSearch.addEventListener("input", () => {
        const batch = batchFilter.value;
        if (!batch) {
            studentSearch.value = "";
            return alert("Select a batch first!");
        }

        const term = studentSearch.value.toLowerCase();

        document.querySelectorAll(".student-row").forEach(row => {
            if (row.dataset.batch === batch) {
                row.style.display = row.textContent.toLowerCase().includes(term)
                    ? "grid"
                    : "none";
            } else {
                row.style.display = "none";
            }
        });
    });


    // ----------------------------------------------------
    // SELECT ALL / DESELECT ALL
    // ----------------------------------------------------
    selectAllBtn.addEventListener("click", () => {
        getVisibleRows().forEach(row => row.querySelector(".student-checkbox").checked = true);
        updateModalCount();
    });

    deselectAllBtn.addEventListener("click", () => {
        getVisibleRows().forEach(row => row.querySelector(".student-checkbox").checked = false);
        updateModalCount();
    });


    // ----------------------------------------------------
    // SELECT EVENS / ODDS
    // ----------------------------------------------------
    selectEvensBtn.addEventListener("click", () => {
        const rows = getVisibleRows();
        rows.forEach(row => {
            const roll = parseInt(row.dataset.rollId);
            if (!isNaN(roll) && roll % 2 === 0) {
                row.querySelector(".student-checkbox").checked = true;
            }
        });
        updateModalCount();
    });

    selectOddsBtn.addEventListener("click", () => {
        const rows = getVisibleRows();
        rows.forEach(row => {
            const roll = parseInt(row.dataset.rollId);
            if (!isNaN(roll) && roll % 2 === 1) {
                row.querySelector(".student-checkbox").checked = true;
            }
        });
        updateModalCount();
    });


    // ----------------------------------------------------
    // ROLL RANGE SELECTION
    // ----------------------------------------------------
    function parseRange(str) {
        const out = new Set();
        const parts = str.split(",").map(s => s.trim());

        for (let part of parts) {
            if (part.includes("-")) {
                let [start, end] = part.split("-").map(Number);
                if (isNaN(start) || isNaN(end) || start > end)
                    throw new Error(`Invalid range: ${part}`);

                for (let i = start; i <= end; i++) out.add(i.toString());
            } else {
                let n = Number(part);
                if (isNaN(n)) throw new Error(`Invalid number: ${part}`);
                out.add(n.toString());
            }
        }
        return [...out];
    }

    applyRangeBtn.addEventListener("click", () => {
        try {
            const batch = batchFilter.value;
            if (!batch) return alert("Select a batch first!");

            const ids = parseRange(rangeInput.value.trim());
            let count = 0;

            getVisibleRows().forEach(row => {
                if (ids.includes(row.dataset.rollId)) {
                    row.querySelector(".student-checkbox").checked = true;
                    count++;
                }
            });

            updateModalCount();
            alert(`Selected ${count} students in range.`);
        } catch (err) {
            alert(err.message);
        }
    });

    clearRangeBtn.addEventListener("click", () => {
        rangeInput.value = "";
    });


    // ----------------------------------------------------
    // SAVE SELECTION
    // ----------------------------------------------------
    saveBtn.addEventListener("click", () => {
        allowedStudentsInput.value = getSelectedStudents().join(",");
        updateSelectedDisplay();
        closeModal();
    });

    studentList.addEventListener("change", updateModalCount);


    // ----------------------------------------------------
    // INITIAL SETUP
    // ----------------------------------------------------
    hideAllStudents();
    updateAccessMode();
    updateSelectedDisplay();
});


// ----------------------------------------------------
// Smooth Drawer Toggle
// ----------------------------------------------------
document.addEventListener("DOMContentLoaded", () => {
    document.querySelectorAll(".drawer-toggle").forEach(btn => {
        btn.addEventListener("click", () => {
            const parent = btn.parentElement;
            if (parent.hasAttribute("open")) {
                setTimeout(() => {
                    parent.scrollIntoView({ behavior: "smooth", block: "center" });
                }, 100);
            }
        });
    });
});
