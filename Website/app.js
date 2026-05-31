/* Operator App — API client + shared client state.
   Loaded BEFORE the inline <script> in index.html, so `API`, `AppState`,
   and `_build` are globals there. Also CommonJS-require-able for node unit tests. */

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
