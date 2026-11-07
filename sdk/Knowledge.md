# Route 1 knowledge API (0.7.7)

`Runtime.knowledge` reads the versioned bundle shipped with the SDK. Constructing
a Runtime and reading knowledge does not discover a game, connect to a bridge,
create a journal directory, or write a cache. The tool release version and the
source game version are separate fields.

```python
from sp2model import Runtime

knowledge = Runtime().knowledge
status = knowledge.status()
options = knowledge.search("templates", query="wing")
part = knowledge.get("parts", "AirBrake-1")
fields = knowledge.export("fields", partType="AirBrake-1", limit=25)
# Follow part["record"]["fieldIds"], sourceFieldIds and enumIds for details.
```

The same implementation serves `Runtime.call("knowledge.search", {...})` and
the schema driven command host. `sp2model commands schema --command
knowledge.search` describes the complete input contract. Unknown properties,
invalid collection names, boolean/negative offsets and limits outside 1–100
are rejected. Identifiers and filters are data, never filesystem paths.

| Command | Arguments | Result |
|---|---|---|
| `knowledge.status` | none | Source version, content identity, counts, coverage, gaps and limits |
| `knowledge.search` | `collection`, optional `query`, `partType`, `role`, `offset`, `limit`, `cursor`, `refresh: true` | Small record summaries |
| `knowledge.get` | `collection`, `id`, optional `cursor`, `refresh: true` | Full record, or recoverable fragments of a very large record |
| `knowledge.export` | Same arguments as search | Full records in bounded pages |
| `knowledge.refresh` | none | Explicit read-only native refresh, version comparison and directory diff |

The collections are `templates`, `parts`, `fields`, `sourceFields`, `enums`,
`choices`, `boundaries`, `sources`, `functions`, `constants`, `variables`,
`rules`, `inputs`, `outputs`, `examples`, `mfd`, and `unknowns`.
`liveTemplates` and `liveFunctions` become available after an explicit refresh.
All records have stable `id`, `title`, and `summary` fields. Part details expose
links to their field, source-field, enum, and template records. Field records
preserve their full XML path and modifier identity; callers must not infer
relationships by splitting the ID text.

`query` performs case-insensitive AND matching of whitespace-separated terms
across record text, including descriptions, categories, fields and source
references. `partType` uses explicit part associations and the part's declared
IDs. It does not infer that a source class belongs to a part from a similar
name. `role` matches `role`, `roles`, `kind`, `fieldRole` or `classification`
values. These filters are shared by search and export. A zero-match result
does not establish the absence of a feature; check coverage and gaps.

Every successful result includes `dataSource`, `datasetId`, `version`,
`coverage`, `gaps`, and `compatibility`. Offline `compatibility.status` is
`offline_unverified`. Source evidence, inference, unresolved resource domains,
and native metadata retain their separate evidence labels. Descriptions and
native metadata do not authorize writes, certify tool support, or describe
the values in the currently open craft.

Query coverage keeps denominators and counts; long ID lists link to
`knowledge.status`, which includes full coverage and generator/input provenance.

## Pagination and content identity

Records are ordered by the exact stable ID. The default page size is 25 and
the maximum is 100. Responses are at most 512 KiB of canonical UTF-8 JSON.
`total`, `offset`, `returned`, `truncated`, `nextOffset` and `nextCursor` make
pagination explicit. An export also supplies `contentHash`, the SHA-256 of
the complete filtered record list in canonical JSON, independent of page size.

```python
page = knowledge.export("fields", partType="AirBrake-1", limit=25)
while True:
    consume(page["records"])
    if page["nextCursor"] is None:
        break
    page = knowledge.export(
        "fields", partType="AirBrake-1", limit=25, cursor=page["nextCursor"]
    )
```

Keep the same command, collection, filters and page size when resuming. Omit
`offset` when supplying a cursor, or supply the matching `nextOffset`. Cursors
bind the dataset, query, page size and exact continuation position. They are
portable between sessions with the same bundle; a changed dataset or query is
rejected. The checksum detects accidental cursor modification; it is not an
authorization token. Dataset identities are derived from the sorted manifest
file descriptors. Both document byte counts and SHA-256 hashes are checked
before loading, along with their schema, record IDs and source consistency.
This detects damaged or inconsistent packages; it is not a digital signature.

If one record exceeds the response budget, a page contains `recordChunk`
instead of that full record. Its `content` is base64 of a UTF-8 JSON byte
fragment, with `offset`, `bytes`, `totalBytes`, and the complete record's
`sha256`. Decode each fragment, concatenate bytes in offset order, verify the
SHA-256, then decode UTF-8 and parse JSON. A fragment may split a Unicode code
point; do not decode individual fragments as text. Continue using `nextCursor`
until the record completes. `nextOffset` stays at the current record until
its last fragment; the final fragment then advances it. Normal records resume
on the following page. No oversized record is silently skipped.

`knowledge.get` normally returns `record`. When fragmented it returns
`record: null`, `recordChunk`, and the same continuation fields. Reissue get
with the same collection/ID and `cursor` until `nextCursor` is null.

## Explicit live refresh

```python
runtime = Runtime(instance="chosen-instance")
receipt = runtime.knowledge.refresh()
directory = runtime.knowledge.search("liveTemplates", limit=25)
```

Each CLI process creates a new Runtime. A standalone `knowledge.refresh` does
not preserve its overlay for a later CLI invocation. Supply `refresh: true`
on a `knowledge.search`, `knowledge.get` or `knowledge.export` request to
perform the three explicit native reads and the query within one invocation:

```text
sp2model knowledge search --collection liveTemplates --refresh true --limit 25 --instance <chosen-instance>
```

This option is accepted only for `liveTemplates` and `liveFunctions`; it must
be the boolean `true`. To continue a live export from another process, repeat
the same query with `refresh: true` and its cursor. An unchanged directory
keeps its content identity and can resume; a changed directory rejects the
old cursor. Static queries remain offline.

Refresh calls exactly `capabilities`, `catalog.export`, and `funky.list`.
It retains an in-memory allowlisted directory and function-signature overlay.
It does not persist a cache, retain default-state snapshots, add parts to a craft,
evaluate FT, or change the craft. Native subassemblies expose their member-type
composition and native description; they do not acquire unverified static
semantics. Live names and descriptions remain local to that Runtime.
`compositionStatus: unavailable` and `compositionGap` distinguish missing or
failed native schemas and inconsistent member types; unknown counts are null,
not an empty complete composition.

The first diff compares native templates with the offline built-in directory;
later diffs compare with the preceding successful refresh. It reports added
and removed IDs and changed member-type mappings. Native directory content
determines the live dataset ID, so unrelated read operations do not invalidate
a cursor. Native directory changes do invalidate old live cursors. Offline
collections and their dataset ID remain unchanged.

A failed refresh preserves the previous overlay and reports
`live.lastRefreshStatus.status: failed` in status. Its compatibility becomes
`stale_after_refresh_failure`; subsequent reads cannot imply the attempted
refresh succeeded. A later successful explicit refresh replaces this state.

The available live source-version fields are compared independently. A
mismatch returns `stale`; missing game-version evidence returns `unverified`.
Matching game versions return `version_matched`, with unavailable build/XML/
assembly provenance listed under `unchecked`. The bridge's plugin `buildId`
is never treated as the Steam build ID. `runtimeCertified` remains false even
when game-version strings match: read-only directory comparison is not runtime
behavior, performance, field-write or assembly-identity certification.

## Compatibility and errors

`knowledge.catalog`, `knowledge.funky` and `knowledge.complex` keep their legacy
payload shapes and include a `legacy` scope notice linking the new index.
Their curated overviews must not be counted as 0.7.7 complete collections.
Native catalog/state/shape/output/variable commands retain their behavior and
guards.

The legacy complex overview retains its record structure, but distribution
replaces historical C# statement excerpts in `parameters[].expression` with
`null` and `expressionStatus: source-reference-only`. Source locations remain;
use the new field details for derived semantics. FT example expressions remain
available. Native catalog schema reads may construct detached `PartData` values
for metadata; they do not create scene parts or change the current craft.

The unused historical `editable-coverage.json` audit resource is distributed
as an explicit `available: false` pointer to the current index. Its old private
template references remain only in the source workspace audit, not the wheel.
No catalog/state/shape/variable/output API uses that historical file.

Status returns `available: false` with explicit gaps if the bundle is missing
or invalid. Other queries raise `knowledge_unavailable`, `knowledge_invalid`
or `knowledge_integrity`. Missing IDs use `knowledge_not_found`; unrefreshed
live collections use `knowledge_live_unavailable`; incompatible continuation
tokens use `knowledge_cursor_mismatch`. Malformed requests use `invalid_input`.
There is no fallback to a game, old snapshot, arbitrary path, or network source.

