// AI Trading Copilot - Single Page Application Engine

const API_BASE = "";
let currentToken = localStorage.getItem("ai_trade_token") || "";
let currentAnalysis = null;
let currentSymbols = [];

// Helper: Toast Notifications
function showToast(message, type = "info") {
  const container = document.getElementById("toast-container");
  const toast = document.createElement("div");
  toast.className = "toast";
  
  let icon = "ℹ️";
  if (type === "success") icon = "✅";
  if (type === "error") icon = "❌";
  if (type === "warning") icon = "⚠️";

  toast.innerHTML = `<span class="text-base">${icon}</span><span>${message}</span>`;
  container.appendChild(toast);

  setTimeout(() => {
    toast.style.opacity = "0";
    toast.style.transform = "translateY(10px)";
    toast.style.transition = "all 0.3s ease";
    setTimeout(() => toast.remove(), 300);
  }, 4000);
}

// Helper: Fetch with Authorization Bearer
async function apiFetch(endpoint, options = {}) {
  const headers = options.headers || {};
  if (currentToken) {
    headers["Authorization"] = `Bearer ${currentToken}`;
  }
  if (!headers["Content-Type"] && !(options.body instanceof FormData)) {
    headers["Content-Type"] = "application/json";
  }
  options.headers = headers;

  const res = await fetch(`${API_BASE}${endpoint}`, options);
  if (res.status === 401) {
    showLoginModal();
    throw new Error("Session expired. Please login again.");
  }
  return res;
}

// ----------------- Authentication ----------------- //

function showLoginModal() {
  const pwd = document.getElementById("login-password");
  if (pwd) pwd.value = "";
  document.getElementById("login-modal").classList.remove("hidden");
}

function hideLoginModal() {
  const pwd = document.getElementById("login-password");
  if (pwd) pwd.value = "";
  document.getElementById("login-modal").classList.add("hidden");
}

async function checkAuth() {
  if (!currentToken) {
    showLoginModal();
    return false;
  }
  try {
    const res = await apiFetch("/api/auth/me");
    if (res.ok) {
      hideLoginModal();
      return true;
    } else {
      showLoginModal();
      return false;
    }
  } catch (e) {
    showLoginModal();
    return false;
  }
}

async function handleLogin(e) {
  e.preventDefault();
  const username = document.getElementById("login-username").value.trim();
  const password = document.getElementById("login-password").value;
  const submitBtn = document.getElementById("login-submit-btn");

  submitBtn.disabled = true;
  submitBtn.innerHTML = `<span class="spinner"></span> <span>Memverifikasi...</span>`;

  try {
    const res = await fetch(`${API_BASE}/api/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, password })
    });
    const data = await res.json();
    if (res.ok && data.access_token) {
      currentToken = data.access_token;
      localStorage.setItem("ai_trade_token", currentToken);
      hideLoginModal();
      showToast("Berhasil login ke sistem", "success");
      initializeApp();
    } else {
      showToast(data.detail || "Login gagal. Cek kembali kredensial Anda.", "error");
    }
  } catch (err) {
    showToast("Terjadi kesalahan jaringan saat login.", "error");
  } finally {
    submitBtn.disabled = false;
    submitBtn.innerHTML = `<span>Masuk ke Dashboard</span><svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M14 5l7 7m0 0l-7 7m7-7H3"/></svg>`;
  }
}

function handleLogout() {
  currentToken = "";
  localStorage.removeItem("ai_trade_token");
  const pwd = document.getElementById("login-password");
  if (pwd) pwd.value = "";
  showLoginModal();
  showToast("Anda telah keluar.", "info");
}

async function handleChangePassword(e) {
  e.preventDefault();
  const curr = document.getElementById("current-password").value;
  const newPass = document.getElementById("new-password").value;
  const conf = document.getElementById("confirm-password").value;

  if (newPass !== conf) {
    showToast("Konfirmasi password baru tidak cocok.", "warning");
    return;
  }

  try {
    const res = await apiFetch("/api/auth/change-password", {
      method: "POST",
      body: JSON.stringify({ current_password: curr, new_password: newPass })
    });
    const data = await res.json();
    if (res.ok && data.success) {
      showToast("Password berhasil diganti dan disimpan ke config.json!", "success");
      document.getElementById("change-password-form").reset();
    } else {
      showToast(data.detail || "Gagal mengubah password.", "error");
    }
  } catch (err) {
    showToast("Error saat mengubah password.", "error");
  }
}

// ----------------- Tab Navigation ----------------- //

function switchTab(tabId) {
  document.querySelectorAll(".tab-content").forEach(el => el.classList.add("hidden"));
  const target = document.getElementById(`tab-${tabId}`);
  if (target) target.classList.remove("hidden");

  // Mobile nav highlight
  document.querySelectorAll(".nav-item").forEach(item => {
    if (item.dataset.tab === tabId) {
      item.classList.add("active");
    } else {
      item.classList.remove("active");
    }
  });

  // Desktop nav highlight
  document.querySelectorAll(".desktop-tab-btn").forEach(btn => {
    if (btn.dataset.tab === tabId) {
      btn.classList.add("text-blue-400", "bg-blue-500/10");
      btn.classList.remove("text-slate-400");
    } else {
      btn.classList.remove("text-blue-400", "bg-blue-500/10");
      btn.classList.add("text-slate-400");
    }
  });

  if (tabId === "history") {
    loadTradingHistory();
    loadHistory();
  }
  if (tabId === "settings") loadSettings();
}

function switchAnalysisTab(subtabId) {
  ["narrative", "news", "seasonality"].forEach(id => {
    document.getElementById(`subtab-${id}`).classList.add("hidden");
    const btn = document.getElementById(`subtab-${id}-btn`);
    btn.classList.remove("text-blue-400", "bg-blue-500/10");
    btn.classList.add("text-slate-400");
  });

  document.getElementById(`subtab-${subtabId}`).classList.remove("hidden");
  const activeBtn = document.getElementById(`subtab-${subtabId}-btn`);
  activeBtn.classList.add("text-blue-400", "bg-blue-500/10");
  activeBtn.classList.remove("text-slate-400");
}

// ----------------- System Status Polling ----------------- //

async function pollSystemStatus() {
  try {
    const res = await apiFetch("/api/status");
    if (res.ok) {
      const data = await res.json();
      updateStatusHeader(data);
    }
  } catch (e) {
    // Silent polling error
  }
}

function updateStatusHeader(data) {
  const mt5 = data.mt5 || {};
  const sessions = data.sessions || {};

  // MT5 Status Dot & Text
  const dot = document.getElementById("mt5-status-dot");
  const txt = document.getElementById("mt5-status-text");

  if (mt5.connected) {
    dot.className = "pulse-dot pulse-green";
    const modeLabel = mt5.mode === 'native' ? 'MT5 Native' : 'Live Bridge';
    const accLabel = mt5.login && mt5.login !== 'None' ? ` #${mt5.login}` : '';
    txt.innerText = `${mt5.server || 'MT5'}${accLabel} (${modeLabel})`;
  } else {
    dot.className = "pulse-dot pulse-red";
    txt.innerText = mt5.error ? `MT5 Offline (${mt5.error})` : "MT5 Offline (Terminal Belum Terbuka)";
  }

  // Account Balance & Equity (USC / Cent aware)
  const curr = mt5.currency || 'USC';
  const balStr = curr === 'USD' ? `$${(mt5.balance || 0).toLocaleString('en-US', { minimumFractionDigits: 2 })}` : `${(mt5.balance || 0).toLocaleString('en-US', { minimumFractionDigits: 2 })} ${curr}`;
  const eqStr = curr === 'USD' ? `$${(mt5.equity || 0).toLocaleString('en-US', { minimumFractionDigits: 2 })}` : `${(mt5.equity || 0).toLocaleString('en-US', { minimumFractionDigits: 2 })} ${curr}`;
  document.getElementById("header-balance").innerText = balStr;
  document.getElementById("header-equity").innerText = eqStr;

  // Dollar Index (DXY)
  const dxy = data.dxy || {};
  const dxyEl = document.getElementById("header-dxy");
  if (dxyEl && dxy.price) {
    const sign = (dxy.change_pct || 0) >= 0 ? "+" : "";
    dxyEl.innerText = `${dxy.price} (${sign}${dxy.change_pct || 0}%)`;
    if ((dxy.change_pct || 0) >= 0) {
      dxyEl.className = "font-mono font-bold text-emerald-400 text-sm";
    } else {
      dxyEl.className = "font-mono font-bold text-red-400 text-sm";
    }
  }

  // Session Clocks
  const tokyo = document.getElementById("session-tokyo");
  const london = document.getElementById("session-london");
  const ny = document.getElementById("session-ny");

  tokyo.className = sessions.is_tokyo ? "px-2 py-0.5 rounded text-[11px] font-bold text-amber-300 bg-amber-500/20 border border-amber-500/30" : "px-2 py-0.5 rounded text-[11px] font-medium text-slate-400 bg-slate-800/50";
  london.className = sessions.is_london ? "px-2 py-0.5 rounded text-[11px] font-bold text-emerald-300 bg-emerald-500/20 border border-emerald-500/30" : "px-2 py-0.5 rounded text-[11px] font-medium text-slate-400 bg-slate-800/50";
  ny.className = sessions.is_new_york ? "px-2 py-0.5 rounded text-[11px] font-bold text-blue-300 bg-blue-500/20 border border-blue-500/30" : "px-2 py-0.5 rounded text-[11px] font-medium text-slate-400 bg-slate-800/50";
}

// ----------------- Symbols Management ----------------- //

async function loadSymbols() {
  try {
    const res = await apiFetch("/api/symbols");
    if (res.ok) {
      currentSymbols = await res.json();
      populateSymbolDropdown();
      renderSymbolsTable();
    }
  } catch (e) {
    console.error("Error loading symbols", e);
  }
}

function populateSymbolDropdown() {
  const sel = document.getElementById("symbol-select");
  sel.innerHTML = "";
  const activeSymbols = currentSymbols.filter(s => s.is_active);

  if (activeSymbols.length === 0) {
    sel.innerHTML = `<option value="">Tidak ada simbol aktif</option>`;
    return;
  }

  activeSymbols.forEach(s => {
    const opt = document.createElement("option");
    opt.value = s.mt5_symbol;
    opt.dataset.base = s.base_symbol;
    opt.dataset.pip = s.pip_size;
    opt.innerText = `${s.display_name} (${s.mt5_symbol})`;
    sel.appendChild(opt);
  });
  onSymbolChange();
}

function onSymbolChange() {
  const sel = document.getElementById("symbol-select");
  const opt = sel.options[sel.selectedIndex];
  if (opt) {
    const pip = opt.dataset.pip || "0.0001";
    document.getElementById("selected-symbol-info").innerText = `Base: ${opt.dataset.base} | Pip: ${pip}`;
  }
}

function renderSymbolsTable() {
  const container = document.getElementById("symbols-table-container");
  if (!container) return;

  if (currentSymbols.length === 0) {
    container.innerHTML = `<div class="text-xs text-slate-500 py-2">Belum ada simbol terdaftar.</div>`;
    return;
  }

  container.innerHTML = currentSymbols.map(s => `
    <div class="flex items-center justify-between p-2.5 rounded-lg bg-slate-900/80 border border-slate-800 text-xs">
      <div>
        <span class="font-bold font-mono text-white">${s.mt5_symbol}</span>
        <span class="text-slate-400 ml-2">(${s.display_name})</span>
        <span class="text-[10px] text-blue-400 font-mono ml-2">Base: ${s.base_symbol} | Pip: ${s.pip_size}</span>
      </div>
      <div class="flex items-center gap-2">
        <button type="button" onclick="toggleSymbol(${s.id})" class="px-2.5 py-1 rounded text-[11px] font-semibold ${s.is_active ? 'bg-emerald-500/20 text-emerald-300' : 'bg-slate-800 text-slate-500'}">
          ${s.is_active ? 'Aktif' : 'Nonaktif'}
        </button>
        <button type="button" onclick="deleteSymbol(${s.id})" class="text-slate-500 hover:text-red-400 px-1.5 py-1 text-sm" title="Hapus">
          🗑️
        </button>
      </div>
    </div>
  `).join("");
}

async function toggleSymbol(id) {
  try {
    const res = await apiFetch(`/api/symbols/${id}/toggle`, { method: "PATCH" });
    if (res.ok) {
      showToast("Status simbol diperbarui", "success");
      await loadSymbols();
    }
  } catch (e) {
    showToast("Gagal mengubah status simbol", "error");
  }
}

async function deleteSymbol(id) {
  if (!confirm("Hapus simbol ini dari whitelist?")) return;
  try {
    const res = await apiFetch(`/api/symbols/${id}`, { method: "DELETE" });
    if (res.ok) {
      showToast("Simbol berhasil dihapus", "success");
      await loadSymbols();
    }
  } catch (e) {
    showToast("Gagal menghapus simbol", "error");
  }
}

function showAddSymbolModal() {
  document.getElementById("add-symbol-modal").classList.remove("hidden");
}

function hideAddSymbolModal() {
  document.getElementById("add-symbol-modal").classList.add("hidden");
}

async function handleAddSymbol(e) {
  e.preventDefault();
  const mt5_symbol = document.getElementById("new-mt5-symbol").value.trim();
  const base_symbol = document.getElementById("new-base-symbol").value.trim().toUpperCase();
  const display_name = document.getElementById("new-display-name").value.trim();
  const pip_size = parseFloat(document.getElementById("new-pip-size").value) || 0.0001;

  try {
    const res = await apiFetch("/api/symbols", {
      method: "POST",
      body: JSON.stringify({ mt5_symbol, base_symbol, display_name, pip_size, is_active: true })
    });
    if (res.ok) {
      showToast("Simbol baru berhasil didaftarkan", "success");
      hideAddSymbolModal();
      await loadSymbols();
    } else {
      const err = await res.json();
      showToast(err.detail || "Gagal menambah simbol", "error");
    }
  } catch (e) {
    showToast("Error saat menambah simbol", "error");
  }
}

// ----------------- Analysis Execution Flow ----------------- //

async function executeAnalysis() {
  const sel = document.getElementById("symbol-select");
  const symbol = sel.value;
  if (!symbol) {
    showToast("Pilih simbol terlebih dahulu", "warning");
    return;
  }

  const btn = document.getElementById("hit-analyze-btn");
  const icon = document.getElementById("analyze-btn-icon");
  const text = document.getElementById("analyze-btn-text");

  btn.disabled = true;
  icon.innerHTML = `<span class="spinner"></span>`;
  text.innerText = "Menganalisa Multi-Timeframe...";

  try {
    const res = await apiFetch("/api/analyze", {
      method: "POST",
      body: JSON.stringify({ mt5_symbol: symbol })
    });
    const data = await res.json();
    if (res.ok) {
      currentAnalysis = data;
      renderAnalysisResult(data);
      showToast(`Analisa ${symbol} selesai (${data.action})`, "success");
    } else {
      showToast(data.detail || "Gagal menjalankan analisa.", "error");
    }
  } catch (err) {
    showToast("Kesalahan saat menghubungi endpoint analisa.", "error");
  } finally {
    btn.disabled = false;
    icon.innerText = "🔍";
    text.innerText = "Hit Analyze";
  }
}

function renderAnalysisResult(data) {
  document.getElementById("analysis-empty-state").classList.add("hidden");
  const resContainer = document.getElementById("analysis-result-container");
  resContainer.classList.remove("hidden");

  // Symbol and Action Badge
  document.getElementById("result-symbol-name").innerText = `${data.display_name} (${data.symbol})`;
  const dualTime = (data.time_gmt && data.time_wib)
    ? { gmt: data.time_gmt, gmt7: data.time_wib }
    : formatDualTime(data.timestamp);
  document.getElementById("result-timestamp").innerHTML = `
    <div class="inline-flex flex-wrap items-center gap-2 mt-1.5 font-mono text-xs">
      <span class="px-2.5 py-1 rounded-lg bg-slate-900 border border-slate-700/80 text-slate-200 flex items-center gap-1.5 shadow-sm" title="Jam Pasar Forex (GMT+0)">
        <span class="text-[10px] font-sans font-bold text-slate-400 uppercase tracking-wider">🌐 Jam Pasar (GMT+0):</span>
        <strong class="text-white">${dualTime.gmt.replace(' GMT', '')}</strong>
      </span>
      <span class="px-2.5 py-1 rounded-lg bg-blue-500/15 border border-blue-500/30 text-blue-200 flex items-center gap-1.5 shadow-sm" title="Waktu Indonesia Barat (GMT+7)">
        <span class="text-[10px] font-sans font-bold text-blue-400 uppercase tracking-wider">🇮🇩 Waktu Lokal (GMT+7):</span>
        <strong class="text-blue-300 font-bold">${dualTime.gmt7.replace(' GMT+7', '').replace(' WIB', '')}</strong>
      </span>
    </div>
  `;

  const actionBadge = document.getElementById("action-badge");
  const glow = document.getElementById("glow-badge");
  const executeBtn = document.getElementById("execute-order-btn");

  actionBadge.innerText = data.action;
  if (data.action === "BUY_LIMIT") {
    actionBadge.className = "px-4 py-1.5 rounded-xl font-black text-sm tracking-wide badge-buy";
    glow.className = "absolute -right-20 -top-20 w-60 h-60 rounded-full blur-3xl pointer-events-none opacity-25 bg-emerald-500";
    executeBtn.disabled = false;
    executeBtn.className = "w-full sm:flex-1 py-3.5 px-6 rounded-xl btn-buy font-bold text-sm flex items-center justify-center gap-2";
    executeBtn.innerHTML = `<span>🚀 Pasang Buy Limit ke MT5</span>`;
  } else if (data.action === "SELL_LIMIT") {
    actionBadge.className = "px-4 py-1.5 rounded-xl font-black text-sm tracking-wide badge-sell";
    glow.className = "absolute -right-20 -top-20 w-60 h-60 rounded-full blur-3xl pointer-events-none opacity-25 bg-red-500";
    executeBtn.disabled = false;
    executeBtn.className = "w-full sm:flex-1 py-3.5 px-6 rounded-xl btn-sell font-bold text-sm flex items-center justify-center gap-2";
    executeBtn.innerHTML = `<span>🚀 Pasang Sell Limit ke MT5</span>`;
  } else {
    // WAIT
    actionBadge.className = "px-4 py-1.5 rounded-xl font-black text-sm tracking-wide badge-wait";
    glow.className = "absolute -right-20 -top-20 w-60 h-60 rounded-full blur-3xl pointer-events-none opacity-25 bg-amber-500";
    executeBtn.disabled = true;
    executeBtn.className = "w-full sm:flex-1 py-3.5 px-6 rounded-xl bg-slate-800 text-slate-500 cursor-not-allowed font-bold text-sm flex items-center justify-center gap-2";
    executeBtn.innerHTML = `<span>⏳ Rekomendasi WAIT (Order Ditahan)</span>`;
  }

  // RR & Confidence
  document.getElementById("result-rr").innerText = data.risk_reward_ratio || "1:2.0";
  document.getElementById("result-confidence").innerText = `${data.confidence_score}%`;

  // Grid Numbers
  document.getElementById("result-entry").innerText = data.entry_price ? data.entry_price.toFixed(5) : "-";
  document.getElementById("result-sl").innerText = data.stop_loss ? data.stop_loss.toFixed(5) : "-";
  document.getElementById("result-tp").innerText = data.take_profit ? data.take_profit.toFixed(5) : "-";

  const lotCalc = data.lot_calculation || {};
  const curr = lotCalc.currency || "USC";
  const finalLot = (lotCalc.calculated_lot || 0.01).toFixed(2);
  document.getElementById("result-lot").innerText = `${finalLot} Lot`;
  document.getElementById("result-max-loss").innerText = lotCalc.expected_max_loss_display || `${(lotCalc.expected_max_loss || 0).toFixed(2)} ${curr}`;
  const actualRisk = lotCalc.actual_risk_pct !== undefined ? lotCalc.actual_risk_pct : lotCalc.risk_percentage;
  document.getElementById("result-risk-pct").innerText = `${actualRisk}% Saldo`;
  document.getElementById("result-sl-pips").innerText = `${lotCalc.sl_distance_pips || 0} Pips`;

  // Anti-MC callout
  document.getElementById("result-anti-mc-text").innerText = lotCalc.anti_mc_guarantee || 
    `Dengan lot minimal ${finalLot}, jika Stop Loss tersentuh modal berkurang maksimal ${lotCalc.expected_max_loss || 0} ${curr} (${actualRisk}% saldo), melindungi akun dari risiko Margin Call.`;

  // Narrative, News, Seasonality
  document.getElementById("result-ai-narrative").innerText = data.analysis_summary || "Tidak ada narasi analisa.";
  document.getElementById("result-calendar-status").innerText = data.calendar_status || "Kalender ekonomi aman.";
  document.getElementById("result-news-headlines").innerText = data.news_summary || "- Steady market conditions.";
  document.getElementById("result-seasonality-note").innerText = data.seasonality_note || "Data musiman konsisten.";

  // Scroll smoothly to results on mobile
  resContainer.scrollIntoView({ behavior: 'smooth' });
}

// ----------------- Order Execution Flow ----------------- //

async function confirmExecuteOrder() {
  if (!currentAnalysis || !currentAnalysis.history_id) {
    showToast("Tidak ada rekomendasi aktif untuk dieksekusi", "warning");
    return;
  }

  if (currentAnalysis.action === "WAIT") {
    showToast("Rekomendasi saat ini adalah WAIT. Order tidak dapat dipasang.", "warning");
    return;
  }

  const btn = document.getElementById("execute-order-btn");
  btn.disabled = true;
  btn.innerHTML = `<span class="spinner"></span> <span>Memasang ke MT5...</span>`;

  try {
    const res = await apiFetch("/api/order/execute", {
      method: "POST",
      body: JSON.stringify({ history_id: currentAnalysis.history_id })
    });
    const data = await res.json();
    if (res.ok && data.success) {
      showToast(`Sukses! Order terpasang di MT5 (Tiket #${data.ticket})`, "success");
      btn.className = "w-full sm:flex-1 py-3.5 px-6 rounded-xl bg-slate-800 text-emerald-400 font-bold text-sm flex items-center justify-center gap-2";
      btn.innerHTML = `<span>✅ Terpasang (Tiket #${data.ticket})</span>`;
    } else {
      showToast(data.detail || "Gagal memasang order ke MT5", "error");
      btn.disabled = false;
      btn.innerHTML = `<span>🚀 Pasang Order ke MT5</span>`;
    }
  } catch (e) {
    showToast("Kesalahan saat mengeksekusi order", "error");
    btn.disabled = false;
    btn.innerHTML = `<span>🚀 Pasang Order ke MT5</span>`;
  }
}

async function confirmRejectOrder() {
  if (!currentAnalysis || !currentAnalysis.history_id) return;
  try {
    const res = await apiFetch("/api/order/reject", {
      method: "POST",
      body: JSON.stringify({ history_id: currentAnalysis.history_id })
    });
    if (res.ok) {
      showToast("Rekomendasi diabaikan.", "info");
      document.getElementById("analysis-result-container").classList.add("hidden");
      document.getElementById("analysis-empty-state").classList.remove("hidden");
      currentAnalysis = null;
    }
  } catch (e) {
    showToast("Error saat mengabaikan rekomendasi", "error");
  }
}

// ----------------- Timezone Utilities ----------------- //

function formatDualTime(dateInput) {
  if (!dateInput) return { gmt: "-", gmt7: "-" };
  let dt;
  if (typeof dateInput === 'string') {
    if (!dateInput.endsWith('Z') && !dateInput.includes('+') && dateInput.includes('T')) {
      dt = new Date(dateInput + 'Z');
    } else if (!dateInput.endsWith('Z') && !dateInput.includes('+') && !dateInput.includes('T')) {
      dt = new Date(dateInput.replace(' ', 'T') + 'Z');
    } else {
      dt = new Date(dateInput);
    }
  } else {
    dt = new Date(dateInput);
  }

  if (isNaN(dt.getTime())) return { gmt: "-", gmt7: "-" };

  const pad = n => String(n).padStart(2, '0');
  // 1. GMT (UTC)
  const gmt = `${pad(dt.getUTCDate())}/${pad(dt.getUTCMonth() + 1)}/${dt.getUTCFullYear()} ${pad(dt.getUTCHours())}:${pad(dt.getUTCMinutes())}:${pad(dt.getUTCSeconds())} GMT`;

  // 2. GMT+7 (WIB / Western Indonesia Time)
  const d7 = new Date(dt.getTime() + (7 * 60 * 60 * 1000));
  const gmt7 = `${pad(d7.getUTCDate())}/${pad(d7.getUTCMonth() + 1)}/${d7.getUTCFullYear()} ${pad(d7.getUTCHours())}:${pad(d7.getUTCMinutes())}:${pad(d7.getUTCSeconds())} GMT+7`;

  return { gmt, gmt7 };
}

// Live Dual Clock Runner (GMT+0 and GMT+7)
function startLiveClocks() {
  function tick() {
    const now = new Date();
    const pad = n => String(n).padStart(2, '0');

    // GMT+0 (UTC)
    const gmtH = pad(now.getUTCHours());
    const gmtM = pad(now.getUTCMinutes());
    const gmtS = pad(now.getUTCSeconds());
    const gmtEl = document.getElementById("clock-gmt");
    if (gmtEl) gmtEl.innerText = `${gmtH}:${gmtM}:${gmtS}`;

    // GMT+7 (WIB)
    const d7 = new Date(now.getTime() + (7 * 60 * 60 * 1000));
    const gmt7H = pad(d7.getUTCHours());
    const gmt7M = pad(d7.getUTCMinutes());
    const gmt7S = pad(d7.getUTCSeconds());
    const gmt7El = document.getElementById("clock-gmt7");
    if (gmt7El) gmt7El.innerText = `${gmt7H}:${gmt7M}:${gmt7S}`;
  }
  tick();
  setInterval(tick, 1000);
}

// ----------------- History Tab ----------------- //

function switchHistorySubTab(subTab) {
  const perfBtn = document.getElementById("subtab-btn-performance");
  const analBtn = document.getElementById("subtab-btn-analysis");
  const perfContent = document.getElementById("subtab-content-performance");
  const analContent = document.getElementById("subtab-content-analysis");

  if (!perfBtn || !analBtn) return;

  if (subTab === "performance") {
    perfBtn.className = "px-3 py-1.5 rounded-lg text-xs font-bold bg-blue-500/10 text-blue-400 border border-blue-500/30 transition";
    analBtn.className = "px-3 py-1.5 rounded-lg text-xs font-medium text-slate-400 hover:text-white transition";
    if (perfContent) perfContent.classList.remove("hidden");
    if (analContent) analContent.classList.add("hidden");
    loadTradingHistory();
  } else {
    analBtn.className = "px-3 py-1.5 rounded-lg text-xs font-bold bg-blue-500/10 text-blue-400 border border-blue-500/30 transition";
    perfBtn.className = "px-3 py-1.5 rounded-lg text-xs font-medium text-slate-400 hover:text-white transition";
    if (analContent) analContent.classList.remove("hidden");
    if (perfContent) perfContent.classList.add("hidden");
    loadHistory();
  }
}

async function manualCloseOrder(ticket, isPending, symbol) {
  const actionText = isPending ? "Batalkan Pending Order" : "Tutup Posisi Sekarang";
  const confirmMsg = isPending
    ? `Batalkan pending limit order MT5 #${ticket} (${symbol})?\nOrder akan dihapus dari terminal MT5.`
    : `Tutup posisi aktif MT5 #${ticket} (${symbol}) sekarang pada harga pasar saat ini?`;

  if (!confirm(confirmMsg)) return;

  showToast(`Memproses ${actionText.toLowerCase()} #${ticket}...`, "info");

  try {
    const res = await apiFetch("/api/order/close", {
      method: "POST",
      body: JSON.stringify({
        ticket: String(ticket),
        action_type: isPending ? "cancel_order" : "close_position"
      })
    });
    const data = await res.json();
    if (res.ok && data.success) {
      showToast(data.message || `Order #${ticket} berhasil diproses.`, "success");
      await loadTradingHistory();
      await pollSystemStatus();
    } else {
      showToast(data.detail || data.message || "Gagal memproses order di MT5", "error");
    }
  } catch (e) {
    showToast("Error saat menghubungi server", "error");
  }
}

async function loadTradingHistory() {
  const container = document.getElementById("trading-performance-container");
  if (!container) return;

  container.innerHTML = `<div class="text-center py-8 text-slate-500 text-xs"><span class="spinner mr-2"></span> Memuat performa & riwayat trading MT5...</div>`;

  try {
    const res = await apiFetch("/api/trading/performance");
    if (!res.ok) {
      container.innerHTML = `<div class="text-center py-6 text-red-400 text-xs">Gagal memuat data performa MT5.</div>`;
      return;
    }

    const data = await res.json();
    const summary = data.summary || {};
    const trades = data.trades || [];

    // 1. Update KPI Dashboard Metrics
    const winRate = summary.win_rate || 0.0;
    const lossRate = summary.loss_rate || 0.0;
    const winRateEl = document.getElementById("stat-win-rate");
    if (winRateEl) {
      winRateEl.textContent = `${winRate}%`;
      winRateEl.className = `text-2xl sm:text-3xl font-black ${winRate >= 50 ? 'text-emerald-400' : 'text-red-400'}`;
    }

    const winLossCountEl = document.getElementById("stat-win-loss-count");
    if (winLossCountEl) {
      winLossCountEl.textContent = `${summary.win_count || 0}W / ${summary.loss_count || 0}L`;
    }

    const winBar = document.getElementById("stat-win-bar");
    const lossBar = document.getElementById("stat-loss-bar");
    if (winBar && lossBar) {
      winBar.style.width = `${winRate}%`;
      lossBar.style.width = `${lossRate}%`;
    }

    const curr = summary.currency || "USC";
    const currEl = document.getElementById("stat-pnl-currency");
    if (currEl) currEl.textContent = curr;

    const netProfit = summary.total_net_profit || 0.0;
    const totalPnlEl = document.getElementById("stat-total-pnl");
    if (totalPnlEl) {
      const sign = netProfit > 0 ? "+" : "";
      totalPnlEl.textContent = `${sign}${netProfit.toFixed(2)}`;
      totalPnlEl.className = `text-2xl sm:text-3xl font-black ${netProfit >= 0 ? 'text-emerald-400' : 'text-red-400'}`;
    }

    const floatingPnl = summary.total_floating_profit || 0.0;
    const floatingEl = document.getElementById("stat-floating-pnl");
    if (floatingEl) {
      const fSign = floatingPnl > 0 ? "+" : "";
      floatingEl.textContent = `${fSign}${floatingPnl.toFixed(2)} ${curr}`;
      floatingEl.className = `font-mono ${floatingPnl >= 0 ? 'text-emerald-300' : 'text-red-400'}`;
    }

    const beCountEl = document.getElementById("stat-be-count");
    if (beCountEl) beCountEl.textContent = `${summary.breakeven_count || 0} Impas`;

    const pfEl = document.getElementById("stat-profit-factor");
    if (pfEl) pfEl.textContent = (summary.profit_factor || 0.0).toFixed(2);

    const grossWinEl = document.getElementById("stat-gross-win");
    if (grossWinEl) grossWinEl.textContent = `+${(summary.total_gross_profit || 0.0).toFixed(2)}`;

    const grossLossEl = document.getElementById("stat-gross-loss");
    if (grossLossEl) grossLossEl.textContent = `${(summary.total_gross_loss || 0.0).toFixed(2)}`;

    const totalTradesEl = document.getElementById("stat-total-trades");
    if (totalTradesEl) totalTradesEl.textContent = summary.total_ai_orders || 0;

    const openCountEl = document.getElementById("stat-open-count");
    if (openCountEl) openCountEl.textContent = `${summary.total_open_trades || 0} Open`;

    const pendingCountEl = document.getElementById("stat-pending-count");
    if (pendingCountEl) pendingCountEl.textContent = `${summary.total_pending_orders || 0} Pending`;

    // 2. Render Matched Trades List
    if (trades.length === 0) {
      container.innerHTML = `
        <div class="text-center py-12 glass-panel p-6 border-dashed border-slate-800 space-y-2">
          <div class="text-2xl">🎫</div>
          <div class="text-xs font-semibold text-slate-300">Belum Ada Trade AI yang Dieksekusi</div>
          <p class="text-[11px] text-slate-500 max-w-sm mx-auto">
            Lakukan analisa di tab <strong>🔍 Analisa</strong> lalu klik <strong>"Eksekusi Order MT5"</strong>. Tiket order akan otomatis dicocokkan dengan deals MT5 Anda di sini.
          </p>
        </div>
      `;
      return;
    }

    container.innerHTML = trades.map(t => {
      const openTime = t.open_time || { gmt: "-", wib: "-" };
      const closeTime = t.close_time || { gmt: "-", wib: "-" };

      let statusBadge = "bg-slate-800 text-slate-400 border border-slate-700";
      let pnlBadge = "";

      if (t.status === "WIN") {
        statusBadge = "bg-emerald-500/20 text-emerald-300 border border-emerald-500/40";
        pnlBadge = `<span class="px-2.5 py-1 rounded-lg text-xs font-black font-mono bg-emerald-500/20 text-emerald-300 border border-emerald-500/30">+${(t.profit || 0).toFixed(2)} ${curr}</span>`;
      } else if (t.status === "LOSS") {
        statusBadge = "bg-red-500/20 text-red-300 border border-red-500/40";
        pnlBadge = `<span class="px-2.5 py-1 rounded-lg text-xs font-black font-mono bg-red-500/20 text-red-300 border border-red-500/30">${(t.profit || 0).toFixed(2)} ${curr}</span>`;
      } else if (t.status === "OPEN") {
        statusBadge = "bg-blue-500/20 text-blue-300 border border-blue-500/40 animate-pulse";
        const sign = t.profit >= 0 ? "+" : "";
        pnlBadge = `<span class="px-2.5 py-1 rounded-lg text-xs font-black font-mono bg-blue-500/20 text-blue-300 border border-blue-500/30">${sign}${(t.profit || 0).toFixed(2)} ${curr} (Floating)</span>`;
      } else if (t.status === "PENDING") {
        statusBadge = "bg-amber-500/20 text-amber-300 border border-amber-500/40";
        pnlBadge = `<span class="px-2.5 py-1 rounded-lg text-xs font-semibold font-mono bg-amber-500/10 text-amber-300 border border-amber-500/20">Pending Entry</span>`;
      } else {
        pnlBadge = `<span class="px-2 py-0.5 rounded text-xs text-slate-400 bg-slate-800">0.00</span>`;
      }

      const isBuy = (t.action || "").includes("BUY");
      const actionBadge = isBuy
        ? `<span class="px-2 py-0.5 rounded text-xs font-bold font-mono bg-emerald-500/20 text-emerald-400 border border-emerald-500/30">BUY</span>`
        : `<span class="px-2 py-0.5 rounded text-xs font-bold font-mono bg-red-500/20 text-red-400 border border-red-500/30">SELL</span>`;

      let actionButton = "";
      if (t.status === "OPEN") {
        actionButton = `
          <button onclick="manualCloseOrder('${t.ticket}', false, '${t.symbol}')" class="px-2.5 py-1 rounded-lg text-xs font-bold bg-red-500/20 hover:bg-red-500/30 text-red-300 border border-red-500/40 transition flex items-center gap-1 shadow-sm" title="Tutup Posisi Sekarang pada Harga Pasar">
            <span>🛑 Tutup Posisi</span>
          </button>
        `;
      } else if (t.status === "PENDING") {
        actionButton = `
          <button onclick="manualCloseOrder('${t.ticket}', true, '${t.symbol}')" class="px-2.5 py-1 rounded-lg text-xs font-bold bg-amber-500/20 hover:bg-amber-500/30 text-amber-300 border border-amber-500/40 transition flex items-center gap-1 shadow-sm" title="Batalkan Pending Order di MT5">
            <span>❌ Batalkan Order</span>
          </button>
        `;
      }

      return `
        <div class="glass-panel p-4 space-y-3 border-white/5 hover:border-slate-700 transition">
          
          <!-- Top Row: Symbol, Action, Lot, PnL & Action Button -->
          <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
            <div class="flex items-center gap-2 flex-wrap">
              <span class="font-bold text-white text-sm sm:text-base">${t.symbol}</span>
              ${actionBadge}
              <span class="px-2 py-0.5 rounded text-xs font-mono font-semibold bg-slate-800 text-slate-300 border border-slate-700">${t.lot} Lot</span>
              <span class="px-2 py-0.5 rounded-full text-[10px] font-bold uppercase tracking-wider ${statusBadge}">
                ${t.status === 'WIN' ? 'WIN (Profit)' : (t.status === 'LOSS' ? 'LOSS (SL Hit)' : t.status)}
              </span>
            </div>
            <div class="flex items-center gap-2 self-start sm:self-auto flex-wrap">
              ${pnlBadge}
              ${actionButton}
            </div>
          </div>

          <!-- Dual Clocks: Open Time & Close Time (GMT+0 dan GMT+7) -->
          <div class="grid grid-cols-1 sm:grid-cols-2 gap-2 text-[11px] font-mono bg-slate-900/80 p-2.5 rounded-lg border border-slate-800/80">
            <div>
              <span class="text-slate-400 font-sans text-[10px] uppercase font-bold block mb-1">Waktu Buka (Open Time):</span>
              <div class="flex items-center gap-1.5 flex-wrap">
                <span class="px-2 py-0.5 rounded bg-slate-950 border border-slate-800 text-slate-300" title="Jam Pasar Forex (GMT+0)">
                  <span class="text-slate-500 text-[10px] font-sans font-semibold">🌐 GMT+0:</span> <strong class="text-white">${openTime.gmt.replace(' GMT', '')}</strong>
                </span>
                <span class="px-2 py-0.5 rounded bg-blue-500/10 border border-blue-500/20 text-blue-300" title="Waktu Lokal (GMT+7 / WIB)">
                  <span class="text-blue-400 text-[10px] font-sans font-semibold">🇮🇩 GMT+7:</span> <strong class="text-blue-200">${openTime.wib.replace(' WIB', '')}</strong>
                </span>
              </div>
            </div>
            <div>
              <span class="text-slate-400 font-sans text-[10px] uppercase font-bold block mb-1">Waktu Tutup (Close Time):</span>
              <div class="flex items-center gap-1.5 flex-wrap">
                <span class="px-2 py-0.5 rounded bg-slate-950 border border-slate-800 text-slate-300" title="Jam Pasar Forex (GMT+0)">
                  <span class="text-slate-500 text-[10px] font-sans font-semibold">🌐 GMT+0:</span> <strong class="text-white">${closeTime.gmt.replace(' GMT', '')}</strong>
                </span>
                <span class="px-2 py-0.5 rounded bg-blue-500/10 border border-blue-500/20 text-blue-300" title="Waktu Lokal (GMT+7 / WIB)">
                  <span class="text-blue-400 text-[10px] font-sans font-semibold">🇮🇩 GMT+7:</span> <strong class="text-blue-200">${closeTime.wib.replace(' WIB', '')}</strong>
                </span>
              </div>
            </div>
          </div>

          <!-- Prices Grid: Open, Close, SL, TP -->
          <div class="grid grid-cols-2 sm:grid-cols-4 gap-2 text-xs font-mono bg-slate-900/50 p-2 rounded-lg border border-slate-800/60">
            <div><span class="text-slate-500">Harga Buka:</span> <strong class="text-slate-200">${t.open_price || '-'}</strong></div>
            <div><span class="text-slate-500">Harga Tutup:</span> <strong class="text-slate-200">${t.close_price || (t.status === 'OPEN' ? 'Live' : '-')}</strong></div>
            <div><span class="text-slate-500">Stop Loss:</span> <strong class="text-red-400">${t.sl || '-'}</strong></div>
            <div><span class="text-slate-500">Take Profit:</span> <strong class="text-emerald-400">${t.tp || '-'}</strong></div>
          </div>

          <!-- Footer: Verification & Ticket -->
          <div class="flex flex-wrap items-center justify-between text-[11px] text-slate-500 pt-1 border-t border-slate-800/60 gap-2">
            <div class="flex items-center gap-2 flex-wrap">
              <span class="text-emerald-400">✓ Match AI Copilot</span>
              <span class="font-mono text-slate-400">Tiket: <strong>#${t.ticket}</strong></span>
              ${t.status === 'PENDING' ? '<span class="text-amber-400 font-mono text-[10px] flex items-center gap-1"><span>⏰</span> Auto-cancel jika belum tersentuh > 6 jam</span>' : ''}
              ${t.swap ? `<span class="text-slate-500 font-mono text-[10px]">Swap: ${t.swap}</span>` : ''}
              ${t.commission ? `<span class="text-slate-500 font-mono text-[10px]">Komisi: ${t.commission}</span>` : ''}
            </div>
            <span class="text-[10px] text-slate-500 italic truncate max-w-xs">${t.comment || 'AI-Copilot'}</span>
          </div>

        </div>
      `;
    }).join("");

  } catch (e) {
    console.error("loadTradingHistory error:", e);
    container.innerHTML = `<div class="text-center py-6 text-red-400 text-xs">Error saat memuat riwayat trading MT5.</div>`;
  }
}

async function loadHistory() {
  const container = document.getElementById("history-container");
  container.innerHTML = `<div class="text-center py-8 text-slate-500 text-xs"><span class="spinner mr-2"></span> Memuat riwayat...</div>`;

  try {
    const res = await apiFetch("/api/history?limit=30");
    if (res.ok) {
      const records = await res.json();
      if (records.length === 0) {
        container.innerHTML = `<div class="text-center py-10 text-slate-500 text-xs">Belum ada riwayat analisa atau order.</div>`;
        return;
      }

      container.innerHTML = records.map(r => {
        const dualTime = (r.time_gmt && r.time_wib) ? { gmt: r.time_gmt, gmt7: r.time_wib } : formatDualTime(r.timestamp);
        let statusBadge = "bg-slate-800 text-slate-400";
        if (r.execution_status === "EXECUTED") statusBadge = "bg-emerald-500/20 text-emerald-300 border border-emerald-500/30";
        if (r.execution_status === "REJECTED") statusBadge = "bg-red-500/20 text-red-300 border border-red-500/30";
        if (r.execution_status === "PENDING_USER") statusBadge = "bg-blue-500/20 text-blue-300 border border-blue-500/30";

        let actionColor = "text-amber-400";
        if (r.action.includes("BUY")) actionColor = "text-emerald-400";
        if (r.action.includes("SELL")) actionColor = "text-red-400";

        return `
          <div class="glass-panel p-4 space-y-2.5 border-white/5">
            <div class="flex flex-col sm:flex-row sm:items-center justify-between text-xs gap-2">
              <div class="flex items-center gap-2">
                <span class="font-bold text-white text-sm">${r.symbol}</span>
                <span class="font-bold font-mono ${actionColor}">[${r.action}]</span>
              </div>
              <span class="self-start sm:self-auto px-2.5 py-0.5 rounded-full text-[10px] font-bold uppercase tracking-wider ${statusBadge}">
                ${r.execution_status}
              </span>
            </div>

            <!-- Jam History 2 Versi: GMT+0 dan GMT+7 -->
            <div class="flex flex-wrap items-center gap-2 text-[11px] font-mono">
              <span class="inline-flex items-center gap-1.5 px-2 py-0.5 rounded bg-slate-900 border border-slate-800 text-slate-300" title="Jam Pasar Forex (GMT+0)">
                <span class="text-slate-400 font-sans text-[10px] uppercase font-bold">🌐 Jam Pasar (GMT+0):</span>
                <span class="text-white font-bold">${dualTime.gmt.replace(' GMT', '')}</span>
              </span>
              <span class="inline-flex items-center gap-1.5 px-2 py-0.5 rounded bg-blue-500/10 border border-blue-500/20 text-blue-300" title="Waktu Lokal (GMT+7 / WIB)">
                <span class="text-blue-400 font-sans text-[10px] uppercase font-bold">🇮🇩 Waktu Lokal (GMT+7):</span>
                <span class="text-blue-200 font-bold">${dualTime.gmt7.replace(' GMT+7', '').replace(' WIB', '')}</span>
              </span>
            </div>

            <div class="grid grid-cols-2 sm:grid-cols-4 gap-2 text-xs font-mono bg-slate-900/60 p-2.5 rounded-lg border border-slate-800">
              <div><span class="text-slate-500">Entry:</span> <strong class="text-slate-200">${r.entry_price || '-'}</strong></div>
              <div><span class="text-slate-500">SL:</span> <strong class="text-red-400">${r.stop_loss || '-'}</strong></div>
              <div><span class="text-slate-500">TP:</span> <strong class="text-emerald-400">${r.take_profit || '-'}</strong></div>
              <div><span class="text-slate-500">Lot:</span> <strong class="text-blue-400">${r.calculated_lot || 0.01} Lot</strong></div>
            </div>

            ${r.mt5_ticket_id ? `<div class="text-[11px] text-emerald-300 font-mono flex items-center gap-1"><span>🎫 Tiket MT5:</span> <strong>#${r.mt5_ticket_id}</strong></div>` : ''}
            
            <p class="text-xs text-slate-400 line-clamp-2">${r.ai_summary || ''}</p>
          </div>
        `;
      }).join("");
    }
  } catch (e) {
    container.innerHTML = `<div class="text-center py-6 text-red-400 text-xs">Gagal memuat riwayat.</div>`;
  }
}

// ----------------- MT5 Live Account & Balance ----------------- //

async function refreshMT5Account() {
  showToast("Memperbarui saldo MT5...", "info");
  try {
    const res = await apiFetch("/api/mt5/account");
    if (res.ok) {
      const data = await res.json();
      const acc = data.account || {};
      if (acc.connected) {
        const curr = acc.currency || 'USC';
        const balStr = curr === 'USD' ? `$${(acc.balance || 0).toLocaleString('en-US', { minimumFractionDigits: 2 })}` : `${(acc.balance || 0).toLocaleString('en-US', { minimumFractionDigits: 2 })} ${curr}`;
        const eqStr = curr === 'USD' ? `$${(acc.equity || 0).toLocaleString('en-US', { minimumFractionDigits: 2 })}` : `${(acc.equity || 0).toLocaleString('en-US', { minimumFractionDigits: 2 })} ${curr}`;
        document.getElementById("header-balance").innerText = balStr;
        document.getElementById("header-equity").innerText = eqStr;
        showToast(`Saldo MT5: ${balStr} (Equity: ${eqStr})`, "success");
      } else {
        showToast(acc.message || "Terminal MT5 belum terhubung atau offline.", "warning");
      }
      pollSystemStatus();
    } else {
      showToast("Gagal mengambil data akun MT5.", "error");
    }
  } catch (e) {
    showToast("Terjadi kesalahan jaringan saat refresh saldo MT5.", "error");
  }
}

// ----------------- Settings Tab ----------------- //

async function loadSettings() {
  try {
    const res = await apiFetch("/api/settings");
    if (res.ok) {
      const data = await res.json();
      document.getElementById("setting-mt5-account").value = data.mt5_account || "";
      document.getElementById("setting-mt5-password").value = data.mt5_password_masked || "";
      document.getElementById("setting-mt5-server").value = data.mt5_server || "HFMarkets-Demo";
      const pathEl = document.getElementById("setting-mt5-path");
      if (pathEl) pathEl.value = data.mt5_path || "";
      document.getElementById("setting-llm-provider").value = data.llm_provider || "openai";
      document.getElementById("setting-llm-model").value = data.llm_model || "gpt-4o";
      const keyEl = document.getElementById("setting-llm-key");
      keyEl.value = data.llm_api_key_masked || "";
      keyEl.dataset.hasKey = data.has_llm_api_key ? "true" : "false";
      if (data.has_llm_api_key) {
        keyEl.placeholder = "•••••••• (Tersimpan - Kosongkan jika tidak diubah)";
      } else {
        keyEl.placeholder = "sk-...";
      }
      document.getElementById("setting-llm-base-url").value = data.llm_base_url || "";
      document.getElementById("setting-max-risk").value = data.max_risk_percentage || 1.0;
      document.getElementById("setting-spread-buffer").value = data.default_spread_pips || 1.4;

      const nc = data.news_config || {};
      document.getElementById("news-toggle-ff").checked = nc.forex_factory !== false;
      const fjToggle = document.getElementById("news-toggle-fj");
      if (fjToggle) fjToggle.checked = nc.financialjuice !== false;
      document.getElementById("news-toggle-fl").checked = nc.forex_live !== false;
      document.getElementById("news-toggle-yf").checked = nc.yahoo_finance !== false;
      document.getElementById("news-toggle-gn").checked = nc.google_news !== false;
      document.getElementById("news-toggle-msn").checked = nc.msn_money !== false;

      const db = data.database || {};
      document.getElementById("setting-db-type").value = db.type || "sqlite";
      document.getElementById("setting-db-host").value = db.host || "localhost";
      document.getElementById("setting-db-port").value = db.port || 3306;
      document.getElementById("setting-db-user").value = db.user || "root";
      document.getElementById("setting-db-password").value = db.password_masked || "";
      document.getElementById("setting-db-name").value = db.database || "ai_trade";
    }
  } catch (e) {
    showToast("Gagal memuat pengaturan sistem", "error");
  }
}

async function handleSaveSettings(e) {
  e.preventDefault();
  const fjToggle = document.getElementById("news-toggle-fj");
  const pathEl = document.getElementById("setting-mt5-path");
  const payload = {
    mt5_account: document.getElementById("setting-mt5-account").value.trim(),
    mt5_password: document.getElementById("setting-mt5-password").value,
    mt5_server: document.getElementById("setting-mt5-server").value.trim(),
    mt5_path: pathEl ? pathEl.value.trim() : "",
    llm_provider: document.getElementById("setting-llm-provider").value,
    llm_model: document.getElementById("setting-llm-model").value.trim(),
    llm_api_key: document.getElementById("setting-llm-key").value.trim(),
    llm_base_url: document.getElementById("setting-llm-base-url").value.trim(),
    max_risk_percentage: parseFloat(document.getElementById("setting-max-risk").value) || 1.0,
    default_spread_pips: parseFloat(document.getElementById("setting-spread-buffer").value) || 1.4,
    news_config: {
      forex_factory: document.getElementById("news-toggle-ff").checked,
      financialjuice: fjToggle ? fjToggle.checked : true,
      forex_live: document.getElementById("news-toggle-fl").checked,
      yahoo_finance: document.getElementById("news-toggle-yf").checked,
      google_news: document.getElementById("news-toggle-gn").checked,
      msn_money: document.getElementById("news-toggle-msn").checked
    },
    db_config: {
      type: document.getElementById("setting-db-type").value,
      host: document.getElementById("setting-db-host").value.trim(),
      port: parseInt(document.getElementById("setting-db-port").value) || 3306,
      user: document.getElementById("setting-db-user").value.trim(),
      password: document.getElementById("setting-db-password").value,
      database: document.getElementById("setting-db-name").value.trim()
    }
  };

  try {
    const res = await apiFetch("/api/settings", {
      method: "POST",
      body: JSON.stringify(payload)
    });
    if (res.ok) {
      showToast("Pengaturan berhasil disimpan ke database & config.json!", "success");
      pollSystemStatus();
    } else {
      showToast("Gagal menyimpan pengaturan", "error");
    }
  } catch (err) {
    showToast("Kesalahan jaringan saat menyimpan pengaturan", "error");
  }
}

async function testDBConnection() {
  const type = document.getElementById("setting-db-type").value;
  const host = document.getElementById("setting-db-host").value.trim();
  const port = parseInt(document.getElementById("setting-db-port").value) || 3306;
  const user = document.getElementById("setting-db-user").value.trim();
  const password = document.getElementById("setting-db-password").value;
  const database = document.getElementById("setting-db-name").value.trim();

  showToast(`Menguji koneksi ke ${type === 'mysql' ? 'Remote MySQL' : 'SQLite'}...`, "info");
  try {
    const res = await apiFetch("/api/settings/test-db", {
      method: "POST",
      body: JSON.stringify({ type, host, port, user, password, database })
    });
    const data = await res.json();
    if (data.success) {
      showToast(data.message, "success");
    } else {
      showToast(data.message, "error");
    }
  } catch (e) {
    showToast("Error saat menguji koneksi basis data", "error");
  }
}

async function testMT5Connection() {
  const account = document.getElementById("setting-mt5-account").value.trim();
  const password = document.getElementById("setting-mt5-password").value;
  const server = document.getElementById("setting-mt5-server").value.trim();
  const pathEl = document.getElementById("setting-mt5-path");
  const path = pathEl ? pathEl.value.trim() : "";

  showToast("Menguji koneksi ke terminal MT5...", "info");
  try {
    const res = await apiFetch("/api/settings/test-mt5", {
      method: "POST",
      body: JSON.stringify({ account, password, server, path })
    });
    const data = await res.json();
    if (data.success) {
      showToast(data.message || `Koneksi MT5 Sukses! Saldo: $${data.balance}`, "success");
      pollSystemStatus();
    } else {
      showToast(data.message || "Koneksi MT5 Gagal. Cek terminal MT5 Anda.", "error");
    }
  } catch (e) {
    showToast("Error saat menguji MT5", "error");
  }
}

async function testLLMConnection() {
  const provider = document.getElementById("setting-llm-provider").value;
  const keyEl = document.getElementById("setting-llm-key");
  const api_key = keyEl.value.trim();
  const model = document.getElementById("setting-llm-model").value.trim();
  const base_url = document.getElementById("setting-llm-base-url").value.trim();
  const hasSavedKey = keyEl.dataset.hasKey === "true" || api_key.startsWith("****");

  if (!api_key && !base_url && !hasSavedKey) {
    showToast("Ketikkan API Key atau Base URL untuk pengujian", "warning");
    return;
  }

  showToast(`Menguji koneksi ke ${base_url ? 'custom base URL' : provider}...`, "info");
  try {
    const res = await apiFetch("/api/settings/test-llm", {
      method: "POST",
      body: JSON.stringify({ provider, api_key, model, base_url })
    });
    const data = await res.json();
    if (data.success) {
      showToast(data.message, "success");
    } else {
      showToast(data.message, "error");
    }
  } catch (e) {
    showToast("Error saat menguji LLM API", "error");
  }
}

// ----------------- App Lifecycle Initialization ----------------- //

async function initializeApp() {
  const isAuthed = await checkAuth();
  if (isAuthed) {
    await loadSymbols();
    await pollSystemStatus();
    // Poll status every 8 seconds
    setInterval(pollSystemStatus, 8000);
  }
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", () => {
    startLiveClocks();
    initializeApp();
  });
} else {
  startLiveClocks();
  initializeApp();
}
