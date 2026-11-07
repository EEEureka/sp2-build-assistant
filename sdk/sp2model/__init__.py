"""Explicit native modeling: construct a plan, preview, apply, then verify."""
from .errors import ModelingError
from .geometry import Frame, Section, GeometryError
from .plan import Plan, PlannedPart, PlannedGroup
from .project import Project
from .objects import MaterialRef
from .wings import WingSection, ControlHandle
from .mesh import MeshEvidence, compare_contours
from .surface import compare_surfaces
from .task import ModelingTask
from .session import Session, Scene, PartRef, Preview, Receipt
from .host import to_jsonable
from .runtime import Runtime
from .native import NativePlan, NativeScope

__version__ = "0.7.8a1"
__all__ = ["Runtime", "NativePlan", "NativeScope", "Session", "Scene", "PartRef", "Preview", "Receipt", "Plan", "PlannedPart",
           "PlannedGroup", "Project", "MaterialRef", "Frame", "Section", "WingSection", "ControlHandle", "MeshEvidence", "compare_contours", "compare_surfaces", "to_jsonable", "ModelingTask", "ModelingError", "GeometryError"]
