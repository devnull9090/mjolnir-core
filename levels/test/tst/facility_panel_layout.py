"""Place the facility's fitted fields in the actual clear bays between ribs.

Distances are metres along a single straight branch segment.  The safety gap
includes the half-thickness of the rib and a visible architectural reveal.
This pure helper is shared by the Blender generator and its layout tests.
"""


def branch_panel_bays(length, stations, start_x, tangent_x, *,
                      end_margin=0.60, rib_half_width=0.24, reveal=0.16,
                      maximum_width=3.10, minimum_width=1.20, wall_limit=37.0,
                      oblique_view_setback=0.95):
    """Return (start, end) intervals for panels which never cross a rib.

    Stop the panels before the lateral-concourse opening. Shorten the end
    on both sides of every rib by an extra setback: player cameras looking
    obliquely along a bent passage can see a rib's inner face projected over
    an otherwise physically disjoint panel. Empty or unusually short
    bays are deliberately left bare. All three nested fields use one extent.
    """
    if length <= 0 or maximum_width <= 0 or minimum_width <= 0 or oblique_view_setback < 0:
        raise ValueError('branch dimensions must be positive')
    lo, hi = end_margin, length - end_margin
    # |start_x + tangent_x * station| < wall_limit.  This also works for
    # mirrored branches and reversed tangents.
    if abs(tangent_x) > 1e-9:
        boundary = sorted(((-wall_limit - start_x) / tangent_x,
                           (wall_limit - start_x) / tangent_x))
        lo, hi = max(lo, boundary[0]), min(hi, boundary[1])
    elif abs(start_x) >= wall_limit:
        return []
    if hi <= lo:
        return []
    gap = rib_half_width + reveal
    exclusions = sorted((s-gap-oblique_view_setback, s+gap+oblique_view_setback)
                        for s in stations
                        if s+gap+oblique_view_setback > lo and s-gap-oblique_view_setback < hi)
    spans = []
    cursor = lo
    for left, right in exclusions:
        if left > cursor:
            spans.append((cursor, min(left, hi)))
        cursor = max(cursor, right)
        if cursor >= hi:
            break
    if cursor < hi:
        spans.append((cursor, hi))
    result = []
    for a, b in spans:
        if b-a < minimum_width:
            continue
        midpoint = (a+b)/2
        half = min((b-a)/2, maximum_width/2)
        result.append((midpoint-half, midpoint+half))
    return result
