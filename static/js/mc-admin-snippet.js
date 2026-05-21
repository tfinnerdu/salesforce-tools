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
    document.getElementById('tab-anonymizer-btn')?.addEventListener('shown.bs.tab', () => {
      this.initAnonymizer();
    });
    document.getElementById('tab-integrations-btn')?.addEventListener('shown.bs.tab', () => {
      this.loadIntegrations();
    });
    document.getElementById('tab-platform-events-btn')?.addEventListener('shown.bs.tab', () => {
      this.loadPlatformEvents();
    });
    document.getElementById('btnRefreshPlatformEvents')?.addEventListener('click', () => {
      this.loadPlatformEvents();
    });
    document.getElementById('tab-record-types-btn')?.addEventListener('shown.bs.tab', () => this.loadRecordTypes());
    document.getElementById('tab-email-templates-btn')?.addEventListener('shown.bs.tab', () => this.loadEmailTemplates());
    document.getElementById('btnRefreshRecordTypes')?.addEventListener('click', () => this.loadRecordTypes());
    document.getElementById('btnRefreshEmailTemplates')?.addEventListener('click', () => this.loadEmailTemplates());
    document.getElementById('emailTemplateSearch')?.addEventListener('input', (e) => {
      this._filterEmailTemplates(e.target.value.trim().toLowerCase());
    });

    // Wire all Refresh buttons inside the integrations tab
    document.querySelectorAll('.integ-refresh-btn').forEach(btn => {
      btn.addEventListener('click', () => this.loadIntegrations());
    });

    document.getElementById('tab-audit-trail-btn')?.addEventListener('shown.bs.tab', () => this.loadAuditTrail());
    document.getElementById('btnRefreshAuditTrail')?.addEventListener('click', () => this.loadAuditTrail());
    document.getElementById('auditTrailSearch')?.addEventListener('input', e => this._filterAuditTrail(e.target.value));
    document.getElementById('auditTrailDays')?.addEventListener('change', () => this.loadAuditTrail());

    document.getElementById('tab-job-queue-btn')?.addEventListener('shown.bs.tab', () => this.loadJobQueue());
    document.getElementById('tab-login-history-btn')?.addEventListener('shown.bs.tab', () => this.loadLoginHistory());
    document.getElementById('btnRefreshJobQueue')?.addEventListener('click', () => this.loadJobQueue());
    document.getElementById('btnRefreshLoginHistory')?.addEventListener('click', () => this.loadLoginHistory());

    MC.customMetadata.init();
    MC.customSettings.init();
    document.getElementById('loginHistorySearch')?.addEventListener('input', e => this._filterTable('loginHistoryTbody', e.target.value));
    document.getElementById('jobQueueAutoRefresh')?.addEventListener('change', e => this._setJobQueueAutoRefresh(e.target.checked));

    document.getElementById('tab-permissions-btn')?.addEventListener('shown.bs.tab', () => MC.permissions.init());
    document.getElementById('btnRefreshPermissions')?.addEventListener('click', () => MC.permissions.reload());

    document.getElementById('tab-automation-btn')?.addEventListener('shown.bs.tab', () => MC.automation.init());
    document.getElementById('btnRefreshAutomation')?.addEventListener('click', () => MC.automation.reload());

    // Status filter pills for job queue
    document.getElementById('jobQueueFilters')?.addEventListener('click', e => {
      const btn = e.target.closest('[data-jq-filter]');
      if (!btn) return;
      document.querySelectorAll('#jobQueueFilters [data-jq-filter]').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      this._applyJobQueueFilter(btn.dataset.jqFilter);
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
        <td>${MC.sfLinkTag(u.id, 'User', u.name)}</td>
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

  // ── Anonymizer ─────────────────────────────────────────────────────────────

  async initAnonymizer() {
    try {
      const objects = await MC.api('/admin/anonymizer/objects');
      const sel = document.getElementById('anonObjectSelect');
      if (sel) {
        (objects || []).forEach(o => {
          const opt = document.createElement('option');
          opt.value = o.object;
          opt.textContent = o.object;
          opt.dataset.fields = JSON.stringify(o.fields);
          sel.appendChild(opt);
        });
        sel.addEventListener('change', () => this._renderAnonFields(sel));
      }
    } catch (err) {
      MC.showToast(`Failed to load anonymizer objects: ${err.message}`, 'danger');
    }
    document.getElementById('btnAnonPreview')?.addEventListener('click', () => this.anonPreview());
    document.getElementById('btnAnonRun')?.addEventListener('click', () => this.anonRun());
  },

  _renderAnonFields(sel) {
    const fields = JSON.parse(sel.selectedOptions[0]?.dataset.fields || '[]');
    const wrap = document.getElementById('anonFieldsList');
    if (!wrap) return;
    if (!fields.length) {
      wrap.innerHTML = '<span class="text-muted small">No fields available</span>';
      return;
    }
    wrap.innerHTML = fields.map(f => `
      <div class="form-check">
        <input class="form-check-input anon-field-check" type="checkbox"
               id="anonField_${MC._escHtml(f)}" value="${MC._escHtml(f)}" checked>
        <label class="form-check-label small font-monospace" for="anonField_${MC._escHtml(f)}">${MC._escHtml(f)}</label>
      </div>`).join('');
    document.getElementById('btnAnonRun').disabled = false;
  },

  _getAnonSelection() {
    const object = document.getElementById('anonObjectSelect')?.value;
    const fields = Array.from(document.querySelectorAll('.anon-field-check:checked')).map(el => el.value);
    return { object, fields };
  },

  async anonPreview() {
    const { object, fields } = this._getAnonSelection();
    if (!object) { MC.showToast('Select an object first', 'warning'); return; }
    try {
      const data = await MC.api('/admin/anonymizer/preview', 'POST', { object, fields });
      document.getElementById('anonRecordCount').textContent = (data.record_count || 0).toLocaleString();
      document.getElementById('anonPreviewObject').textContent = data.object || object;
      document.getElementById('anonPreviewFields').textContent = (data.fields || fields).join(', ');
      document.getElementById('anonPreviewSoql').textContent = data.soql || '';
      document.getElementById('anonPreviewWrap')?.classList.remove('d-none');
      document.getElementById('anonResultWrap')?.classList.add('d-none');
    } catch (err) {
      MC.showToast(`Preview failed: ${err.message}`, 'danger');
    }
  },

  async anonRun() {
    const { object, fields } = this._getAnonSelection();
    const dryRun = document.getElementById('anonDryRun')?.checked ?? true;
    if (!object || !fields.length) { MC.showToast('Select object and at least one field', 'warning'); return; }
    if (!dryRun && !confirm(`Run LIVE anonymization on ${object}? This modifies real data.`)) return;
    MC.showSpinner();
    try {
      const data = await MC.api('/admin/anonymizer/run', 'POST', { object, fields, dry_run: dryRun });
      const alertEl = document.getElementById('anonResultAlert');
      if (alertEl) {
        alertEl.className = `alert py-2 small mb-0 alert-${data.status === 'stub' || data.status === 'dry_run' ? 'info' : 'success'}`;
        alertEl.textContent = data.message || JSON.stringify(data);
      }
      document.getElementById('anonResultWrap')?.classList.remove('d-none');
    } catch (err) {
      MC.showToast(`Run failed: ${err.message}`, 'danger');
    } finally {
      MC.hideSpinner();
    }
  },

  // ── Integrations ────────────────────────────────────────────────────────────

  async loadIntegrations() {
    // Show spinners, hide tables and empty states
    ['namedCreds', 'remoteSites', 'connectedApps'].forEach(key => {
      document.getElementById(`${key}Loading`)?.classList.remove('d-none');
      document.getElementById(`${key}Empty`)?.classList.add('d-none');
      document.getElementById(`${key}CardBody`)?.classList.add('d-none');
    });
    try {
      const data = await MC.api('/admin/integrations');
      this._renderNamedCreds(data.named_credentials || []);
      this._renderRemoteSites(data.remote_sites || []);
      this._renderConnectedApps(data.connected_apps || []);
    } catch (err) {
      MC.showToast(`Failed to load integrations: ${err.message}`, 'danger');
      ['namedCreds', 'remoteSites', 'connectedApps'].forEach(key => {
        document.getElementById(`${key}Empty`)?.classList.remove('d-none');
      });
    } finally {
      ['namedCreds', 'remoteSites', 'connectedApps'].forEach(key => {
        document.getElementById(`${key}Loading`)?.classList.add('d-none');
      });
    }
  },

  _renderNamedCreds(items) {
    const tbody = document.getElementById('namedCredsTbody');
    const empty = document.getElementById('namedCredsEmpty');
    const body  = document.getElementById('namedCredsCardBody');
    if (!tbody) return;
    if (!items.length) {
      empty?.classList.remove('d-none');
      body?.classList.add('d-none');
      return;
    }
    tbody.innerHTML = items.map(nc => {
      const endpoint = nc.endpoint || '';
      const truncated = endpoint.length > 50 ? endpoint.slice(0, 50) + '…' : endpoint;
      const labelCell = nc.master_label !== nc.developer_name
        ? MC._escHtml(nc.master_label)
        : '<span class="text-muted">—</span>';
      return `<tr>
        <td class="fw-semibold font-monospace small">${MC._escHtml(nc.developer_name)}</td>
        <td class="small">${labelCell}</td>
        <td class="small"><code title="${MC._escHtml(endpoint)}">${MC._escHtml(truncated)}</code></td>
        <td class="small">${MC._escHtml(nc.protocol)}</td>
      </tr>`;
    }).join('');
    empty?.classList.add('d-none');
    body?.classList.remove('d-none');
  },

  _renderRemoteSites(items) {
    const tbody = document.getElementById('remoteSitesTbody');
    const empty = document.getElementById('remoteSitesEmpty');
    const body  = document.getElementById('remoteSitesCardBody');
    if (!tbody) return;
    if (!items.length) {
      empty?.classList.remove('d-none');
      body?.classList.add('d-none');
      return;
    }
    tbody.innerHTML = items.map(rs => {
      const activeBadge = rs.is_active
        ? '<span class="badge badge-green">ACTIVE</span>'
        : '<span class="badge badge-amber">INACTIVE</span>';
      const secProtocol = rs.disable_protocol_security
        ? '<span class="text-warning small">Disabled</span>'
        : '<span class="text-muted small">Enforced</span>';
      return `<tr>
        <td class="fw-semibold small">${MC._escHtml(rs.site_name)}</td>
        <td class="small"><code>${MC._escHtml(rs.url)}</code></td>
        <td>${activeBadge}</td>
        <td>${secProtocol}</td>
      </tr>`;
    }).join('');
    empty?.classList.add('d-none');
    body?.classList.remove('d-none');
  },

  _renderConnectedApps(items) {
    const tbody = document.getElementById('connectedAppsTbody');
    const empty = document.getElementById('connectedAppsEmpty');
    const body  = document.getElementById('connectedAppsCardBody');
    if (!tbody) return;
    if (!items.length) {
      empty?.classList.remove('d-none');
      body?.classList.add('d-none');
      return;
    }
    tbody.innerHTML = items.map(ca => {
      return `<tr>
        <td class="fw-semibold small">${MC._escHtml(ca.master_label)}</td>
        <td class="small font-monospace">${MC._escHtml(ca.developer_name)}</td>
        <td class="small text-muted">${MC._escHtml(ca.description || '—')}</td>
      </tr>`;
    }).join('');
    empty?.classList.add('d-none');
    body?.classList.remove('d-none');
  },

  // ── Platform Events ─────────────────────────────────────────────────────────

  async loadPlatformEvents() {
    ['eventChannels', 'eventMembers'].forEach(key => {
      document.getElementById(`${key}Loading`)?.classList.remove('d-none');
      document.getElementById(`${key}Empty`)?.classList.add('d-none');
      document.getElementById(`${key}CardBody`)?.classList.add('d-none');
    });
    try {
      const data = await MC.api('/admin/platform-events');
      this._renderEventChannels(data.events || []);
      this._renderEventMembers(data.members || []);
    } catch (err) {
      MC.showToast(`Failed to load platform events: ${err.message}`, 'danger');
      ['eventChannels', 'eventMembers'].forEach(key => {
        document.getElementById(`${key}Empty`)?.classList.remove('d-none');
      });
    } finally {
      ['eventChannels', 'eventMembers'].forEach(key => {
        document.getElementById(`${key}Loading`)?.classList.add('d-none');
      });
    }
  },

  _renderEventChannels(items) {
    const tbody = document.getElementById('eventChannelsTbody');
    const empty = document.getElementById('eventChannelsEmpty');
    const body  = document.getElementById('eventChannelsCardBody');
    if (!tbody) return;
    if (!items.length) {
      empty?.classList.remove('d-none');
      body?.classList.add('d-none');
      return;
    }
    tbody.innerHTML = items.map(ev => `<tr>
      <td class="fw-semibold small">${MC._escHtml(ev.label)}</td>
      <td class="small font-monospace">${MC._escHtml(ev.developer_name)}</td>
      <td class="small text-muted">${MC._escHtml(ev.description || '—')}</td>
    </tr>`).join('');
    empty?.classList.add('d-none');
    body?.classList.remove('d-none');
  },

  _renderEventMembers(items) {
    const tbody = document.getElementById('eventMembersTbody');
    const empty = document.getElementById('eventMembersEmpty');
    const body  = document.getElementById('eventMembersCardBody');
    if (!tbody) return;
    if (!items.length) {
      empty?.classList.remove('d-none');
      body?.classList.add('d-none');
      return;
    }
    tbody.innerHTML = items.map(m => {
      const typeBadge = this._eventTypeBadge(m.type);
      return `<tr>
        <td class="fw-semibold small font-monospace">${MC._escHtml(m.developer_name)}</td>
        <td class="small font-monospace">${MC._escHtml(m.channel)}</td>
        <td>${typeBadge}</td>
      </tr>`;
    }).join('');
    empty?.classList.add('d-none');
    body?.classList.remove('d-none');
  },

  _eventTypeBadge(type) {
    const t = (type || '').trim();
    const cls =
      t === 'Flow'          ? 'badge-navy'  :
      t === 'ApexTrigger'   ? 'badge-blue'  :
      t === 'WorkflowAlert' ? 'badge-amber' :
      'badge-secondary';
    return `<span class="badge ${cls}">${MC._escHtml(t || '—')}</span>`;
  },

  // ── Record Types ────────────────────────────────────────────────────────────

  async loadRecordTypes() {
    const loading = document.getElementById('recordTypesLoading');
    const empty   = document.getElementById('recordTypesEmpty');
    const card    = document.getElementById('recordTypesCard');
    loading?.classList.remove('d-none');
    empty?.classList.add('d-none');
    card?.classList.add('d-none');
    try {
      const data = await MC.api('/admin/record-types');
      if (!data || data.length === 0) {
        empty?.classList.remove('d-none');
        return;
      }
      this._renderRecordTypesTable(data);
      card?.classList.remove('d-none');
    } catch (err) {
      MC.showToast(`Failed to load record types: ${err.message}`, 'danger');
      empty?.classList.remove('d-none');
    } finally {
      loading?.classList.add('d-none');
    }
  },

  _renderRecordTypesTable(recordTypes) {
    const tbody = document.getElementById('recordTypesTbody');
    if (!tbody) return;
    tbody.innerHTML = recordTypes.map(rt => {
      const activeBadge = rt.is_active
        ? '<span class="badge badge-green">ACTIVE</span>'
        : '<span class="badge badge-amber">INACTIVE</span>';
      const countCell = rt.record_count != null
        ? rt.record_count.toLocaleString()
        : '—';
      const rowCls = rt.is_active ? '' : 'text-muted';
      return `<tr class="${rowCls}">
        <td class="small font-monospace fw-semibold">${MC._escHtml(rt.sobject_type)}</td>
        <td class="small">${MC._escHtml(rt.name)}</td>
        <td class="small font-monospace text-muted">${MC._escHtml(rt.developer_name)}</td>
        <td>${activeBadge}</td>
        <td class="text-end small">${countCell}</td>
      </tr>`;
    }).join('');
  },

  // ── Email Templates ─────────────────────────────────────────────────────────

  _emailTemplates: [],

  async loadEmailTemplates() {
    const loading = document.getElementById('emailTemplatesLoading');
    const empty   = document.getElementById('emailTemplatesEmpty');
    const card    = document.getElementById('emailTemplatesCard');
    const searchEl = document.getElementById('emailTemplateSearch');
    loading?.classList.remove('d-none');
    empty?.classList.add('d-none');
    card?.classList.add('d-none');
    if (searchEl) searchEl.value = '';
    try {
      const data = await MC.api('/admin/email-templates');
      this._emailTemplates = data || [];
      if (this._emailTemplates.length === 0) {
        empty?.classList.remove('d-none');
        return;
      }
      this._renderEmailTemplatesTable(this._emailTemplates);
      card?.classList.remove('d-none');
    } catch (err) {
      MC.showToast(`Failed to load email templates: ${err.message}`, 'danger');
      empty?.classList.remove('d-none');
    } finally {
      loading?.classList.add('d-none');
    }
  },

  _renderEmailTemplatesTable(templates) {
    const tbody = document.getElementById('emailTemplatesTbody');
    if (!tbody) return;
    tbody.innerHTML = templates.map(t => {
      const activeBadge = t.is_active
        ? '<span class="badge badge-green">ACTIVE</span>'
        : '<span class="badge badge-navy">INACTIVE</span>';
      const encodingCell = (t.encoding || '').toUpperCase() === 'UTF-8'
        ? `<span class="small">${MC._escHtml(t.encoding)}</span>`
        : `<span class="badge badge-amber">${MC._escHtml(t.encoding || '—')}</span>`;
      const rowCls = t.is_active ? '' : 'text-muted';
      const modified = t.last_modified_date ? MC._fmtTime(t.last_modified_date) : '—';
      return `<tr class="${rowCls}">
        <td class="small text-muted">${MC._escHtml(t.folder_name)}</td>
        <td class="small fw-semibold">${MC._escHtml(t.name)}</td>
        <td class="small">${MC._escHtml(t.subject)}</td>
        <td>${encodingCell}</td>
        <td>${activeBadge}</td>
        <td class="small text-muted">${modified}</td>
      </tr>`;
    }).join('');
  },

  _filterEmailTemplates(query) {
    if (!query) {
      this._renderEmailTemplatesTable(this._emailTemplates);
      return;
    }
    const filtered = this._emailTemplates.filter(t =>
      (t.name || '').toLowerCase().includes(query) ||
      (t.folder_name || '').toLowerCase().includes(query) ||
      (t.subject || '').toLowerCase().includes(query)
    );
    this._renderEmailTemplatesTable(filtered);
  },

  // ── Setup Audit Trail ───────────────────────────────────────────────────────

  _auditTrailEntries: [],

  async loadAuditTrail() {
    const loading = document.getElementById('auditTrailLoading');
    const empty   = document.getElementById('auditTrailEmpty');
    const card    = document.getElementById('auditTrailCard');
    const searchEl = document.getElementById('auditTrailSearch');
    loading?.classList.remove('d-none');
    empty?.classList.add('d-none');
    card?.classList.add('d-none');
    if (searchEl) searchEl.value = '';
    const days = document.getElementById('auditTrailDays')?.value || 7;
    try {
      const data = await MC.api(`/admin/audit-trail?days=${days}`);
      this._auditTrailEntries = data || [];
      if (this._auditTrailEntries.length === 0) {
        empty?.classList.remove('d-none');
        return;
      }
      this._renderAuditTrail(this._auditTrailEntries);
      card?.classList.remove('d-none');
    } catch (err) {
      MC.showToast(`Failed to load audit trail: ${err.message}`, 'danger');
      empty?.classList.remove('d-none');
    } finally {
      loading?.classList.add('d-none');
    }
  },

  _renderAuditTrail(entries) {
    const tbody = document.getElementById('auditTrailTbody');
    if (!tbody) return;
    tbody.innerHTML = entries.map(e => {
      const dateCell = this._relativeDate(e.created_date);
      const sectionBadge = `<span class="badge bg-secondary bg-opacity-25 text-secondary small">${MC._escHtml(e.section)}</span>`;
      const actionBadge = this._auditActionBadge(e.action);
      return `<tr data-section="${MC._escHtml((e.section || '').toLowerCase())}"
                  data-by="${MC._escHtml((e.created_by || '').toLowerCase())}"
                  data-display="${MC._escHtml((e.display || '').toLowerCase())}">
        <td class="small text-nowrap" title="${MC._escHtml(e.created_date || '')}">${dateCell}</td>
        <td class="small">${MC._escHtml(e.created_by)}</td>
        <td>${sectionBadge}</td>
        <td>${actionBadge}</td>
        <td class="small text-muted">${MC._escHtml(e.display)}</td>
      </tr>`;
    }).join('');
  },

  _auditActionBadge(action) {
    const a = (action || '').trim();
    const cls =
      a === 'Created'   ? 'badge-green'  :
      a === 'Changed'   ? 'badge-amber'  :
      a === 'Deleted'   ? 'badge-red'    :
      a === 'Installed' ? 'badge-navy'   :
      a === 'Activated' ? 'badge-blue'   :
      'badge-secondary';
    return `<span class="badge ${cls}">${MC._escHtml(a || '—')}</span>`;
  },

  _filterAuditTrail(query) {
    const q = (query || '').toLowerCase();
    const tbody = document.getElementById('auditTrailTbody');
    if (!tbody) return;
    tbody.querySelectorAll('tr').forEach(row => {
      if (!q) {
        row.classList.remove('d-none');
        return;
      }
      const section = row.dataset.section || '';
      const by      = row.dataset.by || '';
      const display = row.dataset.display || '';
      const match = section.includes(q) || by.includes(q) || display.includes(q);
      row.classList.toggle('d-none', !match);
    });
  },

  _relativeDate(isoStr) {
    if (!isoStr) return '—';
    try {
      const dt = new Date(isoStr);
      const diffMs = Date.now() - dt.getTime();
      const diffMins = Math.floor(diffMs / 60000);
      if (diffMins < 60) return `${diffMins}m ago`;
      const diffHours = Math.floor(diffMins / 60);
      if (diffHours < 24) return `${diffHours}h ago`;
      const diffDays = Math.floor(diffHours / 24);
      return `${diffDays} day${diffDays !== 1 ? 's' : ''} ago`;
    } catch (e) {
      return isoStr;
    }
  },

  // ── Job Queue ───────────────────────────────────────────────────────────────

  _jobQueueTimer: null,
  _jobQueueData: [],

  async loadJobQueue() {
    const loading = document.getElementById('jobQueueLoading');
    const empty   = document.getElementById('jobQueueEmpty');
    const card    = document.getElementById('jobQueueCard');
    const summary = document.getElementById('jobQueueSummary');
    loading?.classList.remove('d-none');
    empty?.classList.add('d-none');
    card?.classList.add('d-none');
    summary?.classList.add('d-none');
    try {
      const data = await MC.api('/admin/job-queue');
      this._jobQueueData = data || [];
      if (this._jobQueueData.length === 0) {
        empty?.classList.remove('d-none');
        return;
      }
      this._renderJobQueue(this._jobQueueData);
      card?.classList.remove('d-none');
      summary?.classList.remove('d-none');
      this._updateJobQueueSummary(this._jobQueueData);
    } catch (err) {
      MC.showToast(`Failed to load job queue: ${err.message}`, 'danger');
      empty?.classList.remove('d-none');
    } finally {
      loading?.classList.add('d-none');
    }
  },

  _renderJobQueue(jobs) {
    const tbody = document.getElementById('jobQueueTbody');
    if (!tbody) return;
    tbody.innerHTML = jobs.map(j => {
      const rowCls =
        j.status === 'Failed'     ? 'table-danger'  :
        j.status === 'Processing' ? 'table-primary'  :
        '';
      const statusBadge = j.extended_status
        ? `<span class="badge bg-${j.status_flag}" title="${MC._escHtml(j.extended_status)}">${MC._escHtml(j.status)}</span>`
        : `<span class="badge bg-${j.status_flag}">${MC._escHtml(j.status)}</span>`;
      const total = j.total_items || 0;
      const processed = j.items_processed || 0;
      const pct = total > 0 ? Math.round(processed / total * 100) : 0;
      const progressCell = total > 0
        ? `<div class="d-flex align-items-center gap-1">
             <span class="small text-nowrap">${processed.toLocaleString()} / ${total.toLocaleString()}</span>
             <div class="progress flex-grow-1" style="height:6px;min-width:60px">
               <div class="progress-bar bg-${j.status_flag}" style="width:${pct}%"></div>
             </div>
           </div>`
        : '<span class="text-muted small">—</span>';
      const duration = this._jobDuration(j.created_date, j.completed_date, j.status);
      return `<tr class="${rowCls}" data-status="${MC._escHtml(j.status)}">
        <td class="fw-semibold small">${MC._escHtml(j.class_name || '—')}</td>
        <td class="small text-muted">${MC._escHtml(j.job_type)}</td>
        <td>${statusBadge}</td>
        <td>${progressCell}</td>
        <td class="text-end small ${j.errors > 0 ? 'text-danger fw-semibold' : ''}">${j.errors}</td>
        <td class="small text-muted">${MC._escHtml(j.created_by)}</td>
        <td class="small text-nowrap">${this._relativeDate(j.created_date)}</td>
        <td class="small text-nowrap">${duration}</td>
      </tr>`;
    }).join('');
  },

  _jobDuration(createdDate, completedDate, status) {
    if (!createdDate) return '—';
    try {
      const start = new Date(createdDate);
      const end   = completedDate ? new Date(completedDate) : new Date();
      const secs  = Math.round((end - start) / 1000);
      if (secs < 60)   return `${secs}s`;
      if (secs < 3600) return `${Math.floor(secs / 60)}m ${secs % 60}s`;
      return `${Math.floor(secs / 3600)}h ${Math.floor((secs % 3600) / 60)}m`;
    } catch (e) {
      return '—';
    }
  },

  _updateJobQueueSummary(jobs) {
    const running = jobs.filter(j => j.status === 'Processing' || j.status === 'Preparing' || j.status === 'Queued').length;
    const failed  = jobs.filter(j => j.status === 'Failed').length;
    const totalEl   = document.getElementById('jqTotal');
    const runningEl = document.getElementById('jqRunning');
    const failedEl  = document.getElementById('jqFailed');
    if (totalEl)   totalEl.textContent   = jobs.length;
    if (runningEl) runningEl.textContent = running;
    if (failedEl)  failedEl.textContent  = failed;
  },

  _applyJobQueueFilter(filter) {
    const tbody = document.getElementById('jobQueueTbody');
    if (!tbody) return;
    tbody.querySelectorAll('tr').forEach(row => {
      const status = row.dataset.status || '';
      row.classList.toggle('d-none', !!(filter && status !== filter));
    });
  },

  _setJobQueueAutoRefresh(enabled) {
    if (this._jobQueueTimer) {
      clearInterval(this._jobQueueTimer);
      this._jobQueueTimer = null;
    }
    if (enabled) {
      this._jobQueueTimer = setInterval(() => this.loadJobQueue(), 10000);
    }
  },

  // ── Login History ───────────────────────────────────────────────────────────

  async loadLoginHistory() {
    const loading = document.getElementById('loginHistoryLoading');
    const empty   = document.getElementById('loginHistoryEmpty');
    const card    = document.getElementById('loginHistoryCard');
    const summary = document.getElementById('loginHistorySummary');
    const searchEl = document.getElementById('loginHistorySearch');
    loading?.classList.remove('d-none');
    empty?.classList.add('d-none');
    card?.classList.add('d-none');
    summary?.classList.add('d-none');
    if (searchEl) searchEl.value = '';
    try {
      const data = await MC.api('/admin/login-history');
      const logins = data?.logins || [];
      if (logins.length === 0) {
        empty?.classList.remove('d-none');
        return;
      }
      this._renderLoginHistory(logins);
      this._updateLoginHistorySummary(data.summary || {});
      card?.classList.remove('d-none');
      summary?.classList.remove('d-none');
    } catch (err) {
      MC.showToast(`Failed to load login history: ${err.message}`, 'danger');
      empty?.classList.remove('d-none');
    } finally {
      loading?.classList.add('d-none');
    }
  },

  _renderLoginHistory(logins) {
    const tbody = document.getElementById('loginHistoryTbody');
    if (!tbody) return;
    tbody.innerHTML = logins.map(l => {
      const rowCls = l.success ? '' : 'table-danger';
      const statusCell = l.success
        ? '<span class="badge badge-green">Success</span>'
        : `<span class="badge badge-red">${MC._escHtml(l.status)}</span>`;
      return `<tr class="${rowCls}">
        <td class="small text-nowrap">${this._relativeDate(l.login_time)}</td>
        <td class="small font-monospace">${MC._escHtml(l.source_ip)}</td>
        <td class="small">${MC._escHtml(l.platform)}</td>
        <td class="small">${MC._escHtml(l.login_type)}</td>
        <td class="small text-muted">${MC._escHtml(l.browser || '—')}</td>
        <td>${statusCell}</td>
      </tr>`;
    }).join('');
  },

  _updateLoginHistorySummary(s) {
    const totalEl  = document.getElementById('lhTotal');
    const failedEl = document.getElementById('lhFailed');
    const ipsEl    = document.getElementById('lhIPs');
    const usersEl  = document.getElementById('lhUsers');
    if (totalEl)  totalEl.textContent  = `${s.total ?? 0} total`;
    if (failedEl) {
      failedEl.textContent = `${s.failed ?? 0} failed`;
      failedEl.className = `badge fs-6 ${(s.failed ?? 0) > 0 ? 'badge-red' : 'bg-secondary'}`;
    }
    if (ipsEl)    ipsEl.textContent    = `${s.unique_ips ?? 0} unique IPs`;
    if (usersEl)  usersEl.textContent  = `${s.unique_users ?? 0} unique users`;
  },

  // ── Generic table filter ────────────────────────────────────────────────────

  _filterTable(tbodyId, query) {
    const q = (query || '').toLowerCase();
    const tbody = document.getElementById(tbodyId);
    if (!tbody) return;
    tbody.querySelectorAll('tr').forEach(row => {
      const text = row.textContent.toLowerCase();
      row.classList.toggle('d-none', !!(q && !text.includes(q)));
    });
  },
};

// ── Custom Metadata ───────────────────────────────────────────────────────────

MC.customMetadata = {
  _loaded: false,

  init() {
    document.getElementById('btnRefreshCmdts')?.addEventListener('click', () => {
      this._loaded = false;
      this.load();
    });
    document.getElementById('tab-custom-metadata')?.addEventListener('shown.bs.tab', () => {
      if (!this._loaded) this.load();
    });
  },

  async load() {
    const loading = document.getElementById('cmdtsLoading');
    const empty   = document.getElementById('cmdtsEmpty');
    const content = document.getElementById('cmdtsContent');
    const list    = document.getElementById('cmdtTypesList');
    loading?.classList.remove('d-none');
    empty?.classList.add('d-none');
    if (content) content.style.display = 'none';
    document.getElementById('cmdtRecordsWrap')?.classList.add('d-none');
    try {
      const types = await MC.api('/admin/custom-metadata');
      if (!types || types.length === 0) {
        empty?.classList.remove('d-none');
        return;
      }
      if (list) {
        list.innerHTML = types.map(t => {
          const name = MC._escHtml(t.QualifiedApiName || t.DeveloperName || '');
          const label = MC._escHtml(t.Label || name);
          return `<button type="button"
                          class="list-group-item list-group-item-action d-flex justify-content-between align-items-center"
                          data-cmdt-name="${name}">
            <span class="fw-semibold small font-monospace">${name}</span>
            <span class="text-muted small">${label}</span>
          </button>`;
        }).join('');
        list.querySelectorAll('[data-cmdt-name]').forEach(btn => {
          btn.addEventListener('click', () => {
            list.querySelectorAll('[data-cmdt-name]').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            this.loadRecords(btn.dataset.cmdtName);
          });
        });
      }
      if (content) content.style.display = '';
      this._loaded = true;
    } catch (err) {
      MC.showToast(`Failed to load Custom Metadata Types: ${err.message}`, 'danger');
      empty?.classList.remove('d-none');
    } finally {
      loading?.classList.add('d-none');
    }
  },

  async loadRecords(typeName) {
    const wrap  = document.getElementById('cmdtRecordsWrap');
    const tbody = document.getElementById('cmdtRecordsTbody');
    const label = document.getElementById('cmdtSelectedType');
    if (label) label.textContent = typeName;
    wrap?.classList.remove('d-none');
    if (tbody) tbody.innerHTML = '<tr><td colspan="2" class="text-muted small text-center py-3">Loading…</td></tr>';
    try {
      const records = await MC.api(`/admin/custom-metadata/${encodeURIComponent(typeName)}/records`);
      if (!records || records.length === 0) {
        if (tbody) tbody.innerHTML = '<tr><td colspan="2" class="text-muted small text-center py-3">No records found.</td></tr>';
        return;
      }
      tbody.innerHTML = records.map(r => `<tr>
        <td class="small font-monospace">${MC._escHtml(r.DeveloperName || '—')}</td>
        <td class="small">${MC._escHtml(r.Label || r.MasterLabel || '—')}</td>
      </tr>`).join('');
    } catch (err) {
      MC.showToast(`Failed to load records for ${typeName}: ${err.message}`, 'danger');
      if (tbody) tbody.innerHTML = '<tr><td colspan="2" class="text-danger small text-center py-3">Error loading records.</td></tr>';
    }
  },
};

// ── Custom Settings ───────────────────────────────────────────────────────────

MC.customSettings = {
  _loaded: false,

  init() {
    document.getElementById('btnRefreshCs')?.addEventListener('click', () => {
      this._loaded = false;
      this.load();
    });
    document.getElementById('tab-custom-settings')?.addEventListener('shown.bs.tab', () => {
      if (!this._loaded) this.load();
    });
  },

  async load() {
    const loading = document.getElementById('csLoading');
    const empty   = document.getElementById('csEmpty');
    const content = document.getElementById('csContent');
    const list    = document.getElementById('csTypesList');
    loading?.classList.remove('d-none');
    empty?.classList.add('d-none');
    if (content) content.style.display = 'none';
    document.getElementById('csRecordsWrap')?.classList.add('d-none');
    try {
      const settings = await MC.api('/admin/custom-settings');
      if (!settings || settings.length === 0) {
        empty?.classList.remove('d-none');
        return;
      }
      if (list) {
        list.innerHTML = settings.map(s => {
          const name  = MC._escHtml(s.QualifiedApiName || '');
          const label = MC._escHtml(s.Label || name);
          return `<button type="button"
                          class="list-group-item list-group-item-action d-flex justify-content-between align-items-center"
                          data-cs-name="${name}">
            <span class="fw-semibold small font-monospace">${name}</span>
            <span class="text-muted small">${label}</span>
          </button>`;
        }).join('');
        list.querySelectorAll('[data-cs-name]').forEach(btn => {
          btn.addEventListener('click', () => {
            list.querySelectorAll('[data-cs-name]').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            this.loadRecords(btn.dataset.csName);
          });
        });
      }
      if (content) content.style.display = '';
      this._loaded = true;
    } catch (err) {
      MC.showToast(`Failed to load Custom Settings: ${err.message}`, 'danger');
      empty?.classList.remove('d-none');
    } finally {
      loading?.classList.add('d-none');
    }
  },

  async loadRecords(settingName) {
    const wrap  = document.getElementById('csRecordsWrap');
    const tbody = document.getElementById('csRecordsTbody');
    const label = document.getElementById('csSelectedType');
    if (label) label.textContent = settingName;
    wrap?.classList.remove('d-none');
    if (tbody) tbody.innerHTML = '<tr><td colspan="3" class="text-muted small text-center py-3">Loading…</td></tr>';
    try {
      const records = await MC.api(`/admin/custom-settings/${encodeURIComponent(settingName)}/records`);
      if (!records || records.length === 0) {
        if (tbody) tbody.innerHTML = '<tr><td colspan="3" class="text-muted small text-center py-3">No records found.</td></tr>';
        return;
      }
      tbody.innerHTML = records.map(r => {
        const ownerBadgeCls =
          r._owner_type === 'Org'     ? 'badge-navy'  :
          r._owner_type === 'Profile' ? 'badge-blue'  :
          'badge-secondary';
        return `<tr>
          <td class="small fw-semibold">${MC._escHtml(r.Name || '—')}</td>
          <td class="small font-monospace text-muted">${MC._escHtml(r.SetupOwnerId || '—')}</td>
          <td><span class="badge ${ownerBadgeCls}">${MC._escHtml(r._owner_type || '—')}</span></td>
        </tr>`;
      }).join('');
    } catch (err) {
      MC.showToast(`Failed to load records for ${settingName}: ${err.message}`, 'danger');
      if (tbody) tbody.innerHTML = '<tr><td colspan="3" class="text-danger small text-center py-3">Error loading records.</td></tr>';
    }
  },
};

// ── Permissions Audit ─────────────────────────────────────────────────────────

MC.permissions = {
  _initialized: false,
  _permSets: [],

  init() {
    if (this._initialized) return;
    this._initialized = true;
    this._wireEvents();
    this.loadPermSets();
  },

  reload() {
    this._initialized = false;
    this.init();
  },

  _wireEvents() {
    document.getElementById('permSetSearch')?.addEventListener('input', e =>
      this._filterList('permSetsList', e.target.value));

    document.getElementById('btnPermUserSearch')?.addEventListener('click', () => {
      const q = document.getElementById('permUserSearch')?.value.trim() || '';
      this.loadUsers(q);
    });
    document.getElementById('permUserSearch')?.addEventListener('keydown', e => {
      if (e.key === 'Enter') document.getElementById('btnPermUserSearch')?.click();
    });

    document.getElementById('btnPermObjectLoad')?.addEventListener('click', () => {
      const obj = document.getElementById('permObjectName')?.value.trim();
      if (obj) this.loadObjectMatrix(obj);
    });

    document.getElementById('btnPermFieldLoad')?.addEventListener('click', () => {
      const obj = document.getElementById('permFieldObject')?.value.trim();
      if (obj) this.loadFieldMatrix(obj);
    });

    document.getElementById('permFieldFilter')?.addEventListener('input', e =>
      this._filterTable('permFieldTbody', e.target.value));
  },

  // ── Permission Sets ──────────────────────────────────────────────────────

  async loadPermSets() {
    const loading = document.getElementById('permSetsLoading');
    const empty   = document.getElementById('permSetsEmpty');
    const content = document.getElementById('permSetsContent');
    try {
      this._permSets = await MC.api('/admin/permissions/sets') || [];
      loading?.classList.add('d-none');
      if (this._permSets.length === 0) { empty?.classList.remove('d-none'); return; }
      content?.classList.remove('d-none');
      this._renderPermSetList(this._permSets);
    } catch (err) {
      loading?.classList.add('d-none');
      MC.showToast('Failed to load permission sets: ' + err.message, 'danger');
    }
  },

  _renderPermSetList(sets) {
    const list = document.getElementById('permSetsList');
    if (!list) return;
    list.innerHTML = sets.map(ps =>
      `<button class="list-group-item list-group-item-action d-flex justify-content-between align-items-center py-2"
               data-pset-id="${MC._escHtml(ps.id)}" onclick="MC.permissions.loadPermSetDetail('${MC._escHtml(ps.id)}')">
        <span class="small fw-semibold">${MC._escHtml(ps.label || ps.name)}</span>
        <span class="badge ${ps.user_count > 0 ? 'badge-navy' : 'badge-secondary'} ms-2">${ps.user_count}</span>
       </button>`
    ).join('');
  },

  async loadPermSetDetail(psetId) {
    // Highlight selected
    document.querySelectorAll('#permSetsList button').forEach(b =>
      b.classList.toggle('active', b.dataset.psetId === psetId));

    const detail = document.getElementById('permSetDetail');
    if (!detail) return;
    detail.innerHTML = '<div class="text-center py-4"><div class="spinner-border text-warning"></div></div>';
    try {
      const d = await MC.api(`/admin/permissions/set/${encodeURIComponent(psetId)}`);
      const sfLink = MC.sfLink(psetId, 'PermissionSet');
      const linkHtml = sfLink ? `<a href="${sfLink}" target="_blank" class="ms-2 small text-muted">↗ Open in SF</a>` : '';
      detail.innerHTML = `
        <div class="card shadow-sm">
          <div class="card-header py-2">
            <h6 class="fw-semibold mb-0" style="color:var(--doane-navy);">${MC._escHtml(d.label)}${linkHtml}</h6>
            ${d.description ? `<small class="text-muted">${MC._escHtml(d.description)}</small>` : ''}
          </div>
          <div class="card-body p-0">
            <ul class="nav nav-tabs px-3 pt-2" id="psetDetailTabs">
              <li class="nav-item"><button class="nav-link active" data-bs-toggle="tab" data-bs-target="#pset-users-pane">Users (${d.users.length})</button></li>
              <li class="nav-item"><button class="nav-link" data-bs-toggle="tab" data-bs-target="#pset-objs-pane">Object Perms (${d.object_permissions.length})</button></li>
              <li class="nav-item"><button class="nav-link" data-bs-toggle="tab" data-bs-target="#pset-fields-pane">Field Perms (${d.field_permissions.length})</button></li>
            </ul>
            <div class="tab-content p-2">
              <div class="tab-pane fade show active" id="pset-users-pane">
                ${this._renderUserMini(d.users)}
              </div>
              <div class="tab-pane fade" id="pset-objs-pane">
                ${this._renderObjPermsTable(d.object_permissions)}
              </div>
              <div class="tab-pane fade" id="pset-fields-pane">
                ${this._renderFieldPermsTable(d.field_permissions)}
              </div>
            </div>
          </div>
        </div>`;
    } catch (err) {
      detail.innerHTML = `<div class="alert alert-danger">${MC._escHtml(err.message)}</div>`;
    }
  },

  _renderUserMini(users) {
    if (!users.length) return '<p class="text-muted small py-3 text-center">No users assigned.</p>';
    return `<table class="table table-sm table-hover mb-0">
      <thead class="table-light"><tr><th>Name</th><th>Username</th></tr></thead>
      <tbody>${users.map(u => {
        const link = MC.sfLink(u.id, 'User');
        const nameCell = link ? `<a href="${link}" target="_blank">${MC._escHtml(u.name)}</a>` : MC._escHtml(u.name);
        return `<tr><td class="small">${nameCell}</td><td class="small text-muted">${MC._escHtml(u.username)}</td></tr>`;
      }).join('')}</tbody></table>`;
  },

  _renderObjPermsTable(rows) {
    if (!rows.length) return '<p class="text-muted small py-3 text-center">No object permissions.</p>';
    const check = v => v ? '<span class="text-success fw-bold">✓</span>' : '<span class="text-muted">—</span>';
    return `<table class="table table-sm table-hover mb-0">
      <thead class="table-light"><tr><th>Object</th><th class="text-center">R</th><th class="text-center">C</th><th class="text-center">E</th><th class="text-center">D</th><th class="text-center">VA</th><th class="text-center">MA</th></tr></thead>
      <tbody>${rows.map(r =>
        `<tr><td class="small font-monospace">${MC._escHtml(r.object)}</td>
         <td class="text-center">${check(r.read)}</td><td class="text-center">${check(r.create)}</td>
         <td class="text-center">${check(r.edit)}</td><td class="text-center">${check(r.delete)}</td>
         <td class="text-center">${check(r.view_all)}</td><td class="text-center">${check(r.modify_all)}</td></tr>`
      ).join('')}</tbody></table>`;
  },

  _renderFieldPermsTable(rows) {
    if (!rows.length) return '<p class="text-muted small py-3 text-center">No field permissions.</p>';
    const check = v => v ? '<span class="text-success fw-bold">✓</span>' : '<span class="text-muted">—</span>';
    return `<table class="table table-sm table-hover mb-0">
      <thead class="table-light"><tr><th>Object</th><th>Field</th><th class="text-center">Read</th><th class="text-center">Edit</th></tr></thead>
      <tbody>${rows.map(r =>
        `<tr><td class="small font-monospace">${MC._escHtml(r.object)}</td>
         <td class="small font-monospace">${MC._escHtml(r.field)}</td>
         <td class="text-center">${check(r.read)}</td><td class="text-center">${check(r.edit)}</td></tr>`
      ).join('')}</tbody></table>`;
  },

  _filterList(listId, query) {
    const q = (query || '').toLowerCase();
    document.querySelectorAll(`#${listId} button`).forEach(btn => {
      const text = btn.textContent.toLowerCase();
      btn.classList.toggle('d-none', !!q && !text.includes(q));
    });
  },

  // ── By User ──────────────────────────────────────────────────────────────

  async loadUsers(search = '') {
    const loading = document.getElementById('permUsersLoading');
    const list    = document.getElementById('permUsersList');
    loading?.classList.remove('d-none');
    if (list) list.innerHTML = '';
    try {
      const users = await MC.api(`/admin/permissions/users?q=${encodeURIComponent(search)}`) || [];
      loading?.classList.add('d-none');
      if (!users.length) { if (list) list.innerHTML = '<div class="text-muted small p-2">No users found.</div>'; return; }
      list.innerHTML = users.map(u =>
        `<button class="list-group-item list-group-item-action py-2"
                 data-user-id="${MC._escHtml(u.id)}" onclick="MC.permissions.loadUserDetail('${MC._escHtml(u.id)}')">
          <div class="small fw-semibold">${MC._escHtml(u.name)}</div>
          <div class="small text-muted">${MC._escHtml(u.username)}</div>
         </button>`
      ).join('');
    } catch (err) {
      loading?.classList.add('d-none');
      MC.showToast('User search failed: ' + err.message, 'danger');
    }
  },

  async loadUserDetail(userId) {
    document.querySelectorAll('#permUsersList button').forEach(b =>
      b.classList.toggle('active', b.dataset.userId === userId));

    const detail = document.getElementById('permUserDetail');
    if (!detail) return;
    detail.innerHTML = '<div class="text-center py-4"><div class="spinner-border text-warning"></div></div>';
    try {
      const d = await MC.api(`/admin/permissions/user/${encodeURIComponent(userId)}`);
      const sfLink = MC.sfLink(userId, 'User');
      const nameLink = sfLink ? `<a href="${sfLink}" target="_blank">${MC._escHtml(d.name)}</a>` : MC._escHtml(d.name);
      const check = v => v ? '<span class="text-success fw-bold">✓</span>' : '<span class="text-muted">—</span>';

      const psetRows = d.permission_sets.map(ps => {
        const psLink = MC.sfLink(ps.id, 'PermissionSet');
        const cell = psLink ? `<a href="${psLink}" target="_blank">${MC._escHtml(ps.label)}</a>` : MC._escHtml(ps.label);
        return `<tr><td class="small">${cell}</td><td class="small text-muted">${MC._escHtml(ps.name)}</td></tr>`;
      }).join('') || '<tr><td colspan="2" class="text-muted small">None</td></tr>';

      const objRows = d.object_permissions.map(o =>
        `<tr><td class="small font-monospace">${MC._escHtml(o.object)}</td>
         <td class="text-center">${check(o.read)}</td><td class="text-center">${check(o.create)}</td>
         <td class="text-center">${check(o.edit)}</td><td class="text-center">${check(o.delete)}</td>
         <td class="text-center">${check(o.view_all)}</td><td class="text-center">${check(o.modify_all)}</td></tr>`
      ).join('') || '<tr><td colspan="7" class="text-muted small text-center">No object permissions via perm sets</td></tr>';

      detail.innerHTML = `
        <div class="card shadow-sm">
          <div class="card-header py-2">
            <h6 class="fw-semibold mb-0" style="color:var(--doane-navy);">${nameLink}</h6>
            <small class="text-muted">${MC._escHtml(d.username)} &nbsp;·&nbsp; Profile: ${MC._escHtml(d.profile_name)} &nbsp;·&nbsp; License: ${MC._escHtml(d.license || '—')}</small>
          </div>
          <div class="card-body p-0">
            <ul class="nav nav-tabs px-3 pt-2">
              <li class="nav-item"><button class="nav-link active" data-bs-toggle="tab" data-bs-target="#ud-psets-pane">Perm Sets (${d.permission_sets.length})</button></li>
              <li class="nav-item"><button class="nav-link" data-bs-toggle="tab" data-bs-target="#ud-objs-pane">Object Access (${d.object_permissions.length})</button></li>
            </ul>
            <div class="tab-content p-2">
              <div class="tab-pane fade show active" id="ud-psets-pane">
                <table class="table table-sm table-hover mb-0">
                  <thead class="table-light"><tr><th>Label</th><th>API Name</th></tr></thead>
                  <tbody>${psetRows}</tbody>
                </table>
              </div>
              <div class="tab-pane fade" id="ud-objs-pane">
                <table class="table table-sm table-hover mb-0">
                  <thead class="table-light"><tr><th>Object</th><th class="text-center">R</th><th class="text-center">C</th><th class="text-center">E</th><th class="text-center">D</th><th class="text-center">VA</th><th class="text-center">MA</th></tr></thead>
                  <tbody>${objRows}</tbody>
                </table>
              </div>
            </div>
          </div>
        </div>`;
    } catch (err) {
      detail.innerHTML = `<div class="alert alert-danger">${MC._escHtml(err.message)}</div>`;
    }
  },

  // ── Object Matrix ────────────────────────────────────────────────────────

  async loadObjectMatrix(objectName) {
    const loading = document.getElementById('permObjectLoading');
    const empty   = document.getElementById('permObjectEmpty');
    const card    = document.getElementById('permObjectCard');
    loading?.classList.remove('d-none');
    empty?.classList.add('d-none');
    card?.classList.add('d-none');
    try {
      const d = await MC.api(`/admin/permissions/object-matrix?object=${encodeURIComponent(objectName)}`);
      loading?.classList.add('d-none');
      if (!d.rows.length) { empty?.classList.remove('d-none'); return; }
      const check = v => v ? '<span class="text-success fw-bold">✓</span>' : '<span class="text-muted">—</span>';
      const tbody = document.getElementById('permObjectTbody');
      if (tbody) {
        tbody.innerHTML = d.rows.map(r => {
          const link = MC.sfLink(r.pset_id, 'PermissionSet');
          const cell = link ? `<a href="${link}" target="_blank">${MC._escHtml(r.pset_label)}</a>` : MC._escHtml(r.pset_label);
          return `<tr><td class="small">${cell}</td>
            <td class="text-center">${check(r.read)}</td><td class="text-center">${check(r.create)}</td>
            <td class="text-center">${check(r.edit)}</td><td class="text-center">${check(r.delete)}</td>
            <td class="text-center">${check(r.view_all)}</td><td class="text-center">${check(r.modify_all)}</td></tr>`;
        }).join('');
      }
      card?.classList.remove('d-none');
    } catch (err) {
      loading?.classList.add('d-none');
      MC.showToast('Failed to load object matrix: ' + err.message, 'danger');
    }
  },

  // ── Field Coverage ───────────────────────────────────────────────────────

  async loadFieldMatrix(objectName) {
    const loading = document.getElementById('permFieldLoading');
    const empty   = document.getElementById('permFieldEmpty');
    const content = document.getElementById('permFieldContent');
    loading?.classList.remove('d-none');
    empty?.classList.add('d-none');
    content?.classList.add('d-none');
    try {
      const d = await MC.api(`/admin/permissions/field-matrix?object=${encodeURIComponent(objectName)}`);
      loading?.classList.add('d-none');
      if (!d.fields.length) { empty?.classList.remove('d-none'); return; }
      const check = v => v ? '<span class="text-success fw-bold">✓</span>' : '<span class="text-muted">—</span>';
      const tbody = document.getElementById('permFieldTbody');
      if (tbody) {
        tbody.innerHTML = d.fields.flatMap(f =>
          f.access.map((a, i) => {
            const link = MC.sfLink(a.pset_id, 'PermissionSet');
            const cell = link ? `<a href="${link}" target="_blank">${MC._escHtml(a.pset_label)}</a>` : MC._escHtml(a.pset_label);
            return `<tr data-field="${MC._escHtml(f.field.toLowerCase())}">
              ${i === 0 ? `<td class="small font-monospace fw-semibold" rowspan="${f.access.length}">${MC._escHtml(f.field)}</td>` : ''}
              <td class="small">${cell}</td>
              <td class="text-center">${check(a.read)}</td>
              <td class="text-center">${check(a.edit)}</td>
            </tr>`;
          })
        ).join('');
      }
      content?.classList.remove('d-none');
    } catch (err) {
      loading?.classList.add('d-none');
      MC.showToast('Failed to load field coverage: ' + err.message, 'danger');
    }
  },

  _filterTable(tbodyId, query) {
    const q = (query || '').toLowerCase();
    document.querySelectorAll(`#${tbodyId} tr`).forEach(row => {
      row.classList.toggle('d-none', !!q && !row.textContent.toLowerCase().includes(q));
    });
  },
};

// ── Automation & Sharing ──────────────────────────────────────────────────────

MC.automation = {
  _initialized: false,

  init() {
    if (this._initialized) return;
    this._initialized = true;
    this._wireFilters();
    this.loadValidationRules();
    document.getElementById('auto-tab-flows')?.addEventListener('shown.bs.tab', () => this.loadFlows());
    document.getElementById('auto-tab-triggers')?.addEventListener('shown.bs.tab', () => this.loadTriggers());
    document.getElementById('auto-tab-sharing')?.addEventListener('shown.bs.tab', () => this.loadSharing());
  },

  reload() {
    this._initialized = false;
    this._loaded = {};
    this.init();
  },

  _loaded: {},

  _wireFilters() {
    const f = (inputId, tbodyId) =>
      document.getElementById(inputId)?.addEventListener('input', e =>
        MC.permissions._filterTable(tbodyId, e.target.value));
    f('autoVrFilter', 'autoVrTbody');
    f('autoFlowFilter', 'autoFlowTbody');
    f('autoTriggerFilter', 'autoTriggerTbody');
    f('autoSharingFilter', 'autoSharingTbody');
  },

  _statusBadge(status) {
    const s = (status || '').toLowerCase();
    const cls = (s === 'active') ? 'badge-green'
              : (s === 'inactive' || s === 'obsolete' || s === 'draft') ? 'badge-secondary'
              : 'badge-amber';
    return `<span class="badge ${cls}">${MC._escHtml(status || '—')}</span>`;
  },

  // ── Validation Rules ─────────────────────────────────────────────────────

  async loadValidationRules() {
    if (this._loaded.vr) return;
    const loading = document.getElementById('autoVrLoading');
    const empty   = document.getElementById('autoVrEmpty');
    const card    = document.getElementById('autoVrCard');
    loading?.classList.remove('d-none');
    empty?.classList.add('d-none');
    card?.classList.add('d-none');
    try {
      const rules = await MC.api('/admin/automation/validation-rules') || [];
      loading?.classList.add('d-none');
      this._loaded.vr = true;
      if (!rules.length) { empty?.classList.remove('d-none'); return; }
      const tbody = document.getElementById('autoVrTbody');
      if (tbody) {
        tbody.innerHTML = rules.map(r =>
          `<tr>
            <td class="small font-monospace fw-semibold">${MC._escHtml(r.object)}</td>
            <td class="small">${MC._escHtml(r.name)}</td>
            <td>${this._statusBadge(r.active ? 'Active' : 'Inactive')}</td>
            <td class="small font-monospace text-muted">${MC._escHtml(r.error_field || '—')}</td>
            <td class="small">${MC._escHtml(r.error_message)}</td>
          </tr>`
        ).join('');
      }
      card?.classList.remove('d-none');
    } catch (err) {
      loading?.classList.add('d-none');
      MC.showToast('Failed to load validation rules: ' + err.message, 'danger');
    }
  },

  // ── Flows ────────────────────────────────────────────────────────────────

  async loadFlows() {
    if (this._loaded.flows) return;
    const loading = document.getElementById('autoFlowLoading');
    const empty   = document.getElementById('autoFlowEmpty');
    const card    = document.getElementById('autoFlowCard');
    loading?.classList.remove('d-none');
    empty?.classList.add('d-none');
    card?.classList.add('d-none');
    try {
      const flows = await MC.api('/admin/automation/flows') || [];
      loading?.classList.add('d-none');
      this._loaded.flows = true;
      if (!flows.length) { empty?.classList.remove('d-none'); return; }
      const tbody = document.getElementById('autoFlowTbody');
      if (tbody) {
        tbody.innerHTML = flows.map(f =>
          `<tr>
            <td class="small fw-semibold">${MC._escHtml(f.label)}</td>
            <td><span class="badge badge-navy">${MC._escHtml(f.type || '—')}</span></td>
            <td>${this._statusBadge(f.status)}</td>
            <td class="small text-muted">${MC._escHtml(f.description || '—')}</td>
            <td class="small text-nowrap">${MC._fmtTime(f.last_modified)}</td>
          </tr>`
        ).join('');
      }
      card?.classList.remove('d-none');
    } catch (err) {
      loading?.classList.add('d-none');
      MC.showToast('Failed to load flows: ' + err.message, 'danger');
    }
  },

  // ── Apex Triggers ────────────────────────────────────────────────────────

  async loadTriggers() {
    if (this._loaded.triggers) return;
    const loading = document.getElementById('autoTriggerLoading');
    const empty   = document.getElementById('autoTriggerEmpty');
    const card    = document.getElementById('autoTriggerCard');
    loading?.classList.remove('d-none');
    empty?.classList.add('d-none');
    card?.classList.add('d-none');
    try {
      const triggers = await MC.api('/admin/automation/triggers') || [];
      loading?.classList.add('d-none');
      this._loaded.triggers = true;
      if (!triggers.length) { empty?.classList.remove('d-none'); return; }
      const tbody = document.getElementById('autoTriggerTbody');
      if (tbody) {
        tbody.innerHTML = triggers.map(t =>
          `<tr>
            <td class="small font-monospace fw-semibold">${MC._escHtml(t.object || '—')}</td>
            <td class="small">${MC._escHtml(t.name)}</td>
            <td>${this._statusBadge(t.status)}</td>
            <td class="small text-end">${MC._escHtml(t.api_version)}</td>
            <td class="small text-end text-muted">${(t.length || 0).toLocaleString()}</td>
          </tr>`
        ).join('');
      }
      card?.classList.remove('d-none');
    } catch (err) {
      loading?.classList.add('d-none');
      MC.showToast('Failed to load triggers: ' + err.message, 'danger');
    }
  },

  // ── Sharing Model ────────────────────────────────────────────────────────

  async loadSharing() {
    if (this._loaded.sharing) return;
    const loading = document.getElementById('autoSharingLoading');
    const empty   = document.getElementById('autoSharingEmpty');
    const card    = document.getElementById('autoSharingCard');
    loading?.classList.remove('d-none');
    empty?.classList.add('d-none');
    card?.classList.add('d-none');
    try {
      const rows = await MC.api('/admin/automation/sharing-model') || [];
      loading?.classList.add('d-none');
      this._loaded.sharing = true;
      if (!rows.length) { empty?.classList.remove('d-none'); return; }
      const accessBadge = (val, label) => {
        const v = (val || '').toLowerCase();
        const cls = v === 'private' ? 'badge-red'
                  : v.startsWith('read') && v !== 'readwrite' && v !== 'readwritetransfer' ? 'badge-amber'
                  : v.startsWith('controlledby') ? 'badge-secondary'
                  : 'badge-green';
        return `<span class="badge ${cls}">${MC._escHtml(label || val || '—')}</span>`;
      };
      const tbody = document.getElementById('autoSharingTbody');
      if (tbody) {
        tbody.innerHTML = rows.map(r =>
          `<tr>
            <td class="small fw-semibold">${MC._escHtml(r.label)}</td>
            <td class="small font-monospace text-muted">${MC._escHtml(r.object)}</td>
            <td>${accessBadge(r.internal, r.internal_label)}</td>
            <td>${accessBadge(r.external, r.external_label)}</td>
          </tr>`
        ).join('');
      }
      card?.classList.remove('d-none');
    } catch (err) {
      loading?.classList.add('d-none');
      MC.showToast('Failed to load sharing model: ' + err.message, 'danger');
    }
  },
};
