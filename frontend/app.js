const API_BASE = "http://127.0.0.1:8000";

const state = {
  recruiterId: "current_user",
  requisitions: [],
  selectedRequisition: null,
  applications: [],
  selectedCandidateId: null,
  sessionId: null,
  requisitionId: null,
  clarificationQuestions: [],
  rankedCandidates: [],
  candidateBucket: "pool"
};

const els = {
  connectionStatus: document.getElementById("connectionStatus"),
  refreshBtn: document.getElementById("refreshBtn"),
  recruiterLabel: document.getElementById("recruiterLabel"),
  reqSearch: document.getElementById("reqSearch"),
  statusFilter: document.getElementById("statusFilter"),
  requisitionList: document.getElementById("requisitionList"),
  reqTitle: document.getElementById("reqTitle"),
  reqStatusBadge: document.getElementById("reqStatusBadge"),
  reqInfo: document.getElementById("reqInfo"),
  jdInput: document.getElementById("jdInput"),
  ingestBtn: document.getElementById("ingestBtn"),
  ingestSummary: document.getElementById("ingestSummary"),
  loadCandidatesBtn: document.getElementById("loadCandidatesBtn"),
  runSearchBtn: document.getElementById("runSearchBtn"),
  candidateRows: document.getElementById("candidateRows"),
  profileHint: document.getElementById("profileHint"),
  candidateProfile: document.getElementById("candidateProfile"),
  resumeHint: document.getElementById("resumeHint"),
  resumeMeta: document.getElementById("resumeMeta"),
  resumeDoc: document.getElementById("resumeDoc"),
  auditTrail: document.getElementById("auditTrail"),
  chatStream: document.getElementById("chatStream"),
  clarificationBox: document.getElementById("clarificationBox"),
  chatInput: document.getElementById("chatInput"),
  sendChatBtn: document.getElementById("sendChatBtn"),
  agentSessionHint: document.getElementById("agentSessionHint")
};

const decisions = new Map();

function setCandidateBucket(bucket) {
  state.candidateBucket = bucket;
  document.querySelectorAll(".bucket-tab").forEach((tab) => {
    tab.classList.toggle("is-active", tab.dataset.candidateTab === bucket);
  });
  renderCandidates();
}

function rowVisibleForBucket(candidateId) {
  const decision = getDecision(candidateId);
  if (state.candidateBucket === "shortlist") return decision === "Shortlisted";
  if (state.candidateBucket === "rejected") return decision === "Rejected";
  return decision === "Undecided";
}

function addAudit(message) {
  const entry = document.createElement("div");
  entry.className = "timeline-item";
  entry.textContent = `${new Date().toLocaleTimeString()} - ${message}`;
  if (els.auditTrail.querySelector(".muted")) {
    els.auditTrail.innerHTML = "";
  }
  els.auditTrail.prepend(entry);
}

function addChat(message, type = "agent") {
  const msg = document.createElement("div");
  msg.className = `chat-msg ${type}`;
  msg.textContent = message;
  els.chatStream.append(msg);
  els.chatStream.scrollTop = els.chatStream.scrollHeight;
}

function badgeClass(status) {
  const normalized = (status || "").toLowerCase().replace(/\s+/g, "-");
  return `badge ${normalized}`;
}

function activateTab(tabName) {
  document.querySelectorAll(".tab").forEach((tab) => {
    tab.classList.toggle("is-active", tab.dataset.tab === tabName);
  });
  document.querySelectorAll(".tab-panel").forEach((panel) => {
    panel.classList.toggle("is-active", panel.dataset.panel === tabName);
  });
}

async function apiGet(path, params = null) {
  const url = new URL(`${API_BASE}${path}`);
  if (params) {
    Object.entries(params).forEach(([k, v]) => url.searchParams.set(k, v));
  }
  const response = await fetch(url);
  if (!response.ok) throw new Error(`GET ${path} failed (${response.status})`);
  return response.json();
}

async function apiPost(path, body) {
  const response = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body)
  });
  if (!response.ok) throw new Error(`POST ${path} failed (${response.status})`);
  return response.json();
}

function renderRequisitionList() {
  const search = els.reqSearch.value.trim().toLowerCase();
  const statusFilter = els.statusFilter.value;

  const filtered = state.requisitions.filter((req) => {
    const text = `${req.requisition_id} ${req.title} ${req.department} ${req.location}`.toLowerCase();
    const statusMatch = statusFilter === "all" || (req.status || "").toLowerCase() === statusFilter;
    const searchMatch = !search || text.includes(search);
    return statusMatch && searchMatch;
  });

  if (!filtered.length) {
    els.requisitionList.innerHTML = '<div class="muted">No requisitions match your filters.</div>';
    return;
  }

  els.requisitionList.innerHTML = "";
  filtered.forEach((req) => {
    const card = document.createElement("button");
    card.type = "button";
    card.className = `req-card ${state.selectedRequisition?.requisition_id === req.requisition_id ? "active" : ""}`;
    card.innerHTML = `
      <h4>${req.title}</h4>
      <div class="req-meta">${req.requisition_id} - ${req.department}</div>
      <div class="req-meta">${req.location}</div>
      <span class="${badgeClass(req.status)}">${req.status}</span>
    `;
    card.addEventListener("click", () => selectRequisition(req));
    els.requisitionList.appendChild(card);
  });
}

function renderRequisitionInfo() {
  const req = state.selectedRequisition;
  if (!req) {
    els.reqTitle.textContent = "Select a requisition";
    els.reqStatusBadge.textContent = "-";
    els.reqStatusBadge.className = "badge";
    els.reqInfo.innerHTML = "";
    return;
  }

  els.reqTitle.textContent = `${req.title} (${req.requisition_id})`;
  els.reqStatusBadge.textContent = req.status;
  els.reqStatusBadge.className = badgeClass(req.status);

  const rows = [
    ["Requisition ID", req.requisition_id],
    ["Title", req.title],
    ["Department", req.department],
    ["Location", req.location],
    ["Status", req.status]
  ];

  els.reqInfo.innerHTML = rows
    .map(([k, v]) => `<dt>${k}</dt><dd>${v ?? "-"}</dd>`)
    .join("");

  if (!els.jdInput.value.trim()) {
    els.jdInput.value = `Seeking a ${req.title} for ${req.department} in ${req.location}. Include key technical requirements and minimum experience.`;
  }
}

function scoreForCandidate(candidateId) {
  const mod = Number(candidateId) % 37;
  return (0.52 + mod / 100).toFixed(2);
}

function shortEvidenceText(evidence) {
  if (!evidence || !evidence.length) return "-";
  const top = evidence[0]?.detail || "";
  return top.length > 72 ? `${top.slice(0, 69)}...` : top;
}

function getDecision(candidateId) {
  return decisions.get(String(candidateId)) || "Undecided";
}

function applyDecision(candidateId, decision) {
  decisions.set(String(candidateId), decision);
  renderCandidates();
  addAudit(`Candidate ${candidateId} moved to ${decision}.`);
}

function renderRankedCandidates() {
  if (!state.rankedCandidates.length) {
    return false;
  }

  const rows = state.rankedCandidates
    .map((item, idx) => {
      if (!rowVisibleForBucket(item.candidate_id)) return "";
      const skillCoverage = item.score_breakdown?.skill_coverage ?? "-";
      const score = item.total_score ?? "-";
      const gaps = (item.gaps || []).join("; ") || "-";
      return `
        <tr>
          <td>${idx + 1}</td>
          <td>${item.candidate_id}</td>
          <td>-</td>
          <td>${score}</td>
          <td>${skillCoverage}</td>
          <td>${shortEvidenceText(item.evidence)}</td>
          <td>${gaps}</td>
          <td>${getDecision(item.candidate_id)}</td>
          <td>
            <button class="btn btn-ghost view-profile" data-candidate-id="${item.candidate_id}">Profile</button>
            <button class="btn btn-ghost view-resume" data-candidate-id="${item.candidate_id}">Resume</button>
            <button class="btn btn-ghost set-shortlist" data-candidate-id="${item.candidate_id}">Shortlist</button>
            <button class="btn btn-ghost set-reject" data-candidate-id="${item.candidate_id}">Reject</button>
          </td>
        </tr>
      `;
    })
    .filter(Boolean)
    .join("");

  if (rows) {
    els.candidateRows.innerHTML = rows;
    return true;
  }
  return false;
}

function renderApplicationCandidates() {
  if (!state.applications.length) {
    return false;
  }

  const rows = state.applications
    .map((item, idx) => {
      if (!rowVisibleForBucket(item.candidate_id)) return "";
      const score = scoreForCandidate(item.candidate_id);
      return `
        <tr>
          <td>${idx + 1}</td>
          <td>${item.candidate_name}</td>
          <td>${item.current_job_title || "-"}</td>
          <td>${score}</td>
          <td>-</td>
          <td>-</td>
          <td>-</td>
          <td>${getDecision(item.candidate_id)}</td>
          <td>
            <button class="btn btn-ghost view-profile" data-candidate-id="${item.candidate_id}">Profile</button>
            <button class="btn btn-ghost view-resume" data-candidate-id="${item.candidate_id}">Resume</button>
            <button class="btn btn-ghost set-shortlist" data-candidate-id="${item.candidate_id}">Shortlist</button>
            <button class="btn btn-ghost set-reject" data-candidate-id="${item.candidate_id}">Reject</button>
          </td>
        </tr>
      `;
    })
    .filter(Boolean)
    .join("");

  if (rows) {
    els.candidateRows.innerHTML = rows;
    return true;
  }
  return false;
}

function renderCandidates() {
  const hasRanked = renderRankedCandidates();
  const hasApplications = hasRanked ? true : renderApplicationCandidates();

  if (!hasApplications) {
    const label =
      state.candidateBucket === "shortlist"
        ? "shortlisted"
        : state.candidateBucket === "rejected"
          ? "rejected"
          : "pipeline";
    els.candidateRows.innerHTML = `<tr><td colspan="9" class="muted">No candidates in ${label}.</td></tr>`;
  }

  document.querySelectorAll(".view-profile").forEach((btn) => {
    btn.addEventListener("click", () => loadCandidateProfile(btn.dataset.candidateId));
  });
  document.querySelectorAll(".view-resume").forEach((btn) => {
    btn.addEventListener("click", () => loadCandidateResume(btn.dataset.candidateId));
  });
  document.querySelectorAll(".set-shortlist").forEach((btn) => {
    btn.addEventListener("click", () => applyDecision(btn.dataset.candidateId, "Shortlisted"));
  });
  document.querySelectorAll(".set-reject").forEach((btn) => {
    btn.addEventListener("click", () => applyDecision(btn.dataset.candidateId, "Rejected"));
  });
}

async function loadCandidateProfile(candidateId) {
  state.selectedCandidateId = candidateId;
  activateTab("profile");
  els.profileHint.textContent = `Loading candidate ${candidateId}...`;

  try {
    const payload = await apiGet(`/candidate/${candidateId}`);
    const candidate = payload.candidate;

    const profileCard = `
      <article class="card">
        <h4>${candidate.candidate.full_name || "Unknown"} (${candidate.candidate.candidate_id})</h4>
        <p class="muted">${candidate.candidate.current_title || "-"} at ${candidate.candidate.current_employer || "-"}</p>
        <p>${candidate.candidate.summary || "No summary available."}</p>
      </article>
      <article class="card">
        <h4>Skills</h4>
        <p>${(candidate.skills || []).map((s) => s.skill).join(", ") || "-"}</p>
      </article>
      <article class="card">
        <h4>Education</h4>
        <p>${(candidate.education || []).map((e) => `${e.degree_level || ""} ${e.major || ""} (${e.institution || ""})`).join(" | ") || "-"}</p>
      </article>
    `;

    els.candidateProfile.innerHTML = profileCard;
    els.profileHint.textContent = `Candidate ${candidateId} loaded.`;
    addAudit(`Opened candidate profile ${candidateId}`);
  } catch (err) {
    els.candidateProfile.innerHTML = `<div class="card muted">Failed to load profile: ${err.message}</div>`;
  }
}

async function loadCandidateResume(candidateId) {
  state.selectedCandidateId = candidateId;
  activateTab("resume");
  els.resumeHint.textContent = `Loading mock resume for ${candidateId}...`;
  els.resumeDoc.textContent = "Loading...";

  try {
    const payload = await apiGet(`/ats/candidates/${candidateId}`);
    const resumePayload = await apiGet(`/ats/candidates/${candidateId}/resume-markdown`);
    els.resumeDoc.textContent = resumePayload.content || "No resume content available.";
    els.resumeMeta.textContent = JSON.stringify(
      {
        candidate_resume_meta: payload.resume || null,
        mock_resume_path: resumePayload.path || null,
        source: "resumes/<candidate_id>.md"
      },
      null,
      2
    );
    els.resumeHint.textContent = `Showing mock resume for ${candidateId} from ${resumePayload.path}.`;
    addAudit(`Opened resume metadata ${candidateId}`);
  } catch (err) {
    els.resumeMeta.textContent = `Failed to load resume metadata: ${err.message}`;
    els.resumeDoc.textContent = "Resume content could not be loaded.";
    els.resumeHint.textContent = `Failed to load resume for ${candidateId}.`;
  }
}

function renderClarification(questions) {
  els.clarificationBox.innerHTML = "";
  if (!questions || !questions.length) return;

  questions.forEach((q) => {
    const wrapper = document.createElement("div");
    wrapper.className = "question-card";
    wrapper.innerHTML = `
      <strong>${q.prompt}</strong>
      <div class="muted">Field: ${q.target_field}</div>
      <input type="text" data-question-id="${q.question_id}" placeholder="Type answer...">
    `;
    els.clarificationBox.appendChild(wrapper);
  });

  const submit = document.createElement("button");
  submit.className = "btn btn-primary";
  submit.textContent = "Submit Clarifications";
  submit.addEventListener("click", submitClarifications);
  els.clarificationBox.appendChild(submit);
}

async function submitClarifications() {
  if (!state.requisitionId || !state.sessionId) return;

  const answers = [...els.clarificationBox.querySelectorAll("input[data-question-id]")].map((input) => ({
    question_id: input.dataset.questionId,
    answer: input.value.trim() || "Not specified"
  }));

  try {
    addChat("Submitting clarification answers...", "user");
    const result = await apiPost(`/requisition/${state.requisitionId}/clarify`, {
      session_id: state.sessionId,
      answers
    });

    if (result.status === "needs_clarification") {
      addChat("More clarification needed.", "agent");
      renderClarification(result.clarification_questions || []);
      return;
    }

    addChat("Clarifications accepted. Search completed.", "agent");
    state.rankedCandidates = result.ranked_candidates || [];
    els.clarificationBox.innerHTML = "";
    els.ingestSummary.textContent = JSON.stringify(
      {
        status: result.status,
        candidate_count: result.candidate_count,
        top_candidate: state.rankedCandidates[0] || null
      },
      null,
      2
    );
    addAudit("Clarification cycle completed.");
    activateTab("candidates");
    renderCandidates();
  } catch (err) {
    addChat(`Clarification failed: ${err.message}`, "agent");
  }
}

async function runIngest() {
  const req = state.selectedRequisition;
  if (!req) {
    addChat("Select a requisition before running analysis.", "agent");
    return;
  }

  const body = {
    requisition_id: req.requisition_id,
    title: req.title,
    department: req.department,
    location: req.location,
    jd_text: els.jdInput.value.trim()
  };

  try {
    addChat("Running analysis on requisition...", "user");
    const result = await apiPost("/requisition/ingest", body);
    state.sessionId = result.session_id;
    state.requisitionId = result.requisition_id;
    els.agentSessionHint.textContent = `Session: ${state.sessionId}`;

    els.ingestSummary.textContent = JSON.stringify(
      {
        status: result.status,
        requisition_id: result.requisition_id,
        session_id: result.session_id,
        clarification_count: (result.clarification_questions || []).length
      },
      null,
      2
    );

    if (result.status === "needs_clarification") {
      addChat("Clarification needed. Please answer the questions below.", "agent");
      renderClarification(result.clarification_questions || []);
    } else {
      addChat("Analysis completed.", "agent");
      renderClarification([]);
      state.rankedCandidates = result.ranked_candidates || [];
      renderCandidates();
    }
    addAudit(`Ingest completed for ${result.requisition_id}.`);
  } catch (err) {
    els.ingestSummary.textContent = `Failed: ${err.message}`;
    addChat(`Ingest failed: ${err.message}`, "agent");
  }
}

async function loadCandidates() {
  const req = state.selectedRequisition;
  if (!req) {
    addChat("Select a requisition first.", "agent");
    return;
  }
  activateTab("candidates");

  try {
    const result = await apiGet(`/ats/requisitions/${req.requisition_id}/applications`, { limit: 20 });
    state.applications = result.applications || [];
    if (!state.rankedCandidates.length) {
      addChat("Loaded ATS applications. Run ranked search for agent scoring.", "agent");
    }
    renderCandidates();
    addAudit(`Loaded ${state.applications.length} applications for ${req.requisition_id}.`);
  } catch (err) {
    els.candidateRows.innerHTML = `<tr><td colspan="9" class="muted">Failed to load candidates: ${err.message}</td></tr>`;
  }
}

async function runRankedSearch() {
  if (!state.sessionId) {
    addChat("Run ingest and clarifications first to create a session.", "agent");
    return;
  }

  try {
    addChat("Running ranked search...", "user");
    const result = await apiPost("/search", { session_id: state.sessionId });

    if (result.status === "needs_clarification") {
      addChat("Search still needs clarification answers.", "agent");
      renderClarification(result.clarification_questions || []);
      return;
    }

    state.rankedCandidates = result.ranked_candidates || [];
    activateTab("candidates");
    renderCandidates();
    addChat(`Ranked search returned ${state.rankedCandidates.length} candidates.`, "agent");
    addAudit("Ranked search completed.");
  } catch (err) {
    addChat(`Ranked search failed: ${err.message}`, "agent");
  }
}

function selectRequisition(req) {
  state.selectedRequisition = req;
  renderRequisitionList();
  renderRequisitionInfo();
  state.applications = [];
  renderCandidates();
  addChat(`Selected requisition ${req.requisition_id} (${req.title}).`, "agent");
  addAudit(`Selected requisition ${req.requisition_id}.`);
}

async function loadRequisitions() {
  const result = await apiGet("/ats/requisitions", { recruiter_id: state.recruiterId });
  state.requisitions = result.job_requisitions || [];
  els.recruiterLabel.textContent = result.recruiter_id || state.recruiterId;
  renderRequisitionList();

  if (!state.selectedRequisition && state.requisitions.length) {
    selectRequisition(state.requisitions[0]);
  }
}

async function checkApi() {
  try {
    const health = await apiGet("/health");
    els.connectionStatus.textContent = `API ${health.status}`;
    els.connectionStatus.style.color = "var(--success)";
    await loadRequisitions();
  } catch (err) {
    els.connectionStatus.textContent = "API offline";
    els.connectionStatus.style.color = "var(--danger)";
    addChat(`Could not connect to API at ${API_BASE}.`, "agent");
  }
}

function wireEvents() {
  document.querySelectorAll(".tab").forEach((btn) => {
    btn.addEventListener("click", () => activateTab(btn.dataset.tab));
  });

  els.reqSearch.addEventListener("input", renderRequisitionList);
  els.statusFilter.addEventListener("change", renderRequisitionList);
  els.refreshBtn.addEventListener("click", checkApi);
  els.ingestBtn.addEventListener("click", runIngest);
  els.loadCandidatesBtn.addEventListener("click", loadCandidates);
  els.runSearchBtn.addEventListener("click", runRankedSearch);
  document.querySelectorAll(".bucket-tab").forEach((btn) => {
    btn.addEventListener("click", () => setCandidateBucket(btn.dataset.candidateTab));
  });

  els.sendChatBtn.addEventListener("click", () => {
    const text = els.chatInput.value.trim();
    if (!text) return;
    addChat(text, "user");
    els.chatInput.value = "";
  });
}

function init() {
  wireEvents();
  checkApi();
}

init();
