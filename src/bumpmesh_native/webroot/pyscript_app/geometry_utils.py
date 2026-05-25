"""Geometry helpers shared by PyScript mesh modules."""

from __future__ import annotations

import math

from js import Float32Array
from pyscript.js_modules import three


MAX_FILE_SIZE = 500 * 1024 * 1024


def _arr_len(arr):
    return int(arr.length) if hasattr(arr, "length") else len(arr)


def validate_and_clean_geometry(geometry):
    pos = geometry.attributes.position
    src = pos.array
    tri_count = _arr_len(src) // 9
    write_idx = 0
    nan_count = 0
    degenerate_count = 0

    for t in range(tri_count):
        b = t * 9
        ax, ay, az = src[b], src[b + 1], src[b + 2]
        bx, by, bz = src[b + 3], src[b + 4], src[b + 5]
        cx, cy, cz = src[b + 6], src[b + 7], src[b + 8]

        if not all(math.isfinite(v) for v in (ax, ay, az, bx, by, bz, cx, cy, cz)):
            nan_count += 1
            continue

        ux, uy, uz = bx - ax, by - ay, bz - az
        vx, vy, vz = cx - ax, cy - ay, cz - az
        area2 = (uy * vz - uz * vy) ** 2 + (uz * vx - ux * vz) ** 2 + (ux * vy - uy * vx) ** 2
        if area2 < 1e-24:
            degenerate_count += 1
            continue

        if write_idx != b:
            for off, value in enumerate((ax, ay, az, bx, by, bz, cx, cy, cz)):
                src[write_idx + off] = value
        write_idx += 9

    removed = nan_count + degenerate_count
    if removed > 0:
        cleaned = src.slice(0, write_idx)
        geometry.setAttribute("position", three.BufferAttribute.new(cleaned, 3))
        geometry.deleteAttribute("normal")

    if write_idx == 0:
        raise ValueError(
            f"All {tri_count} triangles in the mesh are invalid "
            f"({nan_count} NaN, {degenerate_count} degenerate). Cannot load file."
        )

    return {"nanCount": nan_count, "degenerateCount": degenerate_count}


def setup_geometry(geometry):
    result = validate_and_clean_geometry(geometry)
    geometry.computeBoundingBox()
    box = geometry.boundingBox
    centre = three.Vector3.new()
    box.getCenter(centre)
    geometry.translate(-centre.x, -centre.y, -centre.z)
    geometry.computeBoundingBox()
    if not bool(geometry.attributes.normal):
        geometry.computeVertexNormals()
    return result


def compute_bounds(geometry):
    geometry.computeBoundingBox()
    box = geometry.boundingBox
    min_v = box.min.clone()
    max_v = box.max.clone()
    size = three.Vector3.new()
    box.getSize(size)
    center = three.Vector3.new()
    box.getCenter(center)
    return {"min": min_v, "max": max_v, "center": center, "size": size}


def get_triangle_count(geometry):
    pos = geometry.attributes.position
    return geometry.index.count / 3 if bool(geometry.index) else pos.count / 3


def compute_surface_area(geometry):
    pos_attr = geometry.attributes.position
    if not pos_attr:
        return 0
    pos = pos_attr.array
    idx = geometry.index.array if bool(geometry.index) else None
    area = 0

    tri_count = (_arr_len(idx) // 3) if idx is not None else (_arr_len(pos) // 9)
    for t in range(tri_count):
        if idx is not None:
            ia, ib, ic = idx[t * 3], idx[t * 3 + 1], idx[t * 3 + 2]
            oa, ob, oc = ia * 3, ib * 3, ic * 3
            ax, ay, az = pos[oa], pos[oa + 1], pos[oa + 2]
            bx, by, bz = pos[ob], pos[ob + 1], pos[ob + 2]
            cx, cy, cz = pos[oc], pos[oc + 1], pos[oc + 2]
        else:
            o = t * 9
            ax, ay, az = pos[o], pos[o + 1], pos[o + 2]
            bx, by, bz = pos[o + 3], pos[o + 4], pos[o + 5]
            cx, cy, cz = pos[o + 6], pos[o + 7], pos[o + 8]

        e1x, e1y, e1z = bx - ax, by - ay, bz - az
        e2x, e2y, e2z = cx - ax, cy - ay, cz - az
        cross_x = e1y * e2z - e1z * e2y
        cross_y = e1z * e2x - e1x * e2z
        cross_z = e1x * e2y - e1y * e2x
        area += 0.5 * math.sqrt(cross_x * cross_x + cross_y * cross_y + cross_z * cross_z)
    return area


def merge_group_geometries(group):
    geometries = []

    def visit(child):
        if bool(getattr(child, "isMesh", False)) and bool(child.geometry):
            geo = child.geometry.clone()
            child.updateWorldMatrix(True, False)
            geo.applyMatrix4(child.matrixWorld)
            if bool(geo.index):
                geometries.append(geo.toNonIndexed())
                geo.dispose()
            else:
                geometries.append(geo)

    group.traverse(visit)
    if not geometries:
        raise ValueError("No mesh data found in file")
    if len(geometries) == 1:
        return geometries[0]

    total_verts = sum(g.attributes.position.count for g in geometries)
    merged_pos = Float32Array.new(total_verts * 3)
    has_normals = all(bool(g.attributes.normal) for g in geometries)
    merged_nrm = Float32Array.new(total_verts * 3) if has_normals else None
    offset = 0
    for geo in geometries:
        merged_pos.set(geo.attributes.position.array, offset * 3)
        if has_normals:
            merged_nrm.set(geo.attributes.normal.array, offset * 3)
        offset += geo.attributes.position.count
        geo.dispose()

    merged = three.BufferGeometry.new()
    merged.setAttribute("position", three.BufferAttribute.new(merged_pos, 3))
    if has_normals:
        merged.setAttribute("normal", three.BufferAttribute.new(merged_nrm, 3))
    return merged
