function renderPriceChart(canvasId, priceData, threshold) {
    const ctx = document.getElementById(canvasId).getContext('2d');

    // Group data by source
    const sources = {};
    priceData.forEach(p => {
        if (!sources[p.source]) {
            sources[p.source] = [];
        }
        sources[p.source].push({
            x: new Date(p.scraped_at),
            y: p.price,
        });
    });

    const colors = {
        'trip.com': '#1976d2',
        'skyscanner': '#f57c00',
        'agoda': '#7b1fa2',
    };

    const datasets = Object.entries(sources).map(([source, data]) => ({
        label: source,
        data: data,
        borderColor: colors[source] || '#666',
        backgroundColor: (colors[source] || '#666') + '20',
        tension: 0.3,
        fill: false,
        pointRadius: 3,
    }));

    // Add threshold line if set
    if (threshold !== null && threshold !== undefined) {
        const dates = priceData.map(p => new Date(p.scraped_at));
        const minDate = new Date(Math.min(...dates));
        const maxDate = new Date(Math.max(...dates));
        datasets.push({
            label: 'Threshold',
            data: [
                { x: minDate, y: threshold },
                { x: maxDate, y: threshold },
            ],
            borderColor: '#e53935',
            borderDash: [5, 5],
            pointRadius: 0,
            fill: false,
        });
    }

    new Chart(ctx, {
        type: 'line',
        data: { datasets },
        options: {
            responsive: true,
            scales: {
                x: {
                    type: 'time',
                    time: {
                        unit: 'day',
                        displayFormats: { day: 'MMM d' },
                    },
                    title: { display: true, text: 'Date' },
                },
                y: {
                    title: { display: true, text: 'Price' },
                    beginAtZero: false,
                },
            },
            plugins: {
                legend: { position: 'top' },
                tooltip: {
                    callbacks: {
                        label: function(ctx) {
                            return `${ctx.dataset.label}: ${ctx.parsed.y.toFixed(0)}`;
                        }
                    }
                }
            },
        },
    });
}
