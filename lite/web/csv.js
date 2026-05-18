// Pure CSV utilities shared between the browser app and Node tests.
// Loaded as a classic script in the browser (defines globals consumed by
// app.js) and as a CommonJS module by node:test (via module.exports).

function csvEscape(v) {
  if (v == null) return "";
  const s = String(v);
  return /[",\r\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
}

function arrayToCSV(rows, columns) {
  const header = columns.map(c => csvEscape(c.header)).join(",");
  const body = rows.map((row, i) =>
    columns.map(c => csvEscape(c.value ? c.value(row, i) : row[c.key])).join(",")
  ).join("\r\n");
  // UTF-8 BOM so Excel on Windows detects the encoding.
  return "﻿" + header + "\r\n" + body + "\r\n";
}

function downloadCSV(filename, csv) {
  const blob = new Blob([csv], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 0);
}

function tsStamp() {
  const d = new Date();
  const pad = n => String(n).padStart(2, "0");
  return `${d.getFullYear()}${pad(d.getMonth() + 1)}${pad(d.getDate())}` +
         `-${pad(d.getHours())}${pad(d.getMinutes())}${pad(d.getSeconds())}`;
}

if (typeof module !== "undefined" && module.exports) {
  // downloadCSV is intentionally not exported (requires DOM + Blob).
  module.exports = { csvEscape, arrayToCSV, tsStamp };
}
