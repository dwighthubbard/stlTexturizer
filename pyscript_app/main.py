"""PyScript bootstrap for BumpMesh.

The production UI and mesh algorithms are still the existing browser ES
modules. Importing ``main_js`` runs the current app bootstrap, while
``bumpmesh_js`` exposes the other modules for Python code to call directly.
"""

from js import document

from pyscript_app.core import get_module as get_python_module
from pyscript_app.bumpmesh_js import get_module as get_legacy_js_module


python_core = {
    "displacement": get_python_module("displacement"),
    "exporter": get_python_module("exporter"),
    "exclusion": get_python_module("exclusion"),
    "mapping": get_python_module("mapping"),
    "smart_resolution": get_python_module("smart_resolution"),
    "stl_loader": get_python_module("stl_loader"),
    "texture_analysis": get_python_module("texture_analysis"),
}

# Temporary compatibility bootstrap while the UI/controller layer is migrated.
main_js = get_legacy_js_module("main")

document.documentElement.setAttribute("data-runtime", "pyscript")
