"""Model loaders for PyScript.

STL and OBJ parsing delegates to the external Three.js loader modules. The
normalization, validation, bounds, area, and dispatch logic are Python.
"""

from __future__ import annotations

from js import DOMParser, Float32Array, TextDecoder, Uint32Array
from pyscript.js_modules import fflate, obj_loader_addon, stl_loader_addon, three

from pyscript_app.geometry_utils import (
    MAX_FILE_SIZE,
    compute_bounds,
    compute_surface_area,
    get_triangle_count,
    merge_group_geometries,
    setup_geometry,
)


MAX_3MF_TRIANGLES = 10_000_000
MAX_3MF_DEPTH = 32

_stl_loader = stl_loader_addon.STLLoader.new()
_obj_loader = obj_loader_addon.OBJLoader.new()


def _too_large(file):
    return file.size > MAX_FILE_SIZE


def _large_error(file):
    mb = round(file.size / 1024 / 1024)
    max_mb = round(MAX_FILE_SIZE / 1024 / 1024)
    return ValueError(f"File too large ({mb} MB). Maximum supported: {max_mb} MB.")


async def load_stl_file(file):
    if _too_large(file):
        raise _large_error(file)
    geometry = _stl_loader.parse(await file.arrayBuffer())
    counts = setup_geometry(geometry)
    return {"geometry": geometry, "bounds": compute_bounds(geometry), **counts}


async def load_obj_file(file):
    if _too_large(file):
        raise _large_error(file)
    group = _obj_loader.parse(await file.text())
    geometry = merge_group_geometries(group)
    counts = setup_geometry(geometry)
    return {"geometry": geometry, "bounds": compute_bounds(geometry), **counts}


async def load_3mf_file(file):
    if _too_large(file):
        raise _large_error(file)
    data = Uint8Array.new(await file.arrayBuffer())
    geometry = parse_3mf(data)
    counts = setup_geometry(geometry)
    return {"geometry": geometry, "bounds": compute_bounds(geometry), **counts}


async def load_model_file(file):
    ext = file.name.split(".")[-1].lower()
    if ext == "obj":
        return await load_obj_file(file)
    if ext == "3mf":
        return await load_3mf_file(file)
    return await load_stl_file(file)


def parse_3mf(data):
    files = fflate.unzipSync(data)
    decoder = TextDecoder.new()
    parser = DOMParser.new()
    ns_core = "http://schemas.microsoft.com/3dmanufacturing/core/2015/02"
    ns_prod = "http://schemas.microsoft.com/3dmanufacturing/production/2015/06"
    unit_to_mm = {
        "micron": 0.001,
        "millimeter": 1,
        "centimeter": 10,
        "inch": 25.4,
        "foot": 304.8,
        "meter": 1000,
    }

    file_keys = list(files.keys())

    def read_xml(path):
        clean = path[1:] if path.startswith("/") else path
        bytes_ = files.get(clean) or files.get("/" + clean)
        if not bytes_:
            return None
        return parser.parseFromString(decoder.decode(bytes_), "application/xml")

    object_map = {}
    model_paths = [path for path in file_keys if path.endswith(".model")]

    for path in model_paths:
        doc = read_xml(path)
        if not doc:
            continue
        objects = doc.getElementsByTagNameNS(ns_core, "object")
        for i in range(objects.length):
            obj = objects[i]
            obj_id = obj.getAttribute("id")
            mesh_els = obj.getElementsByTagNameNS(ns_core, "mesh")
            if mesh_els.length == 0:
                continue
            mesh_el = mesh_els[0]
            vert_els = mesh_el.getElementsByTagNameNS(ns_core, "vertex")
            tri_els = mesh_el.getElementsByTagNameNS(ns_core, "triangle")
            vertices = Float32Array.new(vert_els.length * 3)
            for v in range(vert_els.length):
                el = vert_els[v]
                vertices[v * 3] = float(el.getAttribute("x"))
                vertices[v * 3 + 1] = float(el.getAttribute("y"))
                vertices[v * 3 + 2] = float(el.getAttribute("z"))
            triangles = Uint32Array.new(tri_els.length * 3)
            for t in range(tri_els.length):
                el = tri_els[t]
                triangles[t * 3] = int(el.getAttribute("v1"))
                triangles[t * 3 + 1] = int(el.getAttribute("v2"))
                triangles[t * 3 + 2] = int(el.getAttribute("v3"))

            vert_count = vert_els.length
            for i_tri in range(triangles.length):
                if triangles[i_tri] < 0 or triangles[i_tri] >= vert_count:
                    raise ValueError("Invalid triangle index in 3MF file")

            norm_path = path.lstrip("/").replace("\\", "/")
            object_map[f"{norm_path}#{obj_id}"] = {"vertices": vertices, "triangles": triangles}

    if not object_map:
        raise ValueError("No mesh data found in 3MF file")

    root_path = next((p for p in model_paths if p.lstrip("/").lower() == "3d/3dmodel.model"), model_paths[0])
    root_doc = read_xml(root_path)
    root_unit = (root_doc.documentElement.getAttribute("unit") or "millimeter").lower()
    unit_scale = unit_to_mm.get(root_unit, 1)
    unit_matrix = three.Matrix4.new().makeScale(unit_scale, unit_scale, unit_scale)
    instances = []

    def parse_transform(value):
        if not value:
            return three.Matrix4.new()
        values = [float(part) for part in value.strip().split()]
        if len(values) == 12:
            return three.Matrix4.new().set(
                values[0], values[3], values[6], values[9],
                values[1], values[4], values[7], values[10],
                values[2], values[5], values[8], values[11],
                0, 0, 0, 1,
            )
        return three.Matrix4.new()

    def resolve_object(file_path, object_id, parent_matrix, visiting=None, depth=0):
        if visiting is None:
            visiting = set()
        if depth > MAX_3MF_DEPTH:
            raise ValueError("3MF component hierarchy too deep - possible cyclic reference")

        norm_file = file_path.lstrip("/").replace("\\", "/")
        key = f"{norm_file}#{object_id}"
        if key in visiting:
            raise ValueError(f"Cyclic component reference detected in 3MF file ({key})")
        visiting.add(key)

        if key in object_map:
            instances.append({"meshKey": key, "matrix": parent_matrix.clone()})

        doc = read_xml(file_path)
        if not doc:
            visiting.remove(key)
            return
        objects = doc.getElementsByTagNameNS(ns_core, "object")
        for i in range(objects.length):
            obj = objects[i]
            if obj.getAttribute("id") != object_id:
                continue
            components = obj.getElementsByTagNameNS(ns_core, "component")
            for c in range(components.length):
                comp = components[c]
                comp_obj_id = comp.getAttribute("objectid")
                comp_path = comp.getAttributeNS(ns_prod, "path") or comp.getAttribute("p:path") or file_path
                if not comp_path.startswith("/") and not comp_path.startswith("3D"):
                    comp_path = "/" + comp_path
                combined = parent_matrix.clone().multiply(parse_transform(comp.getAttribute("transform")))
                resolve_object(comp_path, comp_obj_id, combined, visiting, depth + 1)
        visiting.remove(key)

    build_items = root_doc.getElementsByTagNameNS(ns_core, "item")
    if build_items.length:
        for i in range(build_items.length):
            item = build_items[i]
            seed_matrix = unit_matrix.clone().multiply(parse_transform(item.getAttribute("transform")))
            resolve_object(root_path, item.getAttribute("objectid"), seed_matrix)
    else:
        for key in object_map:
            instances.append({"meshKey": key, "matrix": unit_matrix.clone()})

    if not instances:
        for key in object_map:
            instances.append({"meshKey": key, "matrix": unit_matrix.clone()})

    total_tris = 0
    for inst in instances:
        mesh = object_map.get(inst["meshKey"])
        if mesh:
            total_tris += mesh["triangles"].length // 3
    if total_tris > MAX_3MF_TRIANGLES:
        raise ValueError(f"3MF file contains {total_tris:,} triangles, exceeding the {MAX_3MF_TRIANGLES:,} limit")

    positions = Float32Array.new(total_tris * 9)
    write_offset = 0
    tmp_v = three.Vector3.new()
    for inst in instances:
        mesh = object_map.get(inst["meshKey"])
        if not mesh:
            continue
        vertices = mesh["vertices"]
        triangles = mesh["triangles"]
        for t in range(0, triangles.length, 3):
            for v in range(3):
                vi = triangles[t + v]
                tmp_v.set(vertices[vi * 3], vertices[vi * 3 + 1], vertices[vi * 3 + 2])
                tmp_v.applyMatrix4(inst["matrix"])
                positions[write_offset] = tmp_v.x
                positions[write_offset + 1] = tmp_v.y
                positions[write_offset + 2] = tmp_v.z
                write_offset += 3

    geometry = three.BufferGeometry.new()
    geometry.setAttribute("position", three.BufferAttribute.new(positions, 3))
    return geometry
