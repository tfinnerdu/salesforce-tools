'use strict';

MC.velocity = {
  _chart: null,
  _days: 30,

  init() {
    document.getElementById('velocityDaysSelect')?.addEventListener('change', e => {
      this._days = parseInt(e.target.value, 10);
      this.load();
    });
    document.getElementById('btnRefreshVelocity')?.addEventListener('click', () => this.load());
    this.load();
  },

  load() {
    const loading = document.getElementById('velocityLoading');
    const wrap = document.getElementById('velocityChartWrap');
    if (loading) loading.classList.remove('d-none');
    if (wrap) wrap.classList.add('d-none');
    MC.api(`/migration/velocity/data?days=${this._days}`)
      .then(data => {
        this._renderStats(data);
        this._renderChart(data);
        if (loading) loading.classList.add('d-none');
        if (wrap) wrap.classList.remove('d-none');
      })
      .catch(err => {
        if (loading) loading.classList.add('d-none');
        MC.showToast('Failed to load velocity data: ' + err, 'danger');
      });
  },

  _renderStats(data) {
    const el = id => document.getElementById(id);
    if (el('statMigrated')) el('statMigrated').textContent = `${data.total_migrated.toLocaleString()} / ${data.target.toLocaleString()}`;
    if (el('statPct')) {
      const pct = data.pct_complete;
      const color = pct >= 90 ? 'success' : pct >= 60 ? 'warning' : 'danger';
      el('statPct').innerHTML = `<div class="progress" style="height:20px"><div class="progress-bar bg-${color}" style="width:${pct}%">${pct}%</div></div>`;
    }
    if (el('statVelocity')) el('statVelocity').textContent = `${data.velocity_avg} rec/day`;
    if (el('statEta')) {
      el('statEta').textContent = data.eta_date
        ? (data.pct_complete >= 100 ? '✓ Complete!' : data.eta_date)
        : 'N/A';
    }
  },

  _renderChart(data) {
    const ctx = document.getElementById('velocityChart')?.getContext('2d');
    if (!ctx) return;
    if (this._chart) this._chart.destroy();
    const labels = data.daily.map(d => d.date);
    const daily = data.daily.map(d => d.records);
    const cumulative = data.daily.map(d => d.cumulative);
    const targetLine = data.daily.map(() => data.target);
    this._chart = new Chart(ctx, {
      type: 'bar',
      data: {
        labels,
        datasets: [
          { label: 'Daily Records', data: daily, backgroundColor: 'rgba(252,185,0,0.7)', yAxisID: 'y' },
          { label: 'Cumulative', data: cumulative, type: 'line', borderColor: '#0063B0', backgroundColor: 'transparent', borderWidth: 2, pointRadius: 0, yAxisID: 'y2' },
          { label: `Target (${data.target.toLocaleString()})`, data: targetLine, type: 'line', borderColor: '#dc3545', backgroundColor: 'transparent', borderWidth: 1, borderDash: [6, 3], pointRadius: 0, yAxisID: 'y2' },
        ],
      },
      options: {
        responsive: true, maintainAspectRatio: false,
        plugins: { legend: { position: 'top' } },
        scales: {
          y: { title: { display: true, text: 'Daily Records' }, beginAtZero: true },
          y2: { position: 'right', title: { display: true, text: 'Cumulative' }, beginAtZero: true, grid: { drawOnChartArea: false } },
        },
      },
    });
  },
};
