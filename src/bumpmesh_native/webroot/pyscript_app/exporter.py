"""Binary STL and 3MF exporters for PyScript."""

from __future__ import annotations

import math

from js import ArrayBuffer, Blob, DataView, TextEncoder, Uint8Array, URL, document, setTimeout
from pyscript.js_modules import fflate


def _trigger_download(buffer, filename, mime="application/octet-stream"):
    blob = Blob.new([buffer], {"type": mime})
    url = URL.createObjectURL(blob)
    anchor = document.createElement("a")
    anchor.href = url
    anchor.download = filename
    anchor.style.display = "none"
    document.body.appendChild(anchor)
    anchor.click()
    document.body.removeChild(anchor)
    setTimeout(lambda: URL.revokeObjectURL(url), 10000)


def export_stl(geometry, filename="textured.stl"):
    buffer = build_stl_buffer(geometry)
    _trigger_download(buffer, filename)


def build_stl_buffer(geometry):
    pos_arr = geometry.attributes.position.array
    nor_arr = geometry.attributes.normal.array if bool(geometry.attributes.normal) else None
    tri_count = int(pos_arr.length / 9)
    buffer = ArrayBuffer.new(84 + 50 * tri_count)
    view = DataView.new(buffer)
    view.setUint32(80, tri_count, True)

    for i in range(tri_count):
        dst = 84 + i * 50
        src = i * 9
        if nor_arr is not None:
            view.setFloat32(dst, nor_arr[src], True)
            view.setFloat32(dst + 4, nor_arr[src + 1], True)
            view.setFloat32(dst + 8, nor_arr[src + 2], True)
        else:
            ux = pos_arr[src + 3] - pos_arr[src]
            uy = pos_arr[src + 4] - pos_arr[src + 1]
            uz = pos_arr[src + 5] - pos_arr[src + 2]
            vx = pos_arr[src + 6] - pos_arr[src]
            vy = pos_arr[src + 7] - pos_arr[src + 1]
            vz = pos_arr[src + 8] - pos_arr[src + 2]
            nx = uy * vz - uz * vy
            ny = uz * vx - ux * vz
            nz = ux * vy - uy * vx
            length = math.sqrt(nx * nx + ny * ny + nz * nz) or 1
            view.setFloat32(dst, nx / length, True)
            view.setFloat32(dst + 4, ny / length, True)
            view.setFloat32(dst + 8, nz / length, True)
        for j in range(9):
            view.setFloat32(dst + 12 + j * 4, pos_arr[src + j], True)
    return buffer


def export_3mf(geometry, filename="textured.3mf"):
    zipped = build_3mf_zip(geometry)
    _trigger_download(zipped, filename, "application/vnd.ms-package.3dmanufacturing-3dmodel+xml")


def _fmt(n):
    text = f"{n:.4f}"
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text


def build_3mf_zip(geometry):
    pos_arr = geometry.attributes.position.array
    tri_count = int(pos_arr.length / 9)
    index_map = {}
    unique_xyz = []
    tri_idx = [0] * (tri_count * 3)

    for i in range(tri_count):
        for j in range(3):
            b = i * 9 + j * 3
            x, y, z = pos_arr[b], pos_arr[b + 1], pos_arr[b + 2]
            key = f"{x:.4f},{y:.4f},{z:.4f}"
            idx = index_map.get(key)
            if idx is None:
                idx = len(unique_xyz) // 3
                unique_xyz.extend([x, y, z])
                index_map[key] = idx
            tri_idx[i * 3 + j] = idx

    parts = [
        '<?xml version="1.0" encoding="UTF-8"?>\n',
        '<model unit="millimeter" xml:lang="en-US" xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02">\n',
        "<resources>\n<object id=\"1\" type=\"model\">\n<mesh>\n<vertices>\n",
    ]
    for i in range(len(unique_xyz) // 3):
        b = i * 3
        parts.append(f'<vertex x="{_fmt(unique_xyz[b])}" y="{_fmt(unique_xyz[b + 1])}" z="{_fmt(unique_xyz[b + 2])}"/>\n')
    parts.append("</vertices>\n<triangles>\n")
    for i in range(tri_count):
        b = i * 3
        parts.append(f'<triangle v1="{tri_idx[b]}" v2="{tri_idx[b + 1]}" v3="{tri_idx[b + 2]}"/>\n')
    parts.append("</triangles>\n</mesh>\n</object>\n</resources>\n<build>\n<item objectid=\"1\"/>\n</build>\n</model>\n")

    encoder = TextEncoder.new()
    model_bytes = encoder.encode("".join(parts))
    content_types_xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">\n'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>\n'
        '<Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/>\n'
        "</Types>\n"
    )
    rels_xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">\n'
        '<Relationship Id="rel-1" Target="/3D/3dmodel.model" '
        'Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/>\n'
        "</Relationships>\n"
    )
    return fflate.zipSync(
        {
            "[Content_Types].xml": fflate.strToU8(content_types_xml),
            "_rels/.rels": fflate.strToU8(rels_xml),
            "3D/3dmodel.model": model_bytes,
        },
        {"level": 6},
    )
