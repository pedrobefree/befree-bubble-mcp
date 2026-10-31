from __future__ import annotations

import pytest

from bubble_mcp.context.editor_keys import (
    decode_keys,
    extract_key_table_from_bundle,
    load_key_table,
    percent_key_paths,
    reverse_key_table,
)


def test_versioned_table_is_the_editor_mapping() -> None:
    table = load_key_table()

    assert len(table) == 141
    reverse = reverse_key_table()
    assert len(reverse) == 141
    assert reverse["el"] == "elements"
    assert reverse["p"] == "properties"
    assert reverse["x"] == "type"
    assert reverse["nm"] == "name"
    assert reverse["wf"] == "workflows"
    assert reverse["ed"] == "element_definitions"
    # The editor refuses to build a table with these, so the copy must not carry them either.
    assert all("%" not in short and short == short.lower() for short in table.values())
    assert all("%" not in long_name for long_name in table)


def test_every_shrunk_key_in_the_table_decodes() -> None:
    table = load_key_table()
    shrunk = {f"%{short}": index for index, short in enumerate(table.values())}

    decoded, stats = decode_keys(shrunk)

    assert set(decoded) == set(table)
    assert stats.decoded_keys == len(table)
    assert not stats.unknown_keys
    assert percent_key_paths(decoded) == []


def test_hydrated_reusable_decodes_recursively() -> None:
    hydrated = {
        "%x": "CustomDefinition",
        "%nm": "header",
        "id": "bAb",
        "%p": {"%w": 320, "%h": 60},
        "%el": {"bAc": {"%x": "Text", "%p": {"%3": "hi"}, "%s": [{"%c": {"%x": "True"}}]}},
    }

    decoded, stats = decode_keys(hydrated)

    assert decoded == {
        "type": "CustomDefinition",
        "name": "header",
        "id": "bAb",
        "properties": {"width": 320, "height": 60},
        "elements": {
            "bAc": {
                "type": "Text",
                "properties": {"text": "hi"},
                "states": [{"condition": {"type": "True"}}],
            }
        },
    }
    assert stats.discarded_paths == []


def test_double_percent_is_an_escape_for_a_literal_key() -> None:
    decoded, stats = decode_keys({"%%el": 1, "%%custom": {"%x": "Text"}})

    assert decoded == {"%el": 1, "%custom": {"type": "Text"}}
    assert stats.escaped_keys == 2
    assert stats.decoded_keys == 1
    assert stats.escaped_paths == {("%el",), ("%custom",)}
    # The literal keys are what the user wrote; validation must not flag them as undecoded.
    assert percent_key_paths(decoded, allowed=stats.escaped_paths) == []
    assert percent_key_paths(decoded) == [("%el",), ("%custom",)]


def test_collision_keeps_the_shrunk_form_and_discards_the_long_copy() -> None:
    # Measured shape: the shrunk data source holds the constraints the editor shows; the long copy
    # is a stale leftover with a single keyless item. Merging would resurrect it.
    node = {
        "%ds": {"%p": {"%co": {"0": {"key": "a"}, "1": {"key": "b"}}}},
        "data_source": {"properties": {"constraints": {"1": {"value": "stale"}}}, "extra": 1},
        "%x": "Group",
        "type": "Text",
    }

    decoded, stats = decode_keys(node, path=("el",))

    assert decoded == {
        "data_source": {"properties": {"constraints": {"0": {"key": "a"}, "1": {"key": "b"}}}},
        "type": "Group",
    }
    assert stats.discarded_paths == [("el", "data_source"), ("el", "type")]
    assert stats.discarded_differing == 2
    assert stats.to_dict()["collisions"] == 2


def test_collision_with_an_equal_long_copy_is_counted_but_not_differing() -> None:
    decoded, stats = decode_keys({"%nm": "header", "name": "header"})

    assert decoded == {"name": "header"}
    assert stats.discarded_paths == [("name",)]
    assert stats.discarded_differing == 0


def test_top_level_keys_are_decoded_too() -> None:
    decoded, _ = decode_keys({"%e1": {"%d": "Event"}, "user": {"%d": "User"}})

    assert decoded == {"event": {"display": "Event"}, "user": {"display": "User"}}


def test_unknown_abbreviation_is_kept_and_reported() -> None:
    decoded, stats = decode_keys({"%zz": 1, "%x": "Text"})

    assert decoded == {"%zz": 1, "type": "Text"}
    assert stats.unknown_keys == {"%zz": 1}
    assert percent_key_paths(decoded) == [("%zz",)]


def test_bundle_extraction_reads_the_mapping_literal() -> None:
    bundle = (
        'var a;mapping={x:1};init();mapping={display_sender_name:"d7",bgcolor:"bgc",'
        'type:"x","quoted_key":"qk"},not_shrunk={provider:!0}'
    )

    assert extract_key_table_from_bundle(bundle) == {
        "display_sender_name": "d7",
        "bgcolor": "bgc",
        "type": "x",
        "quoted_key": "qk",
    }


def test_bundle_extraction_refuses_a_missing_or_ambiguous_table() -> None:
    with pytest.raises(ValueError, match="bgcolor"):
        extract_key_table_from_bundle("mapping={type:\"x\"}")
    with pytest.raises(ValueError, match="already|both"):
        extract_key_table_from_bundle('mapping={bgcolor:"bgc",background:"bgc"}')
