const $ = (s) => document.querySelector(s);
const tbody = $("#submitters tbody");
const detailBody = $("#detail-rows tbody");

let cached = [];
let sortField = "submissions";
let sortDir = -1;

async function fetchJSON(url) {
  const r = await fetch(url);
  if (!r.ok) throw new Error(`${url}: HTTP ${r.status}`);
  return r.json();
}

function fmtDate(s) {
  if (!s) return "—";
  return new Date(s).toLocaleString();
}

function truncate(s, n = 12) {
  if (!s) return "";
  return s.length <= n ? s : `${s.slice(0, n)}…`;
}

function verifiedLabel(verified) {
  if (verified === true) return '<span class="ok">✓</span>';
  if (verified === false) return '<span class="bad">✗</span>';
  return '<span class="muted">…</span>';
}

function renderList() {
  const sorted = [...cached].sort((a, b) => {
    const av = a[sortField], bv = b[sortField];
    if (av === bv) return 0;
    if (av == null) return 1;
    if (bv == null) return -1;
    return av < bv ? -sortDir : sortDir;
  });
  tbody.innerHTML = "";
  for (const row of sorted) {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td><a href="#" data-pk="${row.submitter}"><code>${truncate(row.submitter, 24)}</code></a></td>
      <td class="num">${row.submissions}</td>
      <td class="num ok">${row.chain_verified ?? 0}</td>
      <td class="num bad">${row.chain_rejected ?? 0}</td>
      <td class="num muted">${row.chain_pending ?? 0}</td>
      <td class="num">${row.blocks_produced ?? 0}</td>
      <td>${fmtDate(row.last_seen)}</td>
    `;
    tbody.appendChild(tr);
  }
  $("#submitter-count").textContent = cached.length;
  $("#empty").hidden = cached.length !== 0;
}

async function loadList() {
  $("#error").hidden = true;
  try {
    cached = await fetchJSON("/api/submitters");
    renderList();
    $("#refreshed").textContent = new Date().toLocaleTimeString();
  } catch (e) {
    $("#error").hidden = false;
    $("#error").textContent = `Error loading submitters: ${e.message}`;
  }
}

function drawSparkline(canvas, buckets) {
  const ctx = canvas.getContext("2d");
  const w = canvas.width;
  const h = canvas.height;
  ctx.clearRect(0, 0, w, h);
  if (!buckets || buckets.length === 0) return;
  const max = buckets.reduce((m, b) => Math.max(m, b.submissions), 1);
  const barW = w / buckets.length;
  for (let i = 0; i < buckets.length; i++) {
    const b = buckets[i];
    const ratio = b.submissions / max;
    const barH = Math.max(1, ratio * (h - 4));
    const x = i * barW;
    const y = h - barH;
    ctx.fillStyle = b.chain_verified > 0
      ? "#1e8449"
      : b.submissions > 0 ? "#f5b041" : "#dddddd";
    ctx.fillRect(x + 0.5, y, Math.max(1, barW - 1), barH);
  }
}

async function loadUptime(pubkey) {
  try {
    const data = await fetchJSON(
      `/api/uptime/${encodeURIComponent(pubkey)}?window=24&bucket_minutes=15`,
    );
    $("#uptime-summary").innerHTML = `
      Coverage (24h): <strong>${data.coverage_pct}%</strong>
      &middot; On-chain: <strong>${data.chain_verified_pct}%</strong>
      &middot; ${data.buckets.length} buckets of ${data.bucket_minutes} min
    `;
    drawSparkline($("#uptime-sparkline"), data.buckets);
  } catch (e) {
    $("#uptime-summary").textContent = `Uptime unavailable: ${e.message}`;
  }
}

async function showDetail(pubkey) {
  detailBody.innerHTML = "";
  $("#detail-pubkey").textContent = pubkey;
  $("#detail").hidden = false;
  $("#list").hidden = true;
  $("#uptime-summary").textContent = "Loading…";
  loadUptime(pubkey);
  try {
    const rows = await fetchJSON(`/api/submitter/${encodeURIComponent(pubkey)}`);
    for (const r of rows) {
      const isCreator = r.block_creator && r.block_creator === pubkey;
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td>${fmtDate(r.submitted_at)}</td>
        <td><code>${truncate(r.block_hash || "", 24)}</code></td>
        <td class="num">${verifiedLabel(r.verified)}</td>
        <td><code>${isCreator ? "self" : truncate(r.block_creator || "", 20)}</code></td>
        <td>${r.validation_error || ""}</td>
      `;
      detailBody.appendChild(tr);
    }
  } catch (e) {
    detailBody.innerHTML = `<tr><td colspan="5">Error: ${e.message}</td></tr>`;
  }
}

function hideDetail() {
  $("#detail").hidden = true;
  $("#list").hidden = false;
}

tbody.addEventListener("click", (e) => {
  const link = e.target.closest("a[data-pk]");
  if (!link) return;
  e.preventDefault();
  showDetail(link.dataset.pk);
});

$("#back").addEventListener("click", hideDetail);
$("#refresh").addEventListener("click", loadList);

document.querySelectorAll("#submitters thead th").forEach((th) => {
  th.addEventListener("click", () => {
    const field = th.dataset.sort;
    if (!field) return;
    if (sortField === field) sortDir = -sortDir;
    else { sortField = field; sortDir = -1; }
    renderList();
  });
});

loadList();
setInterval(loadList, 30000);
