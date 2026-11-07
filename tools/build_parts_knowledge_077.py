"""Build the distributable 0.7.7 part reference from a frozen local audit.

Usage: python tools/build_parts_knowledge_077.py --inventory <audit directory>
The input is read-only. No Game installation, running process, or player files
are consulted. The published schema uses collections of id/title/summary records.
Source fields are authoritative semantics; per-part fields are explicit joins,
not editing permissions. Candidate paths are labelled as such.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET


VERSION = "0.7.7.parts.3"
SCHEMA = "sp2model.knowledge/1"
DEFAULT_OUTPUT = Path(__file__).resolve().parents[1] / "knowledge/v077/parts.json"
SOURCE_INPUTS = (
    "parts/templates.jsonl", "parts/template-parts.jsonl", "parts/part-types.jsonl",
    "parts/native-fields.jsonl", "parts/source-field-links.jsonl", "parts/native-choices.json",
    "parts/native-source-boundaries.json", "parts/scope-boundaries.json",
    "xml-source/source-xml-fields.json", "xml-source/source-xml-inventory.json", "xml-source/source-enums.json",
    "xml-source/external-enums.json", "xml-source/dynamic-xml-sites.json",
    "xml-source/coverage.json", "baseline/game-decompilation-manifest.json",
    "baseline/source-file-sha256.json",
)
CODE_KEYS = {"code", "context", "expression", "statement", "accessors", "attributes",
             "initializer", "conditions", "receiver", "originalPurposeZh",
             "xmlNameExpression", "text"}
NATIVE_PREREQUISITES = {
    "tpl-1200a9e31d998b7b": "差速器使用一根传动轴输入、两根传动轴输出；需要按这个动力接口关系接入传动系统。",
    "tpl-1c640c80ce06c2ec": "供喷气发动机进气；原生说明建议放在机体前方、气流扰动较小的位置。该建议不是所有构型的进气性能认证。",
    "tpl-3b2c364061dbd487": "拦阻功能依赖场景中的拦阻索；只有部署钩并实际捕获索才会产生原生说明所指的拦阻作用。",
    "tpl-64ce27fa6dba1643": "需要激活组开启电磁吸附，并有原生允许吸附的金属目标；吸附作用不能仅由磁体放置证明。",
    "tpl-7805b1fb0e164d60": "辅助受油需要加油锥套；探针向锥套提供受油位置。原生说明同时指出其他部件也能受油，探针不是唯一可受油件。",
    "tpl-839bf4b2b3762e44": "原生用途是由飞机通过绞盘拖曳锥套，再向另一飞机输油；需要相应拖曳连接与受油对象。",
    "tpl-db66fd47fd272095": "用于喷气发动机进气；原生说明称多数发动机需要至少两个这种窄进气口，不能据此保证任意发动机和安装位置的进气量。",
}


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def unique(items):
    found = {}
    for item in items:
        found[json.dumps(item, sort_keys=True, ensure_ascii=False)] = item
    return [found[k] for k in sorted(found)]


def source_reader_literal(source):
    """Decode only scalar reader fallbacks; never evaluate C# expressions.

    A scalar fallback passed to a vector reader is not its XML representation.
    Conflicting literals across initializer/reader layers stay unknown here.
    """
    def decode(literal):
        if not isinstance(literal, str):
            return None
        if literal in {"true", "false"}:
            return "bool", literal
        if re.fullmatch(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?[fFdDmM]?", literal):
            return "number", re.sub(r"[fFdDmM]$", "", literal)
        if re.fullmatch(r'"(?:[^"\\\x00-\x1f]|\\["\\/bfnrt]|\\u[0-9a-fA-F]{4})*"', literal):
            decoded = json.loads(literal)
            if all(ord(c) >= 32 or c in "\t\r\n" for c in decoded) and not any(0xD800 <= ord(c) <= 0xDFFF for c in decoded):
                return "string", decoded
        return None

    readers = [d for d in source.get("defaults", []) if d.get("kind") == "reader-fallback"]
    if not readers:
        return None
    candidates = []
    scalar_calls = {"bool": {"GetBoolAttribute"}, "number": {"GetFloatAttribute", "GetDoubleAttribute", "GetIntAttribute"}, "string": {"GetStringAttribute"}}
    for default in readers:
        value = decode(default.get("literal")) if default.get("status") == "literal" else None
        evidence = default.get("evidence", [])
        if value is None or not evidence or any(e.get("call") not in scalar_calls[value[0]] or re.search(r"legacy|upgrade|migrat", e.get("method", ""), re.I) for e in evidence):
            return None
        if any(e.get("call") == "GetIntAttribute" for e in evidence) and not re.fullmatch(r"[+-]?\d+", value[1]):
            return None
        candidates.append((value, default))
    literals = {decode(d.get("literal")) for d in source.get("defaults", []) if d.get("status") == "literal"}
    if len(literals) != 1 or None in literals:
        return None
    value, selected = candidates[0]
    return {"value": value[1], "literal": selected["literal"], "evidence": unique([e for _, d in candidates for e in d["evidence"]])}


def enrich_reading_and_examples(collections):
    """Compose selection guidance from reviewed facts, never from a part name.

    XML snippets are reference fragments, not a new write API. Every literal is
    traceable to an allowlisted builtin template, metadata default, option, or
    confirmed scalar source reader fallback on a native-observed path.
    """
    fields = collections["fields"]
    sources = {row["id"]: row for row in collections["sourceFields"]}
    templates = collections["templates"]
    template_ids = {t["id"] for t in templates}
    by_part = defaultdict(list)
    defaults_by_template = defaultdict(dict)
    available_examples = defaultdict(list)
    excluded_roles = {
        "template-definition": "资源definition用于部件资源创建，不是载具保存State配置。",
        "derived-cache-or-restored-fallback": "这是派生缓存或恢复回退；不提供伪装成用户配置的XML写入示例。",
        "compatibility-or-migration": "这是兼容读入或迁移路径；当前保存字段需单独核实。",
        "structural-identity-or-reference": "结构身份和引用需由载具结构操作共同维护，孤立属性片段不是安全配置。",
        "persisted-without-confirmed-runtime-consumer": "字段可持久化但运行消费者未确认；不能凭保存存在生成作用已确认的配置示例。",
        "shared-or-nonpart-see-scope": "共享或非部件字段不能当作独立Part/Modifier.State配置。",
        "native-boundary": "旧字段或资源错位没有当前完整State读取证据。",
    }
    for field in fields:
        by_part[field["partType"]].append(field)
        native = field.get("native", {})
        for default in native.get("defaultsByTemplate", []):
            if default["templateId"] not in template_ids:
                raise ValueError("Non-builtin default entered example builder")
            key = (field["partType"], default["memberIndex"], default["path"])
            defaults_by_template[default["templateId"]][key] = (default["value"], field)
        example = {"status": "unavailable", "kind": "xml-reference-fragment", "completeWritableConfiguration": False, "toolWriteCertified": False, "runtimeValidated": False}
        role = field["fieldRole"]
        reason = excluded_roles.get(role)
        if field["toolWriteStatus"] != "not-certified":
            reason = "当前原生边界未关联到有效State读取器；保留说明而不展示可用配置。"
        if not reason and field["joinStatus"] not in {"observed_path_join", "observed_constructor_delegation"}:
            reason = "仅有源码候选或definition上下文，尚不能给出此部件的已核实原生XML路径。"
        if not reason and any(word in field["summary"] for word in ("属于派生", "阻力缓存", "面积缓存", "旧版阻力开关", "旧式", "旧格式", "迁移", "格式版本")):
            reason = "该字段说明为派生缓存或旧兼容开关，配置示例需使用当前用户配置字段。"
        if reason:
            example.update(status="not-applicable", reason=reason)
            field["example"] = example
            continue
        value = None
        defaults = native.get("defaultsByTemplate", [])
        if defaults:
            picked = sorted(defaults, key=lambda d: (d["templateId"], d["memberIndex"], d["path"]))[0]
            value = picked["value"]
            example.update(valueOrigin="builtin-template-default", templateId=picked["templateId"], memberIndex=picked["memberIndex"], observedPath=picked["path"], evidenceLevel="native-read-only-snapshot")
        else:
            metadata = native.get("metadata", [])
            literals = [m["defaultValue"] for m in metadata if m.get("defaultValue") is not None]
            if literals:
                value = sorted(literals, key=str)[0]
                example.update(valueOrigin="native-metadata-default", evidenceLevel="native-metadata-default-not-observed-state")
            else:
                options = sorted({v for m in metadata for v in m.get("enumValues") or []})
                if options:
                    value = options[0]
                    example.update(valueOrigin="native-option-not-default", evidenceLevel="native-option-domain")
        if value is None and field["joinStatus"] == "observed_path_join":
            fallback = source_reader_literal(sources.get(field["sourceFieldId"], {}))
            if fallback:
                value = fallback["value"]
                example.update(valueOrigin="source-reader-fallback", evidenceLevel="static-source-reader-default-not-native-readback",
                               sourceDefaultLiteral=fallback["literal"], sourceDefaultEvidence=fallback["evidence"],
                               sourceDefaultMeaning="属性缺省时读取器使用的源码字面默认；不是内置模板实际保存值，也不是运行时回读结果。")
        if value is None:
            example["reason"] = "该路径没有可分发的内置模板值、原生元数据默认、已确认选项或无冲突标量读取默认；null、符号、复合类型和不确定默认不猜测。"
            field["example"] = example
            continue
        path = field["normalizedXmlPath"]
        nodes, attribute = path.rsplit("/@", 1)
        tags = [re.sub(r"\[\*\]$", "", node) for node in nodes.split("/")]
        if tags[0] != "Part" or any(not re.fullmatch(r"[A-Za-z_][\w.-]*", tag) for tag in tags):
            example["reason"] = "路径仍包含符号上下文，无法生成已核实的原生XML片段。"
            field["example"] = example
            continue
        root = ET.Element("Part", {"partType": field["partType"]})
        node = root
        for tag in tags[1:]:
            node = ET.SubElement(node, tag)
        node.set(attribute, str(value))
        xml = ET.tostring(root, encoding="unicode", short_empty_elements=True)
        ET.fromstring(xml)
        example.update(status="available", xml=xml, attribute=attribute, value=str(value), normalizedXmlPath=path,
                       validationLevel="well-formed-xml-and-frozen-value-reference", sourceFieldId=field["sourceFieldId"],
                       applicability="仅展示指定属性及其节点结构。省略其他必需属性、兄弟节点和部件连接；不能直接当完整载具或编辑操作提交。",
                       repeatedNodeSelection="[*]是集合路径；实例定位需实际节点索引/标识。此片段不指定写入某个重复节点。" if "[*]" in path else "单个根节点属性；实际编辑仍需部件身份和作用域。")
        field["example"] = example
        if field["sourceFieldId"]:
            available_examples[field["sourceFieldId"]].append(field["id"])
    for source in sources.values():
        source["exampleFieldIds"] = sorted(available_examples[source["id"]])
        source["exampleStatus"] = "available-via-native-part-path" if source["exampleFieldIds"] else "unavailable-or-not-applicable"
        source["exampleLimit"] = "示例引用内置默认、原生元数据、合法选项或已确认标量读取默认，按valueOrigin区分且未执行写入；无部件路径的共享、definition、兼容和未知值不补造配置。"

    # Selection guidance carries the source field's exact reviewed effect.
    # Different templates are compared using actual compositions/defaults, not
    # dimensions or performance inferred from their display/resource names.
    for template in templates:
        intro = template["introduction"]
        relevant = [f for part in template["partTypes"] for f in by_part[part]
                    if not f["normalizedXmlPath"].startswith("Part/@")
                    and f["fieldRole"] in {"template-definition", "configuration-or-persisted-state-see-field-meaning"}
                    and not f["normalizedXmlPath"].endswith("/@symmetryDisabled")
                    and not any(term in f["summary"] for term in ("属于派生", "阻力缓存", "面积缓存", "旧版阻力开关", "旧式", "旧格式", "迁移", "格式版本"))]
        def rank(field):
            present = any(d["templateId"] == template["id"] for d in field.get("native", {}).get("defaultsByTemplate", []))
            effect = any(term in field["summary"] for term in ("控制", "决定", "改变", "生成", "驱动", "推力", "升力", "输出", "燃油", "大小", "形状", "尺寸", "半径", "长度", "功率"))
            generic = field.get("modifierStateElement", "").startswith(("InputController", "Animator"))
            return (generic, not effect, not present, field["partType"], field["normalizedXmlPath"], field["id"])
        relevant.sort(key=rank)
        capabilities = [{"kind": "native-purpose", "summary": template["summary"], "templateId": template["id"], "evidenceLevel": intro["purposeSource"]}]
        represented = set()
        for field in relevant:
            modifier = (field["partType"], field.get("modifierStateElement"))
            if modifier in represented:
                continue
            represented.add(modifier)
            capabilities.append({"kind": "reviewed-field-effect", "summary": field["summary"], "fieldId": field["id"], "sourceFieldId": field["sourceFieldId"], "partType": field["partType"], "configurationPresence": field["joinStatus"], "toolWriteStatus": "not-certified", "evidenceLevel": "static-source"})
            if len(capabilities) == 6:
                break
        intro["majorCapabilities"] = capabilities
        composition = template["componentCounts"]
        intro["prerequisitesAndDependencies"] = [{"kind": "native-template-composition", "summary": "此模板由" + "、".join(str(c["count"]) + "个" + c["partType"] for c in composition) + "组成；保留这些成员关系才能复现该目录预设，组成类型不能以首个成员替代。", "templateId": template["id"], "componentCounts": composition, "evidenceLevel": "native-read-only-snapshot"}]
        deps_seen = set()
        for field in relevant:
            if field["sourceFieldId"] in deps_seen or not any(term in field["summary"] for term in ("仅在", "只有", "必须", "需", "依赖", "绑定", "前提", "当", "若", "否则", "无效", "不存在", "不能", "输入", "健康度", "资源", "材质", "节点", "变量", "挂点", "相连", "组合", "与", "同时")):
                continue
            deps_seen.add(field["sourceFieldId"])
            intro["prerequisitesAndDependencies"].append({"kind": "reviewed-field-condition", "summary": field["summary"], "fieldId": field["id"], "sourceFieldId": field["sourceFieldId"], "partType": field["partType"], "configurationPresence": field["joinStatus"], "toolWriteStatus": "not-certified", "evidenceLevel": "static-source"})
            if len(deps_seen) == 3:
                break
        if template["id"] in NATIVE_PREREQUISITES:
            intro["prerequisitesAndDependencies"].append({"kind": "native-purpose-prerequisite", "summary": NATIVE_PREREQUISITES[template["id"]], "templateId": template["id"], "nativeDescriptionSha256": hashlib.sha256(template["nativeDescription"].encode("utf-8")).hexdigest(), "evidenceLevel": "native_translation"})
        if len(intro["prerequisitesAndDependencies"]) == 1:
            intro["prerequisitesAndDependencies"].append({"kind": "unavailable-additional-prerequisite", "summary": "已确认此模板的结构组成；该模板对应原生介绍及专属字段没有足够证据列出额外运行前提，保留unknown，不从结构件名称推断功能依赖。", "templateId": template["id"], "status": "unknown", "evidenceLevel": "scope-boundary"})
        # Compare only an actual native neighbor. Prefer shared component types,
        # then original subcategory/category; semantic claims remain cited facts.
        def purpose_tokens(text):
            return set(re.findall(r"[A-Za-z]{3,}", text.lower())) | {text[i:i+2] for i in range(len(text)-1) if all('\u4e00' <= x <= '\u9fff' for x in text[i:i+2])}
        purpose = purpose_tokens(template["summary"])
        neighbors = sorted((t for t in templates if t["id"] != template["id"]), key=lambda t: (-len(set(t["partTypes"]) & set(template["partTypes"])), -len(purpose_tokens(t["summary"]) & purpose), t["category"] != template["category"], t["subcategory"] != template["subcategory"], t["id"]))
        other = neighbors[0]
        own_defaults, other_defaults = defaults_by_template[template["id"]], defaults_by_template[other["id"]]
        differences = []
        for key in sorted(own_defaults.keys() & other_defaults.keys()):
            value, field = own_defaults[key]
            other_value, _ = other_defaults[key]
            if value == other_value or field["example"]["status"] != "available" or key[2].startswith("Part/@"):
                continue
            differences.append({"partType": key[0], "memberIndex": key[1], "xmlPath": key[2], "thisValue": value, "otherValue": other_value, "fieldId": field["id"], "sourceFieldId": field["sourceFieldId"], "meaning": field["summary"]})
            if len(differences) == 3:
                break
        same_composition = composition == other["componentCounts"]
        distinction = {"otherTemplateId": other["id"], "otherTitle": other["title"], "thisPurpose": template["summary"], "otherPurpose": other["summary"], "thisComposition": composition, "otherComposition": other["componentCounts"], "defaultDifferences": differences, "evidenceLevel": "native-purpose-composition-and-defaults", "geometryAndPerformanceInferred": False}
        if differences:
            distinction.update(status="verified-default-differences", summary="两者含相同组成类型，但下列内置默认配置不同；差异作用按已核实字段说明解读，不由预设名称推断性能。")
        elif not same_composition:
            distinction.update(status="verified-composition-and-purpose", summary="两者的部件组成不同；以下原生作用说明和成员清单用于区分选择，不能把组合模板当作其中一个部件。")
        elif template["summary"] != other["summary"]:
            distinction.update(status="native-purpose-only", summary="原生介绍给出的用途不同；已发布配置没有足够证据进一步量化几何或性能差别。")
        else:
            distinction.update(status="unavailable-further-distinction", summary="两者当前已核实的组成与用途说明相同；没有可引用的配置差异证据，不能仅根据显示名补造差别。")
        intro["distinctions"] = [distinction]
        intro["guidanceScope"] = "能力与依赖来自本模板的内置组成和已核实字段作用；不是运行性能认证或完整工程安装手册。"

    return {"templateGuidance": {"denominator": len(templates), "withMajorCapabilities": len(templates), "withCompositionPrerequisites": len(templates), "withAdditionalFieldConditions": sum(any(d["kind"] == "reviewed-field-condition" for d in t["introduction"]["prerequisitesAndDependencies"]) for t in templates), "withNativePrerequisites": len(NATIVE_PREREQUISITES), "unknownAdditionalPrerequisiteTemplateIds": [t["id"] for t in templates if any(d["kind"] == "unavailable-additional-prerequisite" for d in t["introduction"]["prerequisitesAndDependencies"])], "distinctionsByStatus": dict(sorted(Counter(t["introduction"]["distinctions"][0]["status"] for t in templates).items()))}, "xmlExamples": {"denominatorPartFieldAssociations": len(fields), "byStatus": dict(sorted(Counter(f["example"]["status"] for f in fields).items())), "availableSourceFields": sum(bool(v) for v in available_examples.values()), "valueOrigins": dict(sorted(Counter(f["example"].get("valueOrigin", "none") for f in fields if f["example"]["status"] == "available").items())), "runtimeValidated": 0, "completeWritableConfigurations": 0}}


class Builder:
    def __init__(self, inventory):
        self.root = Path(inventory)
        manifest = self.read("inventory-manifest.json")
        expected = {entry["path"]: entry["sha256"] for entry in manifest["files"]}
        self.input_hashes = {name: digest(self.root / name) for name in SOURCE_INPUTS}
        changed = [name for name, sha in self.input_hashes.items() if expected.get(name) != sha]
        if changed:
            raise ValueError("Frozen input changed; re-audit and freeze semantics before generation: " + ", ".join(changed))
        self.hashes = self.read("baseline/source-file-sha256.json")
        self.sources = {}

    def read(self, relative):
        text = (self.root / relative).read_text(encoding="utf-8-sig")
        return [json.loads(line) for line in text.splitlines() if line] if relative.endswith(".jsonl") else json.loads(text)

    def relative_source(self, value):
        value = str(value).replace("\\", "/")
        if "/Game/" in value:
            value = value.split("/Game/", 1)[1]
        if value not in self.hashes:
            return None
        return value

    def evidence(self, value):
        """Retain citations and their grades; never retain decompiled code."""
        result = []
        def visit(node):
            if isinstance(node, list):
                for child in node:
                    visit(child)
            elif isinstance(node, dict):
                path = self.relative_source(node.get("path", node.get("file", node.get("sourceFile", ""))))
                if path:
                    sid = "src-" + hashlib.sha256(path.encode("utf-8")).hexdigest()[:16]
                    self.sources[sid] = {"id": sid, "title": path, "summary": "当前游戏反编译来源；仅发布位置和哈希，不包含源码正文。", "path": path, "sha256": self.hashes[path], "evidenceLevel": "static-source"}
                    row = {"sourceId": sid}
                    for key in ("line", "endLine", "restoreLine", "delegateLine", "method", "call", "kind", "grade"):
                        if key in node and node[key] is not None:
                            row[key] = node[key]
                    result.append(row)
                for key, child in node.items():
                    if key not in CODE_KEYS:
                        visit(child)
        visit(value)
        return unique(result)

    def prose(self, value):
        """Curated prose only. Machine paths are disallowed even inside prose."""
        if isinstance(value, str):
            if re.search(r"(?<![A-Za-z])[A-Za-z]:[\\/]", value) or "```" in value:
                raise ValueError("Private path or code block in curated prose")
        return value

    def curated(self, row, keys):
        return {k: self.prose(row[k]) for k in keys if k in row}

    def source_default(self, row):
        value = row.get("expression")
        result = {"kind": row["kind"], "evidence": self.evidence(row)}
        # A literal is a default. A symbol is a dependency, never a computed value.
        if value is None:
            result.update(status="unavailable", reason="源码记录没有可发布的默认值。")
        elif re.fullmatch(r'[-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?[fFdDmMuUlL]*|true|false|null|"[^"\r\n]*"', value):
            result.update(status="literal", literal=value)
        elif re.fullmatch(r"[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*", value):
            result.update(status="symbolic", symbol=value, reason="依赖枚举、资源或对象成员；不是已求值的模板默认。")
        else:
            result.update(status="requires-source-evaluation", reason="默认值依赖运算、对象构造、调用或缺省控制流；源码表达式不随包分发。")
        return result

    def build(self):
        raw_templates = self.read("parts/templates.jsonl")
        builtin = [t for t in raw_templates if t["source"] == "builtin"]
        tids = {t["id"] for t in builtin}
        builtin_types = {p for t in builtin for p in t["partTypes"]}
        raw_parts = self.read("parts/part-types.jsonl")
        raw_native = self.read("parts/native-fields.jsonl")
        native_map = {f["key"]: f for f in raw_native}
        raw_source = [f for f in self.read("xml-source/source-xml-fields.json") if f["scope"] == "craft-source"]
        source_map = {f["fieldId"]: f for f in raw_source}
        joins = self.read("parts/source-field-links.jsonl")
        raw_choices = self.read("parts/native-choices.json")
        if raw_choices["sourceInventorySha256"] != self.input_hashes["xml-source/source-xml-inventory.json"]:
            raise ValueError("Choice meanings refer to a different source inventory; review required")
        raw_boundaries = self.read("parts/native-source-boundaries.json")["entries"]
        boundary_map = {b["key"]: b for b in raw_boundaries}
        scope = self.read("parts/scope-boundaries.json")
        collections = {name: [] for name in ("templates", "parts", "fields", "sourceFields", "enums", "choices", "boundaries", "sources")}

        # Reconstruct defaults from allowlisted builtin members, never from the
        # aggregate observedValues or any loaded subassembly metadata.
        native_meta, native_defaults = defaultdict(list), defaultdict(list)
        builtin_members = 0
        for member in self.read("parts/template-parts.jsonl"):
            if member["templateId"] not in tids or member["templateSource"] != "builtin":
                continue
            builtin_members += 1
            ptype = member["partType"]
            for attr in member.get("flattenedAttributes", []):
                key = ptype + "::" + attr["normalizedPath"]
                native_defaults[key].append({"templateId": member["templateId"], "memberIndex": member["partIndex"], "path": attr["path"], "value": attr["value"]})
            for node in member["metadata"]:
                context = "Part" if node["element"] == "Part" else "Part/" + node["element"] + "[*]"
                for attr in node.get("attributes", []):
                    key = ptype + "::" + context + "/@" + attr["name"]
                    native_meta[key].append(dict(attr))
        native_data = {key: {"metadata": unique(native_meta[key]), "defaultsByTemplate": unique(native_defaults[key]), "evidenceLevel": "native-read-only-snapshot", "valuesScope": "builtin-template-defaults-not-current-instance"} for key in native_map}

        for template in builtin:
            intro = self.curated(template["introduction"], ("nameZh", "purposeZh", "suggestedScenariosZh", "purposeSource", "scenarioSource", "variantNoteZh"))
            evidence = []
            for p in raw_parts:
                if p["partType"] in template["partTypes"]:
                    evidence += self.evidence(p["modifierMappings"])
            intro["evidence"] = unique(evidence)
            intro["nativeSource"] = {"kind": "native-catalog-description", "templateId": template["id"]}
            collections["templates"].append({"id": template["id"], "title": intro["nameZh"] + " / " + template["name"], "name": template["name"], "summary": intro["purposeZh"], "category": template["category"], "subcategory": template["subcategory"], "source": "builtin", "creatable": template["creatable"], "creatableScope": "frozen-catalog", "partTypes": sorted(template["partTypes"]), "componentCounts": sorted(template["componentCounts"], key=lambda x: x["partType"]), "introduction": intro, "nativeDescription": template["nativeDescription"], "evidenceLevel": intro["purposeSource"]})

        fields = {}
        linked_sources = defaultdict(set)
        native_records = defaultdict(list)
        def add_field(part, path, source_id, join_status, native_key=None, join=None):
            source = source_map.get(source_id, {})
            native = native_map.get(native_key, {})
            identifier = part + "::" + path + "::" + (source_id or "native")
            if join and not native_key:
                identifier += "::modifier=" + join["modifierStateElement"]
            meaning = source.get("purposeZh") or native.get("meaningZh")
            if not meaning:
                raise ValueError("Missing field meaning: " + identifier)
            row = {"id": identifier, "title": part + " · " + path, "summary": self.prose(meaning), "partType": part, "normalizedXmlPath": path, "sourceFieldId": source_id, "joinStatus": join_status, "xmlValueType": source.get("xmlValueType", native.get("xmlValueTypes", [])), "enumIds": sorted(set(source.get("enumIds", []) + source.get("externalEnumIds", []))), "fieldRole": source.get("fieldRole", "native-boundary"), "toolWriteStatus": "not-certified", "pathStatus": "native-observed-path" if native_key else "source-candidate-not-certified-xpath", "evidenceLevel": "static-source" if source_id else "native-boundary-review"}
            if source_id:
                linked_sources[source_id].add(part)
            if native_key:
                row["nativeFieldKey"] = native_key
                row["native"] = native_data[native_key]
                row["choiceGroupId"] = native.get("nativeChoiceGroupKey")
                row["native"]["metadataReadOnly"] = bool(native_meta[native_key]) and all(m.get("readOnly") for m in native_meta[native_key])
                if native_key in boundary_map:
                    row["boundaryId"] = "native:" + native_key
                    row["toolWriteStatus"] = "unavailable-current-reader"
                native_records[native_key].append(identifier)
            if join:
                row.update(modifierStateElement=join["modifierStateElement"], declaringClass=join["declaringClass"])
                if join.get("bridgeEvidence"):
                    row["bridgeEvidence"] = self.evidence(join["bridgeEvidence"])
            if identifier in fields and fields[identifier] != row:
                raise ValueError("Ambiguous field identity: " + identifier)
            fields[identifier] = row

        for join in joins:
            sid = join["sourceFieldId"]
            if sid not in source_map:
                raise ValueError("Join outside Craft source: " + sid)
            if join["nativeFieldKeys"]:
                for key in join["nativeFieldKeys"]:
                    add_field(join["partType"], native_map[key]["normalizedXmlPath"], sid, join["joinStatus"], key, join)
            else:
                # A symbolic source context is intentionally not promoted into
                # an authoritative full Part XPath or a writable operation.
                context = join["resolvedXmlContext"].replace("[]", "[*]")
                modifier = join["modifierStateElement"]
                if join["joinStatus"] == "resource_definition_not_saved_state":
                    context = "ResourceDefinition/" + context
                elif context != "Part" and not context.startswith(("Part/", "Aircraft/")):
                    if modifier != "Part" and not context.startswith(modifier):
                        context = modifier + "[*]/" + context
                    context = "Part/" + "/".join(p if p.endswith("[*]") else p + "[*]" for p in context.split("/"))
                path = context + "/@" + join["xmlName"]
                add_field(join["partType"], path, sid, join["joinStatus"], join=join)
        for native in raw_native:
            if native["key"] not in native_records:
                add_field(native["partType"], native["normalizedXmlPath"], None, "native-without-current-source-reader", native["key"])
        collections["fields"] = list(fields.values())

        for source in raw_source:
            sid = source["fieldId"]
            semantic_notes = []
            for overlay in source.get("semanticOverlays", []):
                note = self.curated(overlay, ("purposeZh", "semanticStatus", "basis", "classification", "valueType", "serializedType", "notes", "validationLimitZh", "limitationZh", "nativeDescriptions", "nativeDescriptionLanguage"))
                note["evidence"] = self.evidence(overlay.get("evidence", []))
                semantic_notes.append(note)
            row = {"id": sid, "title": source["className"] + " · " + source.get("normalizedXmlContext", source["xmlContext"]) + "/@" + source["xmlName"], "summary": self.prose(source["purposeZh"]), "className": source["className"], "classQualifiedName": source["classQualifiedName"], "xmlName": source["xmlName"], "xmlContext": source.get("normalizedXmlContext", source["xmlContext"]), "xmlValueType": source["xmlValueType"], "xmlPathStatus": source["xmlPathStatus"], "fieldRole": source["fieldRole"], "useScope": source["useScope"], "classification": source["classification"], "semanticStatus": source["semanticStatus"], "partTypes": sorted(linked_sources[sid]), "enumIds": sorted(set(source.get("enumIds", []) + source.get("externalEnumIds", []))), "defaults": unique(self.source_default(d) for d in source["defaults"]), "semanticNotes": unique(semantic_notes), "evidenceLevel": "static-source", "toolWriteStatus": "not-certified"}
            row["csharpMemberTypes"] = unique({k: m[k] for k in ("name", "type", "binding") if k in m} for m in source.get("csharpMemberTypes", []))
            row["serializedType"] = self.curated(source.get("serializedType", {}), ("name", "status", "basis"))
            for key in ("readEvidence", "writeEvidence", "consumerEvidence", "metadataEvidence", "purposeEvidence"):
                row[key] = self.evidence(source.get(key, []))
            row["constraintLayers"] = {"nativeReadAndRuntime": self.evidence(source.get("constraintLayers", {}).get("nativeReadAndRuntime", [])), "nativeEditor": self.evidence(source.get("constraintLayers", {}).get("nativeEditor", [])), "interpretation": "引用可能为UI、运行消费者或读取限制，未统一视为XML读取校验。", "toolRestrictions": "not-inferred-from-native-metadata"}
            for key in ("persistenceCaveat", "contextCorrectionReason", "semanticClassification", "semanticInterpretationsDiffer", "serializedEnumTokens", "consumerMemberAliases"):
                if key in source:
                    row[key] = self.prose(source[key])
            collections["sourceFields"].append(row)

        for part in raw_parts:
            ptype = part["partType"]
            intro = self.curated(part["introduction"], ("nameZh", "purposeZh", "suggestedScenariosZh", "purposeSource", "scenarioSource", "variantNoteZh"))
            mappings = []
            for m in [part["basePartClass"]] + part["modifierMappings"]:
                mappings.append({**self.curated(m, ("modifierId", "stateElement", "className", "classQualifiedName")), "evidence": self.evidence(m)})
            pf = [f for f in fields.values() if f["partType"] == ptype]
            collections["parts"].append({"id": ptype, "title": intro["nameZh"] + " / " + ptype, "summary": intro["purposeZh"], "partType": ptype, "introduction": intro, "availability": "builtin" if ptype in builtin_types else "source-only", "creatable": None if ptype not in builtin_types else any(t["creatable"] for t in builtin if ptype in t["partTypes"]), "availabilityReason": "内置模板的组成类型。" if ptype in builtin_types else "当前没有可分发的内置模板；保留源码说明，不提供用户子装配值或创建承诺。", "templateIds": sorted(set(part["templateIds"]) & tids), "fieldIds": sorted(f["id"] for f in pf), "sourceFieldIds": sorted({f["sourceFieldId"] for f in pf if f["sourceFieldId"]}), "enumIds": sorted({e for f in pf for e in f["enumIds"]}), "modifierMappings": mappings, "unmappedStateElements": part["unmappedStateElements"], "evidenceLevel": "static-source-and-native-catalog"})

        local_enums = [e for e in self.read("xml-source/source-enums.json") if set(e.get("fieldIds", [])) & set(source_map)]
        for enum in local_enums + self.read("xml-source/external-enums.json"):
            external = "definitionOrigin" in enum
            values = []
            for value in enum["values"]:
                v = self.curated(value, ("name", "numericValue", "meaningZh", "semanticStatus"))
                v["evidence"] = self.evidence(value.get("consumerEvidence", []))
                if value.get("line"):
                    v["declarationLine"] = value["line"]
                values.append(v)
            field_ids = sorted(set(enum["fieldIds"]) & set(source_map))
            record = {"id": enum["qualifiedName"], "title": enum["name"], "summary": "逐值说明XML枚举的分支、条件和限制；数值读取规则与声明列表分别核对。", "values": values, "flags": enum.get("flags", False), "sourceFieldIds": field_ids, "partTypes": sorted({p for fid in field_ids for p in linked_sources[fid]}), "scope": "external-engine-contract" if external else "local-source-declaration", "evidence": self.evidence(enum), "serializationNotes": enum.get("serializationNotes", "外部引擎命名值；本地数值未核实。"), "evidenceLevel": "external-contract-with-static-consumer" if external else "static-source"}
            if external:
                record["documentationUrl"] = enum["documentationUrl"]
                record["fieldSpecificLimits"] = [{"sourceFieldId": sid, "summary": source_map[sid]["purposeZh"]} for sid in field_ids]
            collections["enums"].append(record)

        choices_for_group = defaultdict(list)
        for choice in raw_choices["fields"]:
            choices_for_group[choice["choiceGroupKey"]].append(choice)
        for group in raw_choices["groups"]:
            values = []
            for value in group["values"]:
                item = self.curated(value, ("value", "kind", "meanings", "meaningZh", "semanticStatus", "lookup", "limitZh"))
                item["evidence"] = self.evidence(value.get("evidence", []))
                values.append(item)
            bindings = [{"nativeFieldKey": b["nativeFieldKey"], "fieldIds": sorted(native_records[b["nativeFieldKey"]]), "allowedValues": b["allowedValues"], "valuesScope": "native-option-domain-not-player-value"} for b in choices_for_group[group["key"]]]
            collections["choices"].append({"id": group["key"], "title": group["xmlContexts"][0], "summary": "原生字段可选项的完整集合；资源ID仅说明选择关系，不推断具体几何或性能。", "sourceFieldIds": group["sourceFieldIds"], "enumIds": group["enumIds"], "values": values, "bindings": sorted(bindings, key=lambda b: b["nativeFieldKey"]), "partTypes": sorted({b["nativeFieldKey"].split("::", 1)[0] for b in bindings}), "evidenceLevel": "native-options-and-static-source"})

        for boundary in raw_boundaries:
            collections["boundaries"].append({"id": "native:" + boundary["key"], "title": boundary["partType"] + " · " + boundary["xmlPath"], "summary": boundary["purposeZh"], "status": boundary["status"], "nativeFieldKey": boundary["key"], "partTypes": [boundary["partType"]], "fieldIds": sorted(native_records[boundary["key"]]), "evidence": self.evidence(boundary), "toolWriteStatus": "unavailable-current-reader", "evidenceLevel": "static-source-review"})
        for modifier in scope["sourceOnlyFactoryModifiers"]:
            source_ids = sorted(f["fieldId"] for f in raw_source if f["classQualifiedName"] == modifier["classQualifiedName"])
            collections["boundaries"].append({"id": "factory:" + modifier["modifierId"], "title": modifier["className"], "summary": "工厂注册存在，但冻结目录未观察到该Modifier；不能由此认定废弃、隐藏或可创建。", "status": "source-only-factory-modifier", "modifierId": modifier["modifierId"], "sourceFieldIds": source_ids, "partTypes": [], "evidence": self.evidence(modifier), "evidenceLevel": "static-source"})
        for legacy in scope["legacyUpgradeMappings"]:
            collections["boundaries"].append({"id": "legacy:" + legacy["legacyPartType"], "title": legacy["legacyPartType"], "summary": "兼容迁移将旧类型映射为 " + legacy["replacementPartType"] + "；它不是当前内置模板。", "status": legacy["status"], "replacementPartType": legacy["replacementPartType"], "partTypes": [legacy["replacementPartType"]], "evidence": self.evidence(legacy), "evidenceLevel": "static-source"})
        dynamic = self.read("xml-source/dynamic-xml-sites.json")
        for index, site in enumerate(dynamic):
            refs = self.evidence(site)
            collections["boundaries"].append({"id": "dynamic:" + str(index).zfill(3), "title": site.get("classQualifiedName", site.get("method", "XML helper")) + " · " + str(site["line"]), "summary": site.get("reviewMeaningZh", "通用库XML帮助器或动态键站点；不等同于已定位的具体部件属性，需按调用者与值域核验。"), "status": site["resolutionStatus"], "xmlContext": site.get("xmlContext"), "resolvedConcreteAttributeNames": site.get("resolvedConcreteAttributeNames", []), "evidence": refs, "evidenceLevel": "static-source-review"})
        for key in ("unloadedMods", "resourceDefinitions"):
            boundary = scope[key]
            collections["boundaries"].append({"id": "scope:" + key, "title": "未加载模组" if key == "unloadedMods" else "部件资源定义", "summary": boundary["reasonZh"], "status": "unavailable", "evidence": self.evidence(boundary), "evidenceLevel": "scope-boundary"})
        for name, meaning in scope["universalStates"].items():
            collections["boundaries"].append({"id": "universal:" + name, "title": name, "summary": "通用相机观察点状态可被任意部件加载；不是独立目录部件类型。", "status": "universal-state", "nativeMeaning": meaning, "evidenceLevel": "static-source"})
        for site in self.read("xml-source/coverage.json")["syntaxErrors"]:
            path = self.relative_source(site["path"])
            collections["boundaries"].append({"id": "syntax:" + path, "title": path, "summary": "当前反编译来源含语法异常；元数据来源与无法完成编译语义绑定的范围须分别核验。", "status": "decompilation-syntax-error", "errorCount": len(site["syntaxErrors"]), "evidence": self.evidence(site), "evidenceLevel": "parser-diagnostic"})
        collections["sources"] = list(self.sources.values())
        reading_coverage = enrich_reading_and_examples(collections)
        for name, rows in collections.items():
            rows.sort(key=lambda r: r["id"])
            if len({r["id"] for r in rows}) != len(rows):
                raise ValueError("Duplicate IDs in " + name)
            if any(not isinstance(r.get(k), str) or not r[k] for r in rows for k in ("id", "title", "summary")):
                raise ValueError("Missing common record fields in " + name)

        manifest = self.read("baseline/game-decompilation-manifest.json")
        source = {"gameVersion": manifest["gameVersion"], "steamBuildId": str(manifest["steamBuildId"]), "xmlVersion": manifest["craftXmlVersion"], "gameAssemblySha256": next(a["sha256"].lower() for a in manifest["assemblyProvenance"] if a["name"] == "Game"), "sourceInventorySha256": raw_choices["sourceInventorySha256"], "catalogSnapshotSha256": builtin[0]["snapshotRef"]["sha256"], "generatorVersion": VERSION, "inputSha256": self.input_hashes}
        coverage = {"catalog": {"snapshotTemplates": len(raw_templates), "distributedBuiltinTemplates": len(builtin), "excludedPrivateSubassemblies": len(raw_templates)-len(builtin), "snapshotPartTypes": len(raw_parts), "builtinPartTypes": len(builtin_types), "sourceOnlyPartTypes": len(raw_parts)-len(builtin_types), "builtinTemplateMemberInstances": builtin_members}, "nativeFields": {"denominator": len(raw_native), "represented": len(native_records), "withBuiltinMetadataOrDefaults": sum(bool(native_meta[k] or native_defaults[k]) for k in native_map), "withoutBuiltinValues": sum(not (native_meta[k] or native_defaults[k]) for k in native_map), "unjoinedBoundaries": len(raw_boundaries)}, "sourceFields": {"denominator": len(raw_source), "represented": len(collections["sourceFields"]), "withPartAssociation": sum(bool(f["partTypes"]) for f in collections["sourceFields"]), "withoutPartAssociationIds": [f["id"] for f in collections["sourceFields"] if not f["partTypes"]], "byUseScope": dict(sorted(Counter(f["useScope"] for f in raw_source).items())), "byFieldRole": dict(sorted(Counter(f["fieldRole"] for f in raw_source).items())), "humanSemanticRecords": len(raw_source), "runtimeValidated": 0}, "localEnums": {"denominatorTypes": len(local_enums), "representedTypes": len(local_enums), "denominatorValues": sum(len(e["values"]) for e in local_enums), "representedValues": sum(len(e["values"]) for e in local_enums)}, "externalEnums": {"types": 1, "namedValues": 3, "numericValuesVerified": False}, "nativeChoices": {"fieldBindings": len(raw_choices["fields"]), "groups": len(raw_choices["groups"]), "values": sum(len(g["values"]) for g in raw_choices["groups"]), "resourceIds": sum(v["kind"] == "resource_id" for g in raw_choices["groups"] for v in g["values"])}, "joins": dict(sorted(Counter(f["joinStatus"] for f in fields.values()).items())), "dynamicSites": {"denominator": len(dynamic), "represented": len(dynamic), "byStatus": dict(sorted(Counter(s["resolutionStatus"] for s in dynamic).items()))}, "collectionCounts": {name: len(rows) for name, rows in collections.items()}}
        limitations = ["全量限于冻结游戏0.7.9.104/build25840865/XML26：178模板仅发布160内置；18用户子装配名字、原文及状态不分发。", "122内置组成类型与2个无内置模板的源码类型分别计数；全局历史、隐藏类型及未加载Mod没有可闭合分母。", "1318是Craft源码字段分母，包含资源定义、共享材料/变量/结构及兼容迁移；不等于1318个可编辑部件属性。", "原生默认来自内置模板；源码默认分为字面量、符号依赖和需源求值。二者不是当前模型实时值。", "相关类候选路径和资源definition不构成合法State写入路径；metadata readOnly=false不保证工具可写。", "静态消费者按语法/名称定位，无完整编译语义绑定；说明保留人工策展结论及证据等级，不宣称属性写入、持久化或飞行动态已验收。", "资源ID的选择用途已说明，具体网格、尺寸、性能及未公开资源原文仍为unavailable。", "166动态站点保留已展开、共享统计、透传、非XML反射和通用库帮助器等状态；未伪装为部件属性。", "4个未确认运行消费者字段、10个派生缓存及83个兼容/迁移字段保留原角色；零运行验收不计语义测试通过。", "当前反编译OverloadPanelScript存在1处语法异常；提取器保留该缺口，原生元数据只能覆盖实际观测范围。"]
        defaults = [d for f in collections["sourceFields"] for d in f["defaults"]]
        coverage["sourceDefaults"] = {"denominator": len(defaults), "byStatus": dict(sorted(Counter(d["status"] for d in defaults).items())), "meaning": "按字段及默认来源去重；符号或需求值默认不冒充已求值模板值。"}
        coverage["introductionEvidence"] = dict(sorted(Counter(t["introduction"]["purposeSource"] for t in builtin).items()))
        coverage.update(reading_coverage)
        coverage["unknowns"] = {"unconfirmedRuntimeConsumerFields": [f["id"] for f in collections["sourceFields"] if f["fieldRole"] == "persisted-without-confirmed-runtime-consumer"], "nonLiteralDefaultRecords": sum(d["status"] != "literal" for d in defaults), "unknownResourceGeometryValues": coverage["nativeChoices"]["resourceIds"], "unloadedModTypeDenominator": None, "historicalOrHiddenTypeDenominator": None}
        result = {"schemaVersion": SCHEMA, "source": source, "collections": collections, "coverage": coverage, "limitations": limitations}
        validate(result)
        return result


def validate(data):
    c = data["collections"]
    ids = {name: {r["id"] for r in rows} for name, rows in c.items()}
    for name, rows in c.items():
        assert len(rows) == len(ids[name]), name
        for r in rows:
            assert all(isinstance(r[k], str) and r[k] for k in ("id", "title", "summary")), (name, r.get("id"))
    for part in c["parts"]:
        assert set(part["fieldIds"]) <= ids["fields"]
        assert set(part["templateIds"]) <= ids["templates"]
    for field in c["fields"]:
        assert field["partType"] in ids["parts"]
        assert field["sourceFieldId"] is None or field["sourceFieldId"] in ids["sourceFields"]
        assert set(field["enumIds"]) <= ids["enums"]
        assert field["toolWriteStatus"] in {"not-certified", "unavailable-current-reader"}
        for default in field.get("native", {}).get("defaultsByTemplate", []):
            assert default["templateId"] in ids["templates"]
    for choice in c["choices"]:
        by_value = {v["value"] for v in choice["values"]}
        for binding in choice["bindings"]:
            assert set(binding["allowedValues"]) <= by_value
            assert set(binding["fieldIds"]) <= ids["fields"]
    def walk(node):
        if isinstance(node, dict):
            assert not (set(node) & {"defaultState", "observedValues", "instanceToken", "code", "statement", "expression", "accessors"}), set(node) & CODE_KEYS
            if "sourceId" in node:
                assert node["sourceId"] in ids["sources"]
            for value in node.values(): walk(value)
        elif isinstance(node, list):
            for value in node: walk(value)
        elif isinstance(node, str):
            assert not re.search(r"(?<![A-Za-z])[A-Za-z]:[\\/]", node), "Absolute path: " + node[:180]
            assert "```" not in node, "Code fence"
    walk(data)


def encode(data):
    return json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--check", action="store_true", help="Compare deterministic bytes without changing output")
    args = parser.parse_args()
    data = Builder(args.inventory).build()
    content = encode(data)
    if args.check:
        if args.output.read_text(encoding="utf-8") != content:
            raise SystemExit("Generated part knowledge is stale")
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(content, encoding="utf-8", newline="\n")
    print(json.dumps({"status": "verified" if args.check else "written", "bytes": len(content.encode("utf-8")), "counts": data["coverage"]["collectionCounts"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
