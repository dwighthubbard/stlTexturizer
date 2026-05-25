"""Per-face exclusion masking."""

from __future__ import annotations

import math
from collections import deque

from js import Float32Array, Uint32Array
from pyscript.js_modules import three


QUANT = 1e4


def _new_float32(length):
    return Float32Array.new(length)


def _new_uint32(length):
    return Uint32Array.new(length)


def build_adjacency(geometry):
    pos_attr = geometry.attributes.position
    tri_count = int(pos_attr.count / 3)
    face_normals = _new_float32(tri_count * 3)
    centroids = _new_float32(tri_count * 3)
    bound_radii = _new_float32(tri_count)

    for t in range(tri_count):
        i = t * 3
        ax, ay, az = pos_attr.getX(i), pos_attr.getY(i), pos_attr.getZ(i)
        bx, by, bz = pos_attr.getX(i + 1), pos_attr.getY(i + 1), pos_attr.getZ(i + 1)
        cx, cy, cz = pos_attr.getX(i + 2), pos_attr.getY(i + 2), pos_attr.getZ(i + 2)
        e1x, e1y, e1z = bx - ax, by - ay, bz - az
        e2x, e2y, e2z = cx - ax, cy - ay, cz - az
        nx = e1y * e2z - e1z * e2y
        ny = e1z * e2x - e1x * e2z
        nz = e1x * e2y - e1y * e2x
        length = math.sqrt(nx * nx + ny * ny + nz * nz) or 1
        nx, ny, nz = nx / length, ny / length, nz / length
        face_normals[i] = nx
        face_normals[i + 1] = ny
        face_normals[i + 2] = nz

        mx = (ax + bx + cx) / 3
        my = (ay + by + cy) / 3
        mz = (az + bz + cz) / 3
        centroids[i] = mx
        centroids[i + 1] = my
        centroids[i + 2] = mz
        da = (ax - mx) ** 2 + (ay - my) ** 2 + (az - mz) ** 2
        db = (bx - mx) ** 2 + (by - my) ** 2 + (bz - mz) ** 2
        dc = (cx - mx) ** 2 + (cy - my) ** 2 + (cz - mz) ** 2
        bound_radii[t] = math.sqrt(max(da, db, dc))

    pos_to_id = {}
    next_id = 0
    vert_id = _new_uint32(tri_count * 3)
    for i in range(tri_count * 3):
        key = f"{round(pos_attr.getX(i) * QUANT)}_{round(pos_attr.getY(i) * QUANT)}_{round(pos_attr.getZ(i) * QUANT)}"
        found = pos_to_id.get(key)
        if found is None:
            found = next_id
            pos_to_id[key] = found
            next_id += 1
        vert_id[i] = found

    def edge_key(a, b):
        return a * next_id + b if a < b else b * next_id + a

    edge_map = {}
    edge_pairs = (0, 1, 0, 2, 1, 2)
    for t in range(tri_count):
        base = t * 3
        for e in range(0, 6, 2):
            key = edge_key(vert_id[base + edge_pairs[e]], vert_id[base + edge_pairs[e + 1]])
            edge_map.setdefault(key, []).append(t)

    adjacency = [[] for _ in range(tri_count)]
    open_edge_count = 0
    non_manifold_edge_count = 0
    for tris in edge_map.values():
        if len(tris) == 1:
            open_edge_count += 1
            continue
        if len(tris) > 2:
            non_manifold_edge_count += 1
        a, b = tris[0], tris[1]
        n_ax, n_ay, n_az = face_normals[a * 3], face_normals[a * 3 + 1], face_normals[a * 3 + 2]
        n_bx, n_by, n_bz = face_normals[b * 3], face_normals[b * 3 + 1], face_normals[b * 3 + 2]
        dot = max(-1, min(1, n_ax * n_bx + n_ay * n_by + n_az * n_bz))
        angle_deg = math.acos(dot) * 180 / math.pi
        adjacency[a].append({"neighbor": b, "angle": angle_deg})
        adjacency[b].append({"neighbor": a, "angle": angle_deg})

    return {
        "adjacency": adjacency,
        "centroids": centroids,
        "boundRadii": bound_radii,
        "faceNormals": face_normals,
        "openEdgeCount": open_edge_count,
        "nonManifoldEdgeCount": non_manifold_edge_count,
    }


def bucket_fill(seed_tri_idx, adjacency, threshold_deg):
    visited = {seed_tri_idx}
    queue = deque([seed_tri_idx])
    while queue:
        cur = queue.popleft()
        if cur >= len(adjacency) or not adjacency[cur]:
            continue
        for edge in adjacency[cur]:
            neighbor = edge["neighbor"]
            if neighbor not in visited and edge["angle"] <= threshold_deg:
                visited.add(neighbor)
                queue.append(neighbor)
    return visited


def _contains(face_set, index):
    if hasattr(face_set, "length"):
        return bool(face_set[index])
    return index in face_set


def build_exclusion_overlay_geo(geometry, face_set, invert=False):
    src_pos = geometry.attributes.position.array
    src_nrm = geometry.attributes.normal.array if bool(geometry.attributes.normal) else None
    total = int(src_pos.length / 9)
    if hasattr(face_set, "length"):
        set_size = sum(1 for i in range(face_set.length) if face_set[i])
    else:
        set_size = len(face_set)
    count = total - set_size if invert else set_size
    out_pos = _new_float32(count * 9)
    out_nrm = _new_float32(count * 9) if src_nrm is not None else None

    dst = 0
    for t in range(total):
        in_set = _contains(face_set, t)
        if (invert and in_set) or (not invert and not in_set):
            continue
        src = t * 9
        out_pos.set(src_pos.subarray(src, src + 9), dst)
        if out_nrm is not None:
            out_nrm.set(src_nrm.subarray(src, src + 9), dst)
        dst += 9

    geo = three.BufferGeometry.new()
    geo.setAttribute("position", three.BufferAttribute.new(out_pos, 3))
    if out_nrm is not None:
        geo.setAttribute("normal", three.BufferAttribute.new(out_nrm, 3))
    return geo


def build_face_weights(geometry, excluded_faces, invert=False):
    count = geometry.attributes.position.count
    weights = _new_float32(count)
    if invert:
        weights.fill(1.0)
        for t in excluded_faces:
            weights[t * 3] = 0.0
            weights[t * 3 + 1] = 0.0
            weights[t * 3 + 2] = 0.0
    else:
        for t in excluded_faces:
            weights[t * 3] = 1.0
            weights[t * 3 + 1] = 1.0
            weights[t * 3 + 2] = 1.0
    return weights
