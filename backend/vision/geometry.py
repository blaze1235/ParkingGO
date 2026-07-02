"""Polygon math for zone/vehicle overlap, dependency-free.

Vehicle boxes are axis-aligned rectangles (convex), so Sutherland-Hodgman
clipping of the (possibly concave) zone polygon against the box gives the
intersection region, and the shoelace formula gives its area.
"""
from typing import Sequence

Point = Sequence[float]
Polygon = Sequence[Point]


def polygon_area(poly: Polygon) -> float:
    n = len(poly)
    if n < 3:
        return 0.0
    acc = 0.0
    for i in range(n):
        x1, y1 = poly[i][0], poly[i][1]
        x2, y2 = poly[(i + 1) % n][0], poly[(i + 1) % n][1]
        acc += x1 * y2 - x2 * y1
    return abs(acc) / 2.0


def clip_polygon_to_rect(poly: Polygon, x1: float, y1: float, x2: float, y2: float) -> list[list[float]]:
    """Clip polygon against axis-aligned rectangle (x1,y1)-(x2,y2)."""

    def clip_edge(points: list[list[float]], inside, intersect) -> list[list[float]]:
        result: list[list[float]] = []
        n = len(points)
        for i in range(n):
            cur, prev = points[i], points[i - 1]
            cur_in, prev_in = inside(cur), inside(prev)
            if cur_in:
                if not prev_in:
                    result.append(intersect(prev, cur))
                result.append(list(cur))
            elif prev_in:
                result.append(intersect(prev, cur))
        return result

    def x_intersect(bound: float):
        def fn(p: Point, q: Point) -> list[float]:
            t = (bound - p[0]) / (q[0] - p[0])
            return [bound, p[1] + t * (q[1] - p[1])]
        return fn

    def y_intersect(bound: float):
        def fn(p: Point, q: Point) -> list[float]:
            t = (bound - p[1]) / (q[1] - p[1])
            return [p[0] + t * (q[0] - p[0]), bound]
        return fn

    pts = [list(p) for p in poly]
    for inside, intersect in (
        (lambda p: p[0] >= x1, x_intersect(x1)),
        (lambda p: p[0] <= x2, x_intersect(x2)),
        (lambda p: p[1] >= y1, y_intersect(y1)),
        (lambda p: p[1] <= y2, y_intersect(y2)),
    ):
        pts = clip_edge(pts, inside, intersect)
        if not pts:
            return []
    return pts


def box_zone_overlap_ratio(box: Sequence[float], zone: Polygon) -> float:
    """Intersection area over min(zone area, box area). box = (x1,y1,x2,y2)."""
    x1, y1, x2, y2 = box[:4]
    box_area = max(0.0, x2 - x1) * max(0.0, y2 - y1)
    zone_area = polygon_area(zone)
    denom = min(box_area, zone_area)
    if denom <= 0:
        return 0.0
    inter = polygon_area(clip_polygon_to_rect(zone, x1, y1, x2, y2))
    return inter / denom
