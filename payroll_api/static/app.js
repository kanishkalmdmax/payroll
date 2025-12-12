const form = document.getElementById("payrollForm");
const statusEl = document.getElementById("status");
const analyzeBtn = document.getElementById("analyzeBtn");

const resultsCard = document.getElementById("resultsCard");
const summaryEl = document.getElementById("summary");
const warningsEl = document.getElementById("warnings");
const rawEl = document.getElementById("rawJson");
const toggleRawBtn = document.getElementById("toggleRaw");

const downloadLink = document.getElementById("downloadLink");

function setStatus(msg, isError=false){
  statusEl.textContent = msg;
  statusEl.style.color = isError ? "#b91c1c" : "#64748b";
}

function escapeHtml(s){
  return String(s).replace(/[&<>"']/g, (m) => ({
    "&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"
  }[m]));
}

function renderTable(containerId, rows){
  const container = document.getElementById(containerId);
  if (!rows || rows.length === 0){
    container.innerHTML = "<div class='muted'>No records flagged.</div>";
    return;
  }
  const cols = Object.keys(rows[0]);
  const maxRows = 50;
  const show = rows.slice(0, maxRows);

  let html = "<div class='tableWrap'><table><thead><tr>";
  for (const c of cols){ html += `<th>${escapeHtml(c)}</th>`; }
  html += "</tr></thead><tbody>";

  for (const r of show){
    html += "<tr>";
    for (const c of cols){ html += `<td>${escapeHtml(r[c])}</td>`; }
    html += "</tr>";
  }
  html += "</tbody></table></div>";

  if (rows.length > maxRows){
    html += `<div class='muted' style='margin-top:8px;'>Showing first ${maxRows} of ${rows.length} rows. Download the report for full output.</div>`;
  }

  container.innerHTML = html;
}

toggleRawBtn.addEventListener("click", () => {
  const isHidden = rawEl.style.display === "none";
  rawEl.style.display = isHidden ? "block" : "none";
  toggleRawBtn.textContent = isHidden ? "Hide raw JSON" : "Show raw JSON";
});

form.addEventListener("submit", async (e) => {
  e.preventDefault();
  setStatus("");
  resultsCard.style.display = "none";
  warningsEl.style.display = "none";
  downloadLink.style.display = "none";
  rawEl.style.display = "none";
  toggleRawBtn.textContent = "Show raw JSON";

  const fileInput = document.getElementById("file");
  const startDate = document.getElementById("start_date").value;
  const endDate = document.getElementById("end_date").value;

  if (!fileInput.files || fileInput.files.length === 0){
    setStatus("Please choose a file.", true);
    return;
  }
  if (!startDate || !endDate){
    setStatus("Please select both start and end dates.", true);
    return;
  }
  if (startDate > endDate){
    setStatus("Start date must be earlier than or equal to end date.", true);
    return;
  }

  const fd = new FormData(form);

  analyzeBtn.disabled = true;
  setStatus("Uploading and analyzing...");

  try{
    const res = await fetch("/payroll/analyze", {
      method: "POST",
      body: fd
    });

    const isJson = (res.headers.get("content-type") || "").includes("application/json");
    const payload = isJson ? await res.json() : { detail: await res.text() };

    if (!res.ok){
      const msg = payload?.detail || "Request failed.";
      setStatus(msg, true);
      return;
    }

    // Render results
    resultsCard.style.display = "block";
    const reqId = payload.request_id;

    const s = payload.summary || {};
    const flags = (s.flags || {});
    summaryEl.innerHTML = `
      <div style="margin-top:10px;">
        <span class="badge">request_id: ${escapeHtml(reqId)}</span>
        <span class="badge">rows received: ${escapeHtml(s.rows_received)}</span>
        <span class="badge">rows after filter: ${escapeHtml(s.rows_after_filter)}</span>
        <span class="badge">employees: ${escapeHtml(s.employees)}</span>
      </div>
      <div style="margin-top:10px; color:#334155;">
        Flags — excess daily: <b>${escapeHtml(flags.excess_daily_hours || 0)}</b>,
        low rest: <b>${escapeHtml(flags.low_rest_hours || 0)}</b>,
        weekly excess: <b>${escapeHtml(flags.weekly_excess_hours || 0)}</b>,
        excess days: <b>${escapeHtml(flags.excess_working_days || 0)}</b>
      </div>
    `;

    renderTable("table_excess_hours", payload.flagged_excess_hours);
    renderTable("table_low_rest", payload.flagged_low_rest_hours);
    renderTable("table_weekly_excess", payload.flagged_weekly_excess);
    renderTable("table_excess_days", payload.flagged_excess_days);

    // warnings
    if (payload.warnings && payload.warnings.length){
      warningsEl.style.display = "block";
      warningsEl.innerHTML = "<b>Warnings:</b><br>" + payload.warnings.map(escapeHtml).join("<br>");
    }

    // raw json
    rawEl.textContent = JSON.stringify(payload, null, 2);

    // download
    if (payload.download_url){
      downloadLink.href = payload.download_url;
      downloadLink.style.display = "inline-flex";
    }

    setStatus("Done.");
  } catch (err){
    setStatus("Network or server error. Check Render logs and try again.", true);
  } finally{
    analyzeBtn.disabled = false;
  }
});
