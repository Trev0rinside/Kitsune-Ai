/**
 * Reverse-Guardrail — Interactive Front-End Controller
 * Supports Phase 1 (Reconstruction) & Phase 2 (Vulnerability Assessment & Hardening Report)
 */

document.addEventListener('DOMContentLoaded', () => {
  // --- DOM Elements ---
  const authCheckbox = document.getElementById('authCheckbox');
  const engagementIdInput = document.getElementById('engagementId');
  const targetUrlInput = document.getElementById('targetUrl');
  const cookiesInput = document.getElementById('cookiesInput');
  const inputSelectorInput = document.getElementById('inputSelector');
  const submitSelectorInput = document.getElementById('submitSelector');
  const responseSelectorInput = document.getElementById('responseSelector');
  const headlessCheckbox = document.getElementById('headlessCheckbox');
  const httpAuthHeaderInput = document.getElementById('httpAuthHeader');

  const maxRoundsInput = document.getElementById('maxRounds');
  const attemptsPerRoundInput = document.getElementById('attemptsPerRound');
  const confThresholdInput = document.getElementById('confThreshold');

  const btnLaunch = document.getElementById('btnLaunch');
  const btnLaunchText = document.getElementById('btnLaunchText');
  const btnCopyPrompt = document.getElementById('btnCopyPrompt');
  const btnCopyHardenedPrompt = document.getElementById('btnCopyHardenedPrompt');
  const btnExampleCookieJson = document.getElementById('btnExampleCookieJson');
  const btnExampleCookieHeader = document.getElementById('btnExampleCookieHeader');

  const modeTabs = document.querySelectorAll('.mode-tab');
  const browserOptions = document.getElementById('browserOptions');
  const httpOptions = document.getElementById('httpOptions');
  const urlGroup = document.getElementById('urlGroup');

  const metricStatus = document.getElementById('metricStatus');
  const metricRound = document.getElementById('metricRound');
  const metricConfidence = document.getElementById('metricConfidence');
  const confProgressBar = document.getElementById('confProgressBar');
  const metricFragments = document.getElementById('metricFragments');

  const reconstructedPromptContent = document.getElementById('reconstructedPromptContent');
  const sectionsContainer = document.getElementById('sectionsContainer');
  const gapsList = document.getElementById('gapsList');
  const fragmentsTableBody = document.getElementById('fragmentsTableBody');
  const fragCategoryFilter = document.getElementById('fragCategoryFilter');
  const logConsole = document.getElementById('logConsole');

  // Phase 2 Elements
  const vulnScoreDelimiter = document.getElementById('vulnScoreDelimiter');
  const vulnScoreAmbiguity = document.getElementById('vulnScoreAmbiguity');
  const vulnScoreSecret = document.getElementById('vulnScoreSecret');
  const vulnScoreOverall = document.getElementById('vulnScoreOverall');
  const vulnListContainer = document.getElementById('vulnListContainer');

  const scoreBeforeHardening = document.getElementById('scoreBeforeHardening');
  const scoreAfterHardening = document.getElementById('scoreAfterHardening');
  const hardeningExecSummary = document.getElementById('hardeningExecSummary');
  const remediationsContainer = document.getElementById('remediationsContainer');
  const hardenedPromptContent = document.getElementById('hardenedPromptContent');
  const archRecsList = document.getElementById('archRecsList');

  let currentTargetMode = 'browser'; // 'browser' | 'http' | 'mock'
  let activeRunId = null;
  let allExtractedFragments = [];

  // --- Mode Tabs Switching ---
  modeTabs.forEach(tab => {
    tab.addEventListener('click', () => {
      modeTabs.forEach(t => t.classList.remove('active'));
      tab.classList.add('active');
      currentTargetMode = tab.dataset.mode;

      if (currentTargetMode === 'browser') {
        browserOptions.classList.remove('hidden');
        httpOptions.classList.add('hidden');
        urlGroup.style.display = 'block';
        targetUrlInput.placeholder = 'https://chat.target.internal';
        if (targetUrlInput.value.includes('localhost:8000') || targetUrlInput.value.includes('localhost:8888')) {
          targetUrlInput.value = 'https://chat.target.internal';
        }
      } else if (currentTargetMode === 'http') {
        browserOptions.classList.add('hidden');
        httpOptions.classList.remove('hidden');
        urlGroup.style.display = 'block';
        targetUrlInput.placeholder = 'http://localhost:8888/api/chat';
      } else if (currentTargetMode === 'mock') {
        browserOptions.classList.add('hidden');
        httpOptions.classList.add('hidden');
        urlGroup.style.display = 'none';
      }
      appendLog(`[Config] Modalità target cambiata in: ${currentTargetMode.toUpperCase()}`, 'info');
    });
  });

  // --- Cookie Helper Buttons ---
  btnExampleCookieJson.addEventListener('click', () => {
    cookiesInput.value = JSON.stringify([
      {
        name: "session_id",
        value: "tok_secure_jwt_session_88129",
        domain: "chat.target.internal",
        path: "/"
      },
      {
        name: "auth_token",
        value: "bearer_secret_user_99",
        domain: "chat.target.internal",
        path: "/"
      }
    ], null, 2);
    appendLog('[Cookie] Inserito esempio cookie JSON.', 'info');
  });

  btnExampleCookieHeader.addEventListener('click', () => {
    cookiesInput.value = 'session_id=tok_secure_jwt_session_88129; auth_token=bearer_secret_user_99; theme=dark';
    appendLog('[Cookie] Inserito esempio cookie Header string.', 'info');
  });

  // --- Navigation Tabs ---
  const tabButtons = document.querySelectorAll('.tab-btn');
  const tabContents = document.querySelectorAll('.tab-content');

  tabButtons.forEach(btn => {
    btn.addEventListener('click', () => {
      tabButtons.forEach(b => b.classList.remove('active'));
      tabContents.forEach(c => c.classList.remove('active'));

      btn.classList.add('active');
      const targetTab = document.getElementById(btn.dataset.tab);
      if (targetTab) targetTab.classList.add('active');

      // Dynamic load if clicking phase 2 tabs
      if (activeRunId && (btn.dataset.tab === 'vulnTab' || btn.dataset.tab === 'hardeningTab')) {
        fetchPhase2Reports(activeRunId);
      }
    });
  });

  // --- Copy Prompt Action ---
  btnCopyPrompt.addEventListener('click', () => {
    const text = reconstructedPromptContent.innerText;
    navigator.clipboard.writeText(text).then(() => {
      const original = btnCopyPrompt.innerText;
      btnCopyPrompt.innerText = '✅ Copiato!';
      setTimeout(() => { btnCopyPrompt.innerText = original; }, 2000);
    });
  });

  // --- Copy Hardened Prompt Action ---
  btnCopyHardenedPrompt.addEventListener('click', () => {
    const text = hardenedPromptContent.innerText;
    navigator.clipboard.writeText(text).then(() => {
      const original = btnCopyHardenedPrompt.innerText;
      btnCopyHardenedPrompt.innerText = '✅ Copiato!';
      setTimeout(() => { btnCopyHardenedPrompt.innerText = original; }, 2000);
    });
  });

  // --- Category Filter on Fragments Table ---
  fragCategoryFilter.addEventListener('change', () => {
    renderFragmentsTable(allExtractedFragments);
  });

  // --- Launch Assessment Action ---
  btnLaunch.addEventListener('click', async () => {
    const isAuthorized = authCheckbox.checked;
    const engagementId = engagementIdInput.value.trim();

    if (!isAuthorized) {
      appendLog('[KILL-SWITCH] Errore: target.authorized deve essere abilitato!', 'error');
      alert('KILL-SWITCH ACTIVATED: Devi confermare l\'autorizzazione formale per eseguire il test.');
      return;
    }

    if (!engagementId) {
      appendLog('[KILL-SWITCH] Errore: engagement_id obbligatorio.', 'error');
      alert('KILL-SWITCH ACTIVATED: Inserisci un Engagement ID valido.');
      return;
    }

    // Build Payload
    const targetConfig = {
      authorized: isAuthorized,
      engagement_id: engagementId,
      target_name: currentTargetMode === 'mock' ? 'Mock NexusTech Guardrail' : 'Target System SUT',
      target_url: currentTargetMode === 'mock' ? null : (targetUrlInput.value.trim() || null),
      use_browser: currentTargetMode === 'browser',
      cookies: currentTargetMode === 'browser' ? (cookiesInput.value.trim() || null) : null,
      input_selector: inputSelectorInput.value.trim() || null,
      submit_selector: submitSelectorInput.value.trim() || null,
      response_selector: responseSelectorInput.value.trim() || null,
      headless: headlessCheckbox.checked,
      custom_headers: {}
    };

    if (currentTargetMode === 'http' && httpAuthHeaderInput.value.trim()) {
      targetConfig.custom_headers['Authorization'] = httpAuthHeaderInput.value.trim();
    }

    const payload = {
      config: {
        target: targetConfig,
        max_rounds: parseInt(maxRoundsInput.value) || 4,
        attempts_per_round: parseInt(attemptsPerRoundInput.value) || 4,
        confidence_threshold: parseFloat(confThresholdInput.value) || 0.85,
        models: {
          tester: "deepseek-v4-flash",
          inspectioner: "deepseek-v4-flash",
          reverse_engineer: "deepseek-v4-flash",
          vulnerability_analyzer: "deepseek-v4-flash",
          hardening_reporter: "deepseek-v4-flash"
        }
      }
    };

    // UI Loading State
    btnLaunch.disabled = true;
    btnLaunchText.innerText = 'Assessment in Esecuzione...';
    metricStatus.innerText = 'RUNNING';
    metricStatus.className = 'metric-value status-running';
    appendLog(`[Pipeline] Avvio Reverse-Guardrail per Engagement ${engagementId}...`, 'scope');

    try {
      const resp = await fetch('/api/v1/pipeline/start', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });

      if (!resp.ok) {
        const errData = await resp.json();
        throw new Error(errData.detail || `HTTP Error ${resp.status}`);
      }

      const data = await resp.json();
      activeRunId = data.run_id;
      appendLog(`[Pipeline] Assessment completato! Run ID: ${activeRunId}`, 'success');

      // Update UI with Results
      updateDashboard(data);

      // Fetch Full Report & Fragments & Phase 2 Assessments
      await fetchFullReportAndFragments(activeRunId);
      await fetchPhase2Reports(activeRunId);

    } catch (err) {
      appendLog(`[Pipeline Error] ${err.message}`, 'error');
      metricStatus.innerText = 'FAILED / BLOCKED';
      metricStatus.className = 'metric-value status-blocked';
    } finally {
      btnLaunch.disabled = false;
      btnLaunchText.innerText = 'Avvia Reverse-Guardrail Assessment';
    }
  });

  // --- Update Dashboard with Status Response ---
  function updateDashboard(data) {
    metricStatus.innerText = data.status.toUpperCase();
    metricStatus.className = data.status === 'completed' ? 'metric-value status-completed' : 'metric-value status-running';
    metricRound.innerText = `${data.current_round} / ${data.max_rounds}`;
    
    const confPct = (data.latest_confidence * 100).toFixed(1);
    metricConfidence.innerText = `${confPct}%`;
    confProgressBar.style.width = `${confPct}%`;
    metricFragments.innerText = data.total_fragments_count;

    // Render Gaps
    gapsList.innerHTML = '';
    if (data.gaps && data.gaps.length > 0) {
      data.gaps.forEach(g => {
        const li = document.createElement('li');
        li.innerText = g;
        gapsList.appendChild(li);
      });
    } else {
      gapsList.innerHTML = '<li>Nessun gap residuo identificato. Prompt interamente ricostruito!</li>';
    }
  }

  // --- Fetch Report and Fragments ---
  async function fetchFullReportAndFragments(runId) {
    try {
      // 1. Fetch Report
      const repResp = await fetch(`/api/v1/pipeline/${runId}/report`);
      if (repResp.ok) {
        const report = await repResp.json();
        reconstructedPromptContent.innerText = report.reconstructed_prompt;

        // Render Covered Sections
        sectionsContainer.innerHTML = '';
        if (report.covered_sections && report.covered_sections.length > 0) {
          report.covered_sections.forEach(sec => {
            const card = document.createElement('div');
            card.className = 'section-card';
            card.innerHTML = `
              <div class="section-card-header">
                <span class="section-card-title">${escapeHtml(sec.section_name)}</span>
                <span class="section-confidence-tag">${(sec.confidence * 100).toFixed(0)}% Conf.</span>
              </div>
              <div class="section-card-content">${escapeHtml(sec.inferred_content)}</div>
            `;
            sectionsContainer.appendChild(card);
          });
        }
      }

      // 2. Fetch Extracted Fragments
      const fragsResp = await fetch(`/api/v1/pipeline/${runId}/fragments`);
      if (fragsResp.ok) {
        allExtractedFragments = await fragsResp.json();
        renderFragmentsTable(allExtractedFragments);
      }

    } catch (err) {
      appendLog(`[Data Sync Error] ${err.message}`, 'warning');
    }
  }

  // --- Fetch Phase 2 Reports (Vulnerabilities & Hardening) ---
  async function fetchPhase2Reports(runId) {
    try {
      // 1. Fetch Vulnerability Report
      const vulnResp = await fetch(`/api/v1/pipeline/${runId}/vulnerabilities`);
      if (vulnResp.ok) {
        const vData = await vulnResp.json();
        renderVulnerabilityReport(vData);
        appendLog(`[Threat Modeling] Individuate ${vData.vulnerabilities?.length || 0} criticità nel prompt.`, 'warning');
      }

      // 2. Fetch Hardening Report
      const hardResp = await fetch(`/api/v1/pipeline/${runId}/hardening`);
      if (hardResp.ok) {
        const hData = await hardResp.json();
        renderHardeningReport(hData);
        appendLog(`[Hardening] Report difensivo sintetizzato (Robustezza: ${(hData.after_hardening_score * 100).toFixed(0)}%).`, 'success');
      }
    } catch (err) {
      appendLog(`[Phase 2 Sync Error] ${err.message}`, 'warning');
    }
  }

  // --- Render Vulnerability Report ---
  function renderVulnerabilityReport(vData) {
    vulnScoreDelimiter.innerText = `${(vData.delimiter_isolation_score * 100).toFixed(0)}%`;
    vulnScoreAmbiguity.innerText = `${(vData.directive_ambiguity_index * 100).toFixed(0)}%`;
    vulnScoreSecret.innerText = `${(vData.secret_exposure_risk * 100).toFixed(0)}%`;

    const sev = (vData.overall_risk_rating || 'info').toLowerCase();
    vulnScoreOverall.innerText = sev.toUpperCase();
    vulnScoreOverall.className = `sev-badge sev-${sev}`;

    vulnListContainer.innerHTML = '';
    if (!vData.vulnerabilities || vData.vulnerabilities.length === 0) {
      vulnListContainer.innerHTML = '<div class="empty-state">Nessuna vulnerabilità critica identificata nel System Prompt.</div>';
      return;
    }

    vData.vulnerabilities.forEach(v => {
      const vSev = (v.severity || 'medium').toLowerCase();
      const card = document.createElement('div');
      card.className = 'vuln-card';
      card.innerHTML = `
        <div class="vuln-card-header">
          <div class="vuln-card-left">
            <span class="sev-badge sev-${vSev}">${vSev.toUpperCase()}</span>
            <span class="vuln-title">${escapeHtml(v.title)}</span>
          </div>
          <span class="vuln-owasp-tag">${escapeHtml(v.owasp_reference || 'OWASP LLM01')}</span>
        </div>
        <div class="vuln-section-tag">📍 Sezione: <strong>${escapeHtml(v.affected_section)}</strong></div>
        <p class="vuln-desc">${escapeHtml(v.description)}</p>
        <div class="vuln-risk-box">⚠️ <strong>Rischio:</strong> ${escapeHtml(v.risk_explanation)}</div>
        ${v.evidence_snippet ? `<div class="vuln-evidence">🔍 Evidenza: <code>${escapeHtml(v.evidence_snippet)}</code></div>` : ''}
      `;
      vulnListContainer.appendChild(card);
    });
  }

  // --- Render Hardening Report ---
  function renderHardeningReport(hData) {
    scoreBeforeHardening.innerText = `${(hData.before_hardening_score * 100).toFixed(0)}%`;
    scoreAfterHardening.innerText = `${(hData.after_hardening_score * 100).toFixed(0)}%`;
    hardeningExecSummary.innerText = hData.executive_summary || 'Nessun riepilogo disponibile.';

    remediationsContainer.innerHTML = '';
    if (hData.remediations && hData.remediations.length > 0) {
      hData.remediations.forEach(rem => {
        const card = document.createElement('div');
        card.className = 'remediation-card';

        const patternsHtml = (rem.applied_patterns || [])
          .map(p => `<span class="pattern-badge">${escapeHtml(p)}</span>`)
          .join('');

        card.innerHTML = `
          <div class="rem-header">
            <span class="rem-title">🛠️ Sezione: ${escapeHtml(rem.affected_section)}</span>
            <div class="rem-patterns">${patternsHtml}</div>
          </div>
          <div class="diff-grid">
            <div class="diff-panel before">
              <div class="diff-panel-title">❌ Vulnerabile (Originale)</div>
              ${escapeHtml(rem.original_text)}
            </div>
            <div class="diff-panel after">
              <div class="diff-panel-title">✅ Hardened (Corretto)</div>
              ${escapeHtml(rem.hardened_text)}
            </div>
          </div>
          <p class="rem-rationale">💡 <strong>Spiegazione & Mitigazione:</strong> ${escapeHtml(rem.rationale)}</p>
        `;
        remediationsContainer.appendChild(card);
      });
    }

    hardenedPromptContent.innerText = hData.hardened_system_prompt || 'Nessun prompt hardened generato.';

    archRecsList.innerHTML = '';
    if (hData.architectural_recommendations && hData.architectural_recommendations.length > 0) {
      hData.architectural_recommendations.forEach(rec => {
        const li = document.createElement('li');
        li.innerText = rec;
        archRecsList.appendChild(li);
      });
    }
  }

  // --- Render Fragments Table ---
  function renderFragmentsTable(fragments) {
    const filter = fragCategoryFilter.value;
    const filtered = filter === 'ALL' ? fragments : fragments.filter(f => f.category === filter);

    fragmentsTableBody.innerHTML = '';
    if (!filtered || filtered.length === 0) {
      fragmentsTableBody.innerHTML = '<tr><td colspan="5" class="text-center">Nessun frammento per il filtro selezionato.</td></tr>';
      return;
    }

    filtered.forEach(f => {
      const tr = document.createElement('tr');
      tr.innerHTML = `
        <td><strong>R#${f.round_id}</strong></td>
        <td><span class="category-tag">${f.category}</span></td>
        <td>${escapeHtml(f.text)}</td>
        <td><span class="conf-pill">${(f.confidence_score * 100).toFixed(0)}%</span></td>
        <td><code>${f.source_strategy}</code></td>
      `;
      fragmentsTableBody.appendChild(tr);
    });
  }

  // --- Helper: Append Log ---
  function appendLog(message, type = 'info') {
    const line = document.createElement('div');
    line.className = `log-line ${type}`;
    const time = new Date().toLocaleTimeString();
    line.innerText = `[${time}] ${message}`;
    logConsole.appendChild(line);
    logConsole.scrollTop = logConsole.scrollHeight;
  }

  // --- Helper: HTML Escape ---
  function escapeHtml(str) {
    if (!str) return '';
    return str
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
  }
});
