# Online Hosting Plan 2: Public Website (Cloudflare Pages) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the public site — magic-link login, match submission, job status with chunked Drive upload (progress / pause / resume / retry), and the admin approve-reject view with quota gauge — deployed free on Cloudflare Pages against the Plan 1 cloud layer.

**Architecture:** A new `site/` directory of plain HTML + ES-module JS (no framework, no build step) deployed as static files to Cloudflare Pages. It talks to Supabase with `@supabase/supabase-js` (ESM CDN) using only the anon key (RLS enforces access), calls the four Plan 1 Edge Functions (`mint-upload`, `complete-upload`, `decide`, `quota`), and PUTs file chunks straight to Google via minted resumable session URIs. Visual language is adapted from the local operator UI (`Website/index.html` — "Sideline" tactics-board look). Spec: `docs/superpowers/specs/2026-06-05-online-hosting-design.md` §6.

**Tech Stack:** Cloudflare Pages + `wrangler` CLI (via `npx`), Supabase JS v2 from `esm.sh`, vanilla ES modules, `node --test` for pure-logic unit tests, existing Python `pytest` suite as the cloud regression check.

**Conventions for this plan:**
- All shell commands are PowerShell, run from repo root `C:\sports-ai`.
- Frozen contracts from Plan 1 are reused verbatim: sports `football`/`basketball`; deliverables `coach_analytics`/`event_highlights`/`player_highlights`; job states `submitted, approved, quota_waiting, uploading, uploaded, processing, operator_action, ready, expired, rejected, failed`.
- The `decide` function emails link to `${SITE_ORIGIN}/job.html?id=<job_id>` — therefore the per-job page MUST be named `job.html` at site root.
- Plan 1 set the function secret `SITE_ORIGIN=http://localhost:8788` — that is exactly `wrangler pages dev`'s default port, so local dev works without secret changes until Task 9.
- The Supabase **anon key is safe to commit** (spec §7: "browser only ever sees the Supabase anon key — safe by design; RLS enforces access"). No other secret ever enters `site/`.
- Plain-English copy everywhere; never show technical errors to users (spec §6).
- Deploys to Supabase/Cloudflare were pre-authorized by the operator in Plan 1 ("deploys are approved, run them yourself").

---

### Task 1: Site scaffold — config, API helper, stylesheet

**Files:**
- Create: `site/js/config.js`
- Create: `site/js/api.js`
- Create: `site/styles.css`

- [ ] **Step 1: Write `site/js/config.js`**

Read `supabase/tests/.env` and copy the real values of `SUPABASE_URL` and `SUPABASE_ANON_KEY` into this file (the anon key is public by design — see conventions):

```js
// Public client config. The anon key is safe to ship: RLS is the gate.
export const SUPABASE_URL = "https://qphkhchhdurvylrunaoz.supabase.co";
export const SUPABASE_ANON_KEY = "<paste the SUPABASE_ANON_KEY value from supabase/tests/.env>";
```

- [ ] **Step 2: Write `site/js/api.js`**

```js
// Shared Supabase client + tiny DOM/format helpers for every page.
import { createClient } from "https://esm.sh/@supabase/supabase-js@2";
import { SUPABASE_URL, SUPABASE_ANON_KEY } from "./config.js";

export const sb = createClient(SUPABASE_URL, SUPABASE_ANON_KEY);

export function el(id) {
  return document.getElementById(id);
}

export function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

export function fmtBytes(n) {
  if (!Number.isFinite(n)) return "?";
  const units = ["B", "KB", "MB", "GB", "TB"];
  let i = 0;
  while (n >= 1024 && i < units.length - 1) { n /= 1024; i++; }
  return `${n.toFixed(n >= 10 || i === 0 ? 0 : 1)} ${units[i]}`;
}

/** Redirect to login when not signed in. Returns the signed-in user. */
export async function requireUser() {
  // a magic-link redirect carries the session in the URL hash; give the
  // client a moment to exchange it before deciding we're signed out
  if (location.hash.includes("access_token")) {
    await new Promise((resolve) => {
      const { data: { subscription } } = sb.auth.onAuthStateChange((event) => {
        if (event === "SIGNED_IN" || event === "INITIAL_SESSION") {
          subscription.unsubscribe();
          resolve();
        }
      });
      setTimeout(resolve, 3000); // never hang the page on a stale hash
    });
  }
  const { data: { session } } = await sb.auth.getSession();
  if (!session) {
    location.replace("index.html");
    throw new Error("not signed in");
  }
  return session.user;
}

/** RLS only lets a user see their OWN app_admins row — perfect for this. */
export async function isAdmin(userId) {
  const { data } = await sb.from("app_admins")
    .select("user_id").eq("user_id", userId).maybeSingle();
  return data !== null;
}

/** Wire the shared header nav (admin link visibility + sign out). */
export async function initNav(user) {
  const adminLink = el("adminLink");
  if (adminLink && await isAdmin(user.id)) adminLink.classList.remove("hidden");
  const out = el("signout");
  if (out) {
    out.onclick = async (e) => {
      e.preventDefault();
      await sb.auth.signOut();
      location.replace("index.html");
    };
  }
}

/** Invoke an Edge Function; throws with the function's friendly message. */
export async function callFn(name, body = {}) {
  const { data, error } = await sb.functions.invoke(name, { body });
  if (error) {
    let msg = "Something went wrong. Please try again.";
    try { msg = (await error.context.json()).error ?? msg; } catch { /* keep default */ }
    throw new Error(msg);
  }
  return data;
}
```

- [ ] **Step 3: Write `site/styles.css`**

Adapted from the local operator UI's design tokens (`Website/index.html` lines 16–46) — same "Sideline" tactics-board palette and type, reduced to a lightweight page kit:

```css
/* ============================================================
   SIDELINE — public site. Same tactics-board language as the
   local operator UI (Website/index.html), reduced to a page kit.
   ============================================================ */
:root{
  --ink:       oklch(16% 0.018 152);
  --ink-deep:  oklch(12.5% 0.016 152);
  --surface:   oklch(20% 0.020 152);
  --surface-2: oklch(24% 0.022 154);
  --surface-3: oklch(29% 0.024 154);
  --fg:        oklch(94% 0.014 95);
  --muted:     oklch(72% 0.018 120);
  --faint:     oklch(55% 0.018 130);
  --line:      oklch(31% 0.018 152);
  --line-2:    oklch(42% 0.022 152);
  --accent:    oklch(87% 0.19 126);
  --accent-2:  oklch(80% 0.17 128);
  --accent-ink:oklch(23% 0.05 140);
  --amber:     oklch(82% 0.14 75);
  --card-red:  oklch(63% 0.20 25);
  --font-display:'Bricolage Grotesque','Hanken Grotesk',system-ui,sans-serif;
  --font:        'Hanken Grotesk',system-ui,sans-serif;
  --mono:        'JetBrains Mono',ui-monospace,monospace;
  --r: 10px;
  --ease: cubic-bezier(.22,1,.36,1);
}
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:var(--font);background:var(--ink);color:var(--fg);min-height:100vh;-webkit-font-smoothing:antialiased}
.wrap{max-width:860px;margin:0 auto;padding:28px 20px 80px}
header.top{display:flex;align-items:center;justify-content:space-between;gap:14px;padding:6px 0 26px;flex-wrap:wrap}
.brand{font-family:var(--font-display);font-weight:800;font-size:20px;letter-spacing:-.03em;text-decoration:none;color:var(--fg)}
.brand b{color:var(--accent)}
nav a{color:var(--muted);text-decoration:none;font-size:14px;margin-left:16px}
nav a:hover{color:var(--fg)}
h1{font-family:var(--font-display);font-weight:800;letter-spacing:-.03em;font-size:clamp(26px,5vw,38px);line-height:1.05;margin-bottom:10px}
h3{font-family:var(--font-display);font-weight:700;letter-spacing:-.02em;font-size:18px;margin-bottom:8px}
.sub{color:var(--muted);font-size:15px;line-height:1.6;max-width:56ch;margin-bottom:26px}
.card{background:var(--surface);border:1px solid var(--line);border-radius:var(--r);padding:20px}
.card+.card{margin-top:14px}
label{display:block;font-size:13px;color:var(--muted);margin:14px 0 6px;font-weight:600}
input,select{width:100%;padding:11px 12px;border-radius:8px;border:1px solid var(--line-2);background:var(--ink-deep);color:var(--fg);font-size:15px;font-family:inherit}
input:focus,select:focus{outline:2px solid var(--accent);outline-offset:-1px;border-color:transparent}
.checks{display:flex;flex-wrap:wrap;gap:10px;margin-top:8px}
.checks label{display:flex;align-items:center;gap:8px;margin:0;padding:10px 12px;border:1px solid var(--line-2);border-radius:8px;cursor:pointer;font-weight:500;color:var(--fg)}
.checks input{width:auto}
.checks label.off{opacity:.4;pointer-events:none}
.btn{display:inline-flex;align-items:center;gap:8px;padding:11px 18px;border-radius:8px;font-family:var(--font-display);font-weight:600;font-size:14px;border:1px solid transparent;cursor:pointer;transition:.2s var(--ease);text-decoration:none}
.btn-primary{background:var(--accent);color:var(--accent-ink)}
.btn-primary:hover{background:var(--accent-2);transform:translateY(-1px)}
.btn-ghost{background:transparent;color:var(--fg);border-color:var(--line-2)}
.btn-ghost:hover{background:var(--surface-2)}
.btn-danger{background:transparent;color:var(--card-red);border-color:var(--card-red)}
.btn[disabled]{opacity:.4;pointer-events:none}
.badge{display:inline-block;font-family:var(--mono);font-size:11px;letter-spacing:.08em;text-transform:uppercase;padding:4px 9px;border-radius:99px;border:1px solid var(--line-2);color:var(--muted)}
.badge.ok{color:var(--accent);border-color:var(--accent)}
.badge.warn{color:var(--amber);border-color:var(--amber)}
.badge.bad{color:var(--card-red);border-color:var(--card-red)}
.progress{height:10px;border-radius:99px;background:var(--ink-deep);border:1px solid var(--line);overflow:hidden;margin:12px 0 6px}
.progress>div{height:100%;background:var(--accent);width:0%;transition:width .3s var(--ease)}
.mono{font-family:var(--mono);font-size:12.5px;color:var(--faint)}
.msg{margin-top:12px;font-size:14px;color:var(--muted);line-height:1.5}
.msg.err{color:var(--card-red)}
.msg a{color:var(--accent)}
table{width:100%;border-collapse:collapse;font-size:14px}
th,td{text-align:left;padding:10px 8px;border-bottom:1px solid var(--line)}
th{font-family:var(--mono);font-size:11px;letter-spacing:.12em;text-transform:uppercase;color:var(--faint);font-weight:500}
.joblist a.card{display:block;text-decoration:none;color:inherit;transition:.2s var(--ease)}
.joblist a.card:hover{border-color:var(--line-2)}
.row{display:flex;justify-content:space-between;align-items:center;gap:12px;flex-wrap:wrap}
.hidden{display:none}
```

- [ ] **Step 4: Smoke-check the dev server**

Run: `npx wrangler pages dev site` (first run downloads wrangler; answer no to telemetry if asked).
Expected: serves at `http://localhost:8788`. Open it — a 404/directory listing is fine (no index.html yet). Stop with Ctrl+C.

- [ ] **Step 5: Commit**

```powershell
git add site/js/config.js site/js/api.js site/styles.css
git commit -m "feat(site): public site scaffold - client config, api helper, sideline styles"
```

---

### Task 2: Job copy + launch-scope rules (TDD)

**Files:**
- Create: `site/tests/jobcopy.test.mjs`
- Create: `site/js/jobcopy.js`

- [ ] **Step 1: Write the failing tests**

`site/tests/jobcopy.test.mjs`:

```js
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `node --test site/tests/`
Expected: FAIL — `Cannot find module ... jobcopy.js`.

- [ ] **Step 3: Write `site/js/jobcopy.js`**

```js
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `node --test site/tests/`
Expected: 7 pass, 0 fail.

- [ ] **Step 5: Commit**

```powershell
git add site/js/jobcopy.js site/tests/jobcopy.test.mjs
git commit -m "feat(site): job state copy + launch-scope deliverable rules, tested"
```

---

### Task 3: Chunked Drive uploader (TDD on the pure parts)

**Files:**
- Create: `site/tests/upload.test.mjs`
- Create: `site/js/upload.js`

The chunk/offset math is unit-tested in node. The `DriveUploader` class itself uses `XMLHttpRequest` (the only browser API with upload progress events) so it runs in the browser only — it is exercised live in Task 7's manual check and Task 9's rehearsal.

- [ ] **Step 1: Write the failing tests**

`site/tests/upload.test.mjs`:

```js
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `node --test site/tests/`
Expected: jobcopy tests pass; upload tests FAIL — `Cannot find module ... upload.js`.

- [ ] **Step 3: Write `site/js/upload.js`**

```js
// Google Drive resumable-upload client (spec §2). The minted session URI
// authenticates by itself — these requests carry NO Authorization header.
// Pure helpers are unit-tested in node; DriveUploader is browser-only (XHR
// is the one API with upload progress events).
export const CHUNK = 32 * 1024 * 1024; // multiple of 256 KiB (Drive rule)

export function chunkRange(offset, total, chunk = CHUNK) {
  const end = Math.min(offset + chunk, total) - 1;
  return { start: offset, end, header: `bytes ${offset}-${end}/${total}` };
}

export function parseRangeOffset(rangeHeader) {
  // Drive 308 responses confirm received bytes as "bytes=0-12345"
  const m = /bytes=\d+-(\d+)/.exec(rangeHeader ?? "");
  return m ? Number(m[1]) + 1 : 0;
}

export function probeHeader(total) {
  return `bytes */${total}`;
}

const MAX_RETRIES = 5;

export class DriveUploader {
  constructor(file, sessionUri, onProgress = () => {}) {
    this.file = file;
    this.uri = sessionUri;
    this.onProgress = onProgress;
    this.paused = false;
    this.xhr = null;
  }

  /** Abort the in-flight chunk; start(resumeOffset()) continues later. */
  pause() {
    this.paused = true;
    this.xhr?.abort();
  }

  /** Upload from `fromOffset` to the end. Resolves with Drive's file JSON. */
  async start(fromOffset = 0) {
    this.paused = false;
    let offset = fromOffset, retries = 0;
    while (true) {
      try {
        const r = await this.#putChunk(offset);
        if (r.done) return r.file;
        offset = r.next;
        retries = 0;
      } catch (e) {
        if (e.paused || ++retries > MAX_RETRIES) throw e;
        await new Promise((res) => setTimeout(res, 2000 * retries));
        offset = await this.resumeOffset(); // re-sync after a network drop
      }
    }
  }

  /** Ask Drive how much it already has (resume-after-disconnect, spec §2). */
  resumeOffset() {
    return new Promise((resolve) => {
      const xhr = new XMLHttpRequest();
      xhr.open("PUT", this.uri);
      xhr.setRequestHeader("Content-Range", probeHeader(this.file.size));
      xhr.onload = () => resolve(
        xhr.status === 308 ? parseRangeOffset(xhr.getResponseHeader("Range")) : 0);
      xhr.onerror = () => resolve(0);
      xhr.send();
    });
  }

  #putChunk(offset) {
    const { end, header } = chunkRange(offset, this.file.size);
    const blob = this.file.slice(offset, end + 1);
    return new Promise((resolve, reject) => {
      const xhr = this.xhr = new XMLHttpRequest();
      xhr.open("PUT", this.uri);
      xhr.setRequestHeader("Content-Range", header);
      xhr.upload.onprogress = (e) =>
        this.onProgress(Math.round(((offset + e.loaded) / this.file.size) * 100));
      xhr.onload = () => {
        if (xhr.status === 308) {            // chunk accepted, more to come
          resolve({ done: false, next: parseRangeOffset(xhr.getResponseHeader("Range")) });
        } else if (xhr.status === 200 || xhr.status === 201) {  // whole file in
          resolve({ done: true, file: JSON.parse(xhr.responseText) });
        } else {
          reject(new Error(`upload chunk failed: ${xhr.status}`));
        }
      };
      xhr.onabort = () =>
        reject(Object.assign(new Error("paused"), { paused: true }));
      xhr.onerror = () => reject(new Error("network error during upload"));
      xhr.send(blob);
    });
  }
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `node --test site/tests/`
Expected: 13 pass (7 jobcopy + 6 upload), 0 fail.

- [ ] **Step 5: Commit**

```powershell
git add site/js/upload.js site/tests/upload.test.mjs
git commit -m "feat(site): chunked drive uploader with pause/resume, chunk math tested"
```

---

### Task 4: Login page (magic links)

**Files:**
- Create: `site/index.html`

- [ ] **Step 1: Allow localhost redirects in Supabase Auth (manual, 2 min)**

Supabase dashboard → Authentication → URL Configuration → **Redirect URLs** → add:

```
http://localhost:8788/*
```

(The production `*.pages.dev` URL is added in Task 9.) Record this in `supabase/SETUP.md` later (Task 9 commits it).

- [ ] **Step 2: Write `site/index.html`**

```html
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Sideline — Sign in</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:opsz,wght@12..96,400..800&family=Hanken+Grotesk:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600&display=swap" rel="stylesheet">
<link rel="stylesheet" href="styles.css">
</head>
<body>
<div class="wrap" style="max-width:460px">
  <header class="top"><a class="brand" href="index.html">Side<b>line</b></a></header>
  <h1>Match analysis for your club</h1>
  <p class="sub">Send us your footage, get back coach analytics and highlights.
     Sign in with your email — we'll send you a magic link. No password needed.</p>
  <div class="card">
    <label for="email">Email</label>
    <input id="email" type="email" placeholder="you@club.com" autocomplete="email">
    <div style="margin-top:16px">
      <button id="send" class="btn btn-primary">Send magic link</button>
    </div>
    <p id="msg" class="msg"></p>
  </div>
</div>
<script type="module">
  import { sb, el } from "./js/api.js";

  // already signed in (or just landed back from the magic link) → go to jobs
  sb.auth.onAuthStateChange((_event, session) => {
    if (session) location.replace("jobs.html");
  });
  const { data: { session } } = await sb.auth.getSession();
  if (session) location.replace("jobs.html");

  el("send").onclick = async () => {
    const email = el("email").value.trim();
    if (!email) return;
    el("send").disabled = true;
    const { error } = await sb.auth.signInWithOtp({
      email,
      options: { emailRedirectTo: `${location.origin}/jobs.html` },
    });
    el("msg").textContent = error
      ? "Couldn't send the link — please check the address and try again."
      : "Check your email — your sign-in link is on its way.";
    el("msg").className = error ? "msg err" : "msg";
    el("send").disabled = false;
  };
</script>
</body>
</html>
```

- [ ] **Step 3: Manual check**

Run: `npx wrangler pages dev site` → open `http://localhost:8788`.
1. Page renders in the Sideline look (dark pitch-green, lime accent).
2. Enter your real email → "Check your email…" appears.
3. Click the magic link in the email → browser lands on `jobs.html` (404 for now — that's Task 6; the session is stored regardless).

Note: the built-in Supabase sender allows ~3-4 emails/hour per address — sign in once and the session persists across all later manual checks.

- [ ] **Step 4: Commit**

```powershell
git add site/index.html
git commit -m "feat(site): magic-link login page"
```

---

### Task 5: Submit page

**Files:**
- Create: `site/submit.html`

- [ ] **Step 1: Write `site/submit.html`**

```html
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Sideline — Submit a match</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:opsz,wght@12..96,400..800&family=Hanken+Grotesk:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600&display=swap" rel="stylesheet">
<link rel="stylesheet" href="styles.css">
</head>
<body>
<div class="wrap" style="max-width:560px">
  <header class="top">
    <a class="brand" href="jobs.html">Side<b>line</b></a>
    <nav>
      <a href="jobs.html">My matches</a>
      <a href="admin.html" id="adminLink" class="hidden">Admin</a>
      <a href="#" id="signout">Sign out</a>
    </nav>
  </header>
  <h1>Submit a match</h1>
  <p class="sub">Tell us about your footage. Once it's approved you'll get an
     email with an upload link.</p>
  <div class="card">
    <label for="sport">Sport</label>
    <select id="sport">
      <option value="football">Football</option>
      <option value="basketball">Basketball</option>
    </select>
    <label for="matchName">Match name</label>
    <input id="matchName" maxlength="120" placeholder="U16 vs Riverside, first half">
    <label for="matchDate">Match date (optional)</label>
    <input id="matchDate" type="date">
    <label for="duration">Footage duration (minutes)</label>
    <input id="duration" type="number" min="1" max="240" placeholder="15">
    <label>What do you want back?</label>
    <div class="checks" id="checks"></div>
    <p id="scopeNote" class="msg hidden">Footage over 20 minutes gets coach
       analytics only for now.</p>
    <div style="margin-top:18px">
      <button id="submit" class="btn btn-primary">Submit for review</button>
    </div>
    <p id="msg" class="msg"></p>
  </div>
</div>
<script type="module">
  import { sb, el, requireUser, initNav } from "./js/api.js";
  import { ALL_DELIVERABLES, allowedDeliverables, restrictDeliverables }
    from "./js/jobcopy.js";

  const user = await requireUser();
  await initNav(user);

  const checks = el("checks");
  checks.innerHTML = ALL_DELIVERABLES.map(([key, label]) => `
    <label data-key="${key}">
      <input type="checkbox" value="${key}" ${key === "coach_analytics" ? "checked" : ""}>
      ${label}
    </label>`).join("");

  function refresh() {
    const allowed = allowedDeliverables(Number(el("duration").value || 0));
    for (const lab of checks.querySelectorAll("label")) {
      const ok = allowed.includes(lab.dataset.key);
      lab.classList.toggle("off", !ok);
      if (!ok) lab.querySelector("input").checked = lab.dataset.key === "coach_analytics";
    }
    el("scopeNote").classList.toggle("hidden", allowed.length > 1);
  }
  el("duration").oninput = refresh;
  refresh();

  el("submit").onclick = async () => {
    const duration = Number(el("duration").value);
    const name = el("matchName").value.trim();
    if (!name || !duration) {
      el("msg").textContent = "Please fill in the match name and duration.";
      el("msg").className = "msg err";
      return;
    }
    const picked = [...checks.querySelectorAll("input:checked")].map((c) => c.value);
    const deliverables = restrictDeliverables(duration, picked);
    el("submit").disabled = true;
    const { data, error } = await sb.from("jobs").insert({
      user_id: user.id,
      sport: el("sport").value,
      match_name: name,
      match_date: el("matchDate").value || null,
      declared_duration_min: duration,
      deliverables,
    }).select().single();
    if (error) {
      el("msg").textContent = "Couldn't submit — please check the form and try again.";
      el("msg").className = "msg err";
      el("submit").disabled = false;
      return;
    }
    location.href = `job.html?id=${data.id}`;
  };
</script>
</body>
</html>
```

- [ ] **Step 2: Manual check**

With `npx wrangler pages dev site` running and a signed-in session (Task 4):
1. Open `http://localhost:8788/submit.html`.
2. Type duration `90` → highlight checkboxes grey out, scope note appears; type `15` → they re-enable.
3. Submit a test match → browser navigates to `job.html?id=<uuid>` (404 for now — Task 7). Confirm the row exists: Supabase dashboard → Table Editor → `jobs` → new row in `submitted`.

- [ ] **Step 3: Commit**

```powershell
git add site/submit.html
git commit -m "feat(site): match submission form with launch-scope deliverable gating"
```

---

### Task 6: My-matches list page

**Files:**
- Create: `site/jobs.html`

- [ ] **Step 1: Write `site/jobs.html`**

```html
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Sideline — My matches</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:opsz,wght@12..96,400..800&family=Hanken+Grotesk:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600&display=swap" rel="stylesheet">
<link rel="stylesheet" href="styles.css">
</head>
<body>
<div class="wrap">
  <header class="top">
    <a class="brand" href="jobs.html">Side<b>line</b></a>
    <nav>
      <a href="submit.html">Submit a match</a>
      <a href="admin.html" id="adminLink" class="hidden">Admin</a>
      <a href="#" id="signout">Sign out</a>
    </nav>
  </header>
  <h1>My matches</h1>
  <p class="sub">Everything you've sent us, newest first.</p>
  <div id="list" class="joblist"></div>
</div>
<script type="module">
  import { sb, el, esc, requireUser, initNav } from "./js/api.js";
  import { friendlyState } from "./js/jobcopy.js";

  const user = await requireUser();
  await initNav(user);

  const { data: jobs, error } = await sb.from("jobs")
    .select("*").order("created_at", { ascending: false });

  const list = el("list");
  if (error) {
    list.innerHTML = `<p class="msg err">Couldn't load your matches. Please refresh.</p>`;
  } else if (!jobs.length) {
    list.innerHTML = `<p class="msg">No matches yet —
      <a href="submit.html">submit your first one</a>.</p>`;
  } else {
    list.innerHTML = jobs.map((j) => {
      const v = friendlyState(j);
      return `<a class="card" href="job.html?id=${j.id}">
        <div class="row">
          <div>
            <div style="font-weight:600">${esc(j.match_name)}</div>
            <div class="mono">${esc(j.sport)} · ${j.declared_duration_min} min
              · ${j.created_at.slice(0, 10)}</div>
          </div>
          <span class="badge ${v.tone}">${esc(v.label)}</span>
        </div>
      </a>`;
    }).join("");
  }
</script>
</body>
</html>
```

- [ ] **Step 2: Manual check**

Open `http://localhost:8788/jobs.html`: the Task 5 test match appears with an "Awaiting review" badge. Sign-out link returns to the login page (sign back in afterwards — or keep a second browser profile signed in).

- [ ] **Step 3: Commit**

```powershell
git add site/jobs.html
git commit -m "feat(site): my-matches list with friendly state badges"
```

---

### Task 7: Job status page with the uploader

**Files:**
- Create: `site/job.html`

This page is the heart of the product: status polling, the chunked upload with progress/pause/resume, and the results download. Its URL shape `job.html?id=<uuid>` is a frozen contract (the `decide` email links to it).

- [ ] **Step 1: Write `site/job.html`**

```html
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Sideline — Match status</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:opsz,wght@12..96,400..800&family=Hanken+Grotesk:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600&display=swap" rel="stylesheet">
<link rel="stylesheet" href="styles.css">
</head>
<body>
<div class="wrap" style="max-width:640px">
  <header class="top">
    <a class="brand" href="jobs.html">Side<b>line</b></a>
    <nav>
      <a href="jobs.html">My matches</a>
      <a href="admin.html" id="adminLink" class="hidden">Admin</a>
      <a href="#" id="signout">Sign out</a>
    </nav>
  </header>
  <p class="mono" id="meta"></p>
  <h1 id="title">Loading…</h1>
  <div class="card">
    <span class="badge" id="stateBadge"></span>
    <p class="msg" id="detail"></p>
    <div id="stageWrap" class="hidden">
      <div class="progress"><div id="stageBar"></div></div>
      <p class="mono" id="stageText"></p>
    </div>
  </div>
  <div class="card hidden" id="uploadCard">
    <h3>Upload your footage</h3>
    <label for="file">Your match video</label>
    <input id="file" type="file" accept="video/*">
    <div style="margin-top:14px;display:flex;gap:8px">
      <button id="startUpload" class="btn btn-primary" disabled>Start upload</button>
      <button id="pauseUpload" class="btn btn-ghost hidden">Pause</button>
    </div>
    <div id="progressWrap" class="hidden">
      <div class="progress"><div id="bar"></div></div>
      <p class="mono" id="pct"></p>
    </div>
    <p id="upMsg" class="msg"></p>
  </div>
  <div class="card hidden" id="resultsCard">
    <h3>Your analysis</h3>
    <p class="msg" id="expiry"></p>
    <a id="resultsLink" class="btn btn-primary" target="_blank" rel="noopener">
      Open your results</a>
  </div>
</div>
<script type="module">
  import { sb, el, requireUser, initNav, callFn, fmtBytes } from "./js/api.js";
  import { friendlyState } from "./js/jobcopy.js";
  import { DriveUploader } from "./js/upload.js";

  const user = await requireUser();
  await initNav(user);
  const jobId = new URLSearchParams(location.search).get("id");
  let uploading = false;
  let uploader = null;

  async function load() {
    const { data: job } = await sb.from("jobs")
      .select("*").eq("id", jobId).maybeSingle();
    if (!job) {
      el("title").textContent = "Match not found";
      el("detail").textContent =
        "This link doesn't point to one of your matches.";
      return;
    }
    render(job);
  }

  function render(job) {
    const v = friendlyState(job);
    el("title").textContent = job.match_name;
    el("meta").textContent = `${job.sport} · ${job.declared_duration_min} min` +
      ` · submitted ${job.created_at.slice(0, 10)}`;
    el("stateBadge").textContent = v.label;
    el("stateBadge").className = `badge ${v.tone}`;
    el("detail").textContent = v.detail;

    const showStage = ["processing", "operator_action"].includes(job.state);
    el("stageWrap").classList.toggle("hidden", !showStage);
    if (showStage) {
      el("stageBar").style.width = `${job.progress ?? 0}%`;
      el("stageText").textContent = `${job.progress ?? 0}%`;
    }

    el("uploadCard").classList.toggle("hidden", !(v.showUpload || uploading));
    el("resultsCard").classList.toggle("hidden", !v.showResults);
    if (v.showResults) {
      el("resultsLink").href = job.results_url;
      el("expiry").textContent = job.expires_at
        ? `Available until ${job.expires_at.slice(0, 10)} — download it soon.`
        : "";
    }
  }

  el("file").onchange = () => {
    el("startUpload").disabled = !el("file").files.length;
  };

  async function runUpload(offset) {
    uploading = true;
    el("pauseUpload").classList.remove("hidden");
    el("pauseUpload").textContent = "Pause";
    try {
      const driveFile = await uploader.start(offset);
      await callFn("complete-upload", { job_id: jobId, drive_file_id: driveFile.id });
      localStorage.removeItem(`session_${jobId}`);
      uploading = false;
      el("upMsg").textContent = "Upload complete!";
      el("upMsg").className = "msg";
      el("pauseUpload").classList.add("hidden");
      el("progressWrap").classList.add("hidden");
      await load();
    } catch (e) {
      uploading = false;
      if (e.paused) {
        el("upMsg").textContent = "Paused — click Resume to continue.";
        el("upMsg").className = "msg";
        return;
      }
      el("upMsg").textContent = e.message || "Upload failed — please try again.";
      el("upMsg").className = "msg err";
      el("pauseUpload").classList.add("hidden");
      el("startUpload").disabled = false;
    }
  }

  el("pauseUpload").onclick = async () => {
    if (!uploader) return;
    if (!uploader.paused) {
      uploader.pause();
      el("pauseUpload").textContent = "Resume";
    } else {
      await runUpload(await uploader.resumeOffset());
    }
  };

  el("startUpload").onclick = async () => {
    const file = el("file").files[0];
    if (!file) return;
    el("startUpload").disabled = true;
    el("upMsg").textContent = "";
    el("upMsg").className = "msg";

    // reuse an interrupted session if Drive still holds partial bytes for it
    let sessionUri = localStorage.getItem(`session_${jobId}`);
    let offset = 0;
    if (sessionUri) {
      const probe = new DriveUploader(file, sessionUri);
      offset = await probe.resumeOffset();
      if (!offset) sessionUri = null; // dead/expired/empty — mint a fresh one
    }
    if (!sessionUri) {
      try {
        const minted = await callFn("mint-upload", {
          job_id: jobId, file_size: file.size,
          mime_type: file.type || "video/mp4",
        });
        if (minted.queued) {  // Drive is full — quota_waiting (spec §8)
          el("upMsg").textContent = minted.message;
          el("startUpload").disabled = false;
          await load();
          return;
        }
        sessionUri = minted.session_uri;
        localStorage.setItem(`session_${jobId}`, sessionUri);
      } catch (e) {
        el("upMsg").textContent = e.message;
        el("upMsg").className = "msg err";
        el("startUpload").disabled = false;
        return;
      }
    }

    uploader = new DriveUploader(file, sessionUri, (pct) => {
      el("bar").style.width = `${pct}%`;
      el("pct").textContent = `${pct}% of ${fmtBytes(file.size)}`;
    });
    el("progressWrap").classList.remove("hidden");
    await runUpload(offset);
  };

  await load();
  setInterval(() => { if (!uploading) load(); }, 5000);
</script>
</body>
</html>
```

- [ ] **Step 2: Manual check — the full user lifecycle on localhost**

With `npx wrangler pages dev site` running and signed in:
1. Open the Task 5 test job's `job.html?id=…` page → "Awaiting review".
2. Approve it from the cloud side (admin page comes in Task 8; for now use the service role like the tests do): Supabase dashboard → Table Editor → `jobs` → set the row's `state` to `approved`.
3. Within 5 s the page flips to "Approved — upload your footage" (polling works).
4. Pick a small video file (any few-MB mp4 — e.g. one of the existing tagging clips under `local_data/`) → Start upload → progress bar fills → "Upload complete!" → state flips to "Footage received".
5. Verify in Drive (operator account, `altaccrv@gmail.com`): "SportsAI Submissions" → folder for this job → `raw_video.mp4`.
6. Clean up: delete the Drive folder; delete the test row(s) in the Table Editor.

If the browser PUT fails with a CORS error, the `Origin` header binding in `mint-upload` is the suspect — confirm the request's `Origin` is `http://localhost:8788` (it is sent automatically; `mint-upload` forwards it to Google).

- [ ] **Step 3: Commit**

```powershell
git add site/job.html
git commit -m "feat(site): job status page - polling, chunked upload with pause/resume, results"
```

---

### Task 8: Admin page (approve / reject / quota)

**Files:**
- Create: `site/admin.html`

- [ ] **Step 1: Register yourself as admin (completes the deferred Plan 1 Task 9 step)**

Your real account now exists in `auth.users` (magic-link sign-in from Task 4). Supabase dashboard → SQL editor:

```sql
insert into public.app_admins (user_id)
select id from auth.users where email = '<the email you signed in with>'
on conflict do nothing;
```

Expected: `INSERT 0 1`. (This is the SQL recorded in `supabase/SETUP.md`.)

- [ ] **Step 2: Write `site/admin.html`**

```html
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Sideline — Admin</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:opsz,wght@12..96,400..800&family=Hanken+Grotesk:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600&display=swap" rel="stylesheet">
<link rel="stylesheet" href="styles.css">
</head>
<body>
<div class="wrap">
  <header class="top">
    <a class="brand" href="jobs.html">Side<b>line</b></a>
    <nav>
      <a href="jobs.html">My matches</a>
      <a href="#" id="signout">Sign out</a>
    </nav>
  </header>
  <h1>Studio admin</h1>
  <p class="sub">Approve or reject submissions, keep an eye on storage.</p>

  <div class="card">
    <h3>Drive storage</h3>
    <div class="progress"><div id="quotaBar"></div></div>
    <p class="mono" id="quotaText">Loading…</p>
  </div>

  <h3 style="margin:26px 0 10px">Waiting for review</h3>
  <div id="pending" class="joblist"></div>

  <h3 style="margin:26px 0 10px">All jobs</h3>
  <div class="card" style="padding:8px 14px;overflow-x:auto">
    <table>
      <thead><tr><th>Match</th><th>Sport</th><th>Submitted</th><th>State</th></tr></thead>
      <tbody id="all"></tbody>
    </table>
  </div>
</div>
<script type="module">
  import { sb, el, esc, requireUser, isAdmin, initNav, callFn, fmtBytes }
    from "./js/api.js";
  import { friendlyState } from "./js/jobcopy.js";

  const user = await requireUser();
  if (!(await isAdmin(user.id))) {
    location.replace("jobs.html");
    throw new Error("not admin");
  }
  await initNav(user);

  async function loadQuota() {
    try {
      const q = await callFn("quota");
      const pct = q.limit_bytes
        ? Math.round((q.usage_bytes / q.limit_bytes) * 100) : 0;
      el("quotaBar").style.width = `${pct}%`;
      el("quotaText").textContent =
        `${fmtBytes(q.free_bytes)} free of ${fmtBytes(q.limit_bytes)} (${pct}% used)`;
    } catch {
      el("quotaText").textContent = "Couldn't read Drive quota.";
    }
  }

  async function loadJobs() {
    const { data: jobs } = await sb.from("jobs")
      .select("*").order("created_at", { ascending: false });
    const pending = (jobs ?? []).filter((j) =>
      ["submitted", "quota_waiting"].includes(j.state));

    el("pending").innerHTML = pending.length ? pending.map((j) => `
      <div class="card">
        <div class="row">
          <div>
            <div style="font-weight:600">${esc(j.match_name)}</div>
            <div class="mono">${esc(j.sport)} · ${j.declared_duration_min} min
              · ${esc((j.deliverables ?? []).join(", "))}
              · ${j.created_at.slice(0, 10)}</div>
          </div>
          <div style="display:flex;gap:8px">
            <button class="btn btn-primary" data-approve="${j.id}">Approve</button>
            <button class="btn btn-danger" data-reject="${j.id}">Reject</button>
          </div>
        </div>
      </div>`).join("")
      : `<p class="msg">Nothing waiting for review.</p>`;

    el("all").innerHTML = (jobs ?? []).map((j) => {
      const v = friendlyState(j);
      return `<tr>
        <td>${esc(j.match_name)}</td>
        <td>${esc(j.sport)}</td>
        <td class="mono">${j.created_at.slice(0, 10)}</td>
        <td><span class="badge ${v.tone}">${esc(v.label)}</span></td>
      </tr>`;
    }).join("");
  }

  document.addEventListener("click", async (e) => {
    const a = e.target.closest("[data-approve]");
    const r = e.target.closest("[data-reject]");
    if (!a && !r) return;
    const job_id = a ? a.dataset.approve : r.dataset.reject;
    const body = { job_id, action: a ? "approve" : "reject" };
    if (r) {
      const reason = prompt("Reason (emailed to the user, optional):");
      if (reason === null) return;        // operator cancelled
      if (reason.trim()) body.reason = reason.trim();
    }
    (a ?? r).disabled = true;
    try {
      await callFn("decide", body);
    } catch (err) {
      alert(err.message);
    }
    await Promise.all([loadJobs(), loadQuota()]);
  });

  await Promise.all([loadJobs(), loadQuota()]);
  setInterval(loadJobs, 10000);
</script>
</body>
</html>
```

- [ ] **Step 3: Manual check**

1. Open `http://localhost:8788/admin.html` as your (now admin) account → quota gauge shows real Drive numbers; the "Admin" nav link also appears on the other pages now.
2. Submit a fresh test match (submit page) → it appears under "Waiting for review" within 10 s.
3. Click **Approve** → it leaves the pending list; its job page shows "Approved — upload your footage". (If `RESEND_API_KEY` is unset the email is skipped server-side — fine.)
4. Submit another test match → **Reject** with a reason → its job page shows "Not accepted … Reason: …".
5. Non-admin check: a second signed-in account (or temporarily delete your `app_admins` row, reload, re-insert) gets bounced from `admin.html` to `jobs.html`.
6. Clean up test rows in the Table Editor.

- [ ] **Step 4: Commit**

```powershell
git add site/admin.html
git commit -m "feat(site): admin page - pending approvals, decide actions, quota gauge"
```

---

### Task 9: Deploy to Cloudflare Pages + production wiring

**Files:**
- Modify: `supabase/SETUP.md` (append Plan 2 section)
- Modify: `supabase/.env` (SITE_ORIGIN — untracked, no commit)

- [ ] **Step 1: Manual Cloudflare account setup (operator, ~5 min)**

1. Create a free account at dash.cloudflare.com (free plan, **no card needed**).
2. Run `npx wrangler login` — opens a browser, approve the CLI.

- [ ] **Step 2: Create the Pages project and deploy**

```powershell
npx wrangler pages project create sideline --production-branch main
npx wrangler pages deploy site --project-name sideline
```

Expected: `✨ Deployment complete! Take a peek over at https://<hash>.sideline.pages.dev` — the stable production URL is `https://sideline.pages.dev` (if the name is taken, wrangler suggests an alternative; use it consistently below).

- [ ] **Step 3: Point the cloud layer at the production origin**

1. Edit `supabase/.env`: set `SITE_ORIGIN=https://sideline.pages.dev` (no trailing slash).
2. Push and re-verify secrets:

```powershell
npx supabase secrets set --env-file supabase/.env
```

(Functions read `SITE_ORIGIN` per-invocation — no redeploy needed.)

3. Supabase dashboard → Authentication → URL Configuration:
   - **Site URL** → `https://sideline.pages.dev`
   - **Redirect URLs** → add `https://sideline.pages.dev/*` (keep the localhost entry for dev).

- [ ] **Step 4: Live smoke test on the production URL**

1. Open `https://sideline.pages.dev` in a fresh/incognito browser → sign in via magic link (lands on `jobs.html` on the production origin).
2. Submit a test match → approve it on `admin.html` → upload a small mp4 on the job page → "Upload complete!" → file visible in Drive.
3. Reject-path spot check: submit + reject another test match.
4. Clean up: delete the Drive folder + test rows.

- [ ] **Step 5: Regression — the cloud suite still passes**

Run: `.\.venv\Scripts\python -m pytest supabase/tests -v`
Expected: 12 passed (nothing in Plan 2 touched the functions, this proves it).

- [ ] **Step 6: Run the site unit tests once more**

Run: `node --test site/tests/`
Expected: 13 pass, 0 fail.

- [ ] **Step 7: Record the Plan 2 state in SETUP.md**

Append to `supabase/SETUP.md`:

```markdown
## Plan 2 final state (2026-06-06)

- Public site: `site/` deployed to Cloudflare Pages → https://sideline.pages.dev
  (project `sideline`, deploy with `npx wrangler pages deploy site --project-name sideline`).
- Supabase Auth URL config: Site URL = pages.dev URL; redirect URLs allow
  `https://sideline.pages.dev/*` and `http://localhost:8788/*` (local dev via
  `npx wrangler pages dev site`).
- Function secret `SITE_ORIGIN` = the pages.dev URL (drives email links + CORS
  origin binding for Drive resumable sessions).
- Operator admin row registered in `public.app_admins` (SQL in Plan 1 section).
- Site unit tests: `node --test site/tests/`. Cloud suite: `pytest supabase/tests -v`.
```

- [ ] **Step 8: Commit**

```powershell
git add supabase/SETUP.md
git commit -m "docs(cloud): record plan 2 deployment state (cloudflare pages + auth urls)"
```

---

## Exit criteria (Plan 2 done)

- [ ] `node --test site/tests/` → 13 pass (chunk math + state copy + scope rules).
- [ ] `pytest supabase/tests -v` → 12 passed (cloud layer unchanged and green).
- [ ] Live site on `*.pages.dev`: magic-link sign-in, submit, approve (admin), chunked upload to Drive with progress, state flips to `uploaded` — all proven with a real file end-to-end.
- [ ] Admin page: quota gauge shows real Drive numbers; approve/reject work and (with Resend configured later) email the user; non-admins are bounced.
- [ ] Full matches (>20 min) cannot request highlights — enforced in the form AND by the DB CHECK from Plan 1.
- [ ] Operator admin row registered (deferred Plan 1 item closed).
- [ ] No secret beyond the public anon key anywhere in `site/`.

**Deferred to Plan 3 (local agent + delivery):** processing states actually progressing, results delivery + expiry cleanup, Resend production sender, and the ~1 GB phone-on-mobile-data upload rehearsal (more meaningful once processing returns something).
