/********************
 * CONFIG
 ********************/
const API_BASE = "http://127.0.0.1:8000"; // άλλαξέ το αργότερα σε production URL

/********************
 * STATE
 ********************/
let currentUser = null;
let workbook = null;
let workbookData = {};
let currentJobId = null;
let results = [];
let pollTimer = null;

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

  if (pollTimer) {
    clearTimeout(pollTimer);
    pollTimer = null;
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

  hideProgress();
}

/********************
 * API
 ********************/
async function apiGet(path) {
  const res = await fetch(`${API_BASE}${path}`);
  const text = await res.text();

  try {
    return JSON.parse(text);
  } catch (err) {
    throw new Error(`Μη έγκυρο JSON από backend: ${text.slice(0, 300)}`);
  }
}

async function apiPost(path, payload) {
  const res = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json"
    },
    body: JSON.stringify(payload)
  });

  const text = await res.text();

  try {
    return JSON.parse(text);
  } catch (err) {
    throw new Error(`Μη έγκυρο JSON από backend: ${text.slice(0, 300)}`);
  }
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

  const headers = rows[0].map((h, i) => String(h || `COL_${i + 1}`).trim());

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
  }
}

function renderColumnOptions(sheetName) {
  columnSelect.innerHTML = "";

  const meta = workbookData[sheetName];
  if (!meta) return;

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

  results.forEach((row, idx) => {
    const tr = document.createElement("tr");
    const score = Number(row.match_percent || 0);
    const scoreClass = score >= 85 ? "high" : score >= 60 ? "mid" : "low";

    tr.innerHTML = `
      <td>${idx + 1}</td>
      <td>${escapeHtml(row.barcode || "")}</td>
      <td>${escapeHtml(row.uploaded_value || "")}</td>
      <td>
        ${escapeHtml(row.master_product_name || "")}
        ${row.selected_manually ? '<div style="margin-top:6px"><span class="badge badge-manual">χειροκίνητη επιλογή</span></div>' : ""}
      </td>
      <td><span class="score ${scoreClass}">${score}%</span></td>
      <td>
        <div class="row-actions">
          <button class="btn btn-secondary" data-alt="${idx}">Εναλλακτικά</button>
        </div>
      </td>
    `;
    resultsBody.appendChild(tr);
  });

  resultsSummary.textContent = `Σύνολο γραμμών: ${results.length}`;
  resultsCard.classList.remove("hidden");
  exportBtn.classList.remove("hidden");

  bindAlternativeButtons();
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

/********************
 * MODAL
 ********************/
function openAlternatives(rowIndex) {
  const row = results[rowIndex];
  if (!row) return;

  const alternatives = Array.isArray(row.alternatives) ? row.alternatives : [];

  modalSubtitle.textContent = `Αρχική τιμή: ${row.uploaded_value}`;
  alternativesList.innerHTML = "";

  if (!alternatives.length) {
    alternativesList.innerHTML = `<div class="muted">Δεν βρέθηκαν εναλλακτικά.</div>`;
  } else {
    alternatives.forEach(alt => {
      const div = document.createElement("div");
      div.className = "alt-item";

      div.innerHTML = `
        <div class="alt-meta">
          <div><strong>${escapeHtml(alt.product_name || "")}</strong></div>
          <div class="tiny">barcode: ${escapeHtml(alt.barcode || "")}</div>
          <div class="tiny">score: ${Number(alt.score || 0)}%</div>
        </div>
        <div>
          <button class="btn">Επιλογή</button>
        </div>
      `;

      div.querySelector("button").addEventListener("click", () => {
        results[rowIndex] = {
          ...results[rowIndex],
          barcode: alt.barcode || "",
          master_product_name: alt.product_name || "",
          match_percent: Number(alt.score || 0),
          selected_manually: true
        };
        renderResults();
        closeModal();
      });

      alternativesList.appendChild(div);
    });
  }

  modalBackdrop.classList.remove("hidden");
}

function closeModal() {
  modalBackdrop.classList.add("hidden");
  alternativesList.innerHTML = "";
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

  if (!statusRes.ok) {
    matchBtn.disabled = false;
    matchBtn.textContent = "Match";
    hideProgress();
    alert(statusRes.error || "Σφάλμα κατά το polling.");
    return;
  }

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

  if (!resultRes.ok) {
    matchBtn.disabled = false;
    matchBtn.textContent = "Match";
    hideProgress();
    alert(resultRes.error || "Αποτυχία φόρτωσης αποτελεσμάτων.");
    return;
  }

  results = resultRes.results || [];
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

  const exportName = exportNameInput.value.trim() || `Match Export ${new Date().toLocaleString("el-GR")}`;

  exportBtn.disabled = true;
  exportBtn.textContent = "Γίνεται export...";

  const payload = {
    export_name: exportName,
    user_email: currentUser.email,
    user_name: currentUser.name,
    rows: results.map(r => ({
      barcode: r.barcode || "",
      uploaded_value: r.uploaded_value || "",
      master_product_name: r.master_product_name || "",
      match_percent: Number(r.match_percent || 0),
      selected_manually: Boolean(r.selected_manually)
    }))
  };

  const res = await apiPost("/export", payload);

  exportBtn.disabled = false;
  exportBtn.textContent = "Εξαγωγή";

  if (!res.ok) {
    alert(res.error || "Αποτυχία export.");
    return;
  }

  alert(`Το export δημιουργήθηκε επιτυχώς.\n\nΌνομα: ${res.export_name}\nΓραμμές: ${res.rows_count}\n\n${res.sheet_url}`);
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

    if (!res.ok) {
      setLoginStatus(res.error || "Αποτυχία σύνδεσης.", "error");
      loginBtn.disabled = false;
      return;
    }

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

document.addEventListener("DOMContentLoaded", () => {
  const savedUser = loadSession();

  if (savedUser && savedUser.email) {
    setLoggedInUI(savedUser);
  } else {
    setLoggedOutUI();
  }
});
