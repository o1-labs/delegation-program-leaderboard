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
      <td class="num">${row.valid}</td>
      <td class="num invalid">${row.invalid}</td>
      <td>${fmtDate(row.last_seen)}</td>
      <td>${fmtDate(row.first_seen)}</td>
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

async function showDetail(pubkey) {
  detailBody.innerHTML = "";
  $("#detail-pubkey").textContent = pubkey;
  $("#detail").hidden = false;
  $("#list").hidden = true;
  try {
    const rows = await fetchJSON(`/api/submitter/${encodeURIComponent(pubkey)}`);
    for (const r of rows) {
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td>${fmtDate(r.submitted_at)}</td>
        <td class="num">${r.height ?? ""}</td>
        <td class="num">${r.slot ?? ""}</td>
        <td><code>${truncate(r.block_hash || "", 20)}</code></td>
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
