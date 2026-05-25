"""Smart subdivision-resolution recommendations."""

from __future__ import annotations

import math

from pyscript_app.geometry_utils import compute_surface_area
from pyscript_app.mapping import (
    MODE_CUBIC,
    MODE_CYLINDRICAL,
    MODE_PLANAR_XY,
    MODE_PLANAR_XZ,
    MODE_PLANAR_YZ,
    MODE_SPHERICAL,
    MODE_TRIPLANAR,
)
from pyscript_app.texture_analysis import analyze_texture


HARD_CAP_TRIANGLES = 16_000_000
HARD_CAP_HEADROOM = 0.5
TRIS_PER_AREA_GEOM = 4 / math.sqrt(3)
DECIM_COARSEN = 1.0
DECIM_REF_AMP = 0.5
DECIM_MIN_AMP = 0.1
DECIM_MIN_TRI = 10_000
DECIM_MAX_TRI = 2_000_000


def _attr(obj, name, default=None):
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def compute_world_period(settings, bounds):
    size = bounds["size"] if isinstance(bounds, dict) else bounds.size
    aspect_u = _attr(settings, "textureAspectU", 1)
    aspect_v = _attr(settings, "textureAspectV", 1)
    scale_u = (_attr(settings, "scaleU") or 1e-6) / aspect_u
    scale_v = (_attr(settings, "scaleV") or 1e-6) / aspect_v

    md = max(size.x, size.y, size.z, 1e-6)
    planar = md * scale_u
    planar_v = md * scale_v
    mode = _attr(settings, "mappingMode")

    if mode in (MODE_PLANAR_XY, MODE_PLANAR_XZ, MODE_PLANAR_YZ):
        return {"periodU_mm": planar, "periodV_mm": planar_v}
    if mode == MODE_CYLINDRICAL:
        radius_default = max(size.x, size.y) * 0.5
        radius = max(_attr(settings, "cylinderRadius", radius_default) or radius_default, 1e-6)
        circumference = 2 * math.pi * radius
        return {"periodU_mm": circumference * scale_u, "periodV_mm": circumference * scale_v}
    if mode == MODE_SPHERICAL:
        radius = max(0.5 * max(size.x, size.y, size.z), 1e-6)
        return {"periodU_mm": 2 * math.pi * radius * scale_u, "periodV_mm": math.pi * radius * scale_v}
    if mode in (MODE_TRIPLANAR, MODE_CUBIC):
        return {"periodU_mm": planar, "periodV_mm": planar_v}
    return {"periodU_mm": planar, "periodV_mm": planar_v}


def _sim_tri(a, b, c, target, memo, depth):
    if a < b:
        a, b = b, a
    if b < c:
        b, c = c, b
    if a < b:
        a, b = b, a

    key = (
        round((a / target) * 256) * 0x40000000
        + round((b / target) * 256) * 0x10000
        + round((c / target) * 256)
    )
    if key in memo:
        return memo[key]
    if depth > 12:
        memo[key] = 1
        return 1

    sa, sb, sc = a > target, b > target, c > target
    n = int(sa) + int(sb) + int(sc)
    if n == 0:
        memo[key] = 1
        return 1
    if n == 3:
        total = 4 * _sim_tri(a / 2, b / 2, c / 2, target, memo, depth + 1)
    elif n == 1:
        median = 0.5 * math.sqrt(max(0, 2 * b * b + 2 * c * c - a * a))
        total = _sim_tri(a / 2, b, median, target, memo, depth + 1) + _sim_tri(a / 2, c, median, target, memo, depth + 1)
    else:
        median = 0.5 * math.sqrt(max(0, 2 * b * b + 2 * c * c - a * a))
        total = (
            _sim_tri(c, a / 2, median, target, memo, depth + 1)
            + _sim_tri(median, c / 2, b / 2, target, memo, depth + 1)
            + _sim_tri(b / 2, c / 2, a / 2, target, memo, depth + 1)
        )

    memo[key] = total
    return total


def compute_recommended_max_tri(*, pixelsPerEdge, pixMm, surfaceArea, amplitude):
    if not (pixelsPerEdge > 0) or not (pixMm > 0) or not (surfaceArea > 0):
        return DECIM_MIN_TRI
    amp_scale = math.sqrt(DECIM_REF_AMP / max(abs(amplitude or 0), DECIM_MIN_AMP))
    target_edge = DECIM_COARSEN * pixelsPerEdge * pixMm * amp_scale
    raw = TRIS_PER_AREA_GEOM * surfaceArea / (target_edge * target_edge)
    stepped = round(raw / 10_000) * 10_000
    return max(DECIM_MIN_TRI, min(DECIM_MAX_TRI, stepped))


def compute_tri_edges(geometry):
    pos = geometry.attributes.position.array
    tri_count = int(pos.length / 9)
    out = [0.0] * (tri_count * 3)
    for t in range(tri_count):
        o = t * 9
        ax, ay, az = pos[o], pos[o + 1], pos[o + 2]
        bx, by, bz = pos[o + 3], pos[o + 4], pos[o + 5]
        cx, cy, cz = pos[o + 6], pos[o + 7], pos[o + 8]
        out[t * 3] = math.dist((ax, ay, az), (bx, by, bz))
        out[t * 3 + 1] = math.dist((cx, cy, cz), (bx, by, bz))
        out[t * 3 + 2] = math.dist((ax, ay, az), (cx, cy, cz))
    return out


def simulate_from_edges(tri_edges, edge):
    memo = {}
    tri_count = len(tri_edges) // 3
    total = 0
    for i in range(tri_count):
        o = i * 3
        a, b, c = tri_edges[o], tri_edges[o + 1], tri_edges[o + 2]
        if a <= edge and b <= edge and c <= edge:
            total += 1
        else:
            total += _sim_tri(a, b, c, edge, memo, 0)
    return total


def estimate_subdivision_tri_count(geometry, edge):
    if not geometry or not geometry.attributes or not geometry.attributes.position:
        return 0
    return simulate_from_edges(compute_tri_edges(geometry), edge)


def compute_smart_resolution(*, geometry, bounds, settings, texture):
    image_data = _attr(texture, "imageData")
    if not geometry or not bounds or not texture or not image_data:
        return None

    analysis = analyze_texture(image_data)
    period = compute_world_period(settings, bounds)
    period_u = period["periodU_mm"]
    period_v = period["periodV_mm"]
    period_mm = min(period_u, period_v)
    tex_w = image_data.width or _attr(texture, "width", 512) or 512
    tex_h = image_data.height or _attr(texture, "height", 512) or 512
    pix_mm = min(period_u / tex_w, period_v / tex_h)
    detail_edge = pix_mm * analysis["pixelsPerEdge"]

    surface_area = compute_surface_area(geometry)
    tri_budget = HARD_CAP_TRIANGLES * HARD_CAP_HEADROOM
    tri_edges = compute_tri_edges(geometry)

    budget_edge = math.sqrt((TRIS_PER_AREA_GEOM * surface_area) / max(tri_budget, 1))
    for _ in range(3):
        sim_count = simulate_from_edges(tri_edges, budget_edge)
        if sim_count <= tri_budget:
            break
        correction = math.sqrt(sim_count / tri_budget)
        if correction < 1.005:
            break
        budget_edge *= correction

    edge = max(detail_edge, budget_edge)
    budget_clamped = budget_edge > detail_edge
    size = bounds["size"] if isinstance(bounds, dict) else bounds.size
    diag = math.sqrt(size.x**2 + size.y**2 + size.z**2)
    lo = 0.05
    hi = min(5.0, diag / 50)
    pre_clamp = edge
    edge = min(max(edge, lo), max(hi, lo))
    edge_clamped = edge != pre_clamp
    edge = max(lo, math.ceil(edge * 100) / 100)
    est_triangles = simulate_from_edges(tri_edges, edge)
    recommended_max_tri = compute_recommended_max_tri(
        pixelsPerEdge=analysis["pixelsPerEdge"],
        pixMm=pix_mm,
        surfaceArea=surface_area,
        amplitude=_attr(settings, "amplitude"),
    )

    return {
        "edge": edge,
        "diagnostics": {
            "pixelsPerEdge": analysis["pixelsPerEdge"],
            "meanGrad": analysis["meanGrad"],
            "sharpFrac": analysis["sharpFrac"],
            "pixMm": pix_mm,
            "period_mm": period_mm,
            "surfaceArea": surface_area,
            "detailEdge": detail_edge,
            "budgetEdge": budget_edge,
            "estTriangles": est_triangles,
            "triBudget": tri_budget,
            "budgetClamped": budget_clamped,
            "edgeClamped": edge_clamped,
            "recommendedMaxTri": recommended_max_tri,
        },
    }
