// Frozen contract names (Plan 1) + plain-English copy for every job state
// (spec §4, §6). Pure module — unit-tested in node, imported by pages.
export const SEGMENT_MAX_MIN = 20;

export const ALL_DELIVERABLES = [
  ["coach_analytics", "Coach analytics"],
  ["event_highlights", "Event highlights"],
  ["player_highlights", "Player highlights"],
];

export function allowedDeliverables(durationMin) {
  return durationMin > SEGMENT_MAX_MIN
    ? ["coach_analytics"]
    : ALL_DELIVERABLES.map(([k]) => k);
}

export function restrictDeliverables(durationMin, selected) {
  const allowed = allowedDeliverables(durationMin);
  const kept = selected.filter((d) => allowed.includes(d));
  return kept.length ? kept : ["coach_analytics"];
}

const COPY = {
  submitted: ["Awaiting review",
    "We're looking at your submission — you'll get an email when it's reviewed.", "warn"],
  approved: ["Approved — upload your footage",
    "Pick your video file below to start the upload.", "ok"],
  quota_waiting: ["In line for storage",
    "Our storage is full right now — you're in line and we'll email you.", "warn"],
  uploading: ["Uploading",
    "Your footage is on its way. Keep this page open until it finishes.", "warn"],
  uploaded: ["Footage received",
    "Processing starts when the studio comes online.", "ok"],
  processing: ["Processing",
    "The studio is working on your match.", "warn"],
  operator_action: ["Waiting for studio review",
    "A person is checking your match — this can take a little while.", "warn"],
  ready: ["Your analysis is ready",
    "Download it below before it expires.", "ok"],
  expired: ["Expired",
    "These results have been cleaned up. You can submit the match again.", ""],
  rejected: ["Not accepted",
    "This submission was not accepted.", "bad"],
  failed: ["Something went wrong",
    "We hit a problem with this match. You can submit it again.", "bad"],
};

export function friendlyState(job) {
  const [label, fallback, tone] = COPY[job.state] ?? [job.state, "", ""];
  let detail = job.state_detail || fallback;
  if (job.state === "rejected" && job.reject_reason) {
    detail = `${fallback} Reason: ${job.reject_reason}`;
  }
  if (job.state === "failed" && job.error_message) detail = job.error_message;
  return {
    label, detail, tone,
    showUpload: ["approved", "uploading", "quota_waiting"].includes(job.state),
    showResults: job.state === "ready" && !!job.results_url,
  };
}
