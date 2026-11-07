"""Small immutable public handles for non-part modeling resources."""
from copy import deepcopy
from dataclasses import dataclass, field


@dataclass(frozen=True)
class MaterialRef:
    id: int
    name: str
    properties: dict
    _identity: dict = field(repr=False)
    _instance: str = field(repr=False)
    _fingerprint: str = field(repr=False)

    @property
    def reserved(self):
        return self.properties.get("reserved", False)

    def to_dict(self):
        return {"id": self.id, "name": self.name, "properties": deepcopy(self.properties),
                "identity": deepcopy(self._identity), "instanceId": self._instance}


@dataclass(frozen=True)
class SetterRef:
    index: int
    variable: str
    function: str
    priority: int
    activator: str | None
    _identity: dict = field(repr=False)
    _instance: str = field(repr=False)

    def to_dict(self):
        return {"index":self.index,"variable":self.variable,"function":self.function,"priority":self.priority,
                "activator":self.activator,"identity":deepcopy(self._identity)}


@dataclass(frozen=True)
class OutputRef:
    part: object
    modifier: str
    modifier_index: int
    output_id: str
    definition: dict
    bindings: tuple

    def to_dict(self):
        return {"partId":self.part.id,"modifier":self.modifier,"modifierIndex":self.modifier_index,
                "outputId":self.output_id,"definition":deepcopy(self.definition),"bindings":deepcopy(list(self.bindings))}


@dataclass(frozen=True)
class ControllerRef:
    part: object
    index: int
    configuration: dict

    def to_dict(self):
        return {"partId":self.part.id,"index":self.index,"configuration":deepcopy(self.configuration)}
