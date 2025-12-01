// Modern Exam Platform - Interactive Features

// Theme Toggle (Optional - for dark mode support)
function initThemeToggle() {
  const prefersDark = window.matchMedia("(prefers-color-scheme: dark)").matches
  if (prefersDark) {
    document.documentElement.style.colorScheme = "dark"
  }
}

// Alert Auto-dismiss
function initAlerts() {
  const alerts = document.querySelectorAll(".alert")
  alerts.forEach((alert) => {
    setTimeout(() => {
      alert.style.animation = "slideOut 300ms ease-out forwards"
      setTimeout(() => alert.remove(), 300)
    }, 5000)
  })
}

// Form Validation
function initFormValidation() {
  const forms = document.querySelectorAll("form")
  forms.forEach((form) => {
    form.addEventListener("submit", function (e) {
      const inputs = this.querySelectorAll("input[required], select[required]")
      let isValid = true

      inputs.forEach((input) => {
        if (!input.value.trim()) {
          input.style.borderColor = "var(--danger-color)"
          isValid = false
        } else {
          input.style.borderColor = "var(--border-color)"
        }
      })

      if (!isValid) {
        e.preventDefault()
      }
    })

    // Clear error on input
    const inputs = form.querySelectorAll("input, select")
    inputs.forEach((input) => {
      input.addEventListener("input", function () {
        this.style.borderColor = "var(--border-color)"
      })
    })
  })
}

// Smooth Scroll
function initSmoothScroll() {
  document.querySelectorAll('a[href^="#"]').forEach((anchor) => {
    anchor.addEventListener("click", function (e) {
      e.preventDefault()
      const target = document.querySelector(this.getAttribute("href"))
      if (target) {
        target.scrollIntoView({ behavior: "smooth" })
      }
    })
  })
}

// Button Ripple Effect (already in CSS, but can enhance with JS)
function initRippleEffect() {
  const buttons = document.querySelectorAll(".btn")
  buttons.forEach((button) => {
    button.addEventListener("click", function (e) {
      const ripple = document.createElement("span")
      const rect = this.getBoundingClientRect()
      const size = Math.max(rect.width, rect.height)
      const x = e.clientX - rect.left - size / 2
      const y = e.clientY - rect.top - size / 2

      ripple.style.width = ripple.style.height = size + "px"
      ripple.style.left = x + "px"
      ripple.style.top = y + "px"
    })
  })
}

// Initialize all features
document.addEventListener("DOMContentLoaded", () => {
  initThemeToggle()
  initAlerts()
  initFormValidation()
  initSmoothScroll()
  initRippleEffect()
})

// Add CSS animation for alert slide out
const style = document.createElement("style")
style.textContent = `
    @keyframes slideOut {
        to {
            opacity: 0;
            transform: translateY(-10px);
        }
    }
`
document.head.appendChild(style)
