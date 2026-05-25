"""Python core module registry for the PyScript app."""

from pyscript_app import displacement
from pyscript_app import exporter
from pyscript_app import exclusion
from pyscript_app import geometry_utils
from pyscript_app import mapping
from pyscript_app import smart_resolution
from pyscript_app import stl_loader
from pyscript_app import texture_analysis


modules = {
    "displacement": displacement,
    "exporter": exporter,
    "exclusion": exclusion,
    "geometry_utils": geometry_utils,
    "mapping": mapping,
    "smart_resolution": smart_resolution,
    "stl_loader": stl_loader,
    "texture_analysis": texture_analysis,
}


def get_module(name):
    return modules[name]
