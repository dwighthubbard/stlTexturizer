"""CPU-side UV mapping for BumpMesh."""

from __future__ import annotations

import math


MODE_PLANAR_XY = 0
MODE_PLANAR_XZ = 1
MODE_PLANAR_YZ = 2
MODE_CYLINDRICAL = 3
MODE_SPHERICAL = 4
MODE_TRIPLANAR = 5
MODE_CUBIC = 6

TWO_PI = math.pi * 2
CUBIC_AXIS_EPSILON = 1e-4


def _attr(obj, name, default=None):
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _settings(settings, name, default=None):
    return _attr(settings, name, default)


def fract(x):
    return x - math.floor(x)


def get_dominant_cubic_axis(normal):
    ax = abs(normal.x)
    ay = abs(normal.y)
    az = abs(normal.z)
    if ax >= ay - CUBIC_AXIS_EPSILON and ax >= az - CUBIC_AXIS_EPSILON:
        return "x"
    if ay >= az - CUBIC_AXIS_EPSILON:
        return "y"
    return "z"


def get_cubic_blend_weights(normal, blend, seam_band_width=0.35):
    axis = get_dominant_cubic_axis(normal)
    ax = abs(normal.x)
    ay = abs(normal.y)
    az = abs(normal.z)
    primary = ax if axis == "x" else ay if axis == "y" else az
    secondary = max(ay, az) if axis == "x" else max(ax, az) if axis == "y" else max(ax, ay)

    if blend <= 0.001:
        return {
            "x": 1 if axis == "x" else 0,
            "y": 1 if axis == "y" else 0,
            "z": 1 if axis == "z" else 0,
        }

    one_hot = {
        "x": 1 if axis == "x" else 0,
        "y": 1 if axis == "y" else 0,
        "z": 1 if axis == "z" else 0,
    }

    seam_width = max(seam_band_width, CUBIC_AXIS_EPSILON * 2)
    seam_mix_raw = 1 - min(1, max(0, (primary - secondary) / seam_width))
    seam_mix = blend * seam_mix_raw * seam_mix_raw * (3 - 2 * seam_mix_raw)
    if seam_mix <= 0.001:
        return one_hot

    power = 1 + (1 - seam_mix) * 11
    sx = ax**power
    sy = ay**power
    sz = az**power
    smooth_sum = sx + sy + sz + 1e-6
    smooth = {"x": sx / smooth_sum, "y": sy / smooth_sum, "z": sz / smooth_sum}

    mx = one_hot["x"] * (1 - seam_mix) + smooth["x"] * seam_mix
    my = one_hot["y"] * (1 - seam_mix) + smooth["y"] * seam_mix
    mz = one_hot["z"] * (1 - seam_mix) + smooth["z"] * seam_mix
    total = mx + my + mz
    return {"x": mx / total, "y": my / total, "z": mz / total}


def apply_transform(u, v, scale_u, scale_v, offset_u, offset_v, cos_r, sin_r):
    uu = u / scale_u + offset_u
    vv = v / scale_v + offset_v
    if cos_r != 1 or sin_r != 0:
        uu -= 0.5
        vv -= 0.5
        ru = cos_r * uu - sin_r * vv
        rv = sin_r * uu + cos_r * vv
        uu = ru + 0.5
        vv = rv + 0.5
    return {"triplanar": False, "u": fract(uu), "v": fract(vv)}


def compute_uv(pos, normal, mode, settings, bounds):
    min_v = bounds["min"] if isinstance(bounds, dict) else bounds.min
    size = bounds["size"] if isinstance(bounds, dict) else bounds.size
    center = bounds["center"] if isinstance(bounds, dict) else bounds.center

    aspect_u = _settings(settings, "textureAspectU", 1)
    aspect_v = _settings(settings, "textureAspectV", 1)
    scale_u = _settings(settings, "scaleU") / aspect_u
    scale_v = _settings(settings, "scaleV") / aspect_v
    offset_u = _settings(settings, "offsetU")
    offset_v = _settings(settings, "offsetV")
    rot_rad = _settings(settings, "rotation", 0) * math.pi / 180
    cos_r = math.cos(rot_rad)
    sin_r = math.sin(rot_rad)
    max_dim = max(size.x, size.y, size.z)
    md = max(max_dim, 1e-6)

    u = 0
    v = 0

    if mode == MODE_PLANAR_XY:
        u = (pos.x - min_v.x) / md
        v = (pos.y - min_v.y) / md
    elif mode == MODE_PLANAR_XZ:
        u = (pos.x - min_v.x) / md
        v = (pos.z - min_v.z) / md
    elif mode == MODE_PLANAR_YZ:
        u = (pos.y - min_v.y) / md
        v = (pos.z - min_v.z) / md
    elif mode == MODE_CYLINDRICAL:
        cx = _settings(settings, "cylinderCenterX", None)
        cy = _settings(settings, "cylinderCenterY", None)
        cx = center.x if cx is None else cx
        cy = center.y if cy is None else cy
        radius = _settings(settings, "cylinderRadius", None)
        r = max(radius if radius is not None else max(size.x, size.y) * 0.5, 1e-6)
        circumference = TWO_PI * r
        rx = pos.x - cx
        ry = pos.y - cy
        blend = _settings(settings, "mappingBlend", 0.0)
        theta = math.atan2(ry, rx)
        u_raw = theta / TWO_PI + 0.5
        v_side = (pos.z - min_v.z) / circumference
        seam_band = _settings(settings, "seamBandWidth", 0.5) * 0.1
        seam_dist = min(u_raw, 1.0 - u_raw)

        if seam_band > 0.001 and seam_dist < seam_band:
            d = u_raw if u_raw < 0.5 else u_raw - 1.0
            t_raw = (d + seam_band) / (2.0 * seam_band)
            t = t_raw * t_raw * (3 - 2 * t_raw)
            t_left = apply_transform(1.0 + d, v_side, scale_u, scale_v, offset_u, offset_v, cos_r, sin_r)
            t_right = apply_transform(d, v_side, scale_u, scale_v, offset_u, offset_v, cos_r, sin_r)
            side_samples = [
                {"u": t_right["u"], "v": t_right["v"], "w": t},
                {"u": t_left["u"], "v": t_left["v"], "w": 1 - t},
            ]
        else:
            t_side = apply_transform(u_raw, v_side, scale_u, scale_v, offset_u, offset_v, cos_r, sin_r)
            side_samples = [{"u": t_side["u"], "v": t_side["v"], "w": 1}]

        if blend <= 0.001:
            return side_samples[0] if len(side_samples) == 1 else {"triplanar": True, "samples": side_samples}

        cap_threshold = math.cos(_settings(settings, "capAngle", 20) * math.pi / 180)
        blend_half = _settings(settings, "seamBandWidth", 0.5) * 0.5
        abs_nz = abs(normal.z)
        cap_w = max(0, min(1, (abs_nz - (cap_threshold - blend_half)) / (2 * blend_half + 1e-6)))
        if cap_w <= 0:
            return side_samples[0] if len(side_samples) == 1 else {"triplanar": True, "samples": side_samples}

        t_cap = apply_transform(rx / circumference + 0.5, ry / circumference + 0.5, scale_u, scale_v, offset_u, offset_v, cos_r, sin_r)
        if cap_w >= 1:
            return t_cap
        samples = [{"u": s["u"], "v": s["v"], "w": s["w"] * (1 - cap_w)} for s in side_samples]
        samples.append({"u": t_cap["u"], "v": t_cap["v"], "w": cap_w})
        return {"triplanar": True, "samples": samples}
    elif mode == MODE_SPHERICAL:
        rx = pos.x - center.x
        ry = pos.y - center.y
        rz = pos.z - center.z
        r = math.sqrt(rx * rx + ry * ry + rz * rz)
        phi = math.acos(max(-1, min(1, rz / max(r, 1e-6))))
        theta = math.atan2(ry, rx)
        u_raw = theta / TWO_PI + 0.5
        v_raw = phi / math.pi
        seam_band = _settings(settings, "seamBandWidth", 0.5) * 0.1
        seam_dist = min(u_raw, 1.0 - u_raw)
        if seam_band > 0.001 and seam_dist < seam_band:
            d = u_raw if u_raw < 0.5 else u_raw - 1.0
            t_raw = (d + seam_band) / (2.0 * seam_band)
            t = t_raw * t_raw * (3 - 2 * t_raw)
            t_left = apply_transform(1.0 + d, v_raw, scale_u, scale_v, offset_u, offset_v, cos_r, sin_r)
            t_right = apply_transform(d, v_raw, scale_u, scale_v, offset_u, offset_v, cos_r, sin_r)
            return {"triplanar": True, "samples": [
                {"u": t_right["u"], "v": t_right["v"], "w": t},
                {"u": t_left["u"], "v": t_left["v"], "w": 1 - t},
            ]}
        u = u_raw
        v = v_raw
    elif mode == MODE_CUBIC:
        weights = get_cubic_blend_weights(normal, _settings(settings, "mappingBlend", 0.0), _settings(settings, "seamBandWidth", 0.35))
        yz_u = (pos.y - min_v.y) / md
        if normal.x < 0:
            yz_u = -yz_u
        xz_u = (pos.x - min_v.x) / md
        if normal.y > 0:
            xz_u = -xz_u
        xy_u = (pos.x - min_v.x) / md
        if normal.z < 0:
            xy_u = -xy_u
        t_yz = apply_transform(yz_u, (pos.z - min_v.z) / md, scale_u, scale_v, offset_u, offset_v, cos_r, sin_r)
        t_xz = apply_transform(xz_u, (pos.z - min_v.z) / md, scale_u, scale_v, offset_u, offset_v, cos_r, sin_r)
        t_xy = apply_transform(xy_u, (pos.y - min_v.y) / md, scale_u, scale_v, offset_u, offset_v, cos_r, sin_r)
        if weights["x"] > 0.999:
            return t_yz
        if weights["y"] > 0.999:
            return t_xz
        if weights["z"] > 0.999:
            return t_xy
        return {"triplanar": True, "samples": [
            {"u": t_xy["u"], "v": t_xy["v"], "w": weights["z"]},
            {"u": t_xz["u"], "v": t_xz["v"], "w": weights["y"]},
            {"u": t_yz["u"], "v": t_yz["v"], "w": weights["x"]},
        ]}
    else:
        ax = abs(normal.x)
        ay = abs(normal.y)
        az = abs(normal.z)
        bx = (ax * ax) ** 2
        by = (ay * ay) ** 2
        bz = (az * az) ** 2
        total = bx + by + bz + 1e-6
        wx = bx / total
        wy = by / total
        wz = bz / total
        yz_u = (pos.y - min_v.y) / md
        if normal.x < 0:
            yz_u = -yz_u
        xz_u = (pos.x - min_v.x) / md
        if normal.y > 0:
            xz_u = -xz_u
        xy_u = (pos.x - min_v.x) / md
        if normal.z < 0:
            xy_u = -xy_u
        t_xy = apply_transform(xy_u, (pos.y - min_v.y) / md, scale_u, scale_v, offset_u, offset_v, cos_r, sin_r)
        t_xz = apply_transform(xz_u, (pos.z - min_v.z) / md, scale_u, scale_v, offset_u, offset_v, cos_r, sin_r)
        t_yz = apply_transform(yz_u, (pos.z - min_v.z) / md, scale_u, scale_v, offset_u, offset_v, cos_r, sin_r)
        return {"triplanar": True, "samples": [
            {"u": t_xy["u"], "v": t_xy["v"], "w": wz},
            {"u": t_xz["u"], "v": t_xz["v"], "w": wy},
            {"u": t_yz["u"], "v": t_yz["v"], "w": wx},
        ]}

    return apply_transform(u, v, scale_u, scale_v, offset_u, offset_v, cos_r, sin_r)
