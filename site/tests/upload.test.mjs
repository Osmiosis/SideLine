import test from "node:test";
import assert from "node:assert/strict";
import { CHUNK, chunkRange, parseRangeOffset, probeHeader } from "../js/upload.js";

test("CHUNK is a multiple of 256 KiB (Drive resumable-upload rule)", () => {
  assert.equal(CHUNK % (256 * 1024), 0);
});

test("chunkRange covers a mid-file chunk", () => {
  const r = chunkRange(CHUNK, CHUNK * 3);
  assert.equal(r.start, CHUNK);
  assert.equal(r.end, CHUNK * 2 - 1);
  assert.equal(r.header, `bytes ${CHUNK}-${CHUNK * 2 - 1}/${CHUNK * 3}`);
});

test("chunkRange clamps the final partial chunk", () => {
  const total = CHUNK + 1000;
  const r = chunkRange(CHUNK, total);
  assert.equal(r.end, total - 1);
  assert.equal(r.header, `bytes ${CHUNK}-${total - 1}/${total}`);
});

test("parseRangeOffset resumes after the last confirmed byte", () => {
  assert.equal(parseRangeOffset("bytes=0-8388607"), 8388608);
});

test("parseRangeOffset treats a missing header as start-over", () => {
  assert.equal(parseRangeOffset(null), 0);
  assert.equal(parseRangeOffset(""), 0);
});

test("probeHeader formats the resume probe (Content-Range: bytes */total)", () => {
  assert.equal(probeHeader(123), "bytes */123");
});
