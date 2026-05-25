"""Vertex displacement baking for PyScript."""

from __future__ import annotations

import math

from js import Float32Array
from pyscript.js_modules import three

from pyscript_app.mapping import compute_uv


def sample_bilinear(data, width, height, u, v):
    u = ((u % 1) + 1) % 1
    v = 1 - (((v % 1) + 1) % 1)
    fx = u * (width - 1)
    fy = v * (height - 1)
    x0 = math.floor(fx)
    y0 = math.floor(fy)
    x1 = min(x0 + 1, width - 1)
    y1 = min(y0 + 1, height - 1)
    tx = fx - x0
    ty = fy - y0
    v00 = data[(y0 * width + x0) * 4] / 255
    v10 = data[(y0 * width + x1) * 4] / 255
    v01 = data[(y1 * width + x0) * 4] / 255
    v11 = data[(y1 * width + x1) * 4] / 255
    return (
        v00 * (1 - tx) * (1 - ty)
        + v10 * tx * (1 - ty)
        + v01 * (1 - tx) * ty
        + v11 * tx * ty
    )


def _attr(obj, name, default=None):
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _settings_with_aspect(settings, aspect_u, aspect_v):
    if isinstance(settings, dict):
        merged = dict(settings)
        merged["textureAspectU"] = aspect_u
        merged["textureAspectV"] = aspect_v
        return merged
    merged = {}
    for key in (
        "mappingMode", "scaleU", "scaleV", "amplitude", "offsetU", "offsetV",
        "rotation", "mappingBlend", "seamBandWidth", "capAngle",
        "cylinderCenterX", "cylinderCenterY", "cylinderRadius",
        "symmetricDisplacement", "noDownwardZ", "bottomAngleLimit", "topAngleLimit",
    ):
        merged[key] = getattr(settings, key, None)
    merged["textureAspectU"] = aspect_u
    merged["textureAspectV"] = aspect_v
    return merged


def apply_displacement(geometry, image_data, img_width, img_height, settings, bounds, on_progress=None):
    """Return a new non-indexed BufferGeometry with texture displacement baked in."""
    pos_attr = geometry.attributes.position
    nrm_attr = geometry.attributes.normal
    count = int(pos_attr.count)
    new_pos = Float32Array.new(count * 3)
    new_nrm = Float32Array.new(count * 3)
    tmp_pos = three.Vector3.new()
    tmp_nrm = three.Vector3.new()

    tmax = max(img_width, img_height, 1)
    settings_with_aspect = _settings_with_aspect(
        settings,
        tmax / max(img_width, 1),
        tmax / max(img_height, 1),
    )

    amplitude = _attr(settings, "amplitude", 0)
    symmetric = bool(_attr(settings, "symmetricDisplacement", False))
    no_downward_z = bool(_attr(settings, "noDownwardZ", False))
    mapping_mode = _attr(settings, "mappingMode")
    min_z = bounds["min"].z if isinstance(bounds, dict) else bounds.min.z
    report_every = 5000

    for i in range(count):
        tmp_pos.fromBufferAttribute(pos_attr, i)
        tmp_nrm.fromBufferAttribute(nrm_attr, i)
        uv = compute_uv(tmp_pos, tmp_nrm, mapping_mode, settings_with_aspect, bounds)
        if uv.get("triplanar"):
            grey = 0
            for sample in uv["samples"]:
                grey += sample_bilinear(image_data.data, img_width, img_height, sample["u"], sample["v"]) * sample["w"]
        else:
            grey = sample_bilinear(image_data.data, img_width, img_height, uv["u"], uv["v"])

        centered = grey - 0.5 if symmetric else grey
        disp = centered * amplitude
        x = tmp_pos.x + tmp_nrm.x * disp
        y = tmp_pos.y + tmp_nrm.y * disp
        z = tmp_pos.z + tmp_nrm.z * disp
        if no_downward_z and z < tmp_pos.z:
            z = tmp_pos.z
        if no_downward_z and tmp_pos.z <= min_z + 1e-5:
            z = tmp_pos.z

        base = i * 3
        new_pos[base] = x
        new_pos[base + 1] = y
        new_pos[base + 2] = z
        new_nrm[base] = tmp_nrm.x
        new_nrm[base + 1] = tmp_nrm.y
        new_nrm[base + 2] = tmp_nrm.z
        if on_progress and i % report_every == 0:
            on_progress(i / count)

    out = three.BufferGeometry.new()
    out.setAttribute("position", three.BufferAttribute.new(new_pos, 3))
    out.setAttribute("normal", three.BufferAttribute.new(new_nrm, 3))
    out.computeVertexNormals()
    return out
