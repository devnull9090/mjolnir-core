// Close-in steering past what stands in the way (tools/bot/README.md,
// "Obstacles"): the navmesh's walls, at a walker's height.

// A walker's half width plus room to spare, wu.
export const CLEAR = 0.7 / 3.048;

/** Heading (deg, plan) from p toward q, bent past the collision standing in
 *  the way (the navmesh's walls: trees, rocks) within `ahead` wu. The
 *  obstacle is every wall side within a walker's reach of the line around
 *  the first one hit; it is passed on the side that turns less, its
 *  outermost point cleared by CLEAR. */
export function steer(mesh, p, q, z, ahead = 4) {
  const straight = (Math.atan2(q[1] - p[1], q[0] - p[0]) * 180) / Math.PI;
  const length = Math.hypot(q[0] - p[0], q[1] - p[1]);
  if (length < 1e-6) return { heading: straight, around: false };
  const ux = (q[0] - p[0]) / length;
  const uy = (q[1] - p[1]) / length;
  const reach = Math.min(ahead, length);
  const end = [p[0] + ux * reach, p[1] + uy * reach];
  const hits = mesh.wallsAlong(p, end, z, CLEAR);
  if (!hits.length) return { heading: straight, around: false };
  const first = Math.min(...hits.map((h) => h.along));
  // The obstacle: the sides near the first hit, with what stands beside them.
  const near = mesh.wallsAlong(p, [p[0] + ux * (first + 1.5), p[1] + uy * (first + 1.5)], z, CLEAR * 4)
    .filter((h) => h.along <= first + 1.0);
  let left = null;
  let right = null;
  for (const h of near) {
    for (const pt of [h.wall.a, h.wall.b]) {
      const along = (pt[0] - p[0]) * ux + (pt[1] - p[1]) * uy;
      if (along <= 0) continue;
      const side = (pt[1] - p[1]) * ux - (pt[0] - p[0]) * uy; // + left of the line
      const angleLeft = Math.atan2(side + CLEAR, along);
      const angleRight = Math.atan2(side - CLEAR, along);
      if (left === null || angleLeft > left) left = angleLeft;
      if (right === null || angleRight < right) right = angleRight;
    }
  }
  if (left === null) return { heading: straight, around: false };
  // Turn left by `left` or right by `-right`, whichever is less.
  const turn = left < -right ? left : right;
  return { heading: straight + (turn * 180) / Math.PI, around: true };
}
