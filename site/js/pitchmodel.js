// Football pitch lines in metres, centre origin (matches worldCorners()).
// Each entry is a polyline [[x,y],...]; the demo projects these through the
// operator's homography and strokes them onto the calibrated frame.
export function pitchSegments() {
  const HX = 52.5, HY = 34;              // half length/width
  const segs = [
    [[-HX, -HY], [HX, -HY], [HX, HY], [-HX, HY], [-HX, -HY]], // outline
    [[0, -HY], [0, HY]],                                       // halfway line
  ];
  // Centre circle r=9.15, 48-gon.
  const circle = [];
  for (let i = 0; i <= 48; i++) { const t = (i / 48) * 2 * Math.PI; circle.push([9.15 * Math.cos(t), 9.15 * Math.sin(t)]); }
  segs.push(circle);
  // Penalty box 16.5 deep x 40.32 wide; goal box 5.5 x 18.32. Both ends.
  for (const s of [-1, 1]) {
    const x0 = s * HX, xP = s * (HX - 16.5), xG = s * (HX - 5.5);
    segs.push([[x0, -20.16], [xP, -20.16], [xP, 20.16], [x0, 20.16]]);   // penalty box
    segs.push([[x0, -9.16], [xG, -9.16], [xG, 9.16], [x0, 9.16]]);       // goal box
  }
  return segs;
}
