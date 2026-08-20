import pytest

from app.llm.contract import ContractError, FieldSpec, extract_json, parse, validate

SPEC = FieldSpec(validators={
    "name": lambda v: isinstance(v, str) and bool(v.strip()),
    "count": lambda v: isinstance(v, int) and 0 <= v <= 10,
})


def test_extract_json_from_a_fenced_block():
    assert extract_json('```json\n{"a": 1}\n```') == {"a": 1}


def test_extract_json_from_a_bare_object():
    assert extract_json('here you go: {"a": 1} hope that helps') == {"a": 1}


def test_extract_json_returns_none_when_there_is_no_object():
    assert extract_json("sorry, I cannot help with that") is None


def test_extract_json_returns_none_for_a_json_array():
    # A list is valid JSON but not the contract shape; callers expect a dict.
    assert extract_json("[1, 2, 3]") is None


def test_validate_reports_a_missing_field():
    assert validate({"count": 1}, SPEC) == ["missing required field 'name'"]


def test_validate_reports_an_invalid_value():
    violations = validate({"name": "ok", "count": 99}, SPEC)
    assert violations == ["field 'count' has invalid value 99"]


def test_validate_returns_empty_for_a_good_payload():
    assert validate({"name": "ok", "count": 3}, SPEC) == []


def test_parse_returns_only_the_spec_fields():
    # Extra keys are dropped, so a model cannot smuggle values into a DB write.
    result = parse('{"name": "ok", "count": 3, "sneaky": "drop me"}', SPEC)
    assert result == {"name": "ok", "count": 3}


def test_parse_raises_when_there_is_no_json():
    with pytest.raises(ContractError, match="no JSON object"):
        parse("nope", SPEC)


def test_parse_raises_with_every_violation_listed():
    with pytest.raises(ContractError) as excinfo:
        parse('{"count": 99}', SPEC)
    message = str(excinfo.value)
    assert "missing required field 'name'" in message
    assert "field 'count' has invalid value 99" in message
