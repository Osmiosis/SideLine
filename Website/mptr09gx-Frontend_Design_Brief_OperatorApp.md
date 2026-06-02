# Frontend Design Brief — Operator App (for Claude Design)
**Product:** A local web app that lets a non-technical operator (PE teacher or Student Council member) turn a recorded sports match into finished deliverables — with ZERO code or terminal. They open it in a browser, set up the match, and request outputs.
**Visual direction:** Premium dark mode, cinematic, VEO/Hudl-like. High-contrast, professional, looks like a real sports-tech product built by a company. Neutral-professional (NOT school-branded).
**Primary users:** BOTH a non-technical teacher AND a tech-savvy student — so it must feel pro and powerful yet stay genuinely simple to operate. Simplicity and guidance are non-negotiable; never expose technical machinery.

---

## CRITICAL: this UI is a data-collection front for a backend pipeline
Every screen exists to either (a) COLLECT a human input the processing pipeline needs, or (b) let the user REQUEST/DOWNLOAD a deliverable. The collected inputs (sport, court marks, roster, player tags, deliverable choice) are saved and handed to the backend. So each screen's JOB is defined by WHAT IT COLLECTS — design around that. (The backend spec lists the exact fields; this brief lists them per screen so they match.)

---

## Visual language (make it look pro)
- **Dark, cinematic base:** near-black / deep charcoal backgrounds (e.g. #0B0E11 / #11151A), not flat black. Subtle depth via layered surfaces.
- **One confident accent color** (electric/sports energy — e.g. a vivid green, cyan, or amber) used sparingly for primary actions, active states, progress. High contrast against the dark base.
- **Crisp, modern typography:** a clean geometric/grotesque sans (Inter, Geist, or similar), strong size hierarchy, generous line-height. Big confident headings.
- **Generous whitespace + breathing room** even in dark mode — premium = uncrowded.
- **Subtle motion:** smooth transitions, gentle hover states, animated progress. Cinematic but not gimmicky.
- **Sports-tech cues:** thin accent lines, pitch/court iconography, data-viz flourishes (small charts, heatmap thumbnails) used as visual texture. Think broadcast graphics restraint, not clutter.
- **Cards/panels** with soft borders (1px subtle), rounded corners (8-12px), gentle shadows/glows for depth on dark.
- **Status as a first-class visual:** processing states, progress bars, "ready" badges should feel polished and reassuring (a match takes hours — the waiting UX must feel calm and trustworthy).

---

## The operator journey (screen by screen)

### 1. Dashboard / Home
- Entry point. Clean hero: product name/logo (neutral, e.g. a wordmark), a single confident primary action: **"New Match"**.
- Below: a list/grid of past matches as cards — each showing sport icon, match name/date, status badge (Processing / Ready / Draft), thumbnail. Click → that match's deliverables.
- Pro touch: the past-matches grid with status badges + thumbnails is what makes it feel like a real product dashboard.

### 2. New Match — Setup (collects: sport, match name/date, video)
- **Sport selector:** Football / Basketball — big, visual, tappable cards (pitch vs court iconography). One choice.
- **Match details:** name, date (simple fields).
- **Video upload:** a large, friendly drag-or-select zone. Show file name, size, an upload progress bar. Honest about big files (footage is large) — reassuring progress, not a frozen spinner.
- Primary action: **Continue → Court Setup**.

### 3. Court / Pitch Marking (collects: calibration points)
- **THE key human-in-the-loop step.** The operator marks reference points on a still frame from their video so the system understands the real-world field.
- Show a freeze-frame of the pitch/court. Overlay clickable target points. Guide the user: "Click the 4 corners of the court" (or the visible landmarks), with a little diagram showing WHICH points, highlighted one at a time.
- Must be forgiving + guided: show marked points, allow undo/redo/re-drag, a clear "auto-detect" button (tries automatically) with manual fallback. Progress indicator ("3 of 4 points marked").
- Pro touch: a clean mini-map / court diagram beside the frame showing the ideal points, ticking off as they're placed.
- Primary action: **Confirm Calibration**.

### 4. Roster + Player Tagging (collects: roster names, player tags)
- **Two parts.** First, enter the roster (list of player names — simple add-name field, chips/tags). Second (for player-highlights), the tagging flow: the system surfaces short clips, the operator names who's in each ("Who is this?" → tap a roster name).
- Design the tagging as fast and almost game-like: big clip preview, roster names as large tappable buttons below, a progress bar ("clip 12 of N"), skip option. It should feel quick, not tedious.
- NOTE for design: this flow may handle MANY clips — design for volume (bulk actions, keyboard shortcuts, "tag all from this group" affordances). Make it the most ergonomic screen in the app.
- This screen is OPTIONAL depending on which deliverables are requested (only needed for player highlights) — so it may be skipped.

### 5. Choose Deliverables (collects: which outputs)
- The operator picks what they want from this match. Present the THREE outputs as rich selectable cards:
  - **Coach Analytics** — "Tactical report + annotated video" (icon: clipboard/heatmap thumbnail)
  - **Event Highlights** — "Auto-clipped key moments, ranked" (icon: play/star)
  - **Player Highlights** — "A reel for every player" (icon: person/film) — note this enables the tagging step (#4)
- Multi-select. Each card: title, one-line plain-English description, a small representative thumbnail. Selected = accent glow/border.
- Primary action: **Generate** → kicks off processing.

### 6. Processing / Status (the waiting UX — make it calm + premium)
- A match takes HOURS. This screen must make waiting feel trustworthy, not broken.
- Big calm status: which deliverable is being made now, an honest progress indication (stage-based: "Analyzing players → Tracking ball → Building analytics → Clipping highlights"), elapsed/estimated time.
- Let the user leave + come back (it's a background job) — "We'll have this ready; check back or we'll notify." A polished idle/processing animation (cinematic, sports-tech — e.g. a subtle animated tracking-overlay motif).
- Pro touch: the stage-based progress with a sports-data-viz aesthetic is a chance to make even the *waiting* look impressive.

### 7. Deliverables / Results (collects: nothing — delivers)
- The payoff screen. The finished outputs for this match, beautifully presented:
  - Coach analytics: a preview of the report (the one-page summary) + the annotated video, download buttons.
  - Event highlights: the ranked clips as a scannable list/grid with thumbnails, a "draft reel" preview, individual + bulk download.
  - Player highlights: per-player reels as cards (player name + thumbnail), download each.
- Clean download affordances, preview-before-download, share/export. This is the screen that proves the product works — make it feel like opening finished professional deliverables.

---

## Cross-cutting design requirements
- **Guided, linear flow** with a clear step indicator (Setup → Court → Roster/Tag → Deliverables → Processing → Results) — a non-technical teacher should never feel lost.
- **Never show technical terms** — no "homography," "tracking," "inference." Plain English: "court setup," "find players," "make highlights."
- **Reassuring at every wait** — uploads and processing are long; progress + calm states everywhere.
- **Responsive** — a teacher might use a phone/tablet on the sideline; a student a laptop. Works on both.
- **Accessible contrast** — dark mode done right (WCAG-legible text on dark, not low-contrast grey-on-grey).
- **Empty/error states designed** — no raw errors; friendly "something went wrong, try again."

---

## What makes it look "like a professional made it" (the bar)
- Consistent spacing system, type scale, and the single accent used with restraint.
- Real-feeling content: thumbnails, status badges, data-viz textures — not lorem-ipsum boxes.
- Polished micro-interactions (hover, transitions, progress).
- The dashboard (#1), processing (#6), and results (#7) screens are the three that sell it — invest the most polish there.
- Restraint over decoration: premium = confident, uncluttered, high-contrast, purposeful. Resist gradients-everywhere; let the dark base + one accent + good type do the work.

---

## Data each screen must collect (the contract with the backend — keep these exact)
- Screen 2: `sport` (football|basketball), `match_name`, `match_date`, `video_file`
- Screen 3: `calibration_points` (list of {pixel_x, pixel_y, real_world_label})
- Screen 4: `roster` (list of names), `player_tags` (clip_id → roster_name)
- Screen 5: `deliverables_requested` (subset of {coach_analytics, event_highlights, player_highlights})
- Screens 6/7: read job status + deliverable file list from backend (display only)
