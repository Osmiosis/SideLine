# Operator App Backend — Plan 2: Frontend Wiring

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the static `Website/index.html` mockup into a real client of the Plan-1 backend, so an operator can click through Dashboard → Setup → Court → Deliverables → Processing → Results end-to-end against live data — for the two settled deliverables (Coach Analytics, Event Highlights). Player Highlights is shown as "Coming soon" (deferred to Plan 4). The visual design is preserved exactly.

**Architecture:** Add one new plain-JS file `Website/app.js` containing a tiny `API` client (fetch wrappers, same-origin `/api/...`) plus shared client state (`currentJobId`). Load it BEFORE the existing inline `<script>` so its symbols are available. Then make surgical in-place edits to the inline simulated functions (`simulateUpload`, `initDashboard`, `initCourt`, `initDeliverables`, `initProcessing`, `initResults`, and the court→next routing) so they call `API` instead of faking data. No build step, no framework. CSS/markup/canvas visuals are untouched except where a screen must show real content (real freeze-frame image, real job cards, real output files) or the "Coming soon" Player-Highlights state.

**Tech Stack:** Plain ES2020 JavaScript (no build), `fetch` + `XMLHttpRequest` (XHR for upload progress), the Plan-1 FastAPI backend, Node v24 for `node --check` syntax validation, Python `.venv` for the scripted full-flow driver.

**Spec:** `docs/superpowers/specs/2026-05-31-operator-app-backend-design.md`
**Builds on:** `docs/superpowers/plans/2026-05-31-operator-app-backend-plan1-skeleton.md` (DONE — backend + stub pipeline, 46 tests green)

---

## Backend contract this plan consumes (from Plan 1, do not change)

- `POST /api/jobs` `{sport, match_name, match_date}` → `{job_id}`
- `POST /api/jobs/{id}/video` — RAW request body is the file bytes (handler reads `request.stream()`); returns `{state:"calibration_pending"}` (or 400 on empty)
- `GET  /api/jobs/{id}/frame` → `image/jpeg` (409 if no video)
- `POST /api/jobs/{id}/calibration` `{calibration_points:[{pixel_x,pixel_y,real_world_label}]}` → `{state:"calibrated"}`
- `POST /api/jobs/{id}/roster` `{roster:[name,...]}` → `{ok:true}`
- `POST /api/jobs/{id}/deliverables` `{deliverables_requested:[...]}` → `{state:"queued"}`
- `GET  /api/jobs/{id}/status` → `{job_id,state,stage,progress,stage_label,error}`
- `GET  /api/jobs` → `[{job_id,sport,match_name,match_date,state,created_at}]`
- `GET  /api/jobs/{id}/outputs` → `["file.ext",...]`
- `GET  /api/jobs/{id}/outputs/{file}` → file download

Backend serves the frontend at `/`, so the client uses **relative** URLs (`/api/...`) — same origin, no CORS.

---

## Known frontend anchors (verified against current index.html)

- Boot call: `initDashboard()` at line ~1437.
- Nav: `views` map (~934), `FLOW_ORDER` (~935), `go(key)` (~939) dispatches to `init*()`.
- Setup: `initSetup` (~1043), `selSport` (~1042), inputs `#mName` (~577), `#mDate` (~578), drop zone `#drop` (~585), progress `#upbar/#upfill/#uppct/#upstat` (~590), `simulateUpload` (~1059), `uploaded` flag (~1058).
- Court: `initCourt` (~1079), `#frame` (~622), `marks[]` (~1072), `CALIB_PTS` (~1073), `addMark` (~1101), `renderMarks` (~1109), `#courtNext` button (~648, currently `data-go="roster"`), `#autoDetect`, `#diagram`.
- Roster: `initRoster` (~1159), `roster[]` (~1157), `#rosterInput`, `addRosterName` (~1175).
- Deliverables: `initDeliverables` (~1222), `selectedDeliv` Set (~1221), `DELIVERABLES` array (~818), grid `#delivGrid`, generate button `#genBtn` (~712, currently `data-go="processing"`), `updateDelivCount` (~1247).
- Processing: `initProcessing` (~1257), `STAGES` (~823), `#stageList`, `#procFill/#procPct/#procEta`, `#skipProc`, `setStage` (~1281), `finishProc` (~1287).
- Results: `initResults` (~1327), `EVENTS` (~830), `#clipList`, `#playerGrid`, `#reportVid`, `.rtab`/`.rpanel`, `.dlbtn`.
- Dashboard: `MATCHES` (~812), `initDashboard` (~1008), match card `el.dataset.go` (~1022).

---

## File Structure

```
Website/
  app.js          # NEW — API client + shared client state (currentJobId). node-checkable.
  index.html      # MODIFIED in place — load app.js; swap simulated fns for API calls
tests/frontend/
  api.test.mjs    # NEW — node --test unit tests for app.js URL/payload builders
scripts/
  e2e_frontend_flow.py   # NEW — Python driver: exercises the exact endpoint sequence the UI follows
```

**Responsibilities:**
- `app.js` — all network I/O + the `currentJobId` handle. Pure, testable helpers for URL/payload building separated from `fetch` so node can unit-test them.
- `index.html` — UI/DOM/canvas only; delegates every data operation to `API`.
- `tests/frontend/api.test.mjs` — verifies the client builds correct URLs/payloads (no network).
- `scripts/e2e_frontend_flow.py` — proves the live server accepts the exact sequence the wired UI performs.

---

## Conventions for every task

- Windows/PowerShell. Repo root `C:\sports-ai`.
- Python: `.venv\Scripts\python.exe`. Node: `node` (v24).
- After editing `index.html`, validate its inline JS by extracting the `<script>`…`</script>` block and running `node --check` on it (Step shown in Task 9). After editing `app.js`, run `node --check Website/app.js`.
- Commit after each task with the shown message.
- **Do NOT alter CSS, layout, or canvas-drawing functions** except the specific swaps each task names.

---

## Task 1: `app.js` — API client + state, with node unit tests

**Files:**
- Create: `Website/app.js`
- Create: `tests/frontend/api.test.mjs`

- [ ] **Step 1: Write the failing unit test**

Create `tests/frontend/api.test.mjs`:

```javascript
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { _build } from '../../Website/app.js';

test('jobsUrl is the api root', () => {
  assert.equal(_build.jobsUrl(), '/api/jobs');
});

test('jobUrl composes job-scoped paths', () => {
  assert.equal(_build.jobUrl('abc', 'status'), '/api/jobs/abc/status');
  assert.equal(_build.jobUrl('abc', 'video'), '/api/jobs/abc/video');
});

test('outputUrl encodes the filename', () => {
  assert.equal(_build.outputUrl('abc', 'report 1.pdf'),
    '/api/jobs/abc/outputs/report%201.pdf');
});

test('calibrationPayload maps normalized marks to pixel points', () => {
  const marks = [{ px: 0.5, py: 0.25 }, { px: 0.1, py: 0.9 }];
  const labels = ['far-left corner', 'far-right corner'];
  const out = _build.calibrationPayload(marks, labels, 1280, 960);
  assert.deepEqual(out, {
    calibration_points: [
      { pixel_x: 640, pixel_y: 240, real_world_label: 'far-left corner' },
      { pixel_x: 128, pixel_y: 864, real_world_label: 'far-right corner' },
    ],
  });
});
```

- [ ] **Step 2: Run it to confirm failure**

Run: `node --test tests/frontend/api.test.mjs`
Expected: FAIL — `Cannot find module ... Website/app.js` (file not created yet).

- [ ] **Step 3: Implement `app.js`**

Create `Website/app.js`:

```javascript
/* Operator App — API client + shared client state.
   Loaded BEFORE the inline <script> in index.html, so `API`, `AppState`,
   and `_build` are globals there. Also an ES module for node unit tests. */

// ---- pure builders (unit-tested; no network) ----
const _build = {
  jobsUrl() { return '/api/jobs'; },
  jobUrl(id, sub) { return `/api/jobs/${id}/${sub}`; },
  outputUrl(id, filename) {
    return `/api/jobs/${id}/outputs/${encodeURIComponent(filename)}`;
  },
  calibrationPayload(marks, labels, frameW, frameH) {
    return {
      calibration_points: marks.map((m, i) => ({
        pixel_x: Math.round(m.px * frameW),
        pixel_y: Math.round(m.py * frameH),
        real_world_label: labels[i],
      })),
    };
  },
};

// ---- shared client state ----
const AppState = { currentJobId: null };

// ---- network client (browser only; uses fetch/XHR) ----
const API = {
  async createJob(sport, matchName, matchDate) {
    const r = await fetch(_build.jobsUrl(), {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ sport, match_name: matchName, match_date: matchDate }),
    });
    if (!r.ok) throw new Error('We could not start the match. Please try again.');
    return (await r.json()).job_id;
  },

  // streamed upload with progress via XHR (fetch can't report upload progress)
  uploadVideo(id, file, onProgress) {
    return new Promise((resolve, reject) => {
      const xhr = new XMLHttpRequest();
      xhr.open('POST', _build.jobUrl(id, 'video'));
      xhr.setRequestHeader('content-type', 'application/octet-stream');
      xhr.upload.onprogress = (e) => {
        if (e.lengthComputable && onProgress) onProgress(e.loaded / e.total);
      };
      xhr.onload = () => (xhr.status >= 200 && xhr.status < 300)
        ? resolve()
        : reject(new Error('The video upload did not finish. Please try again.'));
      xhr.onerror = () => reject(new Error('The video upload was interrupted.'));
      xhr.send(file);
    });
  },

  frameUrl(id) { return _build.jobUrl(id, 'frame'); },

  async saveCalibration(id, marks, labels, frameW, frameH) {
    const r = await fetch(_build.jobUrl(id, 'calibration'), {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify(_build.calibrationPayload(marks, labels, frameW, frameH)),
    });
    if (!r.ok) throw new Error('Court setup could not be saved. Please try again.');
  },

  async saveRoster(id, roster) {
    const r = await fetch(_build.jobUrl(id, 'roster'), {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ roster }),
    });
    if (!r.ok) throw new Error('The roster could not be saved.');
  },

  async setDeliverables(id, deliverables) {
    const r = await fetch(_build.jobUrl(id, 'deliverables'), {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ deliverables_requested: deliverables }),
    });
    if (!r.ok) throw new Error('We could not start processing. Please try again.');
  },

  async getStatus(id) {
    const r = await fetch(_build.jobUrl(id, 'status'));
    if (!r.ok) throw new Error('Could not read match status.');
    return r.json();
  },

  async listJobs() {
    const r = await fetch(_build.jobsUrl());
    if (!r.ok) throw new Error('Could not load your matches.');
    return r.json();
  },

  async listOutputs(id) {
    const r = await fetch(_build.jobUrl(id, 'outputs'));
    if (!r.ok) throw new Error('Could not load the results.');
    return r.json();
  },

  outputUrl(id, filename) { return _build.outputUrl(id, filename); },
};

// expose as globals for the inline <script> (browser only)
if (typeof window !== 'undefined') {
  window.API = API;
  window.AppState = AppState;
  window._build = _build;
}

// ES module export for node tests
export { API, AppState, _build };
```

- [ ] **Step 4: Run the unit test to confirm pass**

Run: `node --test tests/frontend/api.test.mjs`
Expected: PASS (4 tests).

- [ ] **Step 5: Syntax-check the module**

Run: `node --check Website/app.js`
Expected: no output, exit 0.

- [ ] **Step 6: Commit**

```bash
git add Website/app.js tests/frontend/api.test.mjs
git commit -m "feat(frontend): API client + state with node unit tests"
```

---

## Task 2: Load `app.js` and add a global error toast helper

**Files:**
- Modify: `Website/index.html` (add `<script src="app.js"></script>` before the inline `<script>`; the inline script already defines `toast()` — reuse it)

**Note:** `index.html` is served from the same directory as `app.js`, so `src="app.js"` resolves correctly. It must load BEFORE the inline `<script>` so `API`/`AppState` exist when the inline boot code runs.

- [ ] **Step 1: Add the module load**

Find the inline script open tag (line ~805): `<script>`. Immediately BEFORE it, insert:

```html
<script src="app.js"></script>
```

(Plain classic script, not `type="module"` — `app.js` assigns `window.API` etc. The trailing `export` line is ignored by classic-script parsers in browsers? No — a bare `export` is a SyntaxError in a classic script. So load it as a module AND keep the window assignments.)

Use instead:

```html
<script type="module" src="app.js"></script>
```

Because it's a module, `window.API`/`window.AppState`/`window._build` assignments still run (modules can touch `window`), and the inline classic script runs after and reads those globals. Module scripts are deferred, so they execute after HTML parse but BEFORE the inline classic script? NO — classic inline scripts run during parse, modules are deferred to after parse. That means the inline boot (`initDashboard()` at ~1437) could run before the module sets `window.API`.

**Resolution:** Make the inline boot resilient. In Task 7 the dashboard init becomes async and tolerates a missing `API` by waiting. To keep ordering deterministic, ALSO convert the inline `<script>` to `type="module"` is too invasive. Instead: wrap the inline boot lines in a `window.addEventListener('DOMContentLoaded', ...)` is unnecessary; the simplest deterministic fix is to load `app.js` as a normal blocking classic script that does NOT use ES `export`.

**Final approach (do this):**
1. Change the export style in `Website/app.js`: REMOVE the `export { API, AppState, _build };` line and instead guard the node path. Replace the bottom of `app.js` with:

```javascript
// expose as globals for the inline <script> (browser)
if (typeof window !== 'undefined') {
  window.API = API;
  window.AppState = AppState;
  window._build = _build;
}
// CommonJS-style export for node tests (node wraps modules; this is safe)
if (typeof module !== 'undefined' && module.exports) {
  module.exports = { API, AppState, _build };
}
```

2. Update `tests/frontend/api.test.mjs` to import via `createRequire` (since app.js is now CommonJS-ish). Replace its import line with:

```javascript
import { createRequire } from 'node:module';
const require = createRequire(import.meta.url);
const { _build } = require('../../Website/app.js');
```

3. In `index.html`, insert a **classic blocking** script before the inline one:

```html
<script src="app.js"></script>
```

A classic script with `module.exports` guarded by `typeof module !== 'undefined'` is safe in the browser (`module` is undefined there, so the block is skipped) and the `window.*` assignments run synchronously before the inline script — deterministic ordering achieved.

- [ ] **Step 2: Apply the three edits above** (app.js bottom, test import, index.html script tag).

- [ ] **Step 3: Re-run unit + syntax checks**

Run: `node --test tests/frontend/api.test.mjs` → PASS (4).
Run: `node --check Website/app.js` → exit 0.

- [ ] **Step 4: Confirm load order in a browser-less check**

Run: `.venv\Scripts\python.exe -c "import re,sys; h=open('Website/index.html',encoding='utf-8').read(); i=h.index('<script src=\"app.js\"></script>'); j=h.index('<script>', i); print('app.js before inline:', i < j)"`
Expected: `app.js before inline: True`

- [ ] **Step 5: Commit**

```bash
git add Website/app.js Website/index.html tests/frontend/api.test.mjs
git commit -m "feat(frontend): load API client before inline script (deterministic order)"
```

---

## Task 3: Wire Setup — create job + real streamed upload

**Files:**
- Modify: `Website/index.html` (`initSetup` ~1043, `simulateUpload` ~1059; add a hidden file input)

**Behavior:** On the Setup screen the operator picks sport, types name/date, and chooses a file. We create the job lazily when a file is provided (we need a `job_id` to upload to), then stream the upload with a real progress bar. The "Continue → Court Setup" button stays disabled until upload completes.

- [ ] **Step 1: Add a hidden file input to the drop zone**

In the markup for `#drop` (line ~585), add a hidden file input as the first child. Find:

```html
<div class="drop" id="drop">
```

and immediately after the opening tag insert:

```html
<input type="file" id="videoFile" accept="video/*" style="display:none">
```

- [ ] **Step 2: Replace the drop handlers + `simulateUpload`**

Replace the body of `initSetup`'s drop wiring (the four `drop.addEventListener(...)` lines, ~1052-1056) with:

```javascript
  const drop=document.getElementById('drop');
  const fileInput=document.getElementById('videoFile');
  drop.addEventListener('click',()=>fileInput.click());
  fileInput.addEventListener('change',()=>{ if(fileInput.files[0]) startUpload(fileInput.files[0]); });
  drop.addEventListener('dragover',e=>{e.preventDefault();drop.classList.add('drag');});
  drop.addEventListener('dragleave',()=>drop.classList.remove('drag'));
  drop.addEventListener('drop',e=>{e.preventDefault();drop.classList.remove('drag');
    const f=e.dataTransfer.files[0]; if(f) startUpload(f); });
```

Then replace the entire `simulateUpload` function (~1059-1067) with:

```javascript
let uploaded=false;
async function startUpload(file){
  const bar=document.getElementById('upbar'); bar.classList.add('show');
  const fill=document.getElementById('upfill'), pct=document.getElementById('uppct'), stat=document.getElementById('upstat');
  uploaded=false;
  // disable continue until done
  const cont=document.getElementById('setupNext'); if(cont) cont.disabled=true;
  stat.textContent='Uploading footage…';
  try{
    if(!AppState.currentJobId){
      AppState.currentJobId = await API.createJob(
        selSport,
        document.getElementById('mName').value.trim() || 'Untitled match',
        document.getElementById('mDate').value || new Date().toISOString().slice(0,10));
    }
    await API.uploadVideo(AppState.currentJobId, file, frac=>{
      const p=Math.round(frac*100); fill.style.width=p+'%'; pct.textContent=p+'%';
    });
    fill.style.width='100%'; pct.textContent='100%';
    stat.textContent='Upload complete — video ready'; uploaded=true; toast('Video uploaded');
    if(cont) cont.disabled=false;
  }catch(err){
    stat.textContent=err.message || 'Upload failed. Please try again.';
    toast('Upload failed'); uploaded=false;
  }
}
```

- [ ] **Step 3: Ensure the Continue button has id `setupNext` and gates on upload**

Locate the Setup screen's primary "Continue" button (it routes to court; in the markup near the end of `#v-setup`, before `#v-court` at ~612). It should have `data-go="court"`. Add `id="setupNext"` to it and ensure it starts disabled. If the button is e.g. `<button class="btn btn-primary" data-go="court">Continue → Court Setup</button>`, change it to:

```html
<button class="btn btn-primary" data-go="court" id="setupNext" disabled>Continue → Court Setup</button>
```

(If a Continue button with `data-go="court"` does not exist on the Setup screen, add one at the end of the `#v-setup` content with the markup above.)

- [ ] **Step 4: Syntax-check the inline JS** (see Task 9 helper command — run it now)

Run: `.venv\Scripts\python.exe -c "import re; h=open('Website/index.html',encoding='utf-8').read(); s=re.search(r'<script>(.*?)</script>', h, re.S).group(1); open('build/_inline.js','w',encoding='utf-8').write(s)" 2>NUL || .venv\Scripts\python.exe -c "import re,os; os.makedirs('build',exist_ok=True); h=open('Website/index.html',encoding='utf-8').read(); s=re.search(r'<script>(.*?)</script>', h, re.S).group(1); open('build/_inline.js','w',encoding='utf-8').write(s)"`
Then: `node --check build/_inline.js`
Expected: exit 0 (no syntax errors).

- [ ] **Step 5: Manual smoke (documented; run later in Task 9)**

Setup → pick sport, name/date, choose a small file (e.g. `clips/football.mp4`): the bar fills with REAL progress, "Upload complete" appears, Continue enables. (Defer actual browser run to Task 9.)

- [ ] **Step 6: Commit**

```bash
git add Website/index.html
git commit -m "feat(frontend): wire setup to real job create + streamed upload"
```

---

## Task 4: Wire Court — real freeze-frame + save calibration

**Files:**
- Modify: `Website/index.html` (`initCourt` ~1079, `renderMarks` ~1109, the `#courtNext` confirm)

**Behavior:** Replace the drawn canvas footage in `#frame` with the REAL freeze-frame from `GET /frame`. Clicks already map to normalized coords in `marks[]`. On "Confirm calibration", POST the points (converted to image pixels via the image's natural dimensions), then proceed.

- [ ] **Step 1: Show the real frame image instead of canvas footage**

In `initCourt` (~1079-1083), replace the canvas-footage block:

```javascript
  const frame=document.getElementById('frame');
  let cv=frame.querySelector('canvas'); if(!cv){cv=document.createElement('canvas');frame.insertBefore(cv,frame.firstChild);}
  drawFootage(cv, selSport, 42, {players:true});
  drawDiagram();
```

with:

```javascript
  const frame=document.getElementById('frame');
  // real freeze-frame from the uploaded video
  let img=frame.querySelector('img.frameimg');
  if(!img){ img=document.createElement('img'); img.className='frameimg';
    img.style.cssText='position:absolute;inset:0;width:100%;height:100%;object-fit:cover';
    frame.insertBefore(img, frame.firstChild); }
  if(AppState.currentJobId){ img.src=API.frameUrl(AppState.currentJobId)+'?t='+Date.now(); }
  drawDiagram();
```

- [ ] **Step 2: POST calibration on Confirm**

The `#courtNext` button currently has `data-go="roster"`, which would auto-navigate via the global `[data-go]` click handler. We must intercept it to save first AND (per Plan-2 scope) route to **deliverables**, skipping the tagging screen. Change the button markup (~648) from:

```html
<button class="btn btn-primary" data-go="roster" id="courtNext" disabled>Confirm calibration
```

to (remove `data-go` so the global handler ignores it; we wire it explicitly):

```html
<button class="btn btn-primary" id="courtNext" disabled>Confirm calibration
```

Then at the end of `initCourt` (after the `#autoDetect` handler, before the function closes ~1099), add a guarded click handler:

```javascript
  if(!courtNextWired){
    courtNextWired=true;
    document.getElementById('courtNext').addEventListener('click',async()=>{
      const frameEl=document.getElementById('frame');
      const imgEl=frameEl.querySelector('img.frameimg');
      const fw=(imgEl&&imgEl.naturalWidth)||frameEl.clientWidth||1280;
      const fh=(imgEl&&imgEl.naturalHeight)||frameEl.clientHeight||960;
      const labels=CALIB_PTS.map(p=>p.label);
      try{
        await API.saveCalibration(AppState.currentJobId, marks, labels, fw, fh);
        toast('Court setup saved'); go('deliverables');
      }catch(err){ toast(err.message||'Could not save court setup'); }
    });
  }
```

Add the guard flag near the other court state (~1072), changing:

```javascript
let courtInit=false; let marks=[];
```

to:

```javascript
let courtInit=false; let courtNextWired=false; let marks=[];
```

- [ ] **Step 3: Syntax-check** (run the Task 9 extract+`node --check` command). Expected exit 0.

- [ ] **Step 4: Commit**

```bash
git add Website/index.html
git commit -m "feat(frontend): wire court to real freeze-frame + save calibration"
```

---

## Task 5: Wire Deliverables — Player Highlights "Coming soon" + enqueue

**Files:**
- Modify: `Website/index.html` (`DELIVERABLES` ~818, `initDeliverables` ~1222, `selectedDeliv` default ~1221, `#genBtn`)

**Behavior:** Render Player Highlights as a disabled "Coming soon" card (not selectable, not enqueued). The Generate button posts the selected (settled) deliverables and goes to Processing.

- [ ] **Step 1: Default selection excludes player_highlights**

Change (~1221):

```javascript
let delivInit=false; let selectedDeliv=new Set(['coach_analytics','event_highlights']);
```

— leave as-is (already excludes player_highlights). Good.

- [ ] **Step 2: Mark the Player Highlights card disabled**

In `initDeliverables`, inside the `DELIVERABLES.forEach(d=>{...})` loop, change the card element creation (~1227) to add a disabled class for player_highlights and skip its selection toggle. Replace:

```javascript
      const el=document.createElement('div'); el.className='deliv'+(selectedDeliv.has(d.id)?' sel':''); el.dataset.id=d.id;
```

with:

```javascript
      const soon=(d.id==='player_highlights');
      const el=document.createElement('div'); el.className='deliv'+(selectedDeliv.has(d.id)?' sel':'')+(soon?' soon':''); el.dataset.id=d.id;
```

And replace the note line (~1234) so the player card shows a "Coming soon" note. Change:

```javascript
          ${d.note?`<div class="note">...${d.note}</div>`:''}
```

(the existing `d.note` rendering) — append a coming-soon override by changing the click handler block (~1236-1239) to:

```javascript
      el.addEventListener('click',()=>{
        if(soon){ toast('Player Highlights is coming soon'); return; }
        if(selectedDeliv.has(d.id))selectedDeliv.delete(d.id); else selectedDeliv.add(d.id);
        el.classList.toggle('sel'); updateDelivCount();
      });
```

- [ ] **Step 3: Add a minimal "Coming soon" visual (CSS-light, no design overhaul)**

Add a small style rule. In the `<style>` block (anywhere among the existing `.deliv` rules), add:

```css
.deliv.soon{opacity:.55;filter:grayscale(.4);cursor:not-allowed}
.deliv.soon::after{content:'Coming soon';position:absolute;top:10px;right:10px;font-size:11px;letter-spacing:.04em;text-transform:uppercase;color:var(--accent);border:1px solid var(--accent);border-radius:999px;padding:2px 8px}
```

(If `.deliv` is not `position:relative`, add `position:relative` to the existing `.deliv` rule so the badge anchors correctly.)

- [ ] **Step 4: Wire the Generate button to enqueue**

The `#genBtn` (~712) currently has `data-go="processing"`. Remove `data-go` and wire explicitly so we enqueue first. Change the markup to drop `data-go="processing"` (keep id `genBtn`). Then in `initDeliverables`, after `updateDelivCount()` (~1245), add a guarded handler:

```javascript
  if(!genWired){
    genWired=true;
    document.getElementById('genBtn').addEventListener('click',async()=>{
      const chosen=[...selectedDeliv];
      if(!chosen.length){ toast('Pick at least one deliverable'); return; }
      try{
        await API.setDeliverables(AppState.currentJobId, chosen);
        go('processing');
      }catch(err){ toast(err.message||'Could not start processing'); }
    });
  }
```

Add the guard near `delivInit` (~1221): change `let delivInit=false;` to `let delivInit=false, genWired=false;`.

- [ ] **Step 5: Syntax-check** (Task 9 extract + `node --check`). Exit 0.

- [ ] **Step 6: Commit**

```bash
git add Website/index.html
git commit -m "feat(frontend): deliverables enqueue + Player Highlights coming-soon"
```

---

## Task 6: Wire Processing — poll real status

**Files:**
- Modify: `Website/index.html` (`initProcessing` ~1257, `finishProc` ~1287)

**Behavior:** Replace the fake `procTimer` with polling `GET /status` every ~1.5s. Map backend `progress` to the bar, `stage_label` to the active UI stage row, and transition to Results on `state==='ready'` (or show a friendly error on `state==='failed'`).

- [ ] **Step 1: Replace the fake progress loop**

In `initProcessing`, replace the block from `if(procTimer)clearInterval(procTimer);` through the end of the `procTimer=setInterval(...)` definition and the `#skipProc` handler (~1268-1279) with:

```javascript
  if(procTimer)clearInterval(procTimer);
  const fill=document.getElementById('procFill'),pct=document.getElementById('procPct'),eta=document.getElementById('procEta');
  const total=STAGES.length;
  // map a backend stage name to one of the 5 UI stage rows
  function uiStageIndex(stage){
    const map={decoding:0,detecting:0,tracking:1,teams:1,ball:1,analytics:2,events:3,player_highlights:4,ready:4};
    return (stage in map)?map[stage]:0;
  }
  setStage(0);
  async function poll(){
    if(!document.getElementById('v-processing').classList.contains('show')){ clearInterval(procTimer); return; }
    try{
      const s=await API.getStatus(AppState.currentJobId);
      const p=Math.max(0,Math.min(100,s.progress||0));
      fill.style.width=p+'%'; pct.textContent=Math.round(p)+'%';
      if(s.stage_label) document.getElementById('procStageLabel')?.replaceChildren(document.createTextNode(s.stage_label));
      setStage(uiStageIndex(s.stage||'decoding'));
      if(s.state==='ready'){ clearInterval(procTimer); fill.style.width='100%'; pct.textContent='100%'; finishProc(); }
      else if(s.state==='failed'){ clearInterval(procTimer); eta.textContent=s.error||'Something went wrong.'; toast(s.error||'Processing failed'); }
      else { eta.textContent='Working… you can leave and come back'; }
    }catch(err){ /* transient; keep polling */ }
  }
  poll();
  procTimer=setInterval(poll,1500);
```

(If `#procStageLabel` does not exist, the optional-chaining `?.` makes that line a no-op — safe. The five `STAGES` rows still light up via `setStage`.)

- [ ] **Step 2: Keep `finishProc` but make navigation honest**

`finishProc` (~1287) already marks stages done, stops the radar, toasts, unlocks results, and navigates after 1.1s. Leave it as-is — it works with the real flow. (No edit required unless it references removed vars; it does not.)

- [ ] **Step 3: Syntax-check** (Task 9 extract + `node --check`). Exit 0.

- [ ] **Step 4: Commit**

```bash
git add Website/index.html
git commit -m "feat(frontend): processing screen polls real job status"
```

---

## Task 7: Wire Dashboard + Results — real jobs, outputs, downloads

**Files:**
- Modify: `Website/index.html` (`initDashboard` ~1008, `initResults` ~1327, dashboard boot at ~1437)

**Behavior:** Dashboard lists real jobs from `GET /api/jobs` (with the existing visual cards; falls back to the demo `MATCHES` only if the API is unreachable, so the page never looks broken offline). Results lists real output files from `GET /outputs` with working downloads. Player reels section shows an empty/"coming soon" note (Player Highlights deferred).

- [ ] **Step 1: Make `initDashboard` async + data-driven**

Replace `initDashboard` (~1008-1037) with:

```javascript
let dashInit=false;
async function initDashboard(){
  const grid=document.getElementById('matchGrid');
  grid.innerHTML='';
  const nc=document.createElement('div'); nc.className='card new-card reveal'; nc.dataset.go='setup';
  nc.innerHTML=`<div class="plus"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 5v14M5 12h14" stroke-linecap="round"/></svg></div><b>New Match</b><span>Start from a recording</span>`;
  grid.appendChild(nc);
  let jobs=[];
  try{ jobs=await API.listJobs(); }catch(e){ jobs=null; }
  const items = jobs===null
    ? MATCHES.map((m,i)=>({demo:true, ...m}))               // offline fallback: demo cards
    : jobs.map(j=>({job_id:j.job_id, name:j.match_name, date:j.match_date, sport:j.sport,
                    status:(j.state==='ready'?'ready':j.state==='failed'?'draft':'proc'), seed:(j.match_name.length*7)%30}));
  items.forEach(m=>{
    const badge = m.status==='ready'?'<span class="badge ready"><span class="led"></span>Ready</span>'
      : m.status==='proc'?'<span class="badge proc"><span class="led"></span>Processing</span>'
      : '<span class="badge draft"><span class="led"></span>Draft</span>';
    const sportIcon = m.sport==='basketball'
      ? '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6"><circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3v18M5 5c4 3 4 11 0 14M19 5c-4 3-4 11 0 14"/></svg>'
      : '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6"><circle cx="12" cy="12" r="9"/><path d="M12 3l4 3-1.5 5h-5L8 6z"/></svg>';
    const el=document.createElement('div'); el.className='card match reveal';
    el.innerHTML=`
      <div class="thumb"><canvas></canvas>
        <div class="sport-chip">${sportIcon}${m.sport[0].toUpperCase()+m.sport.slice(1)}</div>
        <div class="play"><svg viewBox="0 0 24 24" fill="currentColor"><polygon points="7,5 19,12 7,19"/></svg></div>
      </div>
      <div class="match-body">
        <h3>${m.name}</h3>
        <div class="match-meta">${badge}<span>·</span><span>${m.date}</span></div>
      </div>`;
    el.addEventListener('click',()=>{
      if(m.demo){ go(m.status==='ready'?'results':'processing'); return; }
      AppState.currentJobId=m.job_id;
      go(m.status==='ready'?'results':'processing');
    });
    grid.appendChild(el);
    drawFootage(el.querySelector('canvas'), m.sport, m.seed||7);
  });
  document.querySelectorAll('#v-dashboard .stat .n').forEach(countUp);
  observeReveals();
}
```

(Note: removed the `dashInit` early-return so the dashboard refreshes each visit — real job lists change. `dashInit` var kept declared but unused is fine; or delete the `let dashInit=false;` line.)

- [ ] **Step 2: Make `initResults` show real outputs**

Replace the `initResults` body (~1327-1360). Keep the report-video canvas decoration, but drive the clip list from real outputs and the player section from a coming-soon note:

```javascript
let resultsInit=false;
async function initResults(){
  const rv=document.getElementById('reportVid'); let cv=rv.querySelector('canvas');
  if(!cv){cv=document.createElement('canvas');rv.insertBefore(cv,rv.firstChild);}
  drawFootage(cv,selSport,42,{track:true});

  // tabs (wire once)
  if(!resultsInit){
    resultsInit=true;
    document.querySelectorAll('.rtab').forEach(t=>t.addEventListener('click',()=>{
      document.querySelectorAll('.rtab').forEach(z=>z.classList.remove('active')); t.classList.add('active');
      document.querySelectorAll('.rpanel').forEach(p=>p.classList.remove('show'));
      document.getElementById('rp-'+t.dataset.rtab).classList.add('show');
    }));
  }

  const id=AppState.currentJobId;
  let files=[];
  try{ if(id) files=await API.listOutputs(id); }catch(e){ files=[]; }

  // Event-highlights / coach outputs -> real downloadable file rows
  const cl=document.getElementById('clipList'); if(cl){
    cl.innerHTML='';
    if(!files.length){
      cl.innerHTML='<div class="empty" style="opacity:.7;padding:18px">No files yet. They appear here when processing finishes.</div>';
    } else {
      files.forEach(fn=>{
        const el=document.createElement('div'); el.className='card cliprow';
        el.innerHTML=`<div class="ct"><canvas></canvas></div>
          <div class="ci"><b>${fn}</b><div class="tags"><span>${id}</span></div></div>
          <a class="dlbtn" href="${API.outputUrl(id,fn)}" download><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 3v12m0 0l-4-4m4 4l4-4M4 17v2a2 2 0 002 2h12a2 2 0 002-2v-2" stroke-linecap="round"/></svg></a>`;
        cl.appendChild(el);
        drawFootage(el.querySelector('canvas'),selSport,(fn.length*5)%30,{players:true});
      });
    }
  }

  // Player reels deferred to Plan 4
  const pg=document.getElementById('playerGrid'); if(pg){
    pg.innerHTML='<div class="empty" style="opacity:.7;padding:18px">Player highlight reels are coming soon.</div>';
  }
}
```

- [ ] **Step 3: Fix the boot calls**

At the very bottom of the inline script (~1437-1439):

```javascript
initDashboard();
observeReveals();
document.querySelectorAll('#v-dashboard .stat .n').forEach(countUp);
```

`initDashboard` is now async; calling it bare is fine (fire-and-forget). Leave these lines. (No change required.)

- [ ] **Step 4: Syntax-check** (Task 9 extract + `node --check`). Exit 0.

- [ ] **Step 5: Commit**

```bash
git add Website/index.html
git commit -m "feat(frontend): dashboard lists real jobs; results shows real outputs"
```

---

## Task 8: End-to-end driver script (server-side proof of the UI's sequence)

**Files:**
- Create: `scripts/e2e_frontend_flow.py`

**Behavior:** A Python script that starts nothing itself but, against an already-running server (or via TestClient), performs the EXACT request sequence the wired UI performs, asserting each step. This gives an automated regression for the contract the JS depends on without a browser.

- [ ] **Step 1: Write the driver (uses FastAPI TestClient — no live server needed)**

Create `scripts/e2e_frontend_flow.py`:

```python
"""End-to-end driver mirroring the wired UI's request sequence.
Run: .venv\\Scripts\\python.exe scripts\\e2e_frontend_flow.py
Exits 0 on success, non-zero on any failed step."""
import sys, tempfile
from pathlib import Path

import cv2
import numpy as np
from fastapi.testclient import TestClient

from backend.main import create_app


def _tiny_mp4(path):
    vw = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), 10.0, (64, 48))
    for _ in range(5):
        vw.write(np.zeros((48, 64, 3), np.uint8))
    vw.release()


def main() -> int:
    tmp = Path(tempfile.mkdtemp())
    app = create_app(jobs_dir=tmp / "jobs", start_worker=False)
    c = TestClient(app)

    # 1. Setup: create job (sport + name + date)
    jid = c.post("/api/jobs", json={"sport": "football",
                 "match_name": "Wired Flow", "match_date": "2026-05-31"}).json()["job_id"]
    print("created", jid)

    # 2. Setup: stream upload (raw body, like XHR.send(file))
    vid = tmp / "v.mp4"; _tiny_mp4(vid)
    r = c.post(f"/api/jobs/{jid}/video", content=vid.read_bytes(),
               headers={"content-type": "application/octet-stream"})
    assert r.status_code == 200 and r.json()["state"] == "calibration_pending", r.text
    print("uploaded")

    # 3. Court: fetch frame, then save calibration (4 corner labels)
    assert c.get(f"/api/jobs/{jid}/frame").status_code == 200
    pts = [{"pixel_x": 9, "pixel_y": 9, "real_world_label": "far-left corner"},
           {"pixel_x": 55, "pixel_y": 9, "real_world_label": "far-right corner"},
           {"pixel_x": 58, "pixel_y": 40, "real_world_label": "near-right corner"},
           {"pixel_x": 5, "pixel_y": 40, "real_world_label": "near-left corner"}]
    assert c.post(f"/api/jobs/{jid}/calibration",
                  json={"calibration_points": pts}).status_code == 200
    print("calibrated")

    # 4. Deliverables: enqueue the two settled deliverables
    r = c.post(f"/api/jobs/{jid}/deliverables",
               json={"deliverables_requested": ["coach_analytics", "event_highlights"]})
    assert r.status_code == 200 and r.json()["state"] == "queued", r.text
    print("queued")

    # 5. Processing: run the worker (stub), then poll status to ready
    app.state.worker.run_one()
    st = c.get(f"/api/jobs/{jid}/status").json()
    assert st["state"] == "ready" and st["progress"] == 100, st
    print("ready")

    # 6. Results: list + download outputs
    files = c.get(f"/api/jobs/{jid}/outputs").json()
    assert "analytics.stub.txt" in files and "events.stub.txt" in files, files
    dl = c.get(f"/api/jobs/{jid}/outputs/analytics.stub.txt")
    assert dl.status_code == 200, dl.status_code
    print("downloaded", files)

    # 7. Dashboard: the job shows up in the list
    listing = c.get("/api/jobs").json()
    assert any(j["job_id"] == jid for j in listing), listing
    print("listed")

    print("E2E FRONTEND FLOW: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Run it**

Run: `.venv\Scripts\python.exe scripts\e2e_frontend_flow.py`
Expected: prints each step then `E2E FRONTEND FLOW: OK`, exit 0.

- [ ] **Step 3: Commit**

```bash
git add scripts/e2e_frontend_flow.py
git commit -m "test(frontend): server-side e2e driver mirroring the wired UI sequence"
```

---

## Task 9: Full verification — JS syntax, backend suite, live click-through

**Files:** none (verification only) — except a `build/` scratch dir (gitignored).

- [ ] **Step 1: Ensure `build/` is gitignored**

If `.gitignore` lacks it, append:

```
build/
```

- [ ] **Step 2: Validate the inline JS parses**

Run:
```
.venv\Scripts\python.exe -c "import re,os; os.makedirs('build',exist_ok=True); h=open('Website/index.html',encoding='utf-8').read(); s=re.search(r'<script>(.*?)</script>', h, re.S).group(1); open('build/_inline.js','w',encoding='utf-8').write(s)"
node --check build/_inline.js
node --check Website/app.js
```
Expected: both `node --check` exit 0 (no syntax errors).

- [ ] **Step 3: Run all automated tests**

Run: `.venv\Scripts\python.exe -m pytest tests/backend -q`  → 46 passed.
Run: `node --test tests/frontend/api.test.mjs`  → 4 passed.
Run: `.venv\Scripts\python.exe scripts\e2e_frontend_flow.py`  → `E2E FRONTEND FLOW: OK`.

- [ ] **Step 4: Live click-through (manual, with a real browser)**

Start the server: `.venv\Scripts\python.exe -m backend.main`
In a browser open `http://localhost:8000` and verify:
1. Dashboard loads (no console errors; shows "New Match" + any real jobs, or demo cards if first run).
2. New Match → pick sport, name/date, choose `clips/football.mp4` → real upload progress → Continue enables.
3. Court → the real freeze-frame image appears; click the 4 corners (or Auto-detect) → Confirm → lands on Deliverables.
4. Deliverables → Player Highlights shows "Coming soon" and is not selectable; Coach Analytics + Event Highlights selectable → Generate.
5. Processing → progress advances from real status; transitions to Results (stub finishes fast).
6. Results → real output files listed with working Download links.
7. Open browser devtools Console: confirm NO red errors during the flow.
Stop the server with Ctrl+C. (This step is manual because no headless browser is installed; if any console error or broken step appears, treat it as a failing test and fix before completing.)

- [ ] **Step 5: Commit any gitignore change**

```bash
git add .gitignore
git commit -m "chore: ignore build/ scratch dir for JS syntax checks" || echo "nothing to commit"
```

---

## Self-Review (completed during plan authoring)

**Spec coverage (frontend wiring, spec §4 table):**
- `simulateUpload` → real `/video` (XHR progress): Task 3. ✅
- dashboard mock array → `GET /api/jobs`: Task 7 (with offline fallback so it never looks broken). ✅
- court canvas → `GET /frame` + `POST /calibration`: Task 4. ✅
- roster → `POST /roster`: **deferred** — roster/tagging screen is skipped in Plan 2 (court routes to deliverables) because it only serves Player Highlights, which is deferred to Plan 4. Documented, not silently dropped. The `API.saveRoster` client method exists for Plan 4. ✅ (intentional scope)
- tagging → `/tagging-clips` + `/tags`: deferred to Plan 4 (per user decision "defer cleanly"). ✅
- deliverable select → `POST /deliverables`: Task 5. ✅
- processing → poll `GET /status`: Task 6. ✅
- results → `GET /outputs` + downloads: Task 7. ✅
- static serve at `/`: already from Plan 1. ✅

**Placeholder scan:** No TBD/TODO. Every step has concrete code or an exact command. ✅

**Type/name consistency:** `API` methods (`createJob`, `uploadVideo`, `frameUrl`, `saveCalibration`, `saveRoster`, `setDeliverables`, `getStatus`, `listJobs`, `listOutputs`, `outputUrl`) and `_build` helpers are defined in Task 1 and used identically in Tasks 3–7. `AppState.currentJobId` set in Task 3, read in Tasks 4–7. New guard flags (`courtNextWired`, `genWired`) declared where introduced. Backend field names match the Plan-1 contract exactly. ✅

**Risk notes for the implementer:**
- Editing a 1442-line single file: make each Edit match unique surrounding text; after EVERY task run the Task-9 Step-2 `node --check` to catch a broken edit immediately.
- The `app.js` load-order subtlety is resolved in Task 2 (classic blocking script + guarded `module.exports`). Verify the order check in Task 2 Step 4 passes.
- If the Setup screen's Continue button or specific element IDs differ slightly from the anchors above, search for the nearest matching element and adapt — the behavior (create job, upload, gate Continue) is what matters.
- Manual browser verification (Task 9 Step 4) is required because no headless browser is installed. Do not mark the plan complete on green automated tests alone — the DOM wiring must be eyeballed once.
