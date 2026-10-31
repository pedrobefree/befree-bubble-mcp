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
    assert stats.collisions == 0


def test_double_percent_is_an_escape_for_a_literal_key() -> None:
    decoded, stats = decode_keys({"%%el": 1, "%%custom": {"%x": "Text"}})

    assert decoded == {"%el": 1, "%custom": {"type": "Text"}}
    assert stats.escaped_keys == 2
    assert stats.decoded_keys == 1
    assert stats.escaped_paths == {("%el",), ("%custom",)}
    # The literal keys are what the user wrote; validation must not flag them as undecoded.
    assert percent_key_paths(decoded, allowed=stats.escaped_paths) == []
    assert percent_key_paths(decoded) == [("%el",), ("%custom",)]


def test_collision_merges_and_the_shrunk_form_wins_a_conflict() -> None:
    node = {
        "%x": "Group",
        "type": "Text",
        "%p": {"a": 1, "b": 2},
        "properties": {"b": 3, "c": 4},
    }

    decoded, stats = decode_keys(node)

    assert decoded == {"type": "Group", "properties": {"a": 1, "b": 2, "c": 4}}
    assert stats.collisions == 2
    assert stats.collision_conflicts == 2
    assert stats.collision_paths == [("type",), ("properties",)]


def test_collision_with_equal_values_is_counted_without_a_conflict() -> None:
    decoded, stats = decode_keys({"%nm": "header", "name": "header"})

    assert decoded == {"name": "header"}
    assert stats.collisions == 1
    assert stats.collision_conflicts == 0


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
