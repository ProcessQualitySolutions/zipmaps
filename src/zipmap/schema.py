"""JSON Schema validation for map-item schemas.

Uses the real ``jsonschema`` package when it is installed; otherwise falls
back to a bundled validator covering the subset of draft-07 that map-item
schemas realistically use: type, enum, const, required, properties,
additionalProperties, pattern, min/max (number, length, items), items,
anyOf, allOf, oneOf. Unknown keywords are ignored, matching JSON Schema
semantics.
"""

from __future__ import annotations

import re
from typing import Any

_TYPE_MAP = {
    "object": dict,
    "array": list,
    "string": str,
    "boolean": bool,
    "null": type(None),
}


#: Built validators, keyed by the identity of the schema dict they came from.
#: Constructing one costs ~7 us of the ~29 us it takes to validate an item
#: (jsonschema 4.x builds a referencing Resource, Registry, and Resolver every
#: time), and callers validate every item in a data file against the same
#: schema object. A validator holds no per-instance state across iter_errors,
#: so reuse is safe. Each entry keeps a reference to its schema, which pins
#: that id() for the life of the process, so ids can never be recycled into a
#: false hit. The cache is therefore bounded by the number of distinct schema
#: objects loaded — a handful per run.
#:
#: The one thing this cannot see is a schema dict mutated in place after first
#: use. Nothing in the package does that: schemas are parsed fresh in
#: validate_folder and treated as read-only.
_VALIDATORS: dict[int, tuple[dict, Any]] = {}


def _validator_for(jsonschema, schema: dict):
    hit = _VALIDATORS.get(id(schema))
    if hit is not None:
        return hit[1]
    validator = jsonschema.validators.validator_for(schema)(schema)
    _VALIDATORS[id(schema)] = (schema, validator)
    return validator


def validate_instance(instance: Any, schema: dict) -> list[str]:
    """Validate instance against schema; return a list of error strings."""
    try:
        import jsonschema  # type: ignore
    except ImportError:
        errors: list[str] = []
        _check(instance, schema, "$", errors)
        return errors
    validator = _validator_for(jsonschema, schema)
    out = []
    for err in validator.iter_errors(instance):
        path = "$" + "".join(
            f"[{p}]" if isinstance(p, int) else f".{p}" for p in err.absolute_path
        )
        out.append(f"{path}: {err.message}")
    return sorted(out)


def _type_ok(value: Any, tname: str) -> bool:
    if tname == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if tname == "integer":
        return (
            isinstance(value, int) and not isinstance(value, bool)
        ) or (isinstance(value, float) and value.is_integer())
    expected = _TYPE_MAP.get(tname)
    if expected is None:
        return True  # unknown type name: be permissive
    if expected is not bool and isinstance(value, bool):
        return False
    return isinstance(value, expected)


def _check(value: Any, schema: Any, path: str, errors: list[str]) -> None:
    if schema is True or schema == {}:
        return
    if schema is False:
        errors.append(f"{path}: no value allowed here")
        return
    if not isinstance(schema, dict):
        return

    stype = schema.get("type")
    if stype is not None:
        types = stype if isinstance(stype, list) else [stype]
        if not any(_type_ok(value, t) for t in types):
            errors.append(f"{path}: expected type {' or '.join(types)}, got {type(value).__name__}")
            return  # further keyword checks would just cascade

    if "const" in schema and value != schema["const"]:
        errors.append(f"{path}: must equal {schema['const']!r}")
    if "enum" in schema and value not in schema["enum"]:
        errors.append(f"{path}: {value!r} is not one of {schema['enum']!r}")

    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in schema and value < schema["minimum"]:
            errors.append(f"{path}: {value} is less than minimum {schema['minimum']}")
        if "maximum" in schema and value > schema["maximum"]:
            errors.append(f"{path}: {value} is greater than maximum {schema['maximum']}")
        if "exclusiveMinimum" in schema and value <= schema["exclusiveMinimum"]:
            errors.append(f"{path}: {value} must be > {schema['exclusiveMinimum']}")
        if "exclusiveMaximum" in schema and value >= schema["exclusiveMaximum"]:
            errors.append(f"{path}: {value} must be < {schema['exclusiveMaximum']}")

    if isinstance(value, str):
        if "minLength" in schema and len(value) < schema["minLength"]:
            errors.append(f"{path}: shorter than minLength {schema['minLength']}")
        if "maxLength" in schema and len(value) > schema["maxLength"]:
            errors.append(f"{path}: longer than maxLength {schema['maxLength']}")
        if "pattern" in schema and not re.search(schema["pattern"], value):
            errors.append(f"{path}: {value!r} does not match pattern {schema['pattern']!r}")

    if isinstance(value, dict):
        props = schema.get("properties", {})
        for name in schema.get("required", []):
            if name not in value:
                errors.append(f"{path}: missing required property {name!r}")
        for name, sub in props.items():
            if name in value:
                _check(value[name], sub, f"{path}.{name}", errors)
        addl = schema.get("additionalProperties", True)
        if addl is False:
            for name in value:
                if name not in props:
                    errors.append(f"{path}: additional property {name!r} is not allowed")
        elif isinstance(addl, dict):
            for name in value:
                if name not in props:
                    _check(value[name], addl, f"{path}.{name}", errors)

    if isinstance(value, list):
        if "minItems" in schema and len(value) < schema["minItems"]:
            errors.append(f"{path}: fewer than minItems {schema['minItems']}")
        if "maxItems" in schema and len(value) > schema["maxItems"]:
            errors.append(f"{path}: more than maxItems {schema['maxItems']}")
        items = schema.get("items")
        if isinstance(items, (dict, bool)):
            for i, elem in enumerate(value):
                _check(elem, items, f"{path}[{i}]", errors)

    for sub in schema.get("allOf", []):
        _check(value, sub, path, errors)
    if "anyOf" in schema:
        if not any(_matches(value, sub) for sub in schema["anyOf"]):
            errors.append(f"{path}: does not match any allowed alternative (anyOf)")
    if "oneOf" in schema:
        matches = sum(1 for sub in schema["oneOf"] if _matches(value, sub))
        if matches != 1:
            errors.append(f"{path}: must match exactly one alternative (oneOf), matched {matches}")


def _matches(value: Any, schema: Any) -> bool:
    probe: list[str] = []
    _check(value, schema, "$", probe)
    return not probe
