function initStudentProfile(data) {
    const ctx1 = document.getElementById('performanceTrendChart');
    const ctx2 = document.getElementById('scoreDistributionChart');

    if (!ctx1 || !ctx2) return;

    // Performance Trend
    new Chart(ctx1, {
        type: 'line',
        data: {
            labels: data.exams,
            datasets: [{
                label: 'Score (%)',
                data: data.scores,
                borderColor: '#6366f1',
                backgroundColor: 'rgba(99,102,241,0.1)',
                borderWidth: 3,
                tension: 0.4,
                pointRadius: 5,
                fill: true
            }]
        },
        options: { responsive: true, maintainAspectRatio: false }
    });

    // Score Distribution
    new Chart(ctx2, {
        type: 'doughnut',
        data: {
            labels: ['Passed', 'Failed'],
            datasets: [{
                data: [data.passedCount, data.failedCount],
                backgroundColor: ['#10b981', '#ef4444'],
                borderColor: '#1f2937',
                borderWidth: 3
            }]
        },
        options: {
            plugins: {
                legend: { position: 'bottom' }
            },
            maintainAspectRatio: false
        }
    });
}
