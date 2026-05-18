// Unit tests for the pure CSV helpers shared by the lite leaderboard's
// Export CSV button. Run via: node --test tests/test_csv.js
// (also invoked by ./run-tests.sh after the pytest suite).

const { test } = require("node:test");
const assert = require("node:assert/strict");
const path = require("node:path");

const { csvEscape, arrayToCSV, tsStamp } = require(
  path.join(__dirname, "..", "web", "csv.js"),
);

const BOM = "﻿";

test("csvEscape passes simple ASCII through unquoted", () => {
  assert.equal(csvEscape("hello"), "hello");
  assert.equal(csvEscape("B62qABCDEFGH"), "B62qABCDEFGH");
});

test("csvEscape treats null and undefined as empty strings", () => {
  assert.equal(csvEscape(null), "");
  assert.equal(csvEscape(undefined), "");
});

test("csvEscape stringifies numbers without quoting", () => {
  assert.equal(csvEscape(0), "0");
  assert.equal(csvEscape(42), "42");
  assert.equal(csvEscape(3.14), "3.14");
});

test("csvEscape quotes values containing comma, double-quote, CR, LF", () => {
  assert.equal(csvEscape("a,b"), '"a,b"');
  assert.equal(csvEscape("line1\nline2"), '"line1\nline2"');
  assert.equal(csvEscape("car\rriage"), '"car\rriage"');
  assert.equal(csvEscape('she said "hi"'), '"she said ""hi"""');
});

test("arrayToCSV emits BOM, header, CRLF data rows, trailing CRLF", () => {
  const rows = [{ a: 1, b: "x" }, { a: 2, b: "y" }];
  const cols = [
    { header: "a", key: "a" },
    { header: "b", key: "b" },
  ];
  const csv = arrayToCSV(rows, cols);
  assert.ok(csv.startsWith(BOM), "starts with UTF-8 BOM");
  assert.equal(csv, BOM + "a,b\r\n1,x\r\n2,y\r\n");
});

test("arrayToCSV with empty rows produces just the header (plus BOM and trailing CRLF)", () => {
  const cols = [{ header: "a", key: "a" }];
  assert.equal(arrayToCSV([], cols), BOM + "a\r\n\r\n");
});

test("arrayToCSV supports derived columns via column.value()", () => {
  const rows = [{ k: "A" }, { k: "B" }];
  const cols = [
    { header: "rank", value: (_row, i) => i + 1 },
    { header: "k", key: "k" },
  ];
  assert.equal(arrayToCSV(rows, cols), BOM + "rank,k\r\n1,A\r\n2,B\r\n");
});

test("arrayToCSV preserves full untruncated public keys (the whole point of the export)", () => {
  const fullKey = "B62qoooooooooooooooooooooooooooooooooooooooooooooooooo";
  const rows = [{ submitter: fullKey, score: 100 }];
  const cols = [
    { header: "submitter", key: "submitter" },
    { header: "score", key: "score" },
  ];
  const csv = arrayToCSV(rows, cols);
  assert.ok(csv.includes(fullKey), "full key present in output");
  assert.ok(!csv.includes("…"), "no truncation ellipsis in output");
});

test("arrayToCSV escapes commas inside string fields", () => {
  const rows = [{ k: "B62qA", validation_error: "bad signature, retry" }];
  const cols = [
    { header: "k", key: "k" },
    { header: "validation_error", key: "validation_error" },
  ];
  const csv = arrayToCSV(rows, cols);
  assert.ok(csv.includes('"bad signature, retry"'));
});

test("arrayToCSV emits null/undefined fields as empty (not the literal string 'null')", () => {
  const rows = [{ a: null, b: undefined, c: 0 }];
  const cols = [
    { header: "a", key: "a" },
    { header: "b", key: "b" },
    { header: "c", key: "c" },
  ];
  assert.equal(arrayToCSV(rows, cols), BOM + "a,b,c\r\n,,0\r\n");
});

test("arrayToCSV ISO timestamp fields pass through verbatim", () => {
  // Server returns ISO strings via _row_dates_iso(...); confirm they survive untouched.
  const rows = [{ ts: "2026-05-18T13:35:42" }];
  const cols = [{ header: "ts", key: "ts" }];
  const csv = arrayToCSV(rows, cols);
  assert.ok(csv.includes("2026-05-18T13:35:42"));
});

test("tsStamp matches YYYYMMDD-HHMMSS shape", () => {
  assert.match(tsStamp(), /^\d{8}-\d{6}$/);
});
