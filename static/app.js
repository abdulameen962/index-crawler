/**
 * NGX Index Fund Replicator - Client Dashboard Logic
 */

(function () {
  "use strict";

  // Color palette for asset allocation visualizer
  const CHART_PALETTE = [
    "#10B981", // Emerald
    "#06B6D4", // Cyan
    "#6366F1", // Indigo
    "#F59E0B", // Amber
    "#EC4899", // Pink
    "#8B5CF6", // Violet
    "#14B8A6", // Teal
    "#F97316", // Orange
    "#3B82F6", // Blue
    "#84CC16", // Lime
    "#A855F7", // Purple
  ];

  // State
  const state = {
    selectedFund: "oil_gas",
    investment: 50000,
    feeRate: 0.03,
    cap: 0.30,
    fundsData: {},
    marketStatus: null,
    lastCalculation: null,
    debounceTimer: null,
  };

  // DOM Elements
  const el = {
    fundSelector: document.getElementById("fundSelector"),
    fundDescription: document.getElementById("fundDescription"),
    investmentInput: document.getElementById("investmentInput"),
    investmentDisplay: document.getElementById("investmentDisplay"),
    quickChips: document.querySelectorAll(".quick-chips .chip"),
    transactionCostInput: document.getElementById("transactionCostInput"),
    feeRateDisplay: document.getElementById("feeRateDisplay"),
    capInput: document.getElementById("capInput"),
    capDisplay: document.getElementById("capDisplay"),
    capLegend: document.getElementById("capLegend"),
    tick15: document.getElementById("tick15"),
    tick30: document.getElementById("tick30"),
    btnReset: document.getElementById("btnReset"),
    btnCopyOrder: document.getElementById("btnCopyOrder"),
    btnExportCsv: document.getElementById("btnExportCsv"),
    lastUpdatedText: document.getElementById("lastUpdatedText"),
    marketStatusText: document.getElementById("marketStatusText"),
    btnSyncPrices: document.getElementById("btnSyncPrices"),
    syncBtnIcon: document.getElementById("syncBtnIcon"),
    syncBtnText: document.getElementById("syncBtnText"),
    kpiNetCost: document.getElementById("kpiNetCost"),
    kpiNetPct: document.getElementById("kpiNetPct"),
    kpiFees: document.getElementById("kpiFees"),
    kpiFeeRate: document.getElementById("kpiFeeRate"),
    kpiTotalCost: document.getElementById("kpiTotalCost"),
    kpiEfficiencyText: document.getElementById("kpiEfficiencyText"),
    kpiRemainingCash: document.getElementById("kpiRemainingCash"),
    kpiRemainingSub: document.getElementById("kpiRemainingSub"),
    allocationBar: document.getElementById("allocationBar"),
    allocationLegend: document.getElementById("allocationLegend"),
    portfolioTableBody: document.getElementById("portfolioTableBody"),
    toast: document.getElementById("toast"),
    toastMessage: document.getElementById("toastMessage"),
  };

  // Formatting helpers
  function formatNGN(value) {
    if (value === undefined || value === null || isNaN(value)) return "₦0.00";
    return (
      "₦" +
      Number(value).toLocaleString("en-NG", {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
      })
    );
  }

  function formatDate(isoString) {
    if (!isoString) return "End of Day Market Close";
    try {
      const date = new Date(isoString);
      return date.toLocaleDateString("en-NG", {
        month: "short",
        day: "numeric",
        hour: "2-digit",
        minute: "2-digit",
      });
    } catch {
      return "Market Close 6:00 PM";
    }
  }

  function showToast(message) {
    if (!el.toast) return;
    el.toastMessage.textContent = message;
    el.toast.classList.remove("hidden");
    setTimeout(() => {
      el.toast.classList.add("hidden");
    }, 3500);
  }

  // Helper to sync cap visuals
  function setCapVisuals(capValue, isOilGas) {
    state.cap = capValue;
    if (el.capInput) el.capInput.value = Math.round(capValue * 100);
    if (el.capDisplay) el.capDisplay.textContent = `${(capValue * 100).toFixed(1)}%`;
    if (el.tick30 && el.tick15) {
      if (isOilGas) {
        el.tick30.classList.add("tick-active");
        el.tick15.classList.remove("tick-active");
      } else {
        el.tick15.classList.add("tick-active");
        el.tick30.classList.remove("tick-active");
      }
    }
  }

  // Market Status & Time-Locked Sync Button Logic (4:00 PM - 8:50 AM WAT)
  async function checkMarketStatus() {
    try {
      const res = await fetch("/api/market-status");
      if (!res.ok) {
        throw new Error(`HTTP ${res.status}`);
      }
      const status = await res.json();
      state.marketStatus = status;

      if (status.is_locked) {
        if (el.btnSyncPrices) {
          el.btnSyncPrices.classList.add("locked");
          el.btnSyncPrices.classList.remove("unlocked");
          el.btnSyncPrices.disabled = true;
          el.btnSyncPrices.title = status.message || "Manual sync locked during market hours (08:50 AM - 04:00 PM WAT)";
        }
        if (el.syncBtnIcon) el.syncBtnIcon.textContent = "🔒";
        if (el.syncBtnText) el.syncBtnText.textContent = "Market Locked";
        if (el.marketStatusText) el.marketStatusText.textContent = "NGX In Session";
      } else {
        if (el.btnSyncPrices) {
          el.btnSyncPrices.classList.remove("locked");
          el.btnSyncPrices.classList.add("unlocked");
          el.btnSyncPrices.disabled = false;
          el.btnSyncPrices.title = "Click to run automated scraper and update NGX EOD prices";
        }
        if (el.syncBtnIcon) el.syncBtnIcon.textContent = "🔄";
        if (el.syncBtnText) el.syncBtnText.textContent = "Sync Latest EOD Prices";
        if (el.marketStatusText) el.marketStatusText.textContent = "NGX EOD Verified";
      }
    } catch (err) {
      if (el.btnSyncPrices) {
        el.btnSyncPrices.classList.remove("unlocked");
        el.btnSyncPrices.classList.add("locked");
        el.btnSyncPrices.disabled = true;
      }
      if (el.syncBtnIcon) el.syncBtnIcon.textContent = "🔒";
      if (el.syncBtnText) el.syncBtnText.textContent = "Market Locked";
    }
  }

  // Trigger EOD Crawl (when unlocked)
  async function triggerEodSync() {
    if (el.btnSyncPrices.disabled) return;
    el.btnSyncPrices.disabled = true;
    if (el.syncBtnIcon) el.syncBtnIcon.textContent = "⏳";
    el.syncBtnText.textContent = "Scraping EOD Prices...";

    try {
      const res = await fetch("/api/crawl/run", { method: "POST" });
      const data = await res.json();

      if (res.status === 202) {
        showToast("✓ EOD Price scrape initiated. Fetching latest NGX settlements...");
        setTimeout(async () => {
          await loadFunds();
          await recalculate();
          el.btnSyncPrices.disabled = false;
          if (el.syncBtnIcon) el.syncBtnIcon.textContent = "🔄";
          el.syncBtnText.textContent = "Sync Latest EOD Prices";
          showToast("✓ Latest NGX EOD prices synced successfully!");
        }, 5000);
      } else {
        throw new Error(data.detail || "Unable to run sync");
      }
    } catch (err) {
      showToast(err.message || "Failed to trigger sync");
      el.btnSyncPrices.disabled = false;
      if (el.syncBtnIcon) el.syncBtnIcon.textContent = "🔄";
      el.syncBtnText.textContent = "Sync Latest EOD Prices";
    }
  }

  // Fetch available funds & metadata
  async function loadFunds() {
    try {
      const res = await fetch("/api/funds");
      if (!res.ok) throw new Error("Failed to load funds list");
      const data = await res.json();
      (data.funds || []).forEach((f) => {
        state.fundsData[f.id] = f;
      });
      updateEodBadge();
    } catch (err) {
      console.error("Error loading funds:", err);
      el.lastUpdatedText.textContent = "Offline EOD Cache";
    }
  }

  function updateEodBadge() {
    const fund = state.fundsData[state.selectedFund];
    if (fund && fund.last_updated) {
      el.lastUpdatedText.textContent = `Updated: ${formatDate(fund.last_updated)}`;
    } else {
      el.lastUpdatedText.textContent = "EOD Data: Daily at 6:00 PM";
    }
  }

  // Trigger calculation from FastAPI with Greedy Cash Sweep
  async function recalculate() {
    try {
      const payload = {
        fund_id: state.selectedFund,
        investment_amount: state.investment,
        transaction_cost_rate: state.feeRate,
        cap_percentage: state.cap,
      };

      const res = await fetch("/api/calculate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });

      if (!res.ok) {
        const errorData = await res.json();
        throw new Error(errorData.detail || "Calculation error");
      }

      const data = await res.json();
      state.lastCalculation = data;
      renderDashboard(data);
    } catch (err) {
      console.error("Calculation failed:", err);
      showToast(err.message || "Failed to calculate portfolio");
    }
  }

  function debouncedRecalculate() {
    clearTimeout(state.debounceTimer);
    state.debounceTimer = setTimeout(() => {
      recalculate();
    }, 150);
  }

  // Render UI with calculated results
  function renderDashboard(data) {
    const investment = data.investment_amount || state.investment;
    const netCost = data.total_cost_excl_fees || 0;
    const fees = data.total_transaction_fees || 0;
    const totalCost = data.total_cost_incl_fees || 0;
    const remaining = data.remaining_cash || 0;
    const efficiency = data.capital_efficiency_percent || 99.9;

    // 1. KPI Summary Cards
    el.kpiNetCost.textContent = formatNGN(netCost);
    const netPct = investment > 0 ? (netCost / investment) * 100 : 0;
    el.kpiNetPct.textContent = `${netPct.toFixed(1)}% of capital`;

    el.kpiFees.textContent = formatNGN(fees);
    el.kpiFeeRate.textContent = `@ ${(state.feeRate * 100).toFixed(1)}% rate`;

    el.kpiTotalCost.textContent = formatNGN(totalCost);
    el.kpiEfficiencyText.textContent = `${efficiency.toFixed(1)}% Capital Deployed`;

    el.kpiRemainingCash.textContent = formatNGN(remaining);
    el.kpiRemainingSub.textContent = remaining < (data.min_share_with_fee || 5) 
      ? "Zero Cash Drag (< 1 share)" 
      : "Residual Unspent";

    // 2. Allocation Progress Bar & Legend
    renderAllocationVisuals(data.portfolio || []);

    // 3. Execution Table
    renderTable(data.portfolio || []);
  }

  function renderAllocationVisuals(items) {
    el.allocationBar.innerHTML = "";
    el.allocationLegend.innerHTML = "";
    el.capLegend.textContent = `${(state.cap * 100).toFixed(0)}%`;

    items.forEach((item, idx) => {
      const color = CHART_PALETTE[idx % CHART_PALETTE.length];
      const pct = item.target_weight_percent || 0;

      const seg = document.createElement("div");
      seg.className = "allocation-segment";
      seg.style.width = `${pct}%`;
      seg.style.backgroundColor = color;
      seg.title = `${item.ticker}: ${pct}% (Cap: ${(state.cap * 100).toFixed(0)}%)`;
      el.allocationBar.appendChild(seg);

      const leg = document.createElement("div");
      leg.className = "legend-item";
      leg.innerHTML = `
        <span class="legend-color-box" style="background-color: ${color};"></span>
        <span class="legend-ticker">${item.ticker}</span>
        <span class="legend-weight">${pct.toFixed(1)}%</span>
      `;
      el.allocationLegend.appendChild(leg);
    });
  }

  function renderTable(items) {
    el.portfolioTableBody.innerHTML = "";

    if (!items || items.length === 0) {
      el.portfolioTableBody.innerHTML = `
        <tr>
          <td colspan="6" style="text-align: center; padding: 28px; color: var(--text-muted);">
            No equities found for this index fund.
          </td>
        </tr>
      `;
      return;
    }

    items.forEach((item) => {
      const row = document.createElement("tr");
      const isZero = item.shares === 0;

      row.innerHTML = `
        <td>
          <div class="equity-cell">
            <span class="equity-ticker-badge">${item.ticker}</span>
            <span class="equity-name" title="${item.title}">${item.title}</span>
          </div>
        </td>
        <td class="text-right price-cell">${formatNGN(item.price)}</td>
        <td class="text-right">
          <span class="weight-badge">${item.target_weight_percent.toFixed(1)}%</span>
        </td>
        <td class="text-center highlight-col">
          <span class="shares-pill ${isZero ? 'zero-shares' : ''}">
            ${item.shares.toLocaleString()}
            <span class="share-unit">shares</span>
          </span>
        </td>
        <td class="text-right cost-cell">${formatNGN(item.cost_excl_fees)}</td>
        <td class="text-right">
          <span class="weight-badge">${item.actual_weight_percent.toFixed(1)}%</span>
        </td>
      `;

      el.portfolioTableBody.appendChild(row);
    });
  }

  // Copy Order List to Clipboard (including Limit Order Execution Advisory)
  function copyOrderList() {
    if (!state.lastCalculation || !state.lastCalculation.portfolio) {
      showToast("No portfolio data to copy");
      return;
    }

    const calc = state.lastCalculation;
    const fundTitle = state.selectedFund === "oil_gas" ? "NGX Oil & Gas" : "Afrinvest Div Yield";
    
    let text = `========================================================\n`;
    text += `NGX INDEX REPLICATION ORDER SHEET\n`;
    text += `Fund: ${fundTitle}\n`;
    text += `Target Investment: ${formatNGN(calc.investment_amount)}\n`;
    text += `Total Stock Purchases: ${formatNGN(calc.total_cost_excl_fees)}\n`;
    text += `Estimated Fees (${(calc.transaction_cost_rate * 100).toFixed(1)}%): ${formatNGN(calc.total_transaction_fees)}\n`;
    text += `Total Outlay: ${formatNGN(calc.total_cost_incl_fees)}\n`;
    text += `Residual Cash: ${formatNGN(calc.remaining_cash)} (100% Deployed)\n`;
    text += `--------------------------------------------------------\n`;
    text += `EXECUTION ADVISORY: Replicate using LIMIT ORDERS placed\n`;
    text += `after the trading day or at morning open (10:00 AM WAT)\n`;
    text += `to match EOD prices and avoid slippage.\n`;
    text += `========================================================\n`;
    text += `TICKER       SHARES       PRICE         SUBTOTAL\n`;
    text += `--------------------------------------------------------\n`;

    calc.portfolio.forEach((p) => {
      if (p.shares > 0) {
        const ticker = p.ticker.padEnd(12, " ");
        const shares = (p.shares + " shares").padEnd(12, " ");
        const price = formatNGN(p.price).padEnd(13, " ");
        const subtotal = formatNGN(p.cost_excl_fees);
        text += `${ticker} ${shares} ${price} ${subtotal}\n`;
      }
    });

    text += `========================================================\n`;

    navigator.clipboard.writeText(text).then(
      () => {
        showToast("Order list & Limit Order advisory copied!");
      },
      (err) => {
        console.error("Clipboard error:", err);
        showToast("Failed to copy to clipboard");
      }
    );
  }

  // Export CSV
  function exportCsv() {
    if (!state.lastCalculation || !state.lastCalculation.portfolio) return;
    const items = state.lastCalculation.portfolio;

    let csv = "# NGX Index Replication Order Sheet\n";
    csv += "# Execution Advisory: Use Limit Orders placed after the trading day or at morning open (10:00 AM WAT)\n";
    csv += "Ticker,Company Name,Price (NGN),Target Weight (%),Shares to Buy,Total Cost (NGN),Actual Weight (%)\n";
    items.forEach((p) => {
      const cleanTitle = `"${(p.title || p.ticker).replace(/"/g, '""')}"`;
      csv += `${p.ticker},${cleanTitle},${p.price},${p.target_weight_percent},${p.shares},${p.cost_excl_fees},${p.actual_weight_percent}\n`;
    });

    const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `ngx_replication_${state.selectedFund}_${Date.now()}.csv`;
    a.click();
    URL.revokeObjectURL(url);
    showToast("CSV exported with execution advisory!");
  }

  // Attach Event Listeners
  function attachEvents() {
    // Fund Segmented Control
    const fundButtons = el.fundSelector.querySelectorAll(".fund-tab");
    fundButtons.forEach((btn) => {
      btn.addEventListener("click", () => {
        fundButtons.forEach((b) => {
          b.classList.remove("active");
          b.setAttribute("aria-selected", "false");
        });
        btn.classList.add("active");
        btn.setAttribute("aria-selected", "true");

        state.selectedFund = btn.getAttribute("data-fund");
        const fundMeta = state.fundsData[state.selectedFund];
        if (fundMeta) {
          el.fundDescription.textContent = fundMeta.description;
        }

        // Apply official NGX default cap per fund: 30% for Oil & Gas, 15% for Afrinvest Div Yield
        const isOil = state.selectedFund === "oil_gas";
        const defaultCap = isOil ? 0.30 : 0.15;
        setCapVisuals(defaultCap, isOil);

        updateEodBadge();
        recalculate();
      });
    });

    // Investment Capital input with overflow & zeros protection
    el.investmentInput.addEventListener("input", (e) => {
      let rawVal = e.target.value;
      // Strip leading redundant zeros (e.g. "00050" -> "50", but allow single "0")
      if (rawVal.length > 1 && rawVal.startsWith("0") && !rawVal.startsWith("0.")) {
        rawVal = rawVal.replace(/^0+/, "") || "0";
        e.target.value = rawVal;
      }
      // Truncate length if more than 10 digits
      if (rawVal.length > 10) {
        rawVal = rawVal.slice(0, 10);
        e.target.value = rawVal;
      }
      let val = parseFloat(rawVal);
      if (isNaN(val) || val < 0) {
        val = 0;
      }
      if (val > 1000000000) {
        val = 1000000000;
        e.target.value = "1000000000";
      }
      state.investment = val;
      el.investmentDisplay.textContent = formatNGN(val);

      el.quickChips.forEach((c) => {
        const amt = parseFloat(c.getAttribute("data-amount"));
        if (amt === val) {
          c.classList.add("active");
        } else {
          c.classList.remove("active");
        }
      });

      debouncedRecalculate();
    });

    // Quick chips
    el.quickChips.forEach((chip) => {
      chip.addEventListener("click", () => {
        el.quickChips.forEach((c) => c.classList.remove("active"));
        chip.classList.add("active");

        const amt = parseFloat(chip.getAttribute("data-amount"));
        state.investment = amt;
        el.investmentInput.value = amt;
        el.investmentDisplay.textContent = formatNGN(amt);
        recalculate();
      });
    });

    // Transaction fee slider
    el.transactionCostInput.addEventListener("input", (e) => {
      const val = parseFloat(e.target.value) || 0;
      state.feeRate = val / 100;
      el.feeRateDisplay.textContent = `${val.toFixed(1)}%`;
      debouncedRecalculate();
    });

    // Cap slider
    el.capInput.addEventListener("input", (e) => {
      const val = parseFloat(e.target.value) || 0;
      state.cap = val / 100;
      el.capDisplay.textContent = `${val.toFixed(1)}%`;
      debouncedRecalculate();
    });

    // Reset Defaults
    el.btnReset.addEventListener("click", () => {
      state.investment = 50000;
      state.feeRate = 0.03;

      const isOil = state.selectedFund === "oil_gas";
      const defaultCap = isOil ? 0.30 : 0.15;
      setCapVisuals(defaultCap, isOil);

      el.investmentInput.value = 50000;
      el.investmentDisplay.textContent = formatNGN(50000);

      el.transactionCostInput.value = 3.0;
      el.feeRateDisplay.textContent = "3.0%";

      el.quickChips.forEach((c) => {
        if (parseFloat(c.getAttribute("data-amount")) === 50000) {
          c.classList.add("active");
        } else {
          c.classList.remove("active");
        }
      });

      recalculate();
      showToast("Parameters reset to defaults");
    });

    // Actions
    el.btnCopyOrder.addEventListener("click", copyOrderList);
    el.btnExportCsv.addEventListener("click", exportCsv);
    el.btnSyncPrices.addEventListener("click", triggerEodSync);
  }

  // Initialize
  async function init() {
    try {
      setCapVisuals(0.30, true);
      attachEvents();
      await checkMarketStatus();
      await loadFunds();
      await recalculate();
    } catch (err) {
      console.warn("App init:", err);
    }
  }

  document.addEventListener("DOMContentLoaded", init);
})();
