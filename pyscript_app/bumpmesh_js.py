"""Python facade for BumpMesh's browser ES modules.

PyScript loads the JavaScript modules declared in ``pyscript.json`` and makes
them importable under ``pyscript.js_modules``. Keeping this mapping in one
module gives Python code a stable place to call the existing Three.js and mesh
processing implementation while the browser app is migrated incrementally.
"""

from pyscript.js_modules import (
    decimation_js,
    displacement_js,
    exclusion_js,
    exporter_js,
    i18n_js,
    main_js,
    mapping_js,
    mesh_validation_js,
    preset_textures_js,
    preview_material_js,
    regularize_js,
    smart_resolution_js,
    stl_loader_js,
    subdivision_js,
    texture_analysis_js,
    viewer_js,
)


modules = {
    "decimation": decimation_js,
    "displacement": displacement_js,
    "exclusion": exclusion_js,
    "exporter": exporter_js,
    "i18n": i18n_js,
    "main": main_js,
    "mapping": mapping_js,
    "mesh_validation": mesh_validation_js,
    "preset_textures": preset_textures_js,
    "preview_material": preview_material_js,
    "regularize": regularize_js,
    "smart_resolution": smart_resolution_js,
    "stl_loader": stl_loader_js,
    "subdivision": subdivision_js,
    "texture_analysis": texture_analysis_js,
    "viewer": viewer_js,
}

def get_module(name):
    """Return a configured JavaScript module by its Python-facing name."""
    return modules[name]


__all__ = ["get_module", "modules"]
