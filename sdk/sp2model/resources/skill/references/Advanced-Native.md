# Advanced native modeling — 0.7.2 development

For `plan.shape` raw patches, named corner fields are objects: for example `cornerStretch={"topLeft":False,"topRight":False,"bottomRight":False,"bottomLeft":False}`, rather than one boolean. Read the current `shape.schema` before using a new nested field; invalid-shape feedback includes `details.jsonPath` for supported type/field validation. Raw patches remain partial merges unless a documented replacement/reset is explicitly requested.

Check loaded capabilities, identity and lifetime before writes. These interfaces are implemented in the development workspace; installed/global availability is separate. Configuration, static mesh, section polar, persistence, flight response, visual review and user aesthetics have separate results.

## Wings and controls

`plan.wing_planform(name, span, root_chord, tip_chord, sweep_deg=0, sweep_reference=.25, root_offset=0, root_airfoil="NACA2412", tip_airfoil="NACA0012", position=..., rotation_quaternion=..., flipped=False)` creates one native wing. Dimensions use plan units. Span is local +X; leading edge is +Z. Sweep is aft-positive; reference fraction is measured from leading edge (0) to trailing edge (1). The tool computes centre offsets.

`plan.wing_sections(name, [WingSection(span_position, chord=None, offset=None, airfoil=None, bend_deg=0, smooth_join=False, bend_radius_multiplier=1), ...], ...)` supports 2..32 native sections. Stations start at zero and strictly increase. Root/tip need chord/offset; root needs a foil. Other omitted chord/offset and None foils use native interpolation. Installation rotation gives main/horizontal/vertical wings. aerodynamics accepts discovered native lift/drag/sample/fuel fields; arbitrary advanced attributes use native state.

`plan.wing_airfoils(part, root=..., tip=..., stations={index:name})` edits only selected foil fields; tip=None explicitly restores inheritance. `plan.replace_wing_sections(part, sections)` replaces the complete section list while retaining unrelated fields. Indexed shape sections remain a merge. Controls/ranges still constrain the result; no cosmetic fuselage substitution occurs.

`session.airfoils()` discovers current syntax/limits; `.airfoils(name="NACA2412")` reads native geometry. All valid four-digit values are supported; zero thickness and singular cambered zero-position foils reject. Current five-digit/modified runtime stubs reject explicitly. `.airfoil_curve(name, reynolds=1e6, mach=.2, angles_deg=[...])` runs the native section polar evaluator with declared conditions, not an installed whole-aircraft flight test.

Existing attached StandardFlap, FowlerFlap, Slat and BrakeFlap use:

```python
dependencies = session.dependencies([wing])
# Review the host and native control dependents reported for wing rebuilds.
plan = session.plan(writable=reviewed_parts)
plan.control_resize(flap, span_m=.5, span_anchor="inner", chord_m=(.18,.16))
plan.control_shift(flap, .05, width_policy="metres")
```

span_anchor is inner/outer/center; span_fraction is an alternative native host-span fraction. chord_m accepts one world width or inner/outer widths; chord_fraction uses local host chord. width_policy="fraction" retains chord fraction, "metres" retains effective width after moving/resizing. Arguments ending _m stay metres even in cm/mm plans. Conflicting inputs/clipping reject. Native whole-interval chord, span availability and overlap checks remain authoritative. Aileron is an input/use role, not a fabricated type; true double-slot flap and standalone Spoiler high-level construction remain outside this adapter.

`session.wing_stations(wing, positions)` reports native interpolation/scaling/derived unbent geometry. `.control_handles(control)` returns span/hinge handles with identity, coordinate/value and geometry status; `plan.control_handle(handle,value)` edits native station/fraction coordinates. Uncertified curved-bend world positions remain incomplete; friendly metre conversion refuses them. Explicit native parameters and mesh measurement remain available. Newly planned controls need a successful native attachment boundary before existing-control resize/handle methods.

## Drive shaft

`session.mechanical(part)` reads visual JDriveShaft live endpoints, local/world coordinates, connections/types, endpoint spacing, radius multiplier, boots and limits. `plan.native_part(name, discovered_single_part_template_id, ...)` creates a native template with its defaults.

`plan.mechanical(part, start=..., end=..., length=..., anchor="start", direction=..., radius_multiplier=..., boot_a=..., boot_b=...)` uses plan coordinates/units for endpoints. length is absolute world endpoint spacing; anchor is start/end/center. Endpoints and length are mutually exclusive; direction requires length. Native beam recentering invalidates prior poses. Radius is the game's dimensionless UI multiplier (0.5..2), not metres.

Connected endpoints stay fixed unless reviewed hosts were explicitly moved first; no silent detach or host movement. Tool spacing is .01..1000 m, with native visual direction threshold .01 m. Endpoint spacing is not a complete visible-mesh/collider or power-transmission certificate.

Native shaft serialization originally formats vectors to two decimals. Explicitly loaded sub-centimetre endpoints now retain float roundtrip precision; ordinary two-decimal inputs retain original formatting. Reopen can still produce sub-micrometre transform differences. Default rebind remains strict: inspect nativeEndpointRoundtripCandidates, then explicitly choose `session.rebind(accept_native_endpoint_roundtrip=True)` if appropriate. This cross-session policy only accepts shaft start/end differences up to 2 micrometres; other fields, pose, uniqueness and lifetime guards remain. Revision/write-scope checks never use it.

## Sphere/dome and reset

`plan.sphere(name, radius=... OR diameter=..., center=..., axis=..., tolerance_m=.006, max_parts=12, allow_approximation=True)` and `.dome(name, radius=... OR diameter=..., depth=..., base_center=..., axis=..., ...)` compile adaptive native quadratic loft bands and rounded polar caps. Dome radius is base radius; depth runs from base plane to tip; deep caps may bulge beyond base diameter. Units follow the plan, tolerance_m stays metres.

Approximation needs explicit acceptance. Receipt/project metadata reports strategy, parts, parameters and ideal-curve estimate; native tessellation/exterior still need measurement. `session.semantic(name)` reads definition/members; `plan.reshape_semantic(name, radius=..., depth=..., allow_approximation=True)` edits the same partition in place, preserving other native state. Nonrigid/manual shape changes or a new partition count reject and need a reviewed replacement candidate.

Shape merge retains omitted fields. `plan.clear_cutting(part,section_indices=[...],mode="automatic" OR "nominal_boundary",edges=[...])` explicitly restores automatic cuts (None) or requests zero cuts at nominal boundaries. Curved control sections have no cutting. Native attribute reset uses `plan.edit_attribute(field,action="remove")`; JSON null does not universally mean reset. Preview reports static merged configuration and retained indices; receipt reports settled shape. Neither is a mesh certificate.

## Attributes, logic and recovery

`state=session.state(part)` exposes the full live native XML-editor tree/metadata, including undeclared attributes. `.node(name,occurrence=...)` resolves repeats; `.attribute(name)` discovers optional/custom attributes. `plan.edit_attribute(field,value)` sets; action="remove" removes/resets; action="rename",new_name=... renames. Empty follows native omission; native read-only remains read-only. Native IDs cannot be forged. `plan.retype(part,new_type,name=...,accept_connection_loss=True)` explicitly replaces structure and retires old handles. No arbitrary node-add/delete capability is claimed beyond the native editor.

`session.inputs(part)`, `.outputs(part)`, `.variables()` return discovered handles. `plan.input(controller,input=...,activation_group=...,invert=...,min=...,max=...)` edits real inputs. `.output(output,variable=...,priority=...,activator=...)` binds/updates; action="unbind" removes the binding. Setters use `session.plan(variables=[reviewed_names])` with add_variable, update_variable, delete_variable and reorder_variables. Duplicate providers/order remain visible; index changes do not refresh stale handles.

`session.validate_expression(expression,part=...,controller=...,field=...,type=...)` compiles in native context without telemetry evaluation. `.logic_dependencies(variable=...)` uses native name tokens and reports known Setters/controllers/output activators, duplicate providers, possible cycles and unknown coverage. `plan.rename_variable(setter,new_name,references=reviewed_graph_rows)` migrates only chosen identifiers in a fresh plan, preserving quoted strings, member names, substrings and independent output declarations. Mod-specific expression fields and feedback stability require separate review.

`session.checkpoint(name,pinned=True)`, `.checkpoints()`, `.checkpoint_info(id)` and `.prune_checkpoints(ids,include_pinned=False)` expose session-bound anchors. At 64 entries, eviction excludes pinned, active and queued recovery targets; pruning retains an anchor. Checkpoints do not survive restart. `.restore_preview(id)` shows the whole overwrite scope; `.restore(token,accept_whole_craft=True)` executes once and token reuse queries its original journal. Results distinguish fingerprint, serialized equality, declared native differences and tolerance. Logical aliases remain review_required; inspect `.bindings()` and explicitly rebind.

`session.status()` is compact; host inspect defaults to summary and --detail full loads parts explicitly. `.query(...,offset=0,limit=50,identity=previous_page_identity)` pages up to 200 with truncation and selectable fields. Native filters and project logical_name/tags/group filters are distinct. Retired/unbound logical aliases cannot fall back silently. `.dependencies(parts)` reports connection/native host/symmetry candidates and unknown callbacks; it never expands the write set automatically.
