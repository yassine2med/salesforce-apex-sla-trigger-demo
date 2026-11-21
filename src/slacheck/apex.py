"""Static checks for Apex source files. Heuristics, not a compiler: nothing is run or deployed."""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

SOQL = re.compile(r"\[\s*SELECT\b", re.I)
DML = re.compile(r"(?<![\w.])(insert|update|delete|upsert|undelete|merge)\s+[A-Za-z_(]|\bDatabase\s*\.\s*(insert|update|delete|upsert|undelete|merge|query)\s*\(", re.I)
LOOP = re.compile(r"\b(for|while)\s*\(", re.I)
SHARING = re.compile(r"\b(with|without|inherited)\s+sharing\b", re.I)
CUSTOM_NAME = re.compile(r"\b([A-Za-z][A-Za-z0-9_]*__c)\b")
SLA_MAP = re.compile(r"SLA_HOURS\s*=\s*new\s+Map<\s*String\s*,\s*Integer\s*>\s*\{(?P<body>.*?)\}\s*;", re.S)
MAP_ITEM = re.compile(r"'([^']+)'\s*=>\s*(\d+)")


@dataclass(frozen=True)
class Finding:
    file: str
    line: int
    rule: str
    message: str

    def __str__(self) -> str:
        return f"{self.file}:{self.line}: [{self.rule}] {self.message}"


def strip_comments(src: str) -> str:
    """Remove // and /* */ comments but keep line breaks, so line numbers stay right."""
    out, i, n = [], 0, len(src)
    while i < n:
        c = src[i]
        if c == "'":
            j = i + 1
            while j < n and src[j] != "'":
                j += 2 if src[j] == "\\" else 1
            out.append(src[i:j + 1])
            i = j + 1
        elif src.startswith("//", i):
            while i < n and src[i] != "\n":
                i += 1
        elif src.startswith("/*", i):
            end = src.find("*/", i + 2)
            end = n if end < 0 else end + 2
            out.append("".join("\n" if ch == "\n" else " " for ch in src[i:end]))
            i = end
        else:
            out.append(c)
            i += 1
    return "".join(out)


def blank_strings(src: str) -> str:
    """Replace the inside of string literals with spaces so keywords in text are ignored."""
    return re.sub(r"'(?:\\.|[^'\\])*'", lambda m: "'" + " " * (len(m.group(0)) - 2) + "'", src)


def _match(code: str, start: int, open_ch: str, close_ch: str) -> int:
    depth = 0
    for i in range(start, len(code)):
        if code[i] == open_ch:
            depth += 1
        elif code[i] == close_ch:
            depth -= 1
            if depth == 0:
                return i
    return len(code) - 1


def loop_bodies(code: str) -> list[tuple[int, int]]:
    """Return (start, end) offsets of every for or while loop body."""
    spans = []
    for m in LOOP.finditer(code):
        close = _match(code, m.end() - 1, "(", ")")
        j = close + 1
        while j < len(code) and code[j].isspace():
            j += 1
        if j < len(code) and code[j] == "{":
            spans.append((j, _match(code, j, "{", "}")))
        else:
            semi = code.find(";", j)
            spans.append((j, len(code) if semi < 0 else semi))
    return spans


def _line(code: str, offset: int) -> int:
    return code.count("\n", 0, offset) + 1


def looks_like_id(text: str) -> bool:
    return (len(text) in (15, 18) and text.isalnum() and sum(ch.isdigit() for ch in text) >= 3
            and any(ch.isalpha() for ch in text))


def lint_source(name: str, src: str, is_trigger: bool) -> list[Finding]:
    """Lint one class or trigger file."""
    findings: list[Finding] = []
    text = strip_comments(src)
    code = blank_strings(text)
    is_test = bool(re.search(r"@\s*isTest\b", code, re.I)) and not is_trigger

    for start, end in loop_bodies(code):
        body = code[start:end + 1]
        for m in SOQL.finditer(body):
            findings.append(Finding(name, _line(code, start + m.start()), "soql-in-loop", "SOQL query inside a loop"))
        for m in DML.finditer(body):
            findings.append(Finding(name, _line(code, start + m.start()), "dml-in-loop", "DML statement inside a loop"))
    for m in re.finditer(r"'([A-Za-z0-9]+)'", text):
        if looks_like_id(m.group(1)):
            findings.append(Finding(name, _line(text, m.start()), "hardcoded-id", f"possible hard coded record Id '{m.group(1)}'"))

    if is_trigger:
        header = code[: code.find("{")] if "{" in code else code
        if not re.search(r"\bon\s+\w+\s*\(", header, re.I):
            findings.append(Finding(name, 1, "trigger-header", "trigger declaration not found"))
        body = code[code.find("{"):] if "{" in code else ""
        if LOOP.search(body) or SOQL.search(body) or DML.search(body):
            findings.append(Finding(name, 1, "logic-in-trigger", "trigger body has loops, queries or DML; move them to a handler class"))
        if "Trigger.new" not in body and "Trigger.old" not in body:
            findings.append(Finding(name, 1, "trigger-context", "trigger never reads Trigger.new or Trigger.old"))
    elif is_test:
        methods = len(re.findall(r"@\s*isTest\b[^{;]*?\bstatic\s+void\b", code, re.I)) or len(re.findall(r"\btestMethod\b", code, re.I))
        asserts = len(re.findall(r"\bSystem\s*\.\s*assert\w*\s*\(|\bAssert\s*\.\s*\w+\s*\(", code, re.I))
        if methods == 0:
            findings.append(Finding(name, 1, "test-methods", "test class has no test methods"))
        elif asserts < methods:
            findings.append(Finding(name, 1, "test-asserts", f"{methods} test methods but only {asserts} assertion(s)"))
        if re.search(r"SeeAllData\s*=\s*true", code, re.I):
            findings.append(Finding(name, 1, "see-all-data", "SeeAllData=true makes tests depend on org data"))
        if not re.search(r"\b200\b", code):
            findings.append(Finding(name, 1, "no-bulk-test", "no test covers a bulk of 200 records"))
    else:
        if not SHARING.search(code):
            findings.append(Finding(name, 1, "sharing", "class has no with sharing, without sharing or inherited sharing keyword"))
    return findings


def read_meta(path: Path) -> tuple[str | None, str | None]:
    """Return (apiVersion, status) from a -meta.xml file, or (None, None) if unreadable."""
    try:
        root = ET.parse(path).getroot()
    except (ET.ParseError, OSError):
        return None, None
    values = {c.tag.split("}")[-1]: (c.text or "").strip() for c in root}
    return values.get("apiVersion"), values.get("status")


def parse_sla_table(src: str) -> dict[str, int]:
    """Read the SLA_HOURS map literal out of Apex source."""
    m = SLA_MAP.search(strip_comments(src))
    if not m:
        return {}
    return {k: int(v) for k, v in MAP_ITEM.findall(m.group("body"))}


def custom_names_in_objects(root: Path) -> set[str]:
    """Object and field API names defined under force-app/**/objects."""
    names: set[str] = set()
    for obj in root.glob("force-app/**/objects/*"):
        if obj.is_dir():
            names.add(obj.name)
            names.update(f.name.split(".")[0] for f in (obj / "fields").glob("*.field-meta.xml"))
    return names


def lint_project(root: Path) -> list[Finding]:
    """Lint every class and trigger below force-app and cross-check their files."""
    findings: list[Finding] = []
    sources = sorted(list(root.glob("force-app/**/classes/*.cls")) + list(root.glob("force-app/**/triggers/*.trigger")))
    defined = custom_names_in_objects(root)
    classes = {p.stem for p in sources if p.suffix == ".cls"}
    tested_for: set[str] = set()
    for path in sources:
        rel = path.relative_to(root).as_posix()
        src = path.read_text(encoding="utf-8")
        is_trigger = path.suffix == ".trigger"
        findings += lint_source(rel, src, is_trigger)
        meta = Path(str(path) + "-meta.xml")
        if not meta.exists():
            findings.append(Finding(rel, 1, "meta-file", f"missing {meta.name}"))
        else:
            api, status = read_meta(meta)
            if not api or not re.fullmatch(r"\d+\.0", api):
                findings.append(Finding(meta.relative_to(root).as_posix(), 1, "api-version", "apiVersion missing or not like 61.0"))
            if status != "Active":
                findings.append(Finding(meta.relative_to(root).as_posix(), 1, "status", f"status is '{status}', expected Active"))
        text = strip_comments(src)
        if is_trigger:
            m = re.match(r"\s*trigger\s+(\w+)\s+on\s+(\w+)", text, re.I)
            if m and m.group(1) != path.stem:
                findings.append(Finding(rel, 1, "trigger-name", f"trigger is named {m.group(1)} but the file is {path.stem}"))
            if m and m.group(2).endswith("__c") and m.group(2) not in defined:
                findings.append(Finding(rel, 1, "unknown-object", f"object {m.group(2)} is not defined in this project"))
        else:
            m = re.search(r"\b(?:class)\s+(\w+)", blank_strings(text), re.I)
            if m and m.group(1) != path.stem:
                findings.append(Finding(rel, 1, "class-name", f"class is named {m.group(1)} but the file is {path.stem}"))
            if re.search(r"@\s*isTest\b", text, re.I):
                for ref in classes:
                    if re.search(rf"\b{ref}\s*\.", text) and ref != path.stem:
                        tested_for.add(ref)
        for m in CUSTOM_NAME.finditer(blank_strings(text)):
            if m.group(1) not in defined:
                findings.append(Finding(rel, _line(text, m.start()), "unknown-field", f"{m.group(1)} is not defined in this project"))
    for path in sources:
        if path.suffix == ".cls" and not re.search(r"@\s*isTest\b", strip_comments(path.read_text(encoding="utf-8")), re.I):
            if path.stem not in tested_for:
                findings.append(Finding(path.relative_to(root).as_posix(), 1, "no-test-class", "no test class calls this class"))
    findings.sort(key=lambda f: (f.file, f.line, f.rule))
    seen, unique = set(), []
    for f in findings:
        if (f.file, f.line, f.rule, f.message) not in seen:
            seen.add((f.file, f.line, f.rule, f.message))
            unique.append(f)
    return unique
