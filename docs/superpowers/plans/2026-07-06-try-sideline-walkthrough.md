# Try Sideline Walkthrough Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a public, client-side "Try Sideline" walkthrough (`demo.html`) that simulates the full flow — court setup → find players → choose output → processing → real sample results.

**Architecture:** One wizard page driven by an in-memory step index. The only real logic is a 4-point homography solver reused to warp a football pitch model onto a clicked frame; everything else is bundled images + scripted timing. No backend, no network beyond loading bundled assets.

**Tech Stack:** Vanilla ES modules (matches the existing `site/`), `node:test` for unit tests, HTML canvas for the pitch overlay. Deployed via `wrangler pages deploy`.

## Global Constraints

- Pure frontend only — no backend, no GPU, no Supabase/Drive writes.
- Self-contained: all assets bundled under `site/demo/`; no external hosts (Cloudflare Pages CSP).
- Reachable without login.
- No mp4 embeds (mp4v not browser-playable) — clips reached only via the Drive link.
- Follow existing `site/` conventions: ES modules, `node --test site/tests/*.test.mjs`.

---

### Task 1: Homography math module (`site/js/calibration.js`)

**Files:**
- Create: `site/js/calibration.js`
- Test: `site/tests/calibration.test.mjs`

**Interfaces:**
- Produces:
  - `worldCorners()` → `[[x,y],...]` the 4 pitch corners in metres, order far-left, far-right, near-right, near-left: `[[-52.5,34],[52.5,34],[52.5,-34],[-52.5,-34]]`.
  - `computeHomography(src, dst)` → 3×3 array `H` (row-major) mapping `src`→`dst`, or `null` if degenerate. `src`/`dst` are arrays of 4 `[x,y]`.
  - `project(H, [x,y])` → `[x',y']` applying `H` with perspective divide.

- [ ] **Step 1: Write failing tests**

```js
import test from "node:test";
import assert from "node:assert/strict";
import { worldCorners, computeHomography, project } from "../js/calibration.js";

const near = (a, b, eps = 1e-6) => Math.abs(a - b) <= eps;

test("worldCorners are the FIFA pitch corners in order", () => {
  assert.deepEqual(worldCorners(), [[-52.5,34],[52.5,34],[52.5,-34],[-52.5,-34]]);
});

test("identity mapping: same src and dst yields a projection that returns input", () => {
  const pts = [[0,0],[1,0],[1,1],[0,1]];
  const H = computeHomography(pts, pts);
  const p = project(H, [0.5, 0.5]);
  assert.ok(near(p[0], 0.5) && near(p[1], 0.5));
});

test("maps the unit square to a translated+scaled square", () => {
  const src = [[0,0],[1,0],[1,1],[0,1]];
  const dst = [[10,10],[30,10],[30,30],[10,30]]; // scale 20, offset 10
  const H = computeHomography(src, dst);
  for (let i = 0; i < 4; i++) {
    const p = project(H, src[i]);
    assert.ok(near(p[0], dst[i][0], 1e-4) && near(p[1], dst[i][1], 1e-4));
  }
  const mid = project(H, [0.5, 0.5]);
  assert.ok(near(mid[0], 20, 1e-4) && near(mid[1], 20, 1e-4));
});

test("collinear source points return null (degenerate)", () => {
  const H = computeHomography([[0,0],[1,1],[2,2],[3,3]], [[0,0],[1,0],[2,0],[3,0]]);
  assert.equal(H, null);
});
```

- [ ] **Step 2: Run to verify FAIL**

Run: `node --test site/tests/calibration.test.mjs`
Expected: FAIL (module/exports missing).

- [ ] **Step 3: Implement `site/js/calibration.js`**

Solve the 8×8 linear system for the homography (h33 = 1) via Gaussian elimination with partial pivoting; return null if the matrix is singular (degenerate/collinear).

```js
// 4-point homography (DLT with h33=1), pure JS, no deps.
export function worldCorners() {
  // FIFA 105x68 m, centre origin; order: far-left, far-right, near-right, near-left.
  return [[-52.5, 34], [52.5, 34], [52.5, -34], [-52.5, -34]];
}

function solve(A, b) {
  const n = b.length;
  for (let col = 0; col < n; col++) {
    let piv = col;
    for (let r = col + 1; r < n; r++) if (Math.abs(A[r][col]) > Math.abs(A[piv][col])) piv = r;
    if (Math.abs(A[piv][col]) < 1e-12) return null;           // singular → degenerate
    [A[col], A[piv]] = [A[piv], A[col]];
    [b[col], b[piv]] = [b[piv], b[col]];
    for (let r = 0; r < n; r++) {
      if (r === col) continue;
      const f = A[r][col] / A[col][col];
      for (let c = col; c < n; c++) A[r][c] -= f * A[col][c];
      b[r] -= f * b[col];
    }
  }
  return b.map((v, i) => v / A[i][i]);
}

export function computeHomography(src, dst) {
  const A = [], b = [];
  for (let i = 0; i < 4; i++) {
    const [x, y] = src[i], [u, v] = dst[i];
    A.push([x, y, 1, 0, 0, 0, -u * x, -u * y]); b.push(u);
    A.push([0, 0, 0, x, y, 1, -v * x, -v * y]); b.push(v);
  }
  const h = solve(A, b);
  if (!h) return null;
  return [[h[0], h[1], h[2]], [h[3], h[4], h[5]], [h[6], h[7], 1]];
}

export function project(H, [x, y]) {
  const w = H[2][0] * x + H[2][1] * y + H[2][2];
  return [(H[0][0]*x + H[0][1]*y + H[0][2]) / w, (H[1][0]*x + H[1][1]*y + H[1][2]) / w];
}
```

- [ ] **Step 4: Run to verify PASS**

Run: `node --test site/tests/calibration.test.mjs`
Expected: 4 pass.

- [ ] **Step 5: Commit**

```bash
git add site/js/calibration.js site/tests/calibration.test.mjs
git commit -m "feat(demo): client-side 4-point homography helpers"
```

---

### Task 2: Football pitch model (`site/js/pitchmodel.js`)

**Files:**
- Create: `site/js/pitchmodel.js`

**Interfaces:**
- Produces: `pitchSegments()` → array of polylines, each `[[x,y],...]` in metres, for the pitch outline, halfway line, centre circle (polygon approximation), and both penalty + goal boxes. Consumed by Task 3 drawing.

- [ ] **Step 1: Implement `site/js/pitchmodel.js`**

```js
// Football pitch lines in metres, centre origin (matches worldCorners()).
export function pitchSegments() {
  const HX = 52.5, HY = 34;              // half length/width
  const segs = [
    [[-HX,-HY],[HX,-HY],[HX,HY],[-HX,HY],[-HX,-HY]], // outline
    [[0,-HY],[0,HY]],                                 // halfway line
  ];
  // Centre circle r=9.15, 48-gon.
  const circle = [];
  for (let i = 0; i <= 48; i++) { const t = (i/48)*2*Math.PI; circle.push([9.15*Math.cos(t), 9.15*Math.sin(t)]); }
  segs.push(circle);
  // Penalty box 16.5 deep x 40.32 wide; goal box 5.5 x 18.32. Both ends.
  for (const s of [-1, 1]) {
    const x0 = s * HX, xP = s * (HX - 16.5), xG = s * (HX - 5.5);
    segs.push([[x0,-20.16],[xP,-20.16],[xP,20.16],[x0,20.16]]);   // penalty box
    segs.push([[x0,-9.16],[xG,-9.16],[xG,9.16],[x0,9.16]]);       // goal box
  }
  return segs;
}
```

- [ ] **Step 2: Commit**

```bash
git add site/js/pitchmodel.js
git commit -m "feat(demo): football pitch model line segments"
```

---

### Task 3: Bundle demo assets (`site/demo/`)

**Files:**
- Create: `site/demo/football_frame.png` (from `outputs/frames/football_midframe.png`)
- Create: `site/demo/football_tracked.png` (from `outputs/frames/football_tracked_midframe.png`)
- Create: `site/demo/results/heatmap_team.png`, `heatmap_a.png`, `heatmap_b.png` (from `outputs/deliverables/SNGS-118/`)

- [ ] **Step 1: Copy assets**

```bash
mkdir -p site/demo/results
cp outputs/frames/football_midframe.png site/demo/football_frame.png
cp outputs/frames/football_tracked_midframe.png site/demo/football_tracked.png
cp outputs/deliverables/SNGS-118/heatmap_team.png site/demo/results/heatmap_team.png
cp outputs/deliverables/SNGS-118/heatmap_player007.png site/demo/results/heatmap_a.png
cp outputs/deliverables/SNGS-118/heatmap_player005.png site/demo/results/heatmap_b.png
```

- [ ] **Step 2: Commit**

```bash
git add site/demo/
git commit -m "chore(demo): bundle sample frames and heatmaps"
```

---

### Task 4: The walkthrough wizard (`site/demo.html`)

**Files:**
- Create: `site/demo.html`

**Interfaces:**
- Consumes: `worldCorners`, `computeHomography`, `project` (Task 1); `pitchSegments` (Task 2); bundled images (Task 3); `_STAGE_LABELS` copy from `backend/pipeline.py`.

**Structure (one `<script type="module">`):**
- A `steps` array of section element ids; `showStep(i)` toggles `.hidden`.
- **Step 1 court setup:** draw `football_frame.png` to a `<canvas>`; on click, push image coords (scaled to natural size) into `clicks[]`, draw a dot + label the next corner. On the 4th click: `H = computeHomography(worldCorners(), clicks)`; if `null` → error message + Reset; else redraw frame and, for each `pitchSegments()` polyline, `project(H, pt)` every vertex and stroke it. "Next" enabled once drawn. "Reset" clears `clicks`.
- **Step 2 find players:** show `football_tracked.png`; caption "We found the players automatically."; 2 text inputs ("Name player #7", "Name player #5") — cosmetic. "Next".
- **Step 3 choose output:** 3 checkboxes (Coach analytics / Event highlights / Player highlights), all checked. "Run analysis".
- **Step 4 processing:** show a progress bar; iterate the stage-label list on a timer (~1.2s each), updating a caption; on completion auto-advance to step 5. Labels array (copied verbatim): `["Decoding video","Tracking players","Assigning teams","Computing analytics","Finding involvement","Rendering highlights","Packaging results"]`.
- **Step 5 results:** grid of the 3 heatmap PNGs from `site/demo/results/`; a caption "Sample output — matches you submit are processed for you."; an "Open the full results" button. The button's href is `RESULTS_URL` — a `const` at the top of the script, default `"jobs.html"` (fallback), to be replaced with the Tottenham Drive `results_url` in Task 6.

- [ ] **Step 1: Write `site/demo.html`**

Build the markup + module per the structure above. Reuse `styles.css`. Each step is a `<section id="step-N" class="hidden">`. Keep the pitch overlay stroke bright (e.g. `#39FF88`) over the frame.

- [ ] **Step 2: Manual check locally is not required; verified on deploy in Task 5.** Sanity-run the test suite to ensure nothing else broke.

Run: `node --test site/tests/*.test.mjs`
Expected: all pass (calibration tests included).

- [ ] **Step 3: Commit**

```bash
git add site/demo.html
git commit -m "feat(demo): Try Sideline walkthrough wizard"
```

---

### Task 5: Link + deploy + browser verification

**Files:**
- Modify: `site/index.html` (add a "See how it works" link near the sign-in card, `href="demo.html"`).

- [ ] **Step 1: Add the link**

In `index.html`, below the sign-in card add:
```html
<p class="msg" style="margin-top:12px"><a href="demo.html">See how it works →</a></p>
```

- [ ] **Step 2: Deploy to preview**

Run: `npx wrangler pages deploy site --project-name sideline --commit-dirty=true`

- [ ] **Step 3: Browser verification (real preview)**

Open `https://airline.sideline-d8c.pages.dev/demo.html`, drive all 5 steps:
- Click 4 corners → pitch lines overlay the pitch, no console errors.
- Reset re-arms; fewer than 4 clicks blocks "Next".
- Steps 2–4 advance; loading animates through the stage labels.
- Step 5 shows the 3 heatmaps and the "Open the full results" button.
Read console for errors (must be none).

- [ ] **Step 4: Commit**

```bash
git add site/index.html
git commit -m "feat(demo): link the walkthrough from the sign-in page"
```

---

### Task 6: Wire real Tottenham results (AFTER that job reaches `ready`)

**Files:**
- Modify: `site/demo.html` (`RESULTS_URL` const; swap fallback heatmaps for real ones)
- Create: `site/demo/results/*` replaced with the Tottenham deliverable heatmaps

**Interfaces:**
- Consumes: the Tottenham job's `results_url` (Supabase `jobs` row) and its deliverable heatmap PNGs (from the local backend job dir or Drive).

- [ ] **Step 1:** Set `RESULTS_URL` in `demo.html` to the Tottenham `results_url`.
- [ ] **Step 2:** Replace `site/demo/results/heatmap_*.png` with the real Tottenham heatmaps.
- [ ] **Step 3:** Redeploy (`npx wrangler pages deploy site --project-name sideline --commit-dirty=true`) and re-verify step 5 in the browser.
- [ ] **Step 4: Commit**

```bash
git add site/demo.html site/demo/results/
git commit -m "feat(demo): use real Tottenham results in the walkthrough"
```

---

## Self-Review

- **Spec coverage:** court setup (T1/T2/T4-step1), find players (T4-step2), choose output (T4-step3), processing with real stage labels (T4-step4), results with Tottenham + fallback (T4-step5, T6), entry link (T5), homography math tested (T1). All spec sections covered.
- **Placeholders:** none — all code shown; stage-label list and asset paths are concrete.
- **Type consistency:** `computeHomography(src,dst)`/`project(H,pt)`/`worldCorners()`/`pitchSegments()` names match across Task 1, 2, 4.
