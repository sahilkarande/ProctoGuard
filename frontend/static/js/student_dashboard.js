/* ===========================================================
   Student Dashboard Interactions
   - Exam Preview Modal
   - Live Search, Filter, Sort
   - Modal Management
   - Chart.js Performance Visualization
   =========================================================== */

document.addEventListener("DOMContentLoaded", () => {
  const $ = sel => document.querySelector(sel);
  const $$ = sel => Array.from(document.querySelectorAll(sel));
  const debounce = (fn, ms = 250) => {
    let t;
    return (...args) => { clearTimeout(t); t = setTimeout(() => fn(...args), ms); };
  };

  /* -------------------------
     Dynamic Exam Preview Modal
     ------------------------- */
  const previewModal = document.createElement("div");
  previewModal.className = "custom-modal";
  previewModal.id = "examPreviewModal";
  previewModal.innerHTML = `
    <div class="modal-content" style="max-width:650px;">
      <button class="close-modal" id="closePreviewModal">&times;</button>
      <h2 id="previewTitle" style="font-size:1.6rem; font-weight:800; margin-bottom:0.5rem;"></h2>
      <p id="previewDesc" style="color:#9ca3af; font-size:1rem; margin-bottom:1rem; line-height:1.6;"></p>
      
      <div style="display:grid; grid-template-columns:repeat(2,1fr); gap:0.8rem; margin-bottom:1.2rem;">
        <div class="meta-item"><i class="bi bi-clock"></i> <span id="previewDuration"></span></div>
        <div class="meta-item"><i class="bi bi-question-circle"></i> <span id="previewQuestions"></span></div>
        <div class="meta-item"><i class="bi bi-trophy"></i> <span id="previewPassing"></span></div>
        <div class="meta-item"><i class="bi bi-speedometer2"></i> <span id="previewDifficulty"></span></div>
      </div>

      <div style="display:flex; justify-content:flex-end; gap:1rem;">
        <button id="startExamBtn" class="btn-start-exam" style="flex:unset; min-width:140px;">
          <i class="bi bi-play-circle-fill"></i> Start Exam
        </button>
        <button id="closeExamPreview" class="btn-preview" style="flex:unset;">Close</button>
      </div>
    </div>
  `;
  document.body.appendChild(previewModal);

  // Animation CSS
  const modalStyle = document.createElement("style");
  modalStyle.textContent = `
    @keyframes fadeInModal {
      from {opacity:0; transform: translateY(-15px);}
      to {opacity:1; transform: translateY(0);}
    }
    @keyframes fadeOutModal {
      from {opacity:1; transform: translateY(0);}
      to {opacity:0; transform: translateY(-10px);}
    }
  `;
  document.head.appendChild(modalStyle);

  // Modal open/close functions
  function openPreviewModal(examData) {
    $("#previewTitle").textContent = examData.title || "Untitled Exam";
    $("#previewDesc").textContent = examData.desc || "No description available.";
    $("#previewDuration").textContent = `${examData.duration} minutes`;
    $("#previewQuestions").textContent = `${examData.questions} Questions`;
    $("#previewPassing").textContent = `${examData.passing}% Passing Score`;
    $("#previewDifficulty").textContent = examData.difficulty || "—";

    previewModal.style.display = "flex";
    previewModal.style.animation = "fadeInModal 0.3s ease forwards";
    document.body.style.overflow = "hidden";

    const startBtn = $("#startExamBtn");
    if (examData.examId) {
      startBtn.onclick = () => {
        window.location.href = `/start-exam/${examData.examId}`; // adjust if needed
      };
    }
  }

  function closePreviewModal() {
    previewModal.style.animation = "fadeOutModal 0.25s ease forwards";
    setTimeout(() => {
      previewModal.style.display = "none";
      document.body.style.overflow = "auto";
    }, 250);
  }

  $("#closePreviewModal").addEventListener("click", closePreviewModal);
  $("#closeExamPreview").addEventListener("click", closePreviewModal);
  window.addEventListener("click", e => { if (e.target === previewModal) closePreviewModal(); });

  // Attach preview handlers
  $$(".btn-preview").forEach(btn => {
    btn.addEventListener("click", e => {
      const card = btn.closest(".exam-card");
      const examData = {
        examId: btn.dataset.examId,
        title: btn.dataset.examTitle,
        desc: card.querySelector(".exam-desc")?.textContent || "",
        duration: card.dataset.duration,
        passing: card.dataset.passing,
        questions: card.dataset.questions,
        difficulty: card.dataset.difficulty || "N/A"
      };
      openPreviewModal(examData);
    });
  });

  /* -------------------------
     Search / Filter / Sorting
     ------------------------- */
  const searchInput = $("#examSearchInput");
  const clearSearchBtn = $("#clearSearch");
  const categorySelect = $("#filterCategory");
  const difficultySelect = $("#filterDifficulty");
  const sortSelect = $("#sortBy");
  const examGrid = $("#examGrid");
  const gridToggle = $("#toggleGridView");

  let examCards = examGrid ? Array.from(examGrid.children) : [];

  function normalize(str) {
    return (str || "").toString().trim().toLowerCase();
  }

  function applyFilters() {
    const q = normalize(searchInput?.value);
    const cat = normalize(categorySelect?.value);
    const diff = normalize(difficultySelect?.value);
    const sortBy = sortSelect?.value;

    let cards = examCards.slice();

    // Search
    if (q) {
      cards = cards.filter(card =>
        card.dataset.title.includes(q) ||
        card.dataset.desc.includes(q) ||
        card.dataset.category.includes(q)
      );
      if (clearSearchBtn) clearSearchBtn.style.display = "inline";
    } else if (clearSearchBtn) {
      clearSearchBtn.style.display = "none";
    }

    // Filters
    if (cat) cards = cards.filter(c => normalize(c.dataset.category) === cat);
    if (diff) cards = cards.filter(c => normalize(c.dataset.difficulty) === diff);

    // Sorting
    cards.sort((a, b) => {
      switch (sortBy) {
        case "duration":
          return parseInt(a.dataset.duration) - parseInt(b.dataset.duration);
        case "passing":
          return parseInt(b.dataset.passing) - parseInt(a.dataset.passing);
        case "questions":
          return parseInt(b.dataset.questions) - parseInt(a.dataset.questions);
        default:
          const da = a.dataset.created || "";
          const db = b.dataset.created || "";
          return new Date(db) - new Date(da);
      }
    });

    // Re-render
    if (examGrid) {
      examGrid.innerHTML = "";
      cards.forEach(c => examGrid.appendChild(c));
    }
  }

  const debouncedApply = debounce(applyFilters, 180);
  if (searchInput) searchInput.addEventListener("input", debouncedApply);
  if (clearSearchBtn) clearSearchBtn.addEventListener("click", () => { searchInput.value = ""; applyFilters(); });
  if (categorySelect) categorySelect.addEventListener("change", applyFilters);
  if (difficultySelect) difficultySelect.addEventListener("change", applyFilters);
  if (sortSelect) sortSelect.addEventListener("change", applyFilters);

  /* -------------------------
     Grid Toggle (List Mode)
     ------------------------- */
  if (gridToggle) {
    let compact = false;
    gridToggle.addEventListener("click", () => {
      compact = !compact;
      examGrid.style.gridTemplateColumns = compact
        ? "repeat(auto-fit, minmax(220px,1fr))"
        : "";
      gridToggle.textContent = compact ? "List" : "Grid";
    });
  }

  /* -------------------------
     Modals (Performance / History)
     ------------------------- */
  const modalTriggers = $$(".modal-trigger");
  const modals = $$(".custom-modal");

  function openModal(modal) {
    modal.style.display = "flex";
    modal.setAttribute("aria-hidden", "false");
    document.body.style.overflow = "hidden";
    if (modal.id === "performanceModal") initCharts();
  }

  function closeModal(modal) {
    modal.style.display = "none";
    modal.setAttribute("aria-hidden", "true");
    document.body.style.overflow = "auto";
  }

  modalTriggers.forEach(btn => {
    btn.addEventListener("click", () => {
      const modal = document.getElementById(btn.dataset.modal);
      if (modal) openModal(modal);
    });
  });

  $("[data-close]")?.addEventListener("click", e => closeModal(e.target.closest(".custom-modal")));
  window.addEventListener("click", e => {
    if (e.target.classList.contains("custom-modal")) closeModal(e.target);
  });
  window.addEventListener("keydown", e => {
    if (e.key === "Escape") modals.forEach(m => { if (m.style.display === "flex") closeModal(m); });
  });

  /* -------------------------
     Chart.js Setup
     ------------------------- */
  let perfChart = null, distChart = null;

  function initCharts() {
    const examLabels = window.__perf_labels || [];
    const examScores = window.__perf_scores || [];
    const passed = window.__perf_passed || 0;
    const total = window.__perf_total || 0;
    const failed = Math.max(total - passed, 0);

    const perfCtx = document.getElementById("performanceChart");
    if (perfCtx) {
      if (perfChart) perfChart.destroy();
      perfChart = new Chart(perfCtx, {
        type: "line",
        data: {
          labels: examLabels,
          datasets: [{
            label: "Score (%)",
            data: examScores,
            tension: 0.35,
            fill: true,
            borderWidth: 3,
            borderColor: "#6366f1",
            backgroundColor: "rgba(99,102,241,0.08)",
            pointRadius: 6,
            pointBackgroundColor: "#fff",
            pointBorderColor: "#6366f1"
          }]
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          scales: {
            y: { beginAtZero: true, max: 100, ticks: { callback: v => v + "%" } }
          },
          plugins: { legend: { display: false } }
        }
      });
    }

    const distCtx = document.getElementById("scoreDistributionChart");
    if (distCtx) {
      if (distChart) distChart.destroy();
      distChart = new Chart(distCtx, {
        type: "doughnut",
        data: {
          labels: ["Passed", "Failed"],
          datasets: [{
            data: [passed, failed],
            borderWidth: 2,
            backgroundColor: ["#10b981", "#ef4444"]
          }]
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          plugins: { legend: { position: "bottom" } }
        }
      });
    }
  }

  /* -------------------------
     Initialize
     ------------------------- */
  applyFilters();
  $$(".progress-bar").forEach(pb => {
    const w = pb.style.width || "0%";
    pb.style.width = "0%";
    requestAnimationFrame(() => pb.style.width = w);
  });
});
