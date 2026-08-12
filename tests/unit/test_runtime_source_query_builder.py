import pytest

from bubble_mcp.aria_runtime.source_query_builder import (
    build_message_chain,
    build_search_source_expression,
    normalize_constraints,
)


def test_build_message_chain_handles_empty_and_dotted_paths() -> None:
    assert build_message_chain(None) is None
    assert build_message_chain(" . ") is None
    assert build_message_chain("company.owner.name") == {
        "%x": "Message",
        "%nm": "company",
        "is_slidable": False,
        "%n": {
            "%x": "Message",
            "%nm": "owner",
            "is_slidable": False,
            "%n": {"%x": "Message", "%nm": "name", "is_slidable": False},
        },
    }


def test_normalize_constraints_supports_bubble_and_friendly_shapes() -> None:
    assert normalize_constraints(None) is None
    assert normalize_constraints([]) is None
    assert normalize_constraints({}) is None
    assert normalize_constraints({"%k": "status", "%c2": "is", "%v": "active"}) == {
        "0": {"%k": "status", "%c2": "is", "%v": "active"}
    }
    assert normalize_constraints(
        [
            {"field": "name", "operator": "contains", "value_expr": {"%x": "Message"}},
            {"key": "age", "op": "greater than", "value_expression": 18},
            {"field": "enabled", "constraint": "equals", "value": True},
            {"field": "optional", "constraint_type": "is empty"},
        ]
    ) == {
        "0": {"%k": "name", "%c2": "contains", "%v": {"%x": "Message"}},
        "1": {"%k": "age", "%c2": "greater than", "%v": 18},
        "2": {"%k": "enabled", "%c2": "equals", "%v": True},
        "3": {"%k": "optional", "%c2": "is empty", "%v": None},
    }


def test_normalize_constraints_orders_maps_and_defaults_operator() -> None:
    assert normalize_constraints(
        {
            "9": {"field": "last", "operator": ""},
            "1": {"field": "first"},
        }
    ) == {
        "0": {"%k": "first", "%c2": "equals", "%v": None},
        "1": {"%k": "last", "%c2": "equals", "%v": None},
    }


@pytest.mark.parametrize(
    ("constraints", "message"),
    [
        ("invalid", "JSON object or JSON array"),
        (["invalid"], "Each constraint must be an object"),
        ([{"operator": "equals"}], "missing field key"),
    ],
)
def test_normalize_constraints_rejects_invalid_inputs(constraints: object, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        normalize_constraints(constraints)


def test_build_search_source_expression_supports_all_options() -> None:
    payload = build_search_source_expression(
        "Customer",
        constraints={"field": "active", "value": True},
        ignore_empty_constraints=True,
        sort_field="created date",
        sort_desc=True,
        dynamic_sort_field={"%x": "Message"},
        geo_reference={"lat": 1},
        result_from_field="company.owner",
    )

    assert payload["%p"] == {
        "%t5": "Customer",
        "%co": {"0": {"%k": "active", "%c2": "equals", "%v": True}},
        "ignore_empty_constraints": True,
        "%sf": "created date",
        "%d2": True,
        "dynamic_sort_field": {"%x": "Message"},
        "geo_reference": {"lat": 1},
    }
    assert payload["%n"]["%nm"] == "company"


def test_build_search_source_expression_minimal_and_validation() -> None:
    assert build_search_source_expression(" Thing ") == {"%x": "Search", "%p": {"%t5": "Thing"}}
    with pytest.raises(ValueError, match="query_source_type is required"):
        build_search_source_expression(" ")
