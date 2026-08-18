import json

import pytest

from bubble_mcp.vendor.bubble_modules import merge_app, split_app


def _split(tmp_path, payload):  # type: ignore[no-untyped-def]
    source = tmp_path / "sparse-app.bubble"
    source.write_text(json.dumps(payload), encoding="utf-8")
    modules_root = tmp_path / "modules"
    split_app(
        input_path=source,
        out_dir=modules_root,
        app_name="sparse-app",
        force=True,
        pretty=True,
        write_index=True,
    )
    return modules_root / "sparse-app"


def test_split_groups_wire_custom_definitions_by_element_type(tmp_path) -> None:  # type: ignore[no-untyped-def]
    modules = _split(
        tmp_path,
        {
            "_id": "sparse-app",
            "element_definitions": {
                "reCard": {
                    "%x": "CustomDefinition",
                    "id": "rootCard",
                    "%p": {"%nm": "Card"},
                }
            },
        },
    )

    definition = modules / "element_definitions" / "CustomDefinition" / "reCard.json"
    assert definition.exists()
    assert json.loads(
        (modules / "element_definitions" / "__index.json").read_text(encoding="utf-8")
    ) == {"reCard": "CustomDefinition:Card"}


def test_split_catalogs_index_only_reusables_without_changing_round_trip(tmp_path) -> None:  # type: ignore[no-untyped-def]
    payload = {
        "_id": "sparse-app",
        "element_definitions": {
            "rePresent": {
                "workflows": {"wfPresent": {"actions": {}}},
            }
        },
        "_index": {
            "id_to_path": {
                "rootPresent": "%ed.rePresent",
                "childPresent": "%ed.rePresent.%el.childPresent",
                "rootMissing": "%ed.reMissing",
                "childMissing": "%ed.reMissing.%el.childMissing",
                "pageRoot": "%p3.index",
            }
        },
    }
    modules = _split(tmp_path, payload)

    definitions_dir = modules / "element_definitions" / "CustomDefinition"
    present = json.loads((definitions_dir / "rePresent.json").read_text(encoding="utf-8"))
    missing = json.loads((definitions_dir / "reMissing.json").read_text(encoding="utf-8"))
    index = json.loads(
        (modules / "element_definitions" / "__index.json").read_text(encoding="utf-8")
    )

    assert present["workflows"] == {"wfPresent": {"actions": {}}}
    assert present["id"] == "rootPresent"
    assert missing == {
        "_inferred_from_index": True,
        "id": "rootMissing",
        "type": "CustomDefinition",
        "elements": {"childMissing": {"id": "childMissing"}},
    }
    assert set(index) == {"rePresent", "reMissing"}

    merged = tmp_path / "round-trip.bubble"
    merge_app(modules, merged, pretty=True, strict=True)
    assert json.loads(merged.read_text(encoding="utf-8")) == payload


def test_split_index_only_reusables_respects_no_index_option(tmp_path) -> None:  # type: ignore[no-untyped-def]
    source = tmp_path / "sparse-app.bubble"
    source.write_text(
        json.dumps(
            {
                "_id": "sparse-app",
                "element_definitions": {},
                "_index": {"id_to_path": {"rootCard": "%ed.reCard"}},
            }
        ),
        encoding="utf-8",
    )
    modules_root = tmp_path / "modules"

    split_app(
        input_path=source,
        out_dir=modules_root,
        app_name="sparse-app",
        force=True,
        pretty=True,
        write_index=False,
    )

    definitions = modules_root / "sparse-app" / "element_definitions"
    assert (definitions / "CustomDefinition" / "reCard.json").exists()
    assert not (definitions / "__index.json").exists()
    assert not (definitions / "CustomDefinition" / "__index.json").exists()


def test_split_hydrates_typed_sparse_definition_and_preserves_canonical_round_trip(tmp_path) -> None:  # type: ignore[no-untyped-def]
    payload = {
        "_id": "sparse-app",
        "element_definitions": {
            "reCard": {
                "%x": "CustomDefinition",
                "%p": {"%nm": "Card"},
                "%wf": {"wfLoad": {"actions": {}}},
            }
        },
        "_index": {
            "id_to_path": {
                "rootCard": "%ed.reCard",
                "workflowLoad": "%ed.reCard.%wf.wfLoad",
            }
        },
    }
    modules = _split(tmp_path, payload)

    hydrated = json.loads(
        (
            modules / "element_definitions" / "CustomDefinition" / "reCard.json"
        ).read_text(encoding="utf-8")
    )
    manifest = json.loads((modules / "manifest.json").read_text(encoding="utf-8"))

    assert hydrated["id"] == "rootCard"
    assert hydrated["%wf"]["wfLoad"]["id"] == "workflowLoad"
    assert manifest["filenames"]["element_definitions"]["reCard"].startswith("_source/")

    merged = tmp_path / "typed-round-trip.bubble"
    merge_app(modules, merged, pretty=True, strict=True)
    assert json.loads(merged.read_text(encoding="utf-8")) == payload


@pytest.mark.parametrize("source_key", ["%ed", "CustomDefinition", "custom_definitions"])
def test_split_preserves_material_data_from_reusable_aliases(tmp_path, source_key) -> None:  # type: ignore[no-untyped-def]
    payload = {
        "_id": "alias-app",
        source_key: {
            "reCard": {
                "%x": "CustomDefinition",
                "%p": {"%nm": "Alias Card", "width": 320},
            }
        },
        "_index": {"id_to_path": {"rootCard": f"{source_key}.reCard"}},
    }
    modules = _split(tmp_path, payload)

    hydrated = json.loads(
        (
            modules / "element_definitions" / "CustomDefinition" / "reCard.json"
        ).read_text(encoding="utf-8")
    )

    assert hydrated["%p"] == {"%nm": "Alias Card", "width": 320}
    assert hydrated["id"] == "rootCard"

    merged = tmp_path / f"{source_key.replace('%', 'percent')}-round-trip.bubble"
    merge_app(modules, merged, pretty=True, strict=True)
    assert json.loads(merged.read_text(encoding="utf-8")) == payload


def test_split_names_index_only_reusables_from_custom_name_index(tmp_path) -> None:  # type: ignore[no-untyped-def]
    payload = {
        "_id": "sparse-app",
        "_index": {
            "id_to_path": {
                "rootCard": "%ed.reCard",
                "childCard": "%ed.reCard.%el.childCard",
            },
            "custom_name_to_id": {
                "Card Header": {"custom_id": "reCard", "display": "Card Header"},
            },
        },
    }
    modules = _split(tmp_path, payload)

    definition = json.loads(
        (
            modules / "element_definitions" / "CustomDefinition" / "reCard.json"
        ).read_text(encoding="utf-8")
    )
    index = json.loads(
        (modules / "element_definitions" / "__index.json").read_text(encoding="utf-8")
    )

    assert definition["_inferred_from_index"] is True
    assert definition["name"] == "Card Header"
    assert index == {"reCard": "CustomDefinition:Card Header"}

    merged = tmp_path / "named-round-trip.bubble"
    merge_app(modules, merged, pretty=True, strict=True)
    assert json.loads(merged.read_text(encoding="utf-8")) == payload


def test_split_reports_sparse_reusable_counts(tmp_path, capsys) -> None:  # type: ignore[no-untyped-def]
    _split(
        tmp_path,
        {
            "_id": "sparse-app",
            "element_definitions": {
                "reMaterial": {"%x": "CustomDefinition", "%p": {"%nm": "Material"}}
            },
            "_index": {
                "id_to_path": {
                    "rootMaterial": "%ed.reMaterial",
                    "rootGhostA": "%ed.reGhostA",
                    "rootGhostB": "%ed.reGhostB",
                }
            },
        },
    )

    output = capsys.readouterr().out
    assert "Reusable definitions: 1 material, 2 index-only" in output
    assert "WARNING: most reusable definitions were inferred" in output


def test_split_skips_orphan_deep_only_reusable_references(tmp_path) -> None:  # type: ignore[no-untyped-def]
    # reGhost appears only inside a deep %ed path with no length-2 root entry:
    # it is a stale reference the editor cannot resolve, so no skeleton file.
    modules = _split(
        tmp_path,
        {
            "_id": "sparse-app",
            "_index": {
                "id_to_path": {
                    "rootReal": "%ed.reReal",
                    "ghostAction": "%ed.reGhost.%wf.wfX.actions.0",
                }
            },
        },
    )
    definitions = modules / "element_definitions" / "CustomDefinition"
    assert (definitions / "reReal.json").exists()
    assert not (definitions / "reGhost.json").exists()
    index = json.loads(
        (modules / "element_definitions" / "__index.json").read_text(encoding="utf-8")
    )
    assert set(index) == {"reReal"}


def test_split_force_removes_stale_index_only_reusable_modules(tmp_path) -> None:  # type: ignore[no-untyped-def]
    modules = _split(
        tmp_path,
        {
            "_id": "sparse-app",
            "_index": {"id_to_path": {"oldRoot": "%ed.reOld"}},
        },
    )
    source = tmp_path / "sparse-app.bubble"
    source.write_text(
        json.dumps(
            {
                "_id": "sparse-app",
                "_index": {"id_to_path": {"newRoot": "%ed.reNew"}},
            }
        ),
        encoding="utf-8",
    )

    split_app(
        input_path=source,
        out_dir=tmp_path / "modules",
        app_name="sparse-app",
        force=True,
        pretty=True,
        write_index=True,
    )

    definitions = modules / "element_definitions" / "CustomDefinition"
    index = json.loads(
        (modules / "element_definitions" / "__index.json").read_text(encoding="utf-8")
    )
    assert not (definitions / "reOld.json").exists()
    assert (definitions / "reNew.json").exists()
    assert index == {"reNew": "CustomDefinition:reNew"}


def test_split_publishes_reusable_element_typed_roots_as_custom_definitions(tmp_path) -> None:  # type: ignore[no-untyped-def]
    modules = _split(
        tmp_path,
        {
            "_id": "legacy-app",
            "element_definitions": {
                "reLegacy": {
                    "%x": "ReusableElement",
                    "%p": {"%nm": "Legacy reusable"},
                }
            },
        },
    )

    published = json.loads(
        (
            modules / "element_definitions" / "CustomDefinition" / "reLegacy.json"
        ).read_text(encoding="utf-8")
    )

    assert published["%x"] == "ReusableElement"
    assert not (
        modules / "element_definitions" / "ReusableElement" / "reLegacy.json"
    ).exists()


def test_merge_includes_extra_canonical_definition_below_source_namespace(tmp_path) -> None:  # type: ignore[no-untyped-def]
    modules = _split(
        tmp_path,
        {
            "_id": "source-app",
            "element_definitions": {
                "reCard": {"%x": "CustomDefinition", "%p": {"%nm": "Card"}}
            },
        },
    )
    extra = modules / "element_definitions" / "_source" / "CustomDefinition" / "reExtra.json"
    extra.write_text(
        json.dumps({"%x": "CustomDefinition", "%p": {"%nm": "Extra"}}),
        encoding="utf-8",
    )

    merged = tmp_path / "extra-canonical.bubble"
    merge_app(modules, merged, pretty=True, strict=True)
    definitions = json.loads(merged.read_text(encoding="utf-8"))["element_definitions"]

    assert definitions["reExtra"]["%p"]["%nm"] == "Extra"
