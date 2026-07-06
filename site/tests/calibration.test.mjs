import test from "node:test";
import assert from "node:assert/strict";
import { worldCorners, computeHomography, project } from "../js/calibration.js";

const near = (a, b, eps = 1e-6) => Math.abs(a - b) <= eps;

test("worldCorners are the FIFA pitch corners in order", () => {
  assert.deepEqual(worldCorners(), [[-52.5, 34], [52.5, 34], [52.5, -34], [-52.5, -34]]);
});

test("identity mapping: same src and dst yields a projection that returns input", () => {
  const pts = [[0, 0], [1, 0], [1, 1], [0, 1]];
  const H = computeHomography(pts, pts);
  const p = project(H, [0.5, 0.5]);
  assert.ok(near(p[0], 0.5) && near(p[1], 0.5));
});

test("maps the unit square to a translated+scaled square", () => {
  const src = [[0, 0], [1, 0], [1, 1], [0, 1]];
  const dst = [[10, 10], [30, 10], [30, 30], [10, 30]]; // scale 20, offset 10
  const H = computeHomography(src, dst);
  for (let i = 0; i < 4; i++) {
    const p = project(H, src[i]);
    assert.ok(near(p[0], dst[i][0], 1e-4) && near(p[1], dst[i][1], 1e-4));
  }
  const mid = project(H, [0.5, 0.5]);
  assert.ok(near(mid[0], 20, 1e-4) && near(mid[1], 20, 1e-4));
});

test("collinear source points return null (degenerate)", () => {
  const H = computeHomography([[0, 0], [1, 1], [2, 2], [3, 3]], [[0, 0], [1, 0], [2, 0], [3, 0]]);
  assert.equal(H, null);
});
