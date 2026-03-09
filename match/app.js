/********************
 * CONFIG
 ********************/
const API_BASE = "http://127.0.0.1:8000"; // άλλαξέ το αργότερα σε production URL
const AUTO_SEARCH_DEBOUNCE_MS = 350;
const AUTO_SEARCH_MIN_CHARS = 2;

/********************
 * STATE
 ********************/
let currentUser = null;
let workbook = null;
let workbookData = {};
let currentJobId = null;
let results = [];
let pollTimer = null;

let currentModalRowIndex = -1;
let manualSearchTimer = null;
let manualSearchAbortController = null;

/********************
 * DOM
 ********************/
const loginView = document.getElementById("loginView");
const appView = document.getElementById("appView");

const emailInput = document.getElementById("emailInput");
const passwordInput = document.getElementById("passwordInput");
const loginBtn = document.getElementById("loginBtn");
const loginStatus = document.getElementById("loginStatus");

const userPill = document.getElementById("userPill");
const logoutBtn = document.getElementById("logoutBtn");
const exportBtn = document.getElementById("exportBtn");

const fileInput = document.getElementById("fileInput");
const sheetSelect = document.getElementById("sheetSelect");
const columnSelect = document.getElementById("columnSelect");
const exportNameInput = document.getElementById("exportNameInput");
const matchBtn = document.getElementById("matchBtn");

const fileSummary = document.getElementById("fileSummary");
const resultsCard = document.getElementById("resultsCard");
const resultsSummary = document.getElementById("resultsSummary");
const resultsBody = document.getElementById("resultsBody");

const progressWrap = document.getElementById("progressWrap");
const progressFill = document.getElementById("progressFill");
const progressText = document.getElementById("progressText");

const modalBackdrop = document.getElementById("modalBackdrop");
const modalSubtitle = document.getElementById("modalSubtitle");
const alternativesList = document.getElementById("alternativesList");
const closeModalBtn = document.getElementById("closeModalBtn");

const manualSearchInput = document.getElementById("manualSearchInput");
const manualSearchBtn = document.getElementById("manualSearchBtn");
const manualSearchStatus = document.getElementById("manualSearchStatus");

/********************
 * HELPERS
 ********************/
function setLoginStatus(message, cls = "muted") {
  loginStatus.className = `status ${cls}`;
  loginStatus.textContent = message;
}

function escapeHtml(str = "") {
  return String(str)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function updateProgress(value, text = "") {
  const v = Math.max(0, Math.min(100, Number(value || 0)));
  progressFill.style.width = `${v}%`;
  progressText.textContent = text || `${v}%`;
}

function showProgress() {
  progressWrap.classList.remove("hidden");
}

function hideProgress() {
  progressWrap.classList.add("hidden");
  updateProgress(0, "0%");
}

function saveSession(user) {
  sessionStorage.setItem("myscanner_match_user", JSON.stringify(user));
}

function loadSession() {
  const raw = sessionStorage.getItem("myscanner_match_user");
  if (!raw) return null;

  try {
    return JSON.parse(raw);
  } catch {
    return null;
  }
}

function clearSession() {
  sessionStorage.removeItem("myscanner_match_user");
}

function safeString(value, fallback = "") {
  const v = value == null ? fallback : String(value);
  return v.trim();
}

function safeNumber(value, fallback = 0) {
  const n = Number(value);
  return Number.isFinite(n) ? n : fallback;
}

function normalizeConfidenceZone(zone) {
  const z = safeString(zone).toLowerCase();
  if (["high", "medium", "low", "very_low"].includes(z)) return z;
  return "very_low";
}

function getZoneLabel(zone) {
  const z = normalizeConfidenceZone(zone);
  if (z === "high") return "HIGH";
  if (z === "medium") return "MEDIUM";
  if (z === "low") return "LOW";
  return "VERY LOW";
}

function getZoneClass(zone) {
  const z = normalizeConfidenceZone(zone);
  if (z === "high") return "zone-high";
  if (z === "medium") return "zone-medium";
  if (z === "low") return "zone-low";
  return "zone-very-low";
}

function prettifyReason(reason = "") {
  const text = safeString(reason);
  if (!text) return "Χωρίς διαθέσιμη αιτιολόγηση";

  const map = {
    exact_normalized_match: "Ακριβές normalized match",
    strong_token_overlap: "Πολύ ισχυρή επικάλυψη tokens",
    good_token_overlap: "Καλή επικάλυψη tokens",
    brand_match: "Ταίριασμα brand",
    weight_match: "Ταίριασμα ποσότητας / βάρους",
    number_match: "Ταίριασμα αριθμητικών στοιχείων",
    category_match: "Ταίριασμα κατηγορίας",
    contains_match: "Το ένα περιέχει το άλλο",
    quantity_conflict: "Πιθανή σύγκρουση ποσότητας / συσκευασίας",
    brand_conflict: "Πιθανή σύγκρουση brand",
    weak_signal_match: "Ασθενές συνολικό σήμα",
    no_match: "Δεν βρέθηκε επαρκές match"
  };

  return text
    .split(",")
    .map(x => safeString(x))
    .filter(Boolean)
    .map(x => map[x] || x.replaceAll("_", " "))
    .join(" • ");
}

function deriveReviewStatus(row) {
  if (row?.excluded) return "excluded";
  if (row?.selected_manually) return "manual_selected";

  const zone = normalizeConfidenceZone(row?.confidence_zone);
  if (zone === "high") return "auto_high";
  return "review";
}

function getReviewLabel(status) {
  const s = safeString(status).toLowerCase();
  if (s === "excluded") return "excluded";
  if (s === "manual_selected") return "manual";
  if (s === "auto_high") return "auto";
  return "review";
}

function setLoggedInUI(user) {
  currentUser = user;
  loginView.classList.add("hidden");
  appView.classList.remove("hidden");

  userPill.textContent = `${user.name} • ${user.email}`;
  userPill.classList.remove("hidden");
  logoutBtn.classList.remove("hidden");
}

function setLoggedOutUI() {
  currentUser = null;
  workbook = null;
  workbookData = {};
  currentJobId = null;
  results = [];
  currentModalRowIndex = -1;

  if (pollTimer) {
    clearTimeout(pollTimer);
    pollTimer = null;
  }

  if (manualSearchTimer) {
    clearTimeout(manualSearchTimer);
    manualSearchTimer = null;
  }

  if (manualSearchAbortController) {
    manualSearchAbortController.abort();
    manualSearchAbortController = null;
  }

  loginView.classList.remove("hidden");
  appView.classList.add("hidden");

  userPill.classList.add("hidden");
  logoutBtn.classList.add("hidden");
  exportBtn.classList.add("hidden");
  resultsCard.classList.add("hidden");

  fileInput.value = "";
  sheetSelect.innerHTML = "";
  columnSelect.innerHTML = "";
  sheetSelect.disabled = true;
  columnSelect.disabled = true;
  matchBtn.disabled = true;
  exportNameInput.value = "";

  fileSummary.textContent = "Δεν έχει φορτωθεί αρχείο ακόμα.";
  resultsSummary.textContent = "";
  resultsBody.innerHTML = "";

  closeModal();
  hideProgress();
}

function getScoreClass(score) {
  const v = Number(score || 0);
  if (v >= 85) return "high";
  if (v >= 60) return "mid";
  return "low";
}

function getCurrentModalRow() {
  if (currentModalRowIndex < 0) return null;
  return results[currentModalRowIndex] || null;
}

function resetManualSearchAbort() {
  if (manualSearchAbortController) {
    manualSearchAbortController.abort();
  }
  manualSearchAbortController = new AbortController();
  return manualSearchAbortController;
}

function normalizeResultRow(row) {
  const alternatives = Array.isArray(row?.alternatives)
    ? row.alternatives.map(alt => ({
        barcode: safeString(alt?.barcode),
        product_name: safeString(alt?.product_name),
        score: safeNumber(alt?.score, 0),
        confidence_zone: normalizeConfidenceZone(alt?.confidence_zone),
        match_reason: safeString(alt?.match_reason),
        reason_parts: Array.isArray(alt?.reason_parts) ? alt.reason_parts : []
      }))
    : [];

  const normalized = {
    barcode: safeString(row?.barcode),
    uploaded_value: safeString(row?.uploaded_value),
    master_product_name: safeString(row?.master_product_name),
    match_percent: safeNumber(row?.match_percent, 0),
    confidence_zone: normalizeConfidenceZone(row?.confidence_zone),
    match_reason: safeString(row?.match_reason),
    selected_manually: Boolean(row?.selected_manually),
    excluded: Boolean(row?.excluded),
    review_status: safeString(row?.review_status) || deriveReviewStatus(row),
    alternatives
  };

  return normalized;
}

async function saveLearningEvent(payload) {
  try {
    await apiPost("/learning/save", payload);
  } catch (err) {
    console.error("Learning save failed:", err);
  }
}

/********************
 * API
 ********************/
async function parseApiResponse(res) {
  const text = await res.text();

  try {
    const data = JSON.parse(text);

    if (!res.ok) {
      throw new Error(data.error || `HTTP ${res.status}`);
    }

    return data;
  } catch (err) {
    if (err instanceof SyntaxError) {
      throw new Error(`Μη έγκυρο JSON από backend: ${text.slice(0, 300)}`);
    }
    throw err;
  }
}

async function apiGet(path) {
  const res = await fetch(`${API_BASE}${path}`);
  return parseApiResponse(res);
}

async function apiPost(path, payload, options = {}) {
  const res = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json"
    },
    body: JSON.stringify(payload),
    signal: options.signal
  });

  return parseApiResponse(res);
}

/********************
 * EXCEL
 ********************/
function parseWorkbook(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();

    reader.onload = e => {
      try {
        const data = new Uint8Array(e.target.result);
        const wb = XLSX.read(data, { type: "array" });
        resolve(wb);
      } catch (err) {
        reject(err);
      }
    };

    reader.onerror = reject;
    reader.readAsArrayBuffer(file);
  });
}

function sheetToObjects(ws) {
  const rows = XLSX.utils.sheet_to_json(ws, { header: 1, defval: "" });

  if (!rows.length) {
    return { headers: [], rows: [] };
  }

  const headers = rows[0].map((h, i) => {
    const value = String(h || "").trim();
    return value || `COL_${i + 1}`;
  });

  const outRows = rows.slice(1).map((row, idx) => {
    const obj = {};
    headers.forEach((h, i) => {
      obj[h] = row[i] ?? "";
    });
    obj.__rowNum = idx + 2;
    return obj;
  });

  return { headers, rows: outRows };
}

function renderSheetOptions() {
  sheetSelect.innerHTML = "";
  const sheetNames = Object.keys(workbookData);

  sheetNames.forEach(name => {
    const opt = document.createElement("option");
    opt.value = name;
    opt.textContent = name;
    sheetSelect.appendChild(opt);
  });

  sheetSelect.disabled = !sheetNames.length;

  if (sheetNames.length) {
    renderColumnOptions(sheetNames[0]);
  } else {
    columnSelect.innerHTML = "";
    columnSelect.disabled = true;
    matchBtn.disabled = true;
  }
}

function renderColumnOptions(sheetName) {
  columnSelect.innerHTML = "";

  const meta = workbookData[sheetName];
  if (!meta) {
    columnSelect.disabled = true;
    matchBtn.disabled = true;
    return;
  }

  meta.headers.forEach(h => {
    const opt = document.createElement("option");
    opt.value = h;
    opt.textContent = h;
    columnSelect.appendChild(opt);
  });

  columnSelect.disabled = !meta.headers.length;
  matchBtn.disabled = !meta.headers.length;
}

/********************
 * RESULTS
 ********************/
function renderResults() {
  resultsBody.innerHTML = "";

  results.forEach((rawRow, idx) => {
    const row = normalizeResultRow(rawRow);
    results[idx] = row;

    const tr = document.createElement("tr");

    if (row.excluded) {
      tr.classList.add("excluded-row");
    }

    const score = Number(row.match_percent || 0);
    const scoreClass = getScoreClass(score);
    const zoneClass = getZoneClass(row.confidence_zone);
    const zoneLabel = getZoneLabel(row.confidence_zone);
    const reviewLabel = getReviewLabel(row.review_status);
    const reasonLabel = prettifyReason(row.match_reason);

    tr.innerHTML = `
      <td>${idx + 1}</td>
      <td>${escapeHtml(row.barcode || "")}</td>
      <td>${escapeHtml(row.uploaded_value || "")}</td>
      <td>
        <div><strong>${escapeHtml(row.master_product_name || "")}</strong></div>
        <div style="margin-top:6px; display:flex; flex-wrap:wrap; gap:6px;">
          <span class="badge ${zoneClass}">${zoneLabel}</span>
          <span class="badge badge-review">${escapeHtml(reviewLabel)}</span>
          ${row.selected_manually ? '<span class="badge badge-manual">χειροκίνητη επιλογή</span>' : ""}
          ${row.excluded ? '<span class="badge badge-excluded">εξαιρέθηκε</span>' : ""}
        </div>
        <div class="tiny" style="margin-top:8px;">${escapeHtml(reasonLabel)}</div>
      </td>
      <td><span class="score ${scoreClass}">${score}%</span></td>
      <td>
        <div class="row-actions">
          <button class="btn btn-secondary" data-alt="${idx}">Εναλλακτικά</button>
          ${
            row.excluded
              ? `<button class="btn" data-undo="${idx}">Undo</button>`
              : `<button class="btn btn-secondary" data-exclude="${idx}">Exclude</button>`
          }
        </div>
      </td>
    `;

    resultsBody.appendChild(tr);
  });

  const includedCount = results.filter(r => !r.excluded).length;
  const excludedCount = results.filter(r => r.excluded).length;
  const highCount = results.filter(r => normalizeConfidenceZone(r.confidence_zone) === "high" && !r.excluded).length;
  const reviewCount = results.filter(r => getReviewLabel(r.review_status) === "review" && !r.excluded).length;

  resultsSummary.textContent =
    `Σύνολο: ${results.length} • για export: ${includedCount} • excluded: ${excludedCount} • high: ${highCount} • review: ${reviewCount}`;

  resultsCard.classList.remove("hidden");
  exportBtn.classList.remove("hidden");

  bindAlternativeButtons();
  bindExcludeButtons();
}

function bindAlternativeButtons() {
  const buttons = document.querySelectorAll("[data-alt]");

  buttons.forEach(btn => {
    btn.addEventListener("click", () => {
      const idx = Number(btn.dataset.alt);
      openAlternatives(idx);
    });
  });
}

function bindExcludeButtons() {
  const excludeButtons = document.querySelectorAll("[data-exclude]");
  const undoButtons = document.querySelectorAll("[data-undo]");

  excludeButtons.forEach(btn => {
    btn.addEventListener("click", async () => {
      const idx = Number(btn.dataset.exclude);
      await excludeResult(idx);
    });
  });

  undoButtons.forEach(btn => {
    btn.addEventListener("click", () => {
      const idx = Number(btn.dataset.undo);
      undoExcludeResult(idx);
    });
  });
}

async function excludeResult(idx) {
  if (!results[idx]) return;

  results[idx] = normalizeResultRow({
    ...results[idx],
    excluded: true,
    review_status: "excluded"
  });

  await saveLearningEvent({
    uploaded_value: results[idx]?.uploaded_value || "",
    selected_barcode: results[idx]?.barcode || "",
    selected_name: results[idx]?.master_product_name || "",
    action: "exclude"
  });

  renderResults();

  if (currentModalRowIndex === idx) {
    renderModalHeaderAndState();
  }
}

function undoExcludeResult(idx) {
  if (!results[idx]) return;

  results[idx] = normalizeResultRow({
    ...results[idx],
    excluded: false,
    review_status: results[idx]?.selected_manually ? "manual_selected" : deriveReviewStatus(results[idx])
  });

  renderResults();

  if (currentModalRowIndex === idx) {
    renderModalHeaderAndState();
  }
}

/********************
 * MODAL
 ********************/
function openAlternatives(rowIndex) {
  const row = results[rowIndex];
  if (!row) return;

  currentModalRowIndex = rowIndex;
  modalBackdrop.classList.remove("hidden");

  manualSearchInput.value = row.uploaded_value || "";
  manualSearchStatus.textContent = "";
  renderModalHeaderAndState();

  const alternatives = Array.isArray(row.alternatives) ? row.alternatives : [];
  if (alternatives.length) {
    renderAlternativeItems(alternatives, rowIndex);
  } else {
    alternativesList.innerHTML = `<div class="muted">Γίνεται έξυπνη αναζήτηση...</div>`;
    triggerAutoManualSearch(true);
  }

  manualSearchInput.focus();
  manualSearchInput.select();

  if ((row.uploaded_value || "").trim().length >= AUTO_SEARCH_MIN_CHARS) {
    triggerAutoManualSearch(true);
  }
}

function closeModal() {
  currentModalRowIndex = -1;

  if (manualSearchTimer) {
    clearTimeout(manualSearchTimer);
    manualSearchTimer = null;
  }

  if (manualSearchAbortController) {
    manualSearchAbortController.abort();
    manualSearchAbortController = null;
  }

  modalBackdrop.classList.add("hidden");
  alternativesList.innerHTML = "";
  manualSearchInput.value = "";
  manualSearchStatus.textContent = "";

  if (manualSearchBtn) {
    manualSearchBtn.dataset.rowIndex = "-1";
    manualSearchBtn.disabled = false;
    manualSearchBtn.textContent = "Αναζήτηση";
  }
}

function renderModalHeaderAndState() {
  const row = getCurrentModalRow();

  if (!row) {
    modalSubtitle.textContent = "";
    return;
  }

  const zoneLabel = getZoneLabel(row.confidence_zone);
  const suffix = row.excluded ? " • EXCLUDED" : "";
  modalSubtitle.textContent =
    `Αρχική τιμή: ${row.uploaded_value || ""} • score: ${row.match_percent || 0}% • ${zoneLabel}${suffix}`;

  if (manualSearchBtn) {
    manualSearchBtn.dataset.rowIndex = String(currentModalRowIndex);
  }
}

function renderAlternativeItems(items, rowIndex) {
  alternativesList.innerHTML = "";

  const row = results[rowIndex];
  if (!row) {
    alternativesList.innerHTML = `<div class="muted">Η γραμμή δεν βρέθηκε.</div>`;
    return;
  }

  const actionsWrap = document.createElement("div");
  actionsWrap.className = "alt-actions-top";
  actionsWrap.style.display = "flex";
  actionsWrap.style.gap = "10px";
  actionsWrap.style.marginBottom = "14px";
  actionsWrap.style.flexWrap = "wrap";

  const excludeBtn = document.createElement("button");
  excludeBtn.className = row.excluded ? "btn" : "btn btn-secondary";
  excludeBtn.textContent = row.excluded ? "Undo Exclude" : "Exclude";

  excludeBtn.addEventListener("click", async () => {
    if (!results[rowIndex]) return;

    if (results[rowIndex].excluded) {
      undoExcludeResult(rowIndex);
    } else {
      await excludeResult(rowIndex);
    }

    renderAlternativeItems(items, rowIndex);
  });

  actionsWrap.appendChild(excludeBtn);
  alternativesList.appendChild(actionsWrap);

  if (!items || !items.length) {
    const empty = document.createElement("div");
    empty.className = "muted";
    empty.textContent = "Δεν βρέθηκαν αποτελέσματα.";
    alternativesList.appendChild(empty);
    return;
  }

  items.forEach(altRaw => {
    const alt = {
      barcode: safeString(altRaw?.barcode),
      product_name: safeString(altRaw?.product_name),
      score: safeNumber(altRaw?.score, 0),
      confidence_zone: normalizeConfidenceZone(altRaw?.confidence_zone),
      match_reason: safeString(altRaw?.match_reason),
      reason_parts: Array.isArray(altRaw?.reason_parts) ? altRaw.reason_parts : []
    };

    const div = document.createElement("div");
    div.className = "alt-item";

    const altScore = Number(alt.score || 0);
    const altZoneLabel = getZoneLabel(alt.confidence_zone);
    const altZoneClass = getZoneClass(alt.confidence_zone);
    const altReason = prettifyReason(alt.match_reason);

    div.innerHTML = `
      <div class="alt-meta">
        <div><strong>${escapeHtml(alt.product_name || "")}</strong></div>
        <div class="tiny">barcode: ${escapeHtml(alt.barcode || "")}</div>
        <div class="tiny" style="margin-top:4px; display:flex; flex-wrap:wrap; gap:6px;">
          <span class="badge ${altZoneClass}">${altZoneLabel}</span>
          <span class="badge badge-score">score ${altScore}%</span>
        </div>
        <div class="tiny" style="margin-top:6px;">${escapeHtml(altReason)}</div>
      </div>
      <div>
        <button class="btn">Επιλογή</button>
      </div>
    `;

    div.querySelector("button").addEventListener("click", async () => {
      const updatedRow = normalizeResultRow({
        ...results[rowIndex],
        barcode: alt.barcode || "",
        master_product_name: alt.product_name || "",
        match_percent: altScore,
        confidence_zone: alt.confidence_zone || "very_low",
        match_reason: alt.match_reason || "",
        selected_manually: true,
        excluded: false,
        review_status: "manual_selected"
      });

      results[rowIndex] = updatedRow;

      await saveLearningEvent({
        uploaded_value: results[rowIndex]?.uploaded_value || "",
        selected_barcode: alt.barcode || "",
        selected_name: alt.product_name || "",
        action: "manual_select"
      });

      renderResults();
      closeModal();
    });

    alternativesList.appendChild(div);
  });
}

/********************
 * MATCH FLOW
 ********************/
async function startMatch() {
  const sheetName = sheetSelect.value;
  const columnName = columnSelect.value;
  const meta = workbookData[sheetName];

  if (!meta) {
    alert("Δεν βρέθηκε το επιλεγμένο tab.");
    return;
  }

  const values = meta.rows
    .map(r => String(r[columnName] ?? "").trim())
    .filter(Boolean);

  if (!values.length) {
    alert("Δεν βρέθηκαν τιμές στη στήλη που επέλεξες.");
    return;
  }

  matchBtn.disabled = true;
  matchBtn.textContent = "Matching...";
  exportBtn.classList.add("hidden");
  resultsCard.classList.add("hidden");
  resultsBody.innerHTML = "";
  results = [];

  if (pollTimer) {
    clearTimeout(pollTimer);
    pollTimer = null;
  }

  showProgress();
  updateProgress(2, "2%");
  fileSummary.textContent = `Γίνεται αποστολή ${values.length} γραμμών για match...`;

  const res = await apiPost("/match/start", {
    values,
    user_email: currentUser.email,
    source_column: columnName
  });

  if (!res.ok) {
    matchBtn.disabled = false;
    matchBtn.textContent = "Match";
    hideProgress();
    alert(res.error || "Αποτυχία έναρξης match.");
    return;
  }

  currentJobId = res.job_id;
  pollMatchStatus();
}

async function pollMatchStatus() {
  if (!currentJobId) return;

  const statusRes = await apiGet(`/match/status/${currentJobId}`);

  updateProgress(statusRes.progress, `${statusRes.progress}%`);
  fileSummary.textContent = `Γίνεται match... ${statusRes.processed}/${statusRes.total}`;
  resultsSummary.textContent = `Κατάσταση: ${statusRes.status} • ${statusRes.processed}/${statusRes.total}`;

  if (statusRes.status === "completed") {
    await loadMatchResults();
    matchBtn.disabled = false;
    matchBtn.textContent = "Match";
    return;
  }

  if (statusRes.status === "failed") {
    matchBtn.disabled = false;
    matchBtn.textContent = "Match";
    hideProgress();
    alert(statusRes.error || "Το match απέτυχε.");
    return;
  }

  pollTimer = setTimeout(pollMatchStatus, 1200);
}

async function loadMatchResults() {
  if (!currentJobId) return;

  const resultRes = await apiGet(`/match/result/${currentJobId}`);

  results = (resultRes.results || []).map(r => normalizeResultRow(r));

  renderResults();
  updateProgress(100, "100%");
  fileSummary.textContent = `Ολοκληρώθηκε το match σε ${results.length} γραμμές.`;
  resultsSummary.textContent = `Ολοκληρώθηκε. Σύνολο γραμμών: ${results.length}`;
}

/********************
 * EXPORT FLOW
 ********************/
async function exportResults() {
  if (!currentUser) {
    alert("Δεν υπάρχει ενεργός χρήστης.");
    return;
  }

  if (!results.length) {
    alert("Δεν υπάρχουν αποτελέσματα για export.");
    return;
  }

  const exportName =
    exportNameInput.value.trim() ||
    `Match Export ${new Date().toLocaleString("el-GR")}`;

  const exportableRows = results.filter(r => !r.excluded);

  if (!exportableRows.length) {
    alert("Δεν υπάρχουν γραμμές για export.");
    return;
  }

  exportBtn.disabled = true;
  exportBtn.textContent = "Γίνεται export...";

  const payload = {
    export_name: exportName,
    user_email: currentUser.email,
    user_name: currentUser.name,
    rows: exportableRows.map(r => ({
      barcode: r.barcode || "",
      uploaded_value: r.uploaded_value || "",
      master_product_name: r.master_product_name || "",
      match_percent: Number(r.match_percent || 0),
      confidence_zone: normalizeConfidenceZone(r.confidence_zone),
      match_reason: r.match_reason || "",
      review_status: r.review_status || deriveReviewStatus(r),
      selected_manually: Boolean(r.selected_manually),
      excluded: Boolean(r.excluded)
    }))
  };

  try {
    const res = await apiPost("/export", payload);

    alert(
      `Το export δημιουργήθηκε επιτυχώς.\n\nΌνομα: ${res.export_name}\nΓραμμές: ${res.rows_count}\n\n${res.sheet_url}`
    );
  } finally {
    exportBtn.disabled = false;
    exportBtn.textContent = "Εξαγωγή";
  }
}

/********************
 * MANUAL / AUTO SEARCH
 ********************/
function triggerAutoManualSearch(immediate = false) {
  const query = manualSearchInput.value.trim();
  const row = getCurrentModalRow();

  if (!row) return;

  if (manualSearchTimer) {
    clearTimeout(manualSearchTimer);
    manualSearchTimer = null;
  }

  if (!query || query.length < AUTO_SEARCH_MIN_CHARS) {
    manualSearchStatus.textContent = query.length === 0
      ? "Γράψε προϊόν για έξυπνη αναζήτηση."
      : `Γράψε τουλάχιστον ${AUTO_SEARCH_MIN_CHARS} χαρακτήρες.`;

    const currentAlternatives = Array.isArray(row.alternatives) ? row.alternatives : [];
    renderAlternativeItems(currentAlternatives, currentModalRowIndex);
    return;
  }

  if (immediate) {
    manualSearch().catch(err => {
      manualSearchStatus.textContent = `Σφάλμα αναζήτησης: ${err.message}`;
    });
    return;
  }

  manualSearchTimer = setTimeout(() => {
    manualSearch().catch(err => {
      manualSearchStatus.textContent = `Σφάλμα αναζήτησης: ${err.message}`;
    });
  }, AUTO_SEARCH_DEBOUNCE_MS);
}

async function manualSearch() {
  const query = manualSearchInput.value.trim();
  const rowIndex = currentModalRowIndex;

  if (rowIndex < 0) return;

  if (!query || query.length < AUTO_SEARCH_MIN_CHARS) {
    manualSearchStatus.textContent = `Γράψε τουλάχιστον ${AUTO_SEARCH_MIN_CHARS} χαρακτήρες.`;
    return;
  }

  if (manualSearchBtn) {
    manualSearchBtn.disabled = true;
    manualSearchBtn.textContent = "Ψάχνει...";
  }

  manualSearchStatus.textContent = "Γίνεται έξυπνη αναζήτηση στο master...";
  alternativesList.innerHTML = `<div class="muted">Αναζήτηση...</div>`;

  const controller = resetManualSearchAbort();

  try {
    const res = await apiPost(
      "/master/search",
      {
        query,
        original_value: results[rowIndex]?.uploaded_value || "",
        row_index: rowIndex,
        limit: 20
      },
      { signal: controller.signal }
    );

    if (rowIndex !== currentModalRowIndex) {
      return;
    }

    const found = Array.isArray(res.results)
      ? res.results.map(x => ({
          barcode: safeString(x?.barcode),
          product_name: safeString(x?.product_name),
          score: safeNumber(x?.score, 0),
          confidence_zone: normalizeConfidenceZone(x?.confidence_zone),
          match_reason: safeString(x?.match_reason),
          reason_parts: Array.isArray(x?.reason_parts) ? x.reason_parts : []
        }))
      : [];

    manualSearchStatus.textContent = `Βρέθηκαν ${found.length} αποτελέσματα.`;

    results[rowIndex] = normalizeResultRow({
      ...results[rowIndex],
      alternatives: found
    });

    renderAlternativeItems(found, rowIndex);
  } catch (err) {
    if (err.name === "AbortError") {
      return;
    }

    manualSearchStatus.textContent = `Σφάλμα αναζήτησης: ${err.message}`;
    alternativesList.innerHTML = `<div class="muted">Αποτυχία αναζήτησης.</div>`;
  } finally {
    if (manualSearchBtn) {
      manualSearchBtn.disabled = false;
      manualSearchBtn.textContent = "Αναζήτηση";
    }
  }
}

/********************
 * EVENTS
 ********************/
loginBtn.addEventListener("click", async () => {
  const email = emailInput.value.trim().toLowerCase();
  const password = passwordInput.value.trim();

  if (!email || !password) {
    setLoginStatus("Βάλε email και κωδικό.", "error");
    return;
  }

  setLoginStatus("Γίνεται login...", "muted");
  loginBtn.disabled = true;

  try {
    const res = await apiPost("/login", { email, password });

    saveSession(res.user);
    setLoggedInUI(res.user);
    setLoginStatus("Η σύνδεση ολοκληρώθηκε.", "success");
  } catch (err) {
    setLoginStatus(`Σφάλμα σύνδεσης: ${err.message}`, "error");
  } finally {
    loginBtn.disabled = false;
  }
});

logoutBtn.addEventListener("click", () => {
  clearSession();
  setLoggedOutUI();
  setLoginStatus("Έγινε αποσύνδεση.", "muted");
});

fileInput.addEventListener("change", async e => {
  const file = e.target.files[0];
  if (!file) return;

  try {
    workbook = await parseWorkbook(file);
    workbookData = {};

    workbook.SheetNames.forEach(name => {
      const ws = workbook.Sheets[name];
      workbookData[name] = sheetToObjects(ws);
    });

    renderSheetOptions();
    fileSummary.textContent = `Φορτώθηκε: ${file.name} • tabs: ${workbook.SheetNames.length}`;
  } catch (err) {
    fileSummary.textContent = `Αποτυχία ανάγνωσης αρχείου: ${err.message}`;
  }
});

sheetSelect.addEventListener("change", () => {
  renderColumnOptions(sheetSelect.value);
});

matchBtn.addEventListener("click", async () => {
  try {
    await startMatch();
  } catch (err) {
    matchBtn.disabled = false;
    matchBtn.textContent = "Match";
    hideProgress();
    alert(`Σφάλμα στο match: ${err.message}`);
  }
});

exportBtn.addEventListener("click", async () => {
  try {
    await exportResults();
  } catch (err) {
    exportBtn.disabled = false;
    exportBtn.textContent = "Εξαγωγή";
    alert(`Σφάλμα export: ${err.message}`);
  }
});

closeModalBtn.addEventListener("click", closeModal);

modalBackdrop.addEventListener("click", e => {
  if (e.target === modalBackdrop) {
    closeModal();
  }
});

if (manualSearchBtn) {
  manualSearchBtn.addEventListener("click", async () => {
    await manualSearch();
  });
}

manualSearchInput.addEventListener("input", () => {
  triggerAutoManualSearch(false);
});

manualSearchInput.addEventListener("keydown", e => {
  if (e.key === "Enter") {
    e.preventDefault();
    triggerAutoManualSearch(true);
  }

  if (e.key === "Escape") {
    e.preventDefault();
    closeModal();
  }
});

document.addEventListener("DOMContentLoaded", () => {
  const savedUser = loadSession();

  if (savedUser && savedUser.email) {
    setLoggedInUI(savedUser);
  } else {
    setLoggedOutUI();
  }
});
