'use strict';

// ── Admin ─────────────────────────────────────────────────────────────────────
// Paste this object into mission-control.js after the last MC.* namespace block.

MC.admin = {
  _users: [],

  init() {
    document.getElementById('btnRefreshJobs')?.addEventListener('click', () => this.loadScheduledJobs());
    document.getElementById('btnRefreshCoverage')?.addEventListener('click', () => this.loadTestCoverage());
    document.getElementById('btnRefreshDeploys')?.addEventListener('click', () => this.loadDeployHistory());
    document.getElementById('btnRefreshUsers')?.addEventListener('click', () => this.loadUsers());

    document.getElementById('userFilter')?.addEventListener('input', (e) => {
      this._filterUsers(e.target.value.trim().toLowerCase());
    });

    // Load the default (first) tab on init
    this.loadScheduledJobs();

    // Lazy-load other tabs when first shown
    document.getElementById('tab-coverage')?.addEventListener('shown.bs.tab', () => {
      if (!document.getElementById('coverageCard')?.classList.contains('d-none')) return;
      if (!document.getElementById('coverageEmpty')?.classList.contains('d-none')) return;
      this.loadTestCoverage();
    });
    document.getElementById('tab-deploys')?.addEventListener('shown.bs.tab', () => {
      if (!document.getElementById('deploysCard')?.classList.contains('d-none')) return;
      if (!document.getElementById('deploysEmpty')?.classList.contains('d-none')) return;
      this.loadDeployHistory();
    });
    document.getElementById('tab-users')?.addEventListener('shown.bs.tab', () => {
      if (!document.getElementById('usersCard')?.classList.contains('d-none')) return;
      if (!document.getElementById('usersEmpty')?.classList.contains('d-none')) return;
      this.loadUsers();
    });
  },

  // ── Scheduled Jobs ──────────────────────────────────────────────────────────

  async loadScheduledJobs() {
    const loading = document.getElementById('jobsLoading');
    const empty   = document.getElementById('jobsEmpty');
    const card    = document.getElementById('jobsCard');
    loading?.classList.remove('d-none');
    empty?.classList.add('d-none');
    card?.classList.add('d-none');
    try {
      const jobs = await MC.api('/admin/scheduled-jobs');
      if (!jobs || jobs.length === 0) {
        empty?.classList.remove('d-none');
        return;
      }
      this._renderJobsTable(jobs);
      card?.classList.remove('d-none');
    } catch (err) {
      MC.showToast(`Failed to load scheduled jobs: ${err.message}`, 'danger');
      empty?.classList.remove('d-none');
    } finally {
      loading?.classList.add('d-none');
    }
  },

  _renderJobsTable(jobs) {
    const tbody = document.getElementById('jobsBody');
    if (!tbody) return;
    tbody.innerHTML = jobs.map(j => {
      const stateBadge = this._jobStateBadge(j.state);
      return `<tr>
        <td class="fw-semibold">${MC._escHtml(j.name)}</td>
        <td class="text-muted small">${MC._escHtml(j.job_type_label)}</td>
        <td>${stateBadge}</td>
        <td class="small">${MC._fmtTime(j.next_fire_time)}</td>
        <td class="text-muted small">${MC._fmtTime(j.previous_fire_time)}</td>
        <td class="text-end small">${MC._escHtml(j.times_triggered)}</td>
        <td><code class="small">${MC._escHtml(j.cron_expression)}</code></td>
      </tr>`;
    }).join('');
  },

  _jobStateBadge(state) {
    const s = (state || '').toUpperCase();
    const cls =
      s === 'WAITING'   ? 'badge-green' :
      s === 'EXECUTING' ? 'badge-green' :
      s === 'PAUSED'    ? 'badge-amber' :
      s === 'ERROR'     ? 'badge-red'   :
      'badge-navy';
    return `<span class="badge ${cls}">${MC._escHtml(s)}</span>`;
  },

  // ── Test Coverage ───────────────────────────────────────────────────────────

  async loadTestCoverage() {
    const loading = document.getElementById('coverageLoading');
    const empty   = document.getElementById('coverageEmpty');
    const card    = document.getElementById('coverageCard');
    const summary = document.getElementById('coverageSummary');
    loading?.classList.remove('d-none');
    empty?.classList.add('d-none');
    card?.classList.add('d-none');
    summary?.classList.add('d-none');
    try {
      const data = await MC.api('/admin/test-coverage');
      const classes = data?.classes || [];
      if (classes.length === 0) {
        empty?.classList.remove('d-none');
        return;
      }
      this._renderCoverageSummary(data.summary || {});
      this._renderCoverageTable(classes);
      card?.classList.remove('d-none');
      summary?.classList.remove('d-none');
    } catch (err) {
      MC.showToast(`Failed to load test coverage: ${err.message}`, 'danger');
      empty?.classList.remove('d-none');
    } finally {
      loading?.classList.add('d-none');
    }
  },

  _renderCoverageSummary(s) {
    const passing = s.passing ?? 0;
    const below   = s.below_threshold ?? 0;
    const failing = s.failing ?? 0;
    const passEl  = document.getElementById('covPassing');
    const belowEl = document.getElementById('covBelow');
    const failEl  = document.getElementById('covFailing');
    if (passEl)  passEl.textContent  = `${passing} passing`;
    if (belowEl) belowEl.textContent = `${below} below 75%`;
    if (failEl)  failEl.textContent  = `${failing} below 50%`;
  },

  _renderCoverageTable(classes) {
    const tbody = document.getElementById('coverageBody');
    if (!tbody) return;
    tbody.innerHTML = classes.map(c => {
      const pct = parseFloat(c.pct) || 0;
      const rowCls =
        pct >= 75 ? '' :
        pct >= 50 ? 'table-warning' :
        'table-danger';
      const barCls =
        pct >= 75 ? 'bg-success' :
        pct >= 50 ? 'bg-warning' :
        'bg-danger';
      const pctStr = `${pct.toFixed(1)}%`;
      return `<tr class="${rowCls}">
        <td class="fw-semibold">${MC._escHtml(c.name)}</td>
        <td class="text-end small">${MC._escHtml(c.num_lines_covered)}</td>
        <td class="text-end small">${MC._escHtml(c.num_lines_uncovered)}</td>
        <td>
          <div class="d-flex align-items-center gap-2">
            <div class="progress flex-grow-1" style="height:10px">
              <div class="progress-bar ${barCls}" role="progressbar"
                   style="width:${pct}%" aria-valuenow="${pct}"
                   aria-valuemin="0" aria-valuemax="100"></div>
            </div>
            <span class="small text-nowrap">${pctStr}</span>
          </div>
        </td>
      </tr>`;
    }).join('');
  },

  // ── Deployment History ──────────────────────────────────────────────────────

  async loadDeployHistory() {
    const loading = document.getElementById('deploysLoading');
    const empty   = document.getElementById('deploysEmpty');
    const card    = document.getElementById('deploysCard');
    loading?.classList.remove('d-none');
    empty?.classList.add('d-none');
    card?.classList.add('d-none');
    try {
      const deploys = await MC.api('/admin/deploy-history');
      if (!deploys || deploys.length === 0) {
        empty?.classList.remove('d-none');
        return;
      }
      this._renderDeploysTable(deploys);
      card?.classList.remove('d-none');
    } catch (err) {
      MC.showToast(`Failed to load deployments: ${err.message}`, 'danger');
      empty?.classList.remove('d-none');
    } finally {
      loading?.classList.add('d-none');
    }
  },

  _renderDeploysTable(deploys) {
    const tbody = document.getElementById('deploysBody');
    if (!tbody) return;
    tbody.innerHTML = deploys.map((d, idx) => {
      const statusBadge = MC.statusBadge(d.status);
      const duration = d.duration_seconds != null ? `${d.duration_seconds}s` : '—';
      const hasErrors = (d.num_component_errors > 0) || (d.num_test_errors > 0);
      const detailId  = `deployDetail-${idx}`;
      const expandBtn = hasErrors
        ? `<button class="btn btn-link btn-sm p-0 ms-1" type="button"
                   data-bs-toggle="collapse" data-bs-target="#${detailId}"
                   aria-expanded="false">detail</button>`
        : '';
      const detailRow = hasErrors && d.state_detail
        ? `<tr id="${detailId}" class="collapse">
             <td colspan="7" class="text-danger small ps-3">
               <code>${MC._escHtml(d.state_detail)}</code>
             </td>
           </tr>`
        : '';
      return `<tr>
        <td class="small">${MC._fmtTime(d.start_date)}</td>
        <td class="small">${MC._escHtml(d.created_by)}</td>
        <td class="text-end small">${MC._escHtml(d.num_components_total)}</td>
        <td class="text-end small ${d.num_component_errors > 0 ? 'text-danger fw-semibold' : ''}">${MC._escHtml(d.num_component_errors)}${expandBtn}</td>
        <td class="text-end small">${MC._escHtml(d.num_tests_completed)}</td>
        <td class="text-end small">${duration}</td>
        <td>${statusBadge}</td>
      </tr>${detailRow}`;
    }).join('');
  },

  // ── User Audit ──────────────────────────────────────────────────────────────

  async loadUsers() {
    const loading = document.getElementById('usersLoading');
    const empty   = document.getElementById('usersEmpty');
    const card    = document.getElementById('usersCard');
    const summary = document.getElementById('usersSummary');
    loading?.classList.remove('d-none');
    empty?.classList.add('d-none');
    card?.classList.add('d-none');
    summary?.classList.add('d-none');
    const filterEl = document.getElementById('userFilter');
    if (filterEl) filterEl.value = '';
    try {
      const data = await MC.api('/admin/users');
      this._users = data?.users || [];
      if (this._users.length === 0) {
        empty?.classList.remove('d-none');
        return;
      }
      this._renderUserSummary(data.summary || {});
      this._renderUsersTable(this._users);
      card?.classList.remove('d-none');
      summary?.classList.remove('d-none');
    } catch (err) {
      MC.showToast(`Failed to load user audit: ${err.message}`, 'danger');
      empty?.classList.remove('d-none');
    } finally {
      loading?.classList.add('d-none');
    }
  },

  _renderUserSummary(s) {
    const activeEl    = document.getElementById('sumActive');
    const inactive90El= document.getElementById('sumInactive90');
    const neverEl     = document.getElementById('sumNeverLogin');
    const sysEl       = document.getElementById('sumSysadmins');
    if (activeEl)     activeEl.textContent     = s.total_active ?? '—';
    if (inactive90El) inactive90El.textContent = s.inactive_90d ?? '—';
    if (neverEl)      neverEl.textContent      = s.never_logged_in ?? '—';
    if (sysEl)        sysEl.textContent        = s.sysadmins ?? '—';
  },

  _renderUsersTable(users) {
    const tbody = document.getElementById('usersBody');
    if (!tbody) return;
    tbody.innerHTML = users.map(u => {
      const rowCls =
        !u.is_active        ? 'text-muted'    :
        u.flag === 'never_logged_in' ? 'table-danger'  :
        u.flag === 'inactive_90d'    ? 'table-warning' :
        '';
      const loginText = u.last_login_date ? MC._fmtTime(u.last_login_date) : 'Never';
      const statusBadge = u.is_active
        ? (u.flag === 'never_logged_in' ? '<span class="badge badge-red">NEVER</span>'
         : u.flag === 'inactive_90d'    ? '<span class="badge badge-amber">STALE</span>'
         :                               '<span class="badge badge-green">ACTIVE</span>')
        : '<span class="badge badge-navy">INACTIVE</span>';
      return `<tr class="${rowCls}">
        <td>${MC._escHtml(u.name)}</td>
        <td class="small text-muted"><code>${MC._escHtml(u.username)}</code></td>
        <td class="small">${MC._escHtml(u.profile_name)}</td>
        <td class="small">${loginText}</td>
        <td>${statusBadge}</td>
      </tr>`;
    }).join('');
  },

  _filterUsers(q) {
    if (!q) {
      this._renderUsersTable(this._users);
      return;
    }
    const filtered = this._users.filter(u =>
      (u.name || '').toLowerCase().includes(q) ||
      (u.username || '').toLowerCase().includes(q)
    );
    this._renderUsersTable(filtered);
  },
};
