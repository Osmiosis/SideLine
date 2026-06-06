import test from "node:test";
import assert from "node:assert/strict";
import { allowedDeliverables, restrictDeliverables, friendlyState }
  from "../js/jobcopy.js";

test("segments may pick all three deliverables", () => {
  assert.deepEqual(allowedDeliverables(20),
    ["coach_analytics", "event_highlights", "player_highlights"]);
});

test("full matches are analytics-only (launch scope)", () => {
  assert.deepEqual(allowedDeliverables(21), ["coach_analytics"]);
});

test("restrictDeliverables drops disallowed picks, never returns empty", () => {
  assert.deepEqual(restrictDeliverables(90, ["event_highlights"]), ["coach_analytics"]);
  assert.deepEqual(restrictDeliverables(10, ["event_highlights"]), ["event_highlights"]);
  assert.deepEqual(restrictDeliverables(10, []), ["coach_analytics"]);
});

test("approved jobs show the uploader", () => {
  const v = friendlyState({ state: "approved" });
  assert.equal(v.showUpload, true);
  assert.equal(v.tone, "ok");
});

test("ready jobs expose the results link", () => {
  const v = friendlyState({ state: "ready", results_url: "https://drive.google.com/x" });
  assert.equal(v.showResults, true);
});

test("rejected jobs surface the reason", () => {
  const v = friendlyState({ state: "rejected", reject_reason: "Not a fixed camera." });
  assert.match(v.detail, /Not a fixed camera/);
  assert.equal(v.tone, "bad");
});

test("state_detail from the cloud row wins over the fallback copy", () => {
  const v = friendlyState({ state: "processing", state_detail: "Tracking players" });
  assert.equal(v.detail, "Tracking players");
});
