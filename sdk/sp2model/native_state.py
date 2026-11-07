"""Discovered native attribute handles. No player file access or private field names."""
from dataclasses import dataclass
from copy import deepcopy
from .errors import ModelingError


@dataclass(frozen=True)
class StateAttribute:
    part: object
    path: str
    name: str
    value: str | None
    metadata: dict | None

    @property
    def read_only(self):
        return self.path == 'Part' and self.name == 'id' or bool((self.metadata or {}).get('readOnly'))

    @property
    def structural_operation(self):
        return 'part.retype' if self.path == 'Part' and self.name == 'partType' else None

    def to_dict(self):
        return {'partId':self.part.id,'path':self.path,'attribute':self.name,'value':self.value,
                'metadata':deepcopy(self.metadata),'nativeReadOnly':bool((self.metadata or {}).get('readOnly')),
                'readOnly':self.read_only,'structuralOperation':self.structural_operation}


class StateNode:
    def __init__(self, part, node, metadata, path):
        self.part, self.name, self.path = part, node.get('element', node.get('name')), path
        if not isinstance(self.name, str):
            raise ModelingError('invalid_native_state', 'Native node is missing its element name')
        self._values = deepcopy(node.get('attributes', {}))
        self._metadata = metadata.get(self.name, {})
        counts = {}; self.children = []
        for child in node.get('children', []):
            name = child.get('element', child.get('name'))
            if not isinstance(name, str): raise ModelingError('invalid_native_state', 'Native child is missing its element name')
            index = counts.get(name, 0); counts[name] = index + 1
            child_path = name + '[' + str(index) + ']'
            if path != 'Part': child_path = path + '/' + child_path
            self.children.append(StateNode(part, child, metadata, child_path))
        self.children = tuple(self.children)

    def attribute(self, name):
        if not isinstance(name, str) or not name:
            raise ModelingError('invalid_attribute', 'Use a nonempty native attribute name')
        return StateAttribute(self.part, self.path, name, self._values.get(name), deepcopy(self._metadata.get(name)))

    @property
    def attributes(self):
        return tuple(self.attribute(name) for name in dict.fromkeys([*self._values, *self._metadata]))

    def nodes(self, name=None):
        result = [self] if name is None or self.name == name else []
        for child in self.children: result.extend(child.nodes(name))
        return tuple(result)

    def node(self, name, *, occurrence=None):
        matches = self.nodes(name)
        if occurrence is not None:
            if type(occurrence) is not int or occurrence < 0 or occurrence >= len(matches):
                raise ModelingError('node_not_found', 'Native node occurrence is unavailable')
            return matches[occurrence]
        if len(matches) != 1:
            raise ModelingError('node_ambiguous' if matches else 'node_not_found', 'Select a unique native node or its explicit occurrence', {'paths':[n.path for n in matches]})
        return matches[0]

    def to_dict(self):
        return {'element':self.name,'path':self.path,'attributes':[a.to_dict() for a in self.attributes],
                'children':[child.to_dict() for child in self.children]}


class NativePartState(StateNode):
    def __init__(self, part, result):
        metadata = {row['element']:{a['name']:a for a in row['attributes']} for row in result.get('metadata', [])}
        super().__init__(part, result['state'], metadata, 'Part')
        self.identity = deepcopy(result['identity'])
        self.capabilities = {key:deepcopy(result[key]) for key in ('source','attributeOperations','nodeOperations','structuralOperations','emptyValuePolicy') if key in result}

    def to_dict(self):
        return {**super().to_dict(),'identity':deepcopy(self.identity),'capabilities':deepcopy(self.capabilities)}
