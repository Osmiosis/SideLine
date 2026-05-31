import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
const require = createRequire(import.meta.url);
const { _build } = require('../../Website/app.js');

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
