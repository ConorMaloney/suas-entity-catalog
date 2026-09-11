#!/usr/bin/env python3
"""
run_validation.py - test runner for a FROZEN validation suite.

Targets suite format v3.0.0, which is DISPATCHABLE: every test carries
target / applies_to / checks drawn from the closed vocabularies in the
suite's `runner_contract`. This runner dispatches on those keys.

It NEVER parses `assertion_prose`. Per the suite's own format_note that
field is documentation for a human implementer, not machine input.

Per `runner_contract.unknown_verb_policy`, an unrecognised check verb,
applies_to key, or target is an ERROR that aborts the run. It is never
skipped: a skipped structural check is indistinguishable from a passing
one in a green report.

Inputs (all must exist at the paths given; the runner never searches the
filesystem for a moved file - it stops and says so):

  record  catalog/entities/UAS-QUAD-SKYDIO-X2D.json
  schema  catalog/schema/entity_schema_3.0.json
  suite   catalog/tests/validation_suite_UAS-QUAD-SKYDIO-X2D.yaml

Output:

  catalog/reports/validation_report.json

derived_sets and predicates are resolved from their declarative specs in
the suite at load time. Nothing is hardcoded except the dispatch logic
itself.

Runtime independence: exactly three files are opened and the wall clock is
consulted once. No network, no subprocess.
"""

import argparse
import datetime as _dt
import json
import os
import re
import sys
from collections import OrderedDict

import yaml

REPO_ROOT = os.path.dirname(os.path.abspath(__file__))

DEFAULT_RECORD = os.path.join(REPO_ROOT, "catalog", "entities", "UAS-QUAD-SKYDIO-X2D.json")
DEFAULT_SCHEMA = os.path.join(REPO_ROOT, "catalog", "schema", "entity_schema_3.0.json")
DEFAULT_SUITE = os.path.join(REPO_ROOT, "catalog", "tests",
                             "validation_suite_UAS-QUAD-SKYDIO-X2D.yaml")
# NOT catalog/entities/ - that directory's contract is one entity record
# per file, and catalog.list_entity_ids() globs *.json there. A report
# written into it is loaded as an entity, fails schema_version, and turns
# test_catalog.py check 2 red.
DEFAULT_REPORT = os.path.join(REPO_ROOT, "catalog", "reports", "validation_report.json")

KNOWN_CATEGORIES = (
    "status_coherence", "key_coverage", "confidence_class",
    "source_quote_structure", "cross_field", "top_level_keys",
    "value_type", "readiness_tier",
)

VALID_OUTCOMES = ("pass", "warn", "fail", "info", "gap", "skipped")
SEVERITY_TO_OUTCOME = {"fail": "fail", "warn": "warn", "info": "info", "gap": "gap"}



class SuiteContractError(Exception):
    """The suite used something outside its own declared contract. Per
    unknown_verb_policy this is a SUITE defect, and the run aborts loudly
    rather than reporting a record finding."""


# ==========================================================================
# Small helpers
# ==========================================================================

def is_mapping(x):
    return isinstance(x, dict)


def nonempty_str(x):
    return isinstance(x, str) and x.strip() != ""


ABSENT = object()


def field_of(block, name):
    return block.get(name, ABSENT) if is_mapping(block) else ABSENT


def json_type_of(v):
    if isinstance(v, bool):
        return "boolean"
    if isinstance(v, int):
        return "integer"
    if isinstance(v, float):
        return "float"
    if isinstance(v, str):
        return "string"
    if isinstance(v, dict):
        return "object"
    if isinstance(v, list):
        return "array"
    if v is None:
        return "null"
    return type(v).__name__


def parse_iso_date(value):
    """ISO-8601 date or datetime -> naive-UTC datetime, else None.
    Dates are compared with datetime arithmetic, never as strings."""
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        dt = _dt.datetime.fromisoformat(text)
    except ValueError:
        try:
            dt = _dt.datetime.strptime(text, "%Y-%m-%d")
        except ValueError:
            return None
    if dt.tzinfo is not None:
        dt = dt.astimezone(_dt.timezone.utc).replace(tzinfo=None)
    return dt


def path_exists(record, dotted):
    section, _, leaf = dotted.partition(".")
    blk = record.get(section)
    return is_mapping(blk) and leaf in blk


def path_get(record, dotted):
    section, _, leaf = dotted.partition(".")
    blk = record.get(section)
    return blk.get(leaf) if is_mapping(blk) else None


def walk_key(node, key, trail=""):
    if isinstance(node, dict):
        for k, v in node.items():
            here = trail + "." + k if trail else k
            if k == key:
                yield here, v
            for r in walk_key(v, key, here):
                yield r
    elif isinstance(node, list):
        for i, v in enumerate(node):
            for r in walk_key(v, key, "%s[%d]" % (trail, i)):
                yield r


# ==========================================================================
# Loading
# ==========================================================================

def load_record(path):
    """Returns (record, duplicated_top_level_keys). json.load collapses
    duplicate keys silently, so the text is parsed twice. TL-007 needs it."""
    with open(path, "r", encoding="utf-8") as fh:
        text = fh.read()
    record = json.loads(text)
    pairs = json.loads(text, object_pairs_hook=lambda p: p)
    seen = {}
    for k, _v in pairs:
        seen[k] = seen.get(k, 0) + 1
    return record, sorted(k for k, n in seen.items() if n > 1)


def load_json(path):
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def load_suite(path):
    with open(path, "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh.read())


# ==========================================================================
# derived_sets - resolved from their declarative specs in the suite
# ==========================================================================

def resolve_derived_sets(spec, schema):
    """Evaluate the suite's derived_sets block.

    Grammar actually used by the suite:
      {from: schema, select: parameters, where: {...}, pluck: <attr>}
      {from: schema, select: parameters, map: [<key attr>, <value attr>]}
      {from: schema, keys_of: <key>, exclude_prefix: <str>}
      {from: schema, value_of: <key>}
      {from: derived, value_of: <NAME>, minus: [...]}
      {literal: [...]}
    """
    out = OrderedDict()
    # Two passes: 'derived' sources may reference earlier names.
    pending = list(spec.items())
    for _round in range(len(pending) + 1):
        progressed = False
        still = []
        for name, d in pending:
            if not is_mapping(d):
                raise SuiteContractError("derived_sets.%s is not a mapping" % name)

            if "literal" in d:
                out[name] = list(d["literal"])
                progressed = True
                continue

            src = d.get("from")
            if src == "schema":
                if "keys_of" in d:
                    keys = list((schema.get(d["keys_of"]) or {}).keys())
                    pre = d.get("exclude_prefix")
                    if pre:
                        keys = [k for k in keys if not k.startswith(pre)]
                    out[name] = keys
                elif "value_of" in d:
                    out[name] = list(schema.get(d["value_of"]) or [])
                elif d.get("select") == "parameters":
                    rows = schema.get("parameters", [])
                    where = d.get("where") or {}
                    for attr, want in where.items():
                        rows = [r for r in rows if r.get(attr) == want]
                    if "pluck" in d:
                        out[name] = [r.get(d["pluck"]) for r in rows]
                    elif "map" in d:
                        kf, vf = d["map"]
                        out[name] = OrderedDict((r.get(kf), r.get(vf)) for r in rows)
                    else:
                        raise SuiteContractError(
                            "derived_sets.%s selects parameters with neither pluck nor map"
                            % name)
                else:
                    raise SuiteContractError(
                        "derived_sets.%s: unrecognised schema selector %s"
                        % (name, sorted(d.keys())))
                progressed = True
                continue

            if src == "derived":
                base = d.get("value_of")
                if base not in out:
                    still.append((name, d))
                    continue
                vals = list(out[base])
                for m in d.get("minus") or []:
                    vals = [v for v in vals if v != m]
                out[name] = vals
                progressed = True
                continue

            raise SuiteContractError(
                "derived_sets.%s: unrecognised 'from' value %r" % (name, src))

        pending = still
        if not pending:
            break
        if not progressed:
            raise SuiteContractError(
                "derived_sets has unresolvable references: %s"
                % ", ".join(n for n, _ in pending))
    return out


# ==========================================================================
# Predicates - resolved from their declarative specs in the suite
# ==========================================================================

def eval_field_condition(cond, block, sets):
    """One clause inside a predicate's all_of / any_of.

    Clause vocabulary used by the suite: field + one or more of
    in / or_absent / equals / not_null / is_null / absent / in_enum /
    non_empty_string / json_type.
    """
    name = cond.get("field")
    if name is None:
        raise SuiteContractError("predicate clause has no 'field': %r" % (cond,))
    val = field_of(block, name)
    absent = val is ABSENT

    if cond.get("absent") is True:
        return absent

    if "in" in cond:
        if absent:
            return bool(cond.get("or_absent"))
        if val not in cond["in"]:
            return False

    if "equals" in cond:
        if absent:
            return False
        if cond["equals"] is True:
            # boolean-true clauses must not accept 1
            if not (isinstance(val, bool) and val is True):
                return False
        elif val != cond["equals"]:
            return False

    if cond.get("not_null") is True:
        if absent or val is None:
            return False

    if cond.get("is_null") is True:
        if absent or val is not None:
            return False

    if "in_enum" in cond:
        if absent:
            return False
        vocab = sets.get(cond["in_enum"])
        if vocab is None:
            raise SuiteContractError("unknown enum_ref %r" % cond["in_enum"])
        if val not in vocab:
            return False

    if cond.get("non_empty_string") is True:
        if absent or not nonempty_str(val):
            return False

    if "json_type" in cond:
        if absent or json_type_of(val) != cond["json_type"]:
            return False

    return True


def eval_predicate(pred, block, sets):
    if not is_mapping(pred):
        raise SuiteContractError("predicate is not a mapping: %r" % (pred,))
    if "all_of" in pred:
        return all(eval_field_condition(c, block, sets) for c in pred["all_of"])
    if "any_of" in pred:
        return any(eval_field_condition(c, block, sets) for c in pred["any_of"])
    raise SuiteContractError("predicate has neither all_of nor any_of: %r"
                             % sorted(pred.keys()))


# ==========================================================================
# Findings and results
# ==========================================================================

class Finding(object):
    def __init__(self, test_id, severity, message, subject=None, code=None,
                 reason_code=None):
        self.test_id = test_id
        self.severity = severity
        self.message = message
        self.subject = subject
        self.code = code
        self.reason_code = reason_code

    def to_dict(self):
        d = OrderedDict()
        d["test_id"] = self.test_id
        d["severity"] = self.severity
        if self.code:
            d["code"] = self.code
        if self.subject:
            d["subject"] = self.subject
        d["message"] = self.message
        return d


class Subject(object):
    """One thing a test's checks are applied to."""

    def __init__(self, kind, name, block=None, container=None):
        self.kind = kind        # "parameter" | "top_level_key" | "record_root" | "recursive_key"
        self.name = name        # dotted path, key name, or location
        self.block = block      # the mapping a field-check reads from
        self.container = container


# ==========================================================================
# Runner
# ==========================================================================

class Runner(object):
    ALLOWED_TARGETS = ("record", "report", "suite", "tooling", "human")

    def __init__(self, record, record_path, schema, schema_path,
                 suite, suite_path, dup_top_level_keys, validation_time):
        self.record = record
        self.record_path = record_path
        self.schema = schema
        self.schema_path = schema_path
        self.suite = suite
        self.suite_path = suite_path
        self.dup_top_level_keys = dup_top_level_keys
        self.validation_time = validation_time

        self.contract = suite.get("runner_contract") or {}
        self.scope = suite.get("entity_scope") or {}
        self.sets = resolve_derived_sets(suite.get("derived_sets") or {}, schema)
        self.predicates = suite.get("predicates") or {}

        self.tests_by_id = OrderedDict((t["id"], t) for t in suite.get("tests", []))
        self.results = OrderedDict()
        self.findings = []
        self.schema_conformance = None
        self.coverage_by_class = None
        self.tier_computation = None
        self.unevaluated_tier_clauses = []
        self.preflight = None
        self.opened_files = []

        self.requirement_of = OrderedDict(
            (p["path"], p.get("requirement")) for p in schema.get("parameters", []))
        self.value_type_of = self.sets.get("VALUE_TYPE_OF") or {}
        self.unit_of = self.sets.get("UNIT_OF") or {}

        self._verbs = self._build_verb_table()
        self._validate_contract()

    # -- contract enforcement --------------------------------------------

    def _validate_contract(self):
        """Fail loudly on anything outside the suite's own declared
        vocabularies, before a single test runs."""
        declared_verbs = set(self.contract.get("check_verbs") or [])
        allowed_applies = set(self.contract.get("applies_to_keys") or [])
        allowed_targets = set(self.contract.get("target") or self.ALLOWED_TARGETS)
        problems = []

        for tid, t in self.tests_by_id.items():
            tgt = t.get("target")
            if tgt not in allowed_targets:
                problems.append("%s: target %r is not in runner_contract.target" % (tid, tgt))
            if tgt not in self.ALLOWED_TARGETS:
                problems.append("%s: target %r has no handler in this runner" % (tid, tgt))
            for k in (t.get("applies_to") or {}):
                if k not in allowed_applies:
                    problems.append("%s: applies_to key %r is not in "
                                    "runner_contract.applies_to_keys" % (tid, k))
                if k not in _APPLIES_TO_HANDLED:
                    problems.append("%s: applies_to key %r has no handler in this runner"
                                    % (tid, k))
            for c in (t.get("checks") or []):
                verb = c.get("check")
                if verb not in declared_verbs:
                    problems.append("%s: check verb %r is not in "
                                    "runner_contract.check_verbs" % (tid, verb))
                if verb not in self._verbs:
                    problems.append("%s: check verb %r has no implementation in this "
                                    "runner" % (tid, verb))
            if t.get("category") not in KNOWN_CATEGORIES:
                problems.append("%s: category %r is outside this runner's authorised scope"
                                % (tid, t.get("category")))

        if problems:
            raise SuiteContractError(
                "runner_contract violations (unknown_verb_policy = ERROR, so the run "
                "aborts rather than skipping):\n  - " + "\n  - ".join(problems))

    # -- emit -------------------------------------------------------------

    def emit(self, test_id, severity, message, subject=None, code=None, reason_code=None):
        self.findings.append(Finding(test_id, severity, message, subject, code, reason_code))

    def findings_for(self, test_id):
        return [f for f in self.findings if f.test_id == test_id]

    def severity_for(self, test):
        """severity_map overrides severity, keyed on readiness_declared."""
        for entry in (test.get("severity_map") or []):
            if self.tier() in (entry.get("when_readiness_in") or []):
                return entry.get("severity")
        return test.get("severity")

    def record_result(self, test_id, outcome, detail, extra=None):
        t = self.tests_by_id[test_id]
        assert outcome in VALID_OUTCOMES, outcome
        r = OrderedDict()
        r["id"] = test_id
        r["category"] = t.get("category")
        r["target"] = t.get("target")
        r["severity"] = t.get("severity")
        r["effective_severity"] = self.severity_for(t)
        r["automatable"] = t.get("automatable")
        r["outcome"] = outcome
        r["detail"] = detail
        r["description"] = t.get("description")
        r["rule_reference"] = t.get("rule_reference")
        r["tolerance"] = t.get("tolerance")
        if t.get("human_review") is not None:
            r["human_review"] = t.get("human_review")
        fs = [f.to_dict() for f in self.findings_for(test_id)]
        if fs:
            r["findings"] = fs
        if extra:
            r.update(extra)
        self.results[test_id] = r
        return r

    def tier(self):
        return self.record.get("readiness_declared")

    def fails_in(self, categories):
        cats = set(categories)
        return [tid for tid, r in self.results.items()
                if r["category"] in cats and r["outcome"] == "fail"]

    # -- subject construction from applies_to ------------------------------

    def declared_paths(self):
        return list(self.sets.get("ALL_DECLARED_PATHS") or [])

    def build_subjects(self, test):
        """Turn applies_to into the list of Subjects the checks run over."""
        a = test.get("applies_to") or {}
        scope = a.get("scope")

        if scope is None and not a:
            return [Subject("record_root", "<record>", self.record, self.record)]

        if scope == "record_root":
            keys = None
            if "keys_ref" in a:
                keys = list(self.sets.get(a["keys_ref"]) or [])
            elif "keys" in a:
                keys = list(a["keys"])
            if keys is None:
                return [Subject("record_root", "<record>", self.record, self.record)]
            if a.get("only_present_keys"):
                keys = [k for k in keys if k in self.record]
            return [Subject("top_level_key", k, self.record, self.record) for k in keys]

        if scope == "recursive_key":
            key = a.get("key_name")
            if key is None:
                raise SuiteContractError("%s: recursive_key scope without key_name" % test["id"])
            subs = []
            for where, val in walk_key(self.record, key):
                subs.append(Subject("recursive_key", where, {key: val}, None))
            return subs

        if scope == "parameters":
            paths = None
            if "paths_ref" in a:
                paths = list(self.sets.get(a["paths_ref"]) or [])
            elif "paths" in a:
                paths = list(a["paths"])
            elif "requirement_class" in a:
                want = set(a["requirement_class"])
                paths = [p for p in self.declared_paths()
                         if self.requirement_of.get(p) in want]
            else:
                paths = self.declared_paths()

            if "value_types" in a:
                want = set(a["value_types"])
                paths = [p for p in paths if self.value_type_of.get(p) in want]

            subs = []
            for p in paths:
                exists = path_exists(self.record, p)
                blk = path_get(self.record, p) if exists else None
                s = Subject("parameter", p, blk if is_mapping(blk) else blk, self.record)
                s.exists = exists
                subs.append(s)

            # Filters that require the block to be present and shaped.
            if "statuses" in a:
                want = set(a["statuses"])
                subs = [s for s in subs
                        if s.exists and is_mapping(s.block)
                        and s.block.get("status", "present") in want]
            if "shape" in a:
                pred = self.predicates.get(a["shape"])
                if pred is None:
                    raise SuiteContractError("%s: unknown shape %r" % (test["id"], a["shape"]))
                subs = [s for s in subs
                        if s.exists and is_mapping(s.block)
                        and eval_predicate(pred, s.block, self.sets)]
            if "where" in a:
                subs = [s for s in subs
                        if s.exists and is_mapping(s.block)
                        and eval_field_condition(a["where"], s.block, self.sets)]
            if "only_if_field_present" in a:
                f = a["only_if_field_present"]
                subs = [s for s in subs
                        if s.exists and is_mapping(s.block) and f in s.block]
            if "requires_fields" in a:
                need = a["requires_fields"]
                subs = [s for s in subs
                        if s.exists and is_mapping(s.block)
                        and all(f in s.block for f in need)]
            return subs

        raise SuiteContractError("%s: unrecognised applies_to.scope %r" % (test["id"], scope))

    # -- verb table --------------------------------------------------------

    def _build_verb_table(self):
        return {
            "field_present": self._v_field_present,
            "field_absent": self._v_field_absent,
            "field_not_null": self._v_field_not_null,
            "field_is_null": self._v_field_is_null,
            "field_non_empty_string": self._v_field_non_empty_string,
            "field_in_enum": self._v_field_in_enum,
            "field_is_json_type": self._v_field_is_json_type,
            "block_is_json_type": self._v_block_is_json_type,
            "field_not_in_denylist": self._v_field_not_in_denylist,
            "field_matches_regex": self._v_field_matches_regex,
            "fields_differ": self._v_fields_differ,
            "string_max_length": self._v_string_max_length,
            "exactly_one_shape": self._v_exactly_one_shape,
            "block_matches_shape": self._v_block_matches_shape,
            "implies": self._v_implies,
            "paths_exist": self._v_paths_exist,
            "no_undeclared_paths": self._v_no_undeclared_paths,
            "keys_present": self._v_keys_present,
            "keys_unique_at_top_level": self._v_keys_unique_at_top_level,
            "value_type_matches_declaration": self._v_value_type_matches_declaration,
            "equals_scope": self._v_equals_scope,
            "equals_schema": self._v_equals_schema,
            "equals_schema_attribute": self._v_equals_schema_attribute,
            "filename_matches_field": self._v_filename_matches_field,
            "date_not_future": self._v_date_not_future,
            "date_parseable": self._v_date_parseable,
            "confidence_floor": self._v_confidence_floor,
            "identity_consistency": self._v_identity_consistency,
            "tier_gate": self._v_tier_gate,
            "tier_not_over_declared": self._v_tier_not_over_declared,
            "tier_not_under_declared": self._v_tier_not_under_declared,
            "emit_finding": self._v_emit_finding,
            "report_contract": self._v_report_contract,
            "suite_invariant": self._v_suite_invariant,
            "manual_review": self._v_manual_review,
        }

    # -- per-subject field verbs -------------------------------------------

    def _field_name(self, p, subject, default=None):
        """Which field a check reads. For top_level_key subjects the key
        name IS the field, so params may omit it (TL-002, TL-006)."""
        if "field" in p:
            return p["field"]
        if subject.kind == "top_level_key":
            return subject.name
        if default is not None:
            return default
        raise SuiteContractError("check needs a 'field' param: %r" % (p,))

    def _v_field_present(self, tid, sev, p, subject):
        f = self._field_name(p, subject)
        if field_of(subject.block, f) is ABSENT:
            self.emit(tid, sev, "%s: field %r is absent" % (subject.name, f), subject.name)

    def _v_field_absent(self, tid, sev, p, subject):
        f = self._field_name(p, subject)
        if field_of(subject.block, f) is not ABSENT:
            self.emit(tid, sev, "%s: field %r is present and must not be"
                      % (subject.name, f), subject.name)

    def _v_field_not_null(self, tid, sev, p, subject):
        f = self._field_name(p, subject)
        v = field_of(subject.block, f)
        if v is ABSENT or v is None:
            self.emit(tid, sev, "%s: field %r is %s" % (
                subject.name, f, "absent" if v is ABSENT else "null"), subject.name)

    def _v_field_is_null(self, tid, sev, p, subject):
        f = self._field_name(p, subject)
        v = field_of(subject.block, f)
        if v is ABSENT:
            self.emit(tid, sev, "%s: field %r is absent; an explicit null is required"
                      % (subject.name, f), subject.name)
        elif v is not None:
            self.emit(tid, sev, "%s: field %r is %r, not null" % (subject.name, f, v),
                      subject.name)

    def _v_field_non_empty_string(self, tid, sev, p, subject):
        f = self._field_name(p, subject)
        v = field_of(subject.block, f)
        if v is ABSENT:
            self.emit(tid, sev, "%s: field %r is absent" % (subject.name, f), subject.name)
        elif not nonempty_str(v):
            self.emit(tid, sev, "%s: field %r is %r - not a non-empty string"
                      % (subject.name, f, v), subject.name)

    def _v_field_in_enum(self, tid, sev, p, subject):
        f = self._field_name(p, subject)
        v = field_of(subject.block, f)
        vocab = self.sets.get(p.get("enum_ref"))
        if vocab is None:
            raise SuiteContractError("unknown enum_ref %r" % p.get("enum_ref"))
        if v is ABSENT:
            if not p.get("allow_absent"):
                self.emit(tid, sev, "%s: field %r is absent (enum %s)"
                          % (subject.name, f, p.get("enum_ref")), subject.name)
            return
        if p.get("case_sensitive") is False:
            ok = isinstance(v, str) and v.lower() in [str(x).lower() for x in vocab]
        else:
            ok = v in vocab
        if not ok:
            self.emit(tid, sev, "%s: field %r is %r, not in %s %s"
                      % (subject.name, f, v, p.get("enum_ref"), list(vocab)), subject.name)

    def _v_field_is_json_type(self, tid, sev, p, subject):
        f = self._field_name(p, subject)
        v = field_of(subject.block, f)
        if v is ABSENT:
            return  # only_if_field_present scoping governs applicability
        want = p["json_type"]
        got = json_type_of(v)
        if got != want:
            self.emit(tid, sev, "%s: field %r is JSON %s, expected %s"
                      % (subject.name, f, got, want), subject.name)

    def _v_block_is_json_type(self, tid, sev, p, subject):
        if getattr(subject, "exists", True) is False:
            return
        want = p["json_type"]
        got = json_type_of(subject.block)
        if got != want:
            self.emit(tid, sev, "%s resolves to JSON %s, not %s" % (subject.name, got, want),
                      subject.name)

    def _v_field_not_in_denylist(self, tid, sev, p, subject):
        f = self._field_name(p, subject)
        v = field_of(subject.block, f)
        if v is ABSENT:
            return
        deny = p.get("denylist") or []
        s = v.strip() if isinstance(v, str) else v
        if p.get("case_insensitive") and isinstance(s, str):
            hit = any(isinstance(d, str) and s.lower() == d.lower() for d in deny)
        else:
            hit = s in deny
        if hit:
            self.emit(tid, sev, "%s: field %r is the placeholder %r" % (subject.name, f, v),
                      subject.name)

    def _v_field_matches_regex(self, tid, sev, p, subject):
        f = self._field_name(p, subject)
        v = field_of(subject.block, f)
        rx = p["regex"]
        if v is ABSENT or not isinstance(v, str) or not re.search(rx, v):
            self.emit(tid, sev, "%s: field %r (%r) does not match %s"
                      % (subject.name, f, None if v is ABSENT else v, rx), subject.name)

    def _v_fields_differ(self, tid, sev, p, subject):
        a = field_of(subject.block, p["field_a"])
        b = field_of(subject.block, p["field_b"])
        if a is ABSENT or b is ABSENT:
            return
        if p.get("normalize") == "strip":
            a = a.strip() if isinstance(a, str) else a
            b = b.strip() if isinstance(b, str) else b
        if a == b:
            self.emit(tid, sev, "%s: %r and %r are identical after %s"
                      % (subject.name, p["field_a"], p["field_b"],
                         p.get("normalize") or "no normalisation"), subject.name)

    def _v_string_max_length(self, tid, sev, p, subject):
        f = self._field_name(p, subject)
        v = field_of(subject.block, f)
        if not isinstance(v, str):
            return
        if len(v) > p["max"]:
            self.emit(tid, sev, "%s: %r is %d %s, over the %d bound"
                      % (subject.name, f, len(v), p.get("unit") or "characters", p["max"]),
                      subject.name)

    def _v_exactly_one_shape(self, tid, sev, p, subject):
        if getattr(subject, "exists", True) is False or not is_mapping(subject.block):
            return
        ref = p["shapes_ref"]
        node = self.suite
        for part in ref.split("."):
            node = (node or {}).get(part)
        if not is_mapping(node):
            raise SuiteContractError("shapes_ref %r does not resolve to a mapping" % ref)
        held = [nm for nm, pr in node.items()
                if eval_predicate(pr, subject.block, self.sets)]
        if len(held) != 1:
            self.emit(tid, sev, "%s satisfies %d shape predicates (%s); exactly one required"
                      % (subject.name, len(held), ", ".join(held) or "none"), subject.name)

    def _v_block_matches_shape(self, tid, sev, p, subject):
        pred = self.predicates.get(p["shape"])
        if pred is None:
            raise SuiteContractError("unknown shape %r" % p["shape"])
        if getattr(subject, "exists", True) is False:
            self.emit(tid, sev, "%s is absent, so it cannot satisfy %s"
                      % (subject.name, p["shape"]), subject.name)
            return
        if not is_mapping(subject.block) or not eval_predicate(pred, subject.block, self.sets):
            self.emit(tid, sev, "%s does not satisfy %s (status=%r)"
                      % (subject.name, p["shape"],
                         subject.block.get("status") if is_mapping(subject.block) else None),
                      subject.name)

    def _v_implies(self, tid, sev, p, subject):
        if not self._antecedent_holds(p.get("if_") or {}, subject):
            return
        if not self._consequent_holds(p.get("then") or {}, subject):
            self.emit(tid, sev, "%s: %s held but %s did not"
                      % (subject.name, json.dumps(p.get("if_"), default=str),
                         json.dumps(p.get("then"), default=str)), subject.name)

    def _antecedent_holds(self, cond, subject):
        if "any_key_absent" in cond:
            return any(k not in self.record for k in cond["any_key_absent"])
        if "any_fail_in_categories" in cond:
            return bool(self.fails_in(cond["any_fail_in_categories"]))
        if getattr(subject, "exists", True) is False or not is_mapping(subject.block):
            return False
        return eval_field_condition(cond, subject.block, self.sets)

    def _consequent_holds(self, cond, subject):
        blk = subject.block if is_mapping(subject.block) else {}
        if "not_in" in cond:
            v = field_of(self.record if cond.get("field") in self.record else blk,
                         cond["field"])
            return v is ABSENT or v not in cond["not_in"]
        base = self.record if cond.get("field") in self.record else blk
        return eval_field_condition(cond, base, self.sets)

    # -- set-level verbs ----------------------------------------------------

    def _v_paths_exist(self, tid, sev, p, subject):
        if getattr(subject, "exists", True) is False:
            self.emit(tid, sev, "declared path %s is absent from the record" % subject.name,
                      subject.name)

    def _v_no_undeclared_paths(self, tid, sev, p, subject):
        # Runs once, over the record's parameter-bearing sections.
        declared = set(self.declared_paths())
        sections = sorted(set(x.split(".")[0] for x in declared))
        ignore = set(p.get("ignore_block_keys") or [])
        for sec in sections:
            blk = self.record.get(sec)
            if not is_mapping(blk):
                continue
            for k in blk:
                if k in ignore:
                    continue
                dotted = "%s.%s" % (sec, k)
                if dotted not in declared:
                    self.emit(tid, sev, "%s is not a schema-declared parameter path" % dotted,
                              dotted)

    def _v_keys_present(self, tid, sev, p, subject):
        if subject.kind != "top_level_key":
            raise SuiteContractError("keys_present expects top-level key subjects")
        if subject.name not in self.record:
            msg = "required top-level key %r is absent" % subject.name
            extra = p.get("on_absent_message")
            if extra:
                msg += " - %s" % extra
            self.emit(tid, sev, msg, subject.name)

    def _v_keys_unique_at_top_level(self, tid, sev, p, subject):
        if subject.kind == "top_level_key" and subject.name in self.dup_top_level_keys:
            self.emit(tid, sev, "top-level key %r appears more than once" % subject.name,
                      subject.name)

    def _v_value_type_matches_declaration(self, tid, sev, p, subject):
        declared = self.value_type_of.get(subject.name)
        v = field_of(subject.block, "value")
        if v is ABSENT:
            return
        want = set(p.get("json_types") or [])
        got = json_type_of(v)

        if p.get("exclude_boolean") and isinstance(v, bool):
            self.emit(tid, sev, "%s declared %s but the value is a boolean"
                      % (subject.name, declared), subject.name)
            return
        if p.get("reject_numeric_strings") and isinstance(v, str):
            self.emit(tid, sev, "%s declared %s but the value is the string %r"
                      % (subject.name, declared, v), subject.name)
            return
        if got in want:
            return
        if (p.get("allow_float_with_zero_fraction") and isinstance(v, float)
                and float(v).is_integer()):
            return
        if isinstance(v, float) and "integer" in want and not float(v).is_integer():
            self.emit(tid, sev, "%s declared %s but %r has a non-zero fractional part"
                      % (subject.name, declared, v), subject.name)
            return
        self.emit(tid, sev, "%s declared %s but the value is JSON %s (expected one of %s)"
                  % (subject.name, declared, got, sorted(want)), subject.name)

    # -- identity / scope verbs ---------------------------------------------

    def _v_equals_scope(self, tid, sev, p, subject):
        want = self.scope.get(p["scope_key"], ABSENT)
        got = self.record.get(p["field"], ABSENT)
        if want is ABSENT:
            self.emit(tid, sev, "entity_scope has no key %r" % p["scope_key"])
        elif got != want:
            self.emit(tid, sev, "record.%s is %r but entity_scope declares %r"
                      % (p["field"], None if got is ABSENT else got, want))

    def _v_equals_schema(self, tid, sev, p, subject):
        want = self.schema.get(p["schema_key"], ABSENT)
        got = self.record.get(p["field"], ABSENT)
        if got != want:
            self.emit(tid, sev, "record.%s is %r but SCHEMA.%s is %r"
                      % (p["field"], None if got is ABSENT else got,
                         p["schema_key"], None if want is ABSENT else want))

    def _v_equals_schema_attribute(self, tid, sev, p, subject):
        attr = p["schema_attribute"]
        table = self.unit_of if attr == "unit" else None
        if table is None:
            raise SuiteContractError("no resolver for schema_attribute %r" % attr)
        want = table.get(subject.name)
        got = field_of(subject.block, p["field"])
        if got is ABSENT:
            return
        if got != want:
            self.emit(tid, sev, "%s records %s %r but the schema declares %r"
                      % (subject.name, p["field"], got, want), subject.name)

    def _v_filename_matches_field(self, tid, sev, p, subject):
        base = os.path.basename(self.record_path)
        if p.get("strip_extension"):
            base = os.path.splitext(base)[0]
        got = self.record.get(p["field"])
        ok = (base == got) if p.get("case_sensitive", True) else \
             (isinstance(got, str) and base.lower() == got.lower())
        if not ok:
            self.emit(tid, sev, "filename basename %r != record.%s %r"
                      % (base, p["field"], got))

    # -- date verbs ----------------------------------------------------------

    def _date_value(self, p, subject):
        if "field" in p:
            return p["field"], self.record.get(p["field"], ABSENT)
        # recursive_key subject: the block is {key_name: value}
        if subject.kind == "recursive_key" and is_mapping(subject.block):
            k = list(subject.block.keys())[0]
            return subject.name, subject.block[k]
        return subject.name, ABSENT

    def _v_date_not_future(self, tid, sev, p, subject):
        label, v = self._date_value(p, subject)
        if v is ABSENT:
            if not p.get("absence_is_pass"):
                self.emit(tid, sev, "%s is absent" % label, subject.name)
            return
        dt = parse_iso_date(v)
        if dt is None:
            return  # unparseable is date_parseable's business
        cutoff = self.validation_time + _dt.timedelta(days=p.get("max_future_days", 0))
        if dt > cutoff:
            self.emit(tid, sev, "%s is %s, later than validation_time + %d day(s) (%s)"
                      % (label, dt.isoformat(), p.get("max_future_days", 0),
                         cutoff.isoformat()), subject.name)

    def _v_date_parseable(self, tid, sev, p, subject):
        label, v = self._date_value(p, subject)
        if v is ABSENT:
            if not p.get("absence_is_pass"):
                self.emit(tid, sev, "%s is absent" % label, subject.name)
            return
        if parse_iso_date(v) is None:
            self.emit(tid, sev, "%s is %r, which does not parse as an ISO-8601 date or "
                      "datetime; a future-date check cannot fire on it" % (label, v),
                      subject.name)

    # -- confidence / identity ----------------------------------------------

    def _v_confidence_floor(self, tid, sev, p, subject):
        conf = field_of(subject.block, "confidence")
        if conf is ABSENT or conf in (p.get("allowed") or []):
            return
        want_marker = p.get("marker_state", "any")
        if want_marker != "any":
            pred = self.predicates.get("escalation_marker_present")
            if pred is None:
                raise SuiteContractError("predicates.escalation_marker_present is missing")
            marked = eval_predicate(pred, subject.block, self.sets)
            if want_marker == "present" and not marked:
                return
            if want_marker == "absent" and marked:
                return
        self.emit(tid, sev,
                  "%s carries confidence %r, outside the floor %s (marker_state=%s)"
                  % (subject.name, conf, p.get("allowed"), want_marker),
                  subject.name, code=p.get("finding_code"), reason_code="measured_floor")

    def _v_identity_consistency(self, tid, sev, p, subject):
        def norm(s):
            if p.get("normalize") == "uppercase_alnum_only":
                return re.sub(r"[^A-Za-z0-9]", "", s or "").upper() if isinstance(s, str) else ""
            return s
        a, b = norm(self.record.get(p["field_a"])), norm(self.record.get(p["field_b"]))
        if not (a and b):
            self.emit(tid, sev, "%s (%r) or %s (%r) is absent or empty; cannot compare"
                      % (p["field_a"], self.record.get(p["field_a"]),
                         p["field_b"], self.record.get(p["field_b"])))
            return
        if a not in b and b not in a:
            self.emit(tid, sev, "neither normalised %s (%r) nor %s (%r) contains the other"
                      % (p["field_a"], a, p["field_b"], b))
        for tok in (p.get("qualifier_tokens") or []):
            if (tok in a) != (tok in b):
                self.emit(tid, sev, "qualifier token %r appears in %s but not %s"
                          % (tok, p["field_a"] if tok in a else p["field_b"],
                             p["field_b"] if tok in a else p["field_a"]))

    # -- tier verbs -----------------------------------------------------------

    def _tier_gate_holds(self, params):
        """Evaluate a tier_gate's body independently of what is declared, so
        RT-006 can compute a tier. Returns (ok, reasons)."""
        reasons = []
        for cat_list in [params.get("requires_no_fail_in") or []]:
            f = self.fails_in(cat_list)
            if f:
                reasons.append("fail-level findings in %s: %s"
                               % ("/".join(cat_list), ", ".join(f)))
        for tid in (params.get("requires_pass") or []):
            r = self.results.get(tid)
            if r is None:
                # A gate may name a test that was skipped by its own condition.
                gate = self._gate_params_of(tid)
                if gate is not None:
                    ok, why = self._tier_gate_holds(gate)
                    if not ok:
                        reasons.extend("%s: %s" % (tid, w) for w in why)
                    continue
                reasons.append("%s produced no result" % tid)
            elif r["outcome"] == "fail":
                reasons.append("%s failed" % tid)
            elif r["outcome"] == "skipped":
                gate = self._gate_params_of(tid)
                if gate is not None:
                    ok, why = self._tier_gate_holds(gate)
                    if not ok:
                        reasons.extend("%s: %s" % (tid, w) for w in why)
                else:
                    ok, why = self._rerun_conditional(tid)
                    if not ok:
                        reasons.extend("%s: %s" % (tid, w) for w in why)
        for field in (params.get("requires_all_present_blocks_have") or []):
            pred = self.predicates.get("present_shape")
            for path in self.declared_paths():
                blk = path_get(self.record, path)
                if is_mapping(blk) and eval_predicate(pred, blk, self.sets):
                    if not nonempty_str(blk.get(field)):
                        reasons.append("%s is present-shape without a non-empty %s"
                                       % (path, field))
        return (not reasons), reasons

    def _gate_params_of(self, tid):
        t = self.tests_by_id.get(tid)
        if not t:
            return None
        for c in (t.get("checks") or []):
            if c.get("check") == "tier_gate":
                return c.get("params") or {}
        return None

    def _rerun_conditional(self, tid):
        """Re-evaluate a condition-skipped test's checks, ignoring its
        condition, so a tier computation is not silently satisfied by a
        test that never ran."""
        t = self.tests_by_id.get(tid)
        if not t:
            return True, []
        before = len(self.findings)
        sev = self.severity_for(t) or "fail"
        try:
            subjects = self.build_subjects(t)
            for c in (t.get("checks") or []):
                fn = self._verbs[c.get("check")]
                params = c.get("params") or {}
                if c.get("check") in _RUN_ONCE_VERBS:
                    fn("__probe__", sev, params, subjects[0] if subjects else
                       Subject("record_root", "<record>", self.record, self.record))
                else:
                    for s in subjects:
                        fn("__probe__", sev, params, s)
        except SuiteContractError:
            raise
        probe = [f for f in self.findings[before:]]
        del self.findings[before:]
        return (not probe), [f.message for f in probe]

    def _v_tier_gate(self, tid, sev, p, subject):
        ok, reasons = self._tier_gate_holds(p)
        for r in reasons:
            self.emit(tid, sev, r)
        if p.get("unevaluated_clauses"):
            for c in p["unevaluated_clauses"]:
                if c not in self.unevaluated_tier_clauses:
                    self.unevaluated_tier_clauses.append(
                        "%s clause NOT evaluated: %s" % (p.get("tier"), c))

    def _computed_tier(self, p):
        labels = p.get("qualify_labels") or {}
        best, best_label = "R0", "R0"
        for tid in (p.get("compute_from") or []):
            gate = self._gate_params_of(tid)
            if gate is None:
                continue
            ok, _why = self._tier_gate_holds(gate)
            if ok:
                t = gate.get("tier")
                best = t
                best_label = labels.get(t, t)
            else:
                break
        return best, best_label

    def _v_tier_not_over_declared(self, tid, sev, p, subject):
        order = {"R0": 0, "R1": 1, "R2": 2, "R3": 3}
        computed, label = self._computed_tier(p)
        declared = self.tier()
        self.tier_computation = OrderedDict([
            ("readiness_declared", declared),
            ("computed_tier", computed),
            ("computed_tier_label", label),
        ])
        if declared not in order:
            self.emit(tid, sev, "readiness_declared %r is not a recognised tier, so "
                                "over-declaration cannot be assessed" % declared)
            return
        if order[declared] > order[computed]:
            self.emit(tid, sev, "readiness_declared %s exceeds the computed tier %s"
                      % (declared, label))

    def _v_tier_not_under_declared(self, tid, sev, p, subject):
        order = {"R0": 0, "R1": 1, "R2": 2, "R3": 3}
        tc = self.tier_computation or {}
        computed = tc.get("computed_tier")
        label = tc.get("computed_tier_label", computed)
        declared = self.tier()
        if declared not in order or computed not in order:
            return
        if order[computed] > order[declared]:
            self.emit(tid, sev, "the computed tier %s is higher than readiness_declared %s; "
                                "work already done may be going unclaimed" % (label, declared))

    def _v_emit_finding(self, tid, sev, p, subject):
        self.emit(tid, sev, "%s: %s" % (subject.name, p.get("message") or "finding"),
                  subject.name)

    # -- meta verbs -----------------------------------------------------------

    def _v_report_contract(self, tid, sev, p, subject):
        """Verify the report this run emits actually satisfies the stated
        requirement, rather than asserting it."""
        req = p.get("requirement") or ""
        cov = self.coverage_by_class or {}
        if tid == "SC-014":
            if not cov or not all(("absent_keys" in c and "status_missing" in c)
                                  for c in cov.values()):
                self.emit(tid, sev, "report does not emit absent_keys and status_missing as "
                                    "separate labelled counts per requirement class")
        elif tid == "KC-006":
            for cls, c in cov.items():
                total = (c["present_shape"] + c["status_missing"] + c["not_applicable"]
                         + c["absent_keys"] + c["other"])
                if total != c["declared"]:
                    self.emit(tid, sev, "%s: buckets sum to %d but %d declared"
                              % (cls, total, c["declared"]))
        elif tid == "RT-010":
            if self.tier() in ("R2", "R3") and not self.unevaluated_tier_clauses:
                self.emit(tid, sev, "readiness_declared is %s but the report names no "
                                    "unevaluated tier clauses" % self.tier())
        else:
            raise SuiteContractError(
                "report_contract used by %s, which this runner has no verification for. "
                "Requirement: %s" % (tid, req))

    def _v_suite_invariant(self, tid, sev, p, subject):
        """Negative tests, verified over the findings this run produced."""
        if tid == "KC-004":
            optional_absent = set(x for x in (self.sets.get("OPTIONAL_PATHS") or [])
                                  if not path_exists(self.record, x))
            for f in self.findings:
                if f.severity == "fail" and f.subject in optional_absent:
                    self.emit(tid, sev, "absence of OPTIONAL path %s produced a fail from %s"
                              % (f.subject, f.test_id), f.subject)
        elif tid == "CC-003":
            modeling = set(self.sets.get("REQUIRED_MODELING_PATHS") or [])
            for f in self.findings:
                if (f.reason_code == "measured_floor" and f.subject in modeling
                        and f.severity in ("fail", "warn")):
                    self.emit(tid, sev, "%s emitted %s against REQUIRED_MODELING path %s "
                              "for confidence alone" % (f.test_id, f.severity, f.subject),
                              f.subject)
        elif tid == "VT-006":
            pred = self.predicates.get("present_shape")
            ps = set(x for x in self.declared_paths()
                     if is_mapping(path_get(self.record, x))
                     and eval_predicate(pred, path_get(self.record, x), self.sets))
            vt = ("VT-001", "VT-002", "VT-003", "VT-004", "VT-005")
            for f in self.findings:
                if f.test_id in vt and f.subject and f.subject not in ps:
                    self.emit(tid, sev, "%s produced a finding against %s, which is not "
                              "present_shape" % (f.test_id, f.subject), f.subject)
        else:
            raise SuiteContractError(
                "suite_invariant used by %s, which this runner has no verification for. "
                "Requirement: %s" % (tid, p.get("requirement")))

    def _v_manual_review(self, tid, sev, p, subject):
        return  # handled by the gap path; never automated

    # -- execution -----------------------------------------------------------

    def run_test(self, test):
        tid = test["id"]
        sev = self.severity_for(test)

        # automatable: false -> gap, human_review carried verbatim.
        if test.get("automatable") is False:
            return self.record_result(
                tid, "gap",
                "GAP - not automatable (target: %s). Requires human review." % test.get("target"))

        # condition unmet -> the suite says the test is SKIPPED ENTIRELY.
        cond = test.get("condition")
        if cond:
            tiers = cond.get("readiness_declared_in")
            if tiers is not None and self.tier() not in tiers:
                return self.record_result(
                    tid, "skipped",
                    "SKIPPED - condition readiness_declared_in %s not met "
                    "(readiness_declared=%r). Per runner_contract.condition the test is "
                    "skipped entirely; nothing was checked." % (tiers, self.tier()))

        subjects = self.build_subjects(test)
        for c in (test.get("checks") or []):
            verb = c.get("check")
            fn = self._verbs[verb]          # presence guaranteed by _validate_contract
            params = c.get("params") or {}
            if verb in _RUN_ONCE_VERBS:
                anchor = subjects[0] if subjects else Subject(
                    "record_root", "<record>", self.record, self.record)
                fn(tid, sev, params, anchor)
            else:
                for s in subjects:
                    fn(tid, sev, params, s)

        fs = self.findings_for(tid)
        if not fs:
            return self.record_result(
                tid, "pass",
                "PASS - %d check(s) over %d subject(s); no findings."
                % (len(test.get("checks") or []), len(subjects)))
        outcome = SEVERITY_TO_OUTCOME.get(sev, "fail")
        return self.record_result(
            tid, outcome,
            "%d finding(s): %s" % (len(fs), "; ".join(f.message for f in fs[:4])
                                   + (" ..." if len(fs) > 4 else "")))


# Verbs that evaluate the record as a whole, not once per subject.
_RUN_ONCE_VERBS = frozenset([
    "no_undeclared_paths", "equals_scope", "equals_schema", "filename_matches_field",
    "identity_consistency", "tier_gate", "tier_not_over_declared",
    "tier_not_under_declared", "report_contract", "suite_invariant", "manual_review",
])

_APPLIES_TO_HANDLED = frozenset([
    "scope", "requirement_class", "paths", "paths_ref", "keys", "keys_ref",
    "value_types", "statuses", "shape", "where", "only_if_field_present",
    "requires_fields", "only_present_keys", "key_name",
])


# ==========================================================================
# Coverage table
# ==========================================================================

def compute_coverage(R):
    pred = R.predicates.get("present_shape")
    classes = OrderedDict()
    for path in R.declared_paths():
        cls = R.requirement_of.get(path)
        c = classes.setdefault(cls, OrderedDict([
            ("declared", 0), ("present_shape", 0), ("status_missing", 0),
            ("not_applicable", 0), ("absent_keys", 0), ("other", 0),
            ("absent_key_paths", []), ("status_missing_paths", []),
        ]))
        c["declared"] += 1
        if not path_exists(R.record, path):
            c["absent_keys"] += 1
            c["absent_key_paths"].append(path)
            continue
        blk = path_get(R.record, path)
        st = blk.get("status") if is_mapping(blk) else None
        if is_mapping(blk) and eval_predicate(pred, blk, R.sets):
            c["present_shape"] += 1
        elif st == "missing":
            c["status_missing"] += 1
            c["status_missing_paths"].append(path)
        elif st == "not_applicable":
            c["not_applicable"] += 1
        else:
            c["other"] += 1
    return classes


# ==========================================================================
# Schema conformance (informational only - see README Q2)
# ==========================================================================

def run_schema_conformance(schema, schema_path, record):
    """entity_schema_3.0.json declares itself 'deliberately NOT JSON Schema'
    and says jsonschema must not be vendored. Its top-level keys are not
    draft-07 keywords, so a draft-07 interpreter would validate any input
    vacuously.

    This result is INFORMATIONAL and feeds no test. RT-002's tier_gate
    names exactly `requires_no_fail_in` four categories plus
    `requires_pass: [KC-001, KC-002]` - there is no schema-conformance
    clause for it to feed.
    """
    out = OrderedDict()
    out["library"] = "jsonschema"
    out["schema_path"] = schema_path
    declares_not = any("NOT JSON Schema" in str(l) for l in schema.get("_what_this_is", []))
    out["schema_declares_not_json_schema"] = declares_not
    out["feeds_any_test"] = False

    try:
        import jsonschema
    except ImportError as exc:
        out["outcome"] = "skipped"
        out["reason"] = ("jsonschema is not importable (%s); the schema also states it must "
                         "not be vendored." % exc)
        return out
    if declares_not:
        out["outcome"] = "skipped"
        out["reason"] = ("the schema declares itself NOT JSON Schema; a draft-07 "
                         "interpreter would pass any input vacuously.")
        return out
    base = "file:///" + os.path.abspath(schema_path).replace(os.sep, "/")
    try:
        resolver = jsonschema.RefResolver(base_uri=base, referrer=schema)
        v = jsonschema.Draft7Validator(schema, resolver=resolver)
        errs = sorted(v.iter_errors(record), key=lambda e: list(e.absolute_path))
    except jsonschema.SchemaError as exc:
        out["outcome"] = "skipped"
        out["reason"] = "not a valid JSON Schema document: %s" % exc.message
        return out
    if errs:
        out["outcome"] = "fail"
        out["reason"] = errs[0].message
        out["error_count"] = len(errs)
    else:
        out["outcome"] = "pass"
        out["reason"] = "no validation errors"
    return out


# ==========================================================================
# Report
# ==========================================================================

def build_report(R, started):
    suite = R.suite
    open_items = [oi for oi in (suite.get("open_items") or [])
                  if str(oi.get("status", "")).upper().startswith("OPEN")]
    gaps = [r for r in R.results.values() if r["outcome"] == "gap"]
    nonauto = [r for r in R.results.values() if r.get("automatable") is False]

    by_cat, by_sev, by_out, by_target = OrderedDict(), OrderedDict(), OrderedDict(), OrderedDict()
    for r in R.results.values():
        by_cat.setdefault(r["category"], OrderedDict((o, 0) for o in VALID_OUTCOMES))[r["outcome"]] += 1
        by_sev.setdefault(r["severity"], OrderedDict((o, 0) for o in VALID_OUTCOMES))[r["outcome"]] += 1
        by_target.setdefault(r["target"], OrderedDict((o, 0) for o in VALID_OUTCOMES))[r["outcome"]] += 1
        by_out[r["outcome"]] = by_out.get(r["outcome"], 0) + 1

    rep = OrderedDict()
    rep["record_path"] = R.record_path
    rep["schema_path"] = R.schema_path
    rep["suite_path"] = R.suite_path
    rep["suite_id"] = suite.get("suite_id")
    rep["suite_version"] = suite.get("suite_version")
    rep["suite_frozen"] = suite.get("frozen")
    rep["run_timestamp"] = started.isoformat() + "Z"
    rep["validation_time"] = R.validation_time.isoformat()
    rep["entity_identity_preflight"] = R.preflight
    rep["schema_conformance"] = R.schema_conformance
    rep["entity_scope"] = R.scope
    rep["derived_sets_resolved"] = R.sets
    rep["coverage_by_requirement_class"] = R.coverage_by_class
    rep["tier_computation"] = R.tier_computation
    rep["unevaluated_tier_clauses"] = R.unevaluated_tier_clauses
    rep["results"] = list(R.results.values())
    rep["summary"] = OrderedDict([
        ("total_tests", len(R.results)),
        ("by_outcome", by_out),
        ("by_category", by_cat),
        ("by_severity", by_sev),
        ("by_target", by_target),
    ])
    rep["open_items_still_open"] = [
        OrderedDict([("id", o.get("id")), ("status", o.get("status")),
                     ("title", o.get("title")), ("affects", o.get("affects"))])
        for o in open_items]
    rep["gap_severity_tests_that_fired"] = [
        OrderedDict([("id", r["id"]), ("category", r["category"]), ("target", r["target"]),
                     ("detail", r["detail"]), ("human_review", r.get("human_review"))])
        for r in gaps]
    rep["tests_not_automatable"] = [
        OrderedDict([("id", r["id"]), ("category", r["category"]),
                     ("severity", r["severity"]), ("outcome", r["outcome"]),
                     ("human_review", r.get("human_review"))])
        for r in nonauto]
    rep["closing_report_open_gaps_not_closed"] = \
        (suite.get("closing_report") or {}).get("open_gaps_not_closed")
    rep["explicitly_out_of_scope"] = suite.get("explicitly_out_of_scope")
    rep["skipped_tests"] = [
        OrderedDict([("id", r["id"]), ("detail", r["detail"])])
        for r in R.results.values() if r["outcome"] == "skipped"]
    return rep


def print_console(rep):
    W = sys.stdout.write
    bar = "=" * 74
    W("\n%s\nVALIDATION RUN  %s  (suite v%s, frozen=%s)\n%s\n"
      % (bar, rep["suite_id"], rep["suite_version"], rep["suite_frozen"], bar))
    W("  record : %s\n  schema : %s\n  suite  : %s\n  run at : %s\n\n"
      % (rep["record_path"], rep["schema_path"], rep["suite_path"], rep["run_timestamp"]))

    pf = rep["entity_identity_preflight"]
    W("-- ENTITY IDENTITY PRE-FLIGHT ------------------------------------------\n")
    for row in pf["comparisons"]:
        W("  %-30s %-30s %-30s %s\n" % (row["field"], repr(row["left"]), repr(row["right"]),
                                        "OK" if row["match"] else "MISMATCH"))
    W("  (the record's directory is deliberately NOT part of this check)\n  result: %s\n\n"
      % pf["outcome"])

    sc = rep["schema_conformance"]
    W("-- SCHEMA CONFORMANCE (informational; feeds no test) -------------------\n")
    W("  outcome: %s\n  reason : %s\n\n" % (sc["outcome"].upper(), sc["reason"]))

    hdr = "  %-24s %5s %5s %5s %5s %5s %5s %5s\n"
    for title, key in (("COUNTS PER CATEGORY", "by_category"),
                       ("COUNTS PER SEVERITY (as declared)", "by_severity"),
                       ("COUNTS PER TARGET", "by_target")):
        W("-- %s %s\n" % (title, "-" * max(0, 68 - len(title))))
        W(hdr % ("", "total", "pass", "warn", "fail", "info", "gap", "skip"))
        for k, c in rep["summary"][key].items():
            W(hdr % (k, sum(c.values()), c["pass"], c["warn"], c["fail"],
                     c["info"], c["gap"], c["skipped"]))
        W("\n")

    W("-- OUTCOMES ------------------------------------------------------------\n")
    for o in VALID_OUTCOMES:
        W("  %-8s %d\n" % (o, rep["summary"]["by_outcome"].get(o, 0)))
    W("  %-8s %d\n\n" % ("TOTAL", rep["summary"]["total_tests"]))

    for label, tag in (("FAILING TESTS", "fail"), ("WARNINGS", "warn"),
                       ("INFORMATIONAL", "info")):
        rows = [r for r in rep["results"] if r["outcome"] == tag]
        if rows:
            W("-- %s %s\n" % (label, "-" * max(0, 68 - len(label))))
            for r in rows:
                W("  [%-4s] %-9s %-22s %s\n" % (tag.upper(), r["id"], r["category"], r["detail"]))
            W("\n")

    W("-- GAPS (automatable: false - human review required) -------------------\n")
    for r in rep["gap_severity_tests_that_fired"]:
        W("  [GAP]  %-9s (%s) %s\n" % (r["id"], r["target"], r["detail"]))
        if r.get("human_review"):
            W("         human_review: %s\n" % " ".join(str(r["human_review"]).split()))
    W("\n")

    if rep["skipped_tests"]:
        W("-- SKIPPED -------------------------------------------------------------\n")
        for r in rep["skipped_tests"]:
            W("  [SKIP] %-9s %s\n" % (r["id"], r["detail"]))
        W("\n")

    W("-- OPEN ITEMS STILL OPEN (reported, NOT resolved) ----------------------\n")
    for o in rep["open_items_still_open"]:
        W("  %-6s %s\n         status : %s\n         affects: %s\n"
          % (o["id"], o["title"], o["status"], ", ".join(o["affects"] or [])))
    W("\n")

    W("-- OPEN GAPS NOT CLOSED (closing_report) -------------------------------\n")
    for g in rep["closing_report_open_gaps_not_closed"] or []:
        W("  * %s  [ref: %s]\n" % (g.get("gap"), g.get("ref")))
    W("\n")

    if rep["unevaluated_tier_clauses"]:
        W("-- TIER CLAUSES NOT EVALUATED ------------------------------------------\n")
        for c in rep["unevaluated_tier_clauses"]:
            W("  ! %s\n" % c)
        W("\n")

    tc = rep["tier_computation"] or {}
    W("-- READINESS -----------------------------------------------------------\n")
    W("  declared: %s\n  computed: %s\n\n"
      % (tc.get("readiness_declared"), tc.get("computed_tier_label")))

    W("-- EXPLICITLY OUT OF SCOPE (verbatim from the suite) -------------------\n")
    for s in rep["explicitly_out_of_scope"] or []:
        W("  - %s\n" % " ".join(str(s).split()))
    W("\n")


# ==========================================================================
# Main
# ==========================================================================

def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Execute a frozen v3.0.0 validation suite against a catalog record.")
    ap.add_argument("--record", default=DEFAULT_RECORD)
    ap.add_argument("--schema", default=DEFAULT_SCHEMA)
    ap.add_argument("--suite", default=DEFAULT_SUITE)
    ap.add_argument("--report", default=DEFAULT_REPORT)
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args(argv)

    started = _dt.datetime.now(_dt.timezone.utc).replace(tzinfo=None)

    record_path = os.path.abspath(args.record)
    schema_path = os.path.abspath(args.schema)
    suite_path = os.path.abspath(args.suite)
    report_path = os.path.abspath(args.report)

    for label, p in (("record", record_path), ("schema", schema_path), ("suite", suite_path)):
        if not os.path.isfile(p):
            sys.stderr.write("ERROR: %s file not found at:\n  %s\nThis runner does not "
                             "search the filesystem for moved files. Pass --%s.\n"
                             % (label, p, label))
            return 2

    rdir = os.path.dirname(report_path)
    if not os.path.isdir(rdir) or not os.access(rdir, os.W_OK):
        sys.stderr.write("ERROR: report directory missing or not writable:\n  %s\n"
                         "Not falling back to another location.\n" % rdir)
        return 2

    record, dup_keys = load_record(record_path)
    schema = load_json(schema_path)
    suite = load_suite(suite_path)

    try:
        R = Runner(record, record_path, schema, schema_path, suite, suite_path,
                   dup_keys, started)
    except SuiteContractError as exc:
        sys.stderr.write("\nSUITE CONTRACT ERROR - the run is aborted.\n%s\n\n"
                         "runner_contract.unknown_verb_policy is ERROR: a check this runner "
                         "cannot execute must never be silently skipped, because a skipped "
                         "structural check is indistinguishable from a passing one.\n" % exc)
        return 2

    R.opened_files = [record_path, schema_path, suite_path]

    # ---- entity identity pre-flight (basename only; directory excluded) ----
    basename = os.path.splitext(os.path.basename(record_path))[0]
    scope = R.scope
    comparisons = [OrderedDict([("field", "basename vs scope entity_id"),
                                ("left", basename), ("right", scope.get("entity_id")),
                                ("match", basename == scope.get("entity_id"))])]
    for f in ("entity_id", "entity", "category", "segment_id"):
        comparisons.append(OrderedDict([
            ("field", "record.%s vs scope" % f), ("left", record.get(f)),
            ("right", scope.get(f)), ("match", record.get(f) == scope.get(f))]))
    comparisons.append(OrderedDict([
        ("field", "basename vs record.entity_id"), ("left", basename),
        ("right", record.get("entity_id")), ("match", basename == record.get("entity_id"))]))
    if scope.get("expected_filename"):
        comparisons.append(OrderedDict([
            ("field", "filename vs scope expected_filename"),
            ("left", os.path.basename(record_path)),
            ("right", scope.get("expected_filename")),
            ("match", os.path.basename(record_path) == scope.get("expected_filename"))]))

    ok = all(c["match"] for c in comparisons)
    R.preflight = OrderedDict([
        ("outcome", "PASS" if ok else "FAIL"),
        ("record_path", record_path),
        ("record_directory", os.path.dirname(record_path)),
        ("_note", "The directory component is NOT part of the identity check; XF-001 "
                  "compares the basename only."),
        ("comparisons", comparisons),
    ])
    if not ok:
        sys.stderr.write("\nENTITY IDENTITY PRE-FLIGHT FAILED. Stopping before any test runs.\n")
        for c in comparisons:
            if not c["match"]:
                sys.stderr.write("  MISMATCH  %-34s %r != %r\n"
                                 % (c["field"], c["left"], c["right"]))
        sys.stderr.write("\nXF-001 and XF-013 compare against these values. This runner will "
                         "not pick one as authoritative, and will not edit the record or the "
                         "suite to reconcile them. Say which is authoritative, then re-run.\n")
        return 2

    R.schema_conformance = run_schema_conformance(schema, schema_path, record)
    R.coverage_by_class = compute_coverage(R)

    # ---- execute, in category order, readiness_tier last -------------------
    order = {c: i for i, c in enumerate(KNOWN_CATEGORIES)}
    tests = sorted(suite.get("tests", []), key=lambda t: order.get(t.get("category"), 99))
    try:
        for t in tests:
            R.run_test(t)
    except SuiteContractError as exc:
        sys.stderr.write("\nSUITE CONTRACT ERROR during execution - the run is aborted.\n%s\n"
                         % exc)
        return 2

    for tid in R.tests_by_id:
        if tid not in R.results:
            R.record_result(tid, "skipped",
                            "SKIPPED - the runner produced no result. Runner defect, not a "
                            "record finding.")

    rep = build_report(R, started)
    with open(report_path, "w", encoding="utf-8") as fh:
        json.dump(rep, fh, indent=2, ensure_ascii=False, default=str)

    if not args.quiet:
        print_console(rep)
        sys.stdout.write("Machine-readable report written to:\n  %s\n" % report_path)

    n_fail = rep["summary"]["by_outcome"].get("fail", 0)
    code = 1 if n_fail else 0
    if not args.quiet:
        sys.stdout.write("Exit code %d - %d test(s) with outcome 'fail'. warn, info, gap and "
                         "skipped do not affect the exit code.\n\n" % (code, n_fail))
    return code


if __name__ == "__main__":
    sys.exit(main())
