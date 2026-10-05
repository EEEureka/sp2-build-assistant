"""Offline write contracts mirroring ShapeCodec bounds; native context stays authoritative."""
STYLES = ["StandardFlap", "FowlerFlap", "BrakeFlap", "Slat"]
FAMILIES = ["fuselage", "wing", "controlSurface"]


def obj(properties, required=(), **extra):
    return {"type": "object", "properties": properties, "required": list(required), "additionalProperties": False, **extra}


def number(low, high, unit=None, integer=False, nullable=False):
    result = {"type": "integer" if integer else "number", "minimum": low, "maximum": high}
    if nullable:
        result["type"] = [result["type"], "null"]
    if unit:
        result["description"] = unit
    return result


def vector(size, low, high, description):
    return {"type": "array", "minItems": size, "maxItems": size, "items": number(low, high), "description": description}


def control(style):
    fields = {
        "spanRange": vector(2, 0, 1000, "[start,end] metres along source wing stations; end-start >= 0.001, inside the attached wing. Native overlap/availability checks still apply."),
        "chordFraction": vector(2, .05, .4 if style == "Slat" else .8, "[root,tip] fractions of local chord at the span endpoints; not metres or a single scalar."),
    }
    if style in ("StandardFlap", "FowlerFlap", "Slat"):
        fields["maxDeflectionDegrees"] = number(0, 90, "degrees")
    else:
        fields.update({key: number(0, 90, "degrees") for key in ("flapDeflectionDegrees", "brakeTopDegrees", "brakeBottomDegrees")})
        fields["brakeDeflectionSpeed"] = number(.001, 100, "Native brake deflection speed")
    return obj(fields, title=style + " patch", description="Only supplied fields change. Query shape.get for actual style; the DLL validates wing membership and native limits.")


def fuselage():
    boolean = {"type": "boolean"}
    corners = ("topLeft", "topRight", "bottomRight", "bottomLeft")
    edges = ("top", "right", "bottom", "left")
    section = obj({
        "index": {"type": "integer", "minimum": 0, "description": "Existing zero-based slice index, unique within this patch."},
        "width": number(0, 1000, "metres"), "height": number(0, 1000, "metres"),
        "smoothing": boolean, "syncAdjacent": boolean, "thicknessFraction": number(.01, 1, "fraction; unavailable for legacyThickness"),
        "trapezium": number(-1, 1),
        "cornerRadius": obj({k: number(0, 1000) for k in corners}, description="Metres normally; with cornerStretch=true this is a fraction constrained to [0,1]. Native geometry may clamp against adjacent edges."),
        "cornerStretch": obj({k: boolean for k in corners}),
        "cornerSamples": obj({k: number(1, 32, integer=True) for k in corners}),
        "edgeCurvature": obj({k: number(0, 1, "fraction") for k in edges}),
        "edgeSamples": obj({k: number(1, 32, integer=True) for k in edges}),
        "cutting": obj({k: number(0, 1, "fraction; null restores automatic", nullable=True) for k in edges}, description="Opposite cuts must sum to <1. Curved middle slices do not support cutting; check shape.get section capabilities."),
    }, ["index"], description="Patch an existing section. Curved middle slices and cone tips have native capability restrictions.")
    fields = {k: boolean for k in ("hollow", "glass", "autoResize")}
    fields["autoResize"] = {"type": "boolean", "description": "When true, native connection callbacks can copy the neighbour's sections/length and reposition this fuselage or cone, then reset this flag. Set false explicitly before connection to preserve manually configured dimensions; shape.update does not implicitly disable it."}
    fields.update({k: number(0, 1, "fraction") for k in ("fuelFraction", "buoyancy", "noseconeRoundness")})
    fields["noseconeRoundness"]["description"] = "0..1; cone part types only"
    fields.update({"deadMassKg": number(0, 500, "kg"), "colliderCount": number(3, 16, integer=True), "colliderCornerSamples": number(1, 32, integer=True),
                   "length": number(.001, 1000, "Absolute local Z separation, metres. Preserves offset X/Y and the existing Z sign."),
                   "offset": vector(3, -1000, 1000, "Local [x,y,z] metres; abs(z) >= 0.001. Mutually exclusive with length."),
                   "sections": {"type": "array", "minItems": 1, "items": section}})
    return obj(fields, title="fuselage patch", description="Existing slice edits only; replaceSections is a wing feature and is not supported for fuselage. At least one section must retain positive width and height.", **{"not": {"required": ["offset", "length"]}})


def wing():
    boolean = {"type": "boolean"}
    section = {
        "spanPosition": number(0, 1000, "metres; first station is zero and stations increase by >=0.001"),
        "chord": number(.001, 1000, "metres; root/tip cannot be null", nullable=True),
        "offset": number(-1000, 1000, "chordwise metres; root/tip cannot be null", nullable=True),
        "airfoil": {"type": ["string", "null"], "minLength": 1, "description": "Native airfoil expression e.g. NACA0012 or NACA2412. Root needs an airfoil; nullable interior/tip values use native inheritance/interpolation. Native parser validates expressions."},
        "smoothJoin": boolean, "bendDegrees": number(-170, 170, "degrees"), "bendRadiusMultiplier": number(.01, 100),
        "chordSamples": number(3, 64, integer=True, nullable=True), "colliderSamples": number(3, 32, integer=True, nullable=True),
    }
    fields = {k: boolean for k in ("flipped", "disableWingtipVortices")}
    fields.update({"fuelFraction": number(0, 1, "fraction"), "liftScale": number(0, 100), "zeroLiftDragScale": number(0, 100), "viscousDragScale": number(0, 100),
                   "physicsSamples": number(2, 256, integer=True, nullable=True), "chordSamples": number(3, 64, integer=True), "colliderSamples": number(3, 32, integer=True),
                   "sections": {"type": "array", "minItems": 1, "items": obj({"index": {"type": "integer", "minimum": 0}, **section}, ["index"])},
                   "replaceSections": {"type": "array", "minItems": 2, "maxItems": 32, "items": obj(section, ["spanPosition"]), "description": "Complete ordered station list. Root/tip need chord and offset; root needs airfoil. Native parser/geometry checks still apply."},
                   "wingtip": {"anyOf": [{"type": "null"}, obj({"stretch": number(0, 4)}, ["stretch"])]}})
    return obj(fields, title="wing patch", **{"not": {"required": ["sections", "replaceSections"]}})


def patch():
    return {"type": "object", "anyOf": [fuselage(), wing(), *[control(s) for s in STYLES]],
            "description": "Choose the matching family/style from shape.get. Each branch names legal keys and bounds; validation of actual part family, slice indices, overlap, airfoil expressions and native geometry occurs in the DLL. Spoiler/SplitFlap have no supported typed write contract.",
            "x-discoveryCommands": ["sp2build shape get --id PART_ID", "sp2build shape schema --family FAMILY"]}


def enrich(command, result):
    props = result["properties"]
    if command == "shape.update":
        props["patch"] = patch()
    elif command == "wing.control.add":
        props["style"] = {"type": "string", "enum": STYLES[:], "description": "Creatable native styles. Spoiler/SplitFlap are inventory/read-only and cannot be added through this operation."}
        props["patch"] = {"type": "object", "anyOf": [control(s) for s in STYLES], "description": "Style-specific patch; the matching allOf branch below supplies its exact fields."}
        result["allOf"] = [{"if": {"properties": {"style": {"const": style}}, "required": ["style"]}, "then": {"properties": {"patch": control(style)}}} for style in STYLES]
    elif command == "shape.schema":
        props["family"] = {"type": "string", "enum": FAMILIES[:], "description": "Exact case-sensitive typed family identifier; not a native PartTypeId."}
    return result
