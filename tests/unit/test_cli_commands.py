import json
from pathlib import Path

from bubble_mcp.aria_runtime.bubble_cli import BubbleCLI
import bubble_mcp.cli.main as cli_module
from bubble_mcp.cli.main import main
from bubble_mcp.core.config import BubbleMcpSettings, BubbleProfile, save_settings
from bubble_mcp.sessions.store import session_from_payload


FIXTURE = Path("tests/fixtures/context/synthetic-app-context.json")


def first_change(payload: dict, intent_name: str) -> dict:  # type: ignore[type-arg]
    return next(change for change in payload["changes"] if change.get("intent", {}).get("name") == intent_name)


def payload_from_dry_run_output(output: str) -> dict:  # type: ignore[type-arg]
    return json.loads(output[output.index("{") :])


def test_delete_data_field_emits_bubble_editor_delete_contract(tmp_path, capsys) -> None:  # type: ignore[no-untyped-def]
    app_path = tmp_path / "app.json"
    app_path.write_text(
        json.dumps(
            {
                "user_types": {
                    "user": {
                        "%d": "User",
                        "%f3": {
                            "campo_novo_text": {
                                "%d": "campo novo",
                                "%v": "text",
                            }
                        },
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    cli = BubbleCLI(app_json_path=str(app_path), appname="courselaunch")

    assert cli.delete_data_field("user", "campo_novo_text", dry_run=True) is True

    payload = payload_from_dry_run_output(capsys.readouterr().out)
    changes = payload["changes"]
    assert len(changes) == 2
    assert changes[0]["intent"]["name"] == "WriteCustomField"
    assert changes[0]["path_array"] == ["user_types", "user", "%f3", "campo_novo_text", "%del"]
    assert changes[0]["body"] is True
    assert changes[1]["intent"]["name"] == "WriteCustomField"
    assert changes[1]["path_array"] == ["user_types", "user", "%f3", "campo_novo_text", "%d"]
    assert changes[1]["body"] == "campo novo - deleted"


def test_delete_data_field_resolves_display_name_to_internal_custom_type_key(tmp_path, capsys) -> None:  # type: ignore[no-untyped-def]
    app_path = tmp_path / "app.json"
    app_path.write_text(
        json.dumps(
            {
                "user_types": {
                    "user": {
                        "%d": "User",
                        "%f3": {
                            "teste_delete_custom_enrollment": {
                                "%d": "teste_delete",
                                "%v": "custom.enrollment",
                            }
                        },
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    cli = BubbleCLI(app_json_path=str(app_path), appname="courselaunch")

    assert cli.delete_data_field("user", "teste_delete", dry_run=True) is True

    payload = payload_from_dry_run_output(capsys.readouterr().out)
    changes = payload["changes"]
    assert changes[0]["path_array"] == ["user_types", "user", "%f3", "teste_delete_custom_enrollment", "%del"]
    assert changes[0]["body"] is True
    assert changes[1]["path_array"] == ["user_types", "user", "%f3", "teste_delete_custom_enrollment", "%d"]
    assert changes[1]["body"] == "teste_delete - deleted"


def test_privacy_rule_tools_emit_bubble_editor_contracts(tmp_path, capsys) -> None:  # type: ignore[no-untyped-def]
    app_path = tmp_path / "app.json"
    app_path.write_text(
        json.dumps(
            {
                "user_types": {
                    "testimonial": {
                        "%d": "Testimonial",
                        "%f3": {
                            "avatar_image": {"%d": "avatar", "%v": "image"},
                            "public_boolean": {"%d": "public", "%v": "yes_no"},
                        },
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    cli = BubbleCLI(app_json_path=str(app_path), appname="courselaunch")

    assert cli.create_privacy_rule("testimonial", dry_run=True, id_counter=20000318) is True

    payload = payload_from_dry_run_output(capsys.readouterr().out)
    changes = payload["changes"]
    assert changes[0]["intent"]["name"] == "ChangeAppSetting"
    assert changes[0]["path_array"] == ["user_types", "testimonial", "privacy_role", "everyone"]
    assert changes[0]["body"]["permissions"]["non_filterable_fields"]["avatar_image"] is True
    assert changes[1]["path_array"] == ["user_types", "testimonial", "privacy_role", "new_rule_"]
    assert changes[1]["body"] == {
        "%d": "New rule",
        "permissions": {
            "view_all": True,
            "view_attachments": True,
            "search_for": True,
            "auto_binding": False,
        },
    }
    assert changes[2] == {"type": "id_counter", "value": 20000318}

    assert cli.set_privacy_rule_name("testimonial", "new_rule_", "public_testimonial", dry_run=True) is True
    payload = payload_from_dry_run_output(capsys.readouterr().out)
    assert payload["changes"][0]["path_array"] == ["user_types", "testimonial", "privacy_role", "new_rule_", "%d"]
    assert payload["changes"][0]["body"] == "public_testimonial"

    condition = {
        "%x": "InjectedValue",
        "%n": {
            "%x": "Message",
            "%nm": "public_boolean",
            "is_slidable": False,
            "%n": {"%x": "Message", "%nm": "is_true", "is_slidable": False},
        },
        "is_slidable": False,
        "said": "Y291cnNlbGF1bmNo",
    }
    assert cli.set_privacy_rule_condition("testimonial", "new_rule_", condition, dry_run=True) is True
    payload = payload_from_dry_run_output(capsys.readouterr().out)
    assert payload["changes"][0]["path_array"] == ["user_types", "testimonial", "privacy_role", "new_rule_", "%c"]
    assert payload["changes"][0]["body"] == condition

    assert cli.set_privacy_rule_field_visibility(
        "testimonial",
        "new_rule_",
        view_all=False,
        view_fields=["avatar_image", "public_boolean"],
        dry_run=True,
    ) is True
    payload = payload_from_dry_run_output(capsys.readouterr().out)
    assert payload["changes"][0]["path_array"] == [
        "user_types", "testimonial", "privacy_role", "new_rule_", "permissions", "view_all"
    ]
    assert payload["changes"][0]["body"] is False
    assert payload["changes"][1]["path_array"] == [
        "user_types", "testimonial", "privacy_role", "new_rule_", "permissions", "view_fields"
    ]
    assert payload["changes"][1]["body"] == {"0": "avatar_image", "1": "public_boolean"}

    assert cli.set_privacy_rule_auto_binding(
        "testimonial",
        "new_rule_",
        True,
        binding_fields="avatar_image",
        dry_run=True,
    ) is True
    payload = payload_from_dry_run_output(capsys.readouterr().out)
    assert payload["changes"][0]["path_array"][-1] == "auto_binding"
    assert payload["changes"][0]["body"] is True
    assert payload["changes"][1]["path_array"][-1] == "binding_fields"
    assert payload["changes"][1]["body"] == {"0": "avatar_image"}

    assert cli.delete_privacy_rule("testimonial", "new_rule_1", dry_run=True) is True
    payload = payload_from_dry_run_output(capsys.readouterr().out)
    assert payload["changes"][0]["path_array"] == ["user_types", "testimonial", "privacy_role", "new_rule_1"]
    assert payload["changes"][0]["body"] is None


def test_update_name_renames_element_in_reusable(tmp_path, capsys) -> None:  # type: ignore[no-untyped-def]
    app_path = tmp_path / "app.json"
    app_path.write_text(
        json.dumps(
            {
                "element_definitions": {
                    "bTHce": {
                        "name": "Popup login",
                        "elements": {
                            "bTHcz": {
                                "id": "elGroupLogin",
                                "name": "Group login",
                                "elements": {},
                            }
                        },
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    cli = BubbleCLI(app_json_path=str(app_path), appname="courselaunch")

    assert cli.update_name("Popup login", "Group login", "Grupo Login", dry_run=True) is True

    payload = payload_from_dry_run_output(capsys.readouterr().out)
    changes = payload["changes"]
    assert changes[0]["body"] == "Grupo Login"
    assert changes[0]["path_array"][-1] == "%nm"
    assert changes[1]["body"] == "Grupo Login"
    assert changes[1]["path_array"][-1] == "%dn"


def test_update_name_exact_default_name_match_wins_over_earlier_fuzzy_text_match(tmp_path, capsys) -> None:  # type: ignore[no-untyped-def]
    # bTHdq is a Text element whose content is "Login". Its synthesized search
    # candidate "Text Login" contains "text l" (the target's default name,
    # lowercased) as a text-prefix, and it appears before the real target in
    # traversal order. Without an exact-match-first rule, searching for
    # "Text L" would silently resolve to bTHdq instead of bTKyF.
    app_path = tmp_path / "app.json"
    app_path.write_text(
        json.dumps(
            {
                "element_definitions": {
                    "bTHce": {
                        "name": "Popup login",
                        "elements": {
                            "bTHdq": {
                                "id": "elTextLogin",
                                "default_name": "Text C",
                                "type": "Text",
                                "properties": {"text": {"entries": {"0": "Login"}}},
                            },
                            "bTKyF": {
                                "id": "elTextL",
                                "default_name": "Text L",
                                "type": "Text",
                                "properties": {"text": {"entries": {"0": "Email"}}},
                            },
                        },
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    cli = BubbleCLI(app_json_path=str(app_path), appname="courselaunch")

    assert cli.update_name("Popup login", "Text L", "Texto Label Email Login", dry_run=True) is True

    payload = payload_from_dry_run_output(capsys.readouterr().out)
    changes = payload["changes"]
    assert changes[0]["path_array"] == ["%ed", "bTHce", "%el", "bTKyF", "%nm"]
    assert changes[1]["path_array"] == ["%ed", "bTHce", "%el", "bTKyF", "%dn"]


def test_cli_context_summary(capsys) -> None:  # type: ignore[no-untyped-def]
    assert main(["context", "summary", "--file", str(FIXTURE)]) == 0

    payload = json.loads(capsys.readouterr().out)

    assert payload["ok"] is True
    assert payload["summary"]["app_id"] == "synthetic-app"


def test_cli_context_find_exact_avoids_fuzzy_matches(capsys) -> None:  # type: ignore[no-untyped-def]
    assert main(["context", "find", "user email", "--file", str(FIXTURE), "--exact"]) == 0

    payload = json.loads(capsys.readouterr().out)

    assert payload["ok"] is True
    assert payload["results"] == []

    assert main(["context", "find", "page:index", "--file", str(FIXTURE), "--exact", "--no-include-metadata"]) == 0

    payload = json.loads(capsys.readouterr().out)

    assert payload["query"] == "page:index"
    assert payload["count"] == 1
    assert payload["limit"] == 10
    assert payload["truncated"] is False
    assert payload["exact"] is True
    assert payload["include_metadata"] is False
    assert payload["results"][0]["id"] == "page:index"
    assert payload["results"][0]["match"] == "exact"
    assert payload["results"][0]["match_field"] == "id"
    assert payload["results"][0]["match_value"] == "page:index"
    assert "metadata" not in payload["results"][0]


def test_cli_context_find_can_resolve_context_from_profile(tmp_path, monkeypatch, capsys) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path))
    context_path = tmp_path / "client-context.json"
    context_path.write_text(FIXTURE.read_text(encoding="utf-8"), encoding="utf-8")
    save_settings(
        BubbleMcpSettings(
            config_dir=tmp_path,
            default_profile="client",
            profiles={
                "client": BubbleProfile(
                    name="client",
                    app_id="synthetic-app",
                    appname="synthetic-app",
                    app_json_path=str(context_path),
                )
            },
        )
    )

    assert main(["context", "find", "page:index", "--profile", "client", "--exact", "--no-include-metadata"]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["count"] == 1
    assert payload["exact"] is True
    assert payload["include_metadata"] is False
    assert payload["results"][0]["id"] == "page:index"
    assert "metadata" not in payload["results"][0]


def test_cli_profile_status_reports_existing_profile(tmp_path, monkeypatch, capsys) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path))
    save_settings(
        BubbleMcpSettings(
            config_dir=tmp_path,
            default_profile="client",
            profiles={"client": BubbleProfile(name="client", app_id="client-app", appname="client-app")},
        )
    )

    assert main(["profile", "status", "--profile", "client"]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["ready"] is False
    assert payload["profile"]["app_id"] == "client-app"


def test_cli_transfer_inventory_uses_source_profile_context(tmp_path, monkeypatch, capsys) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path))
    context_path = tmp_path / "contexts" / "source" / "source-app-context.json"
    context_path.parent.mkdir(parents=True)
    context_path.write_text(
        json.dumps(
            {
                "app_id": "source-app",
                "source": "test",
                "nodes": [
                    {"id": "page:index", "label": "index", "type": "page", "metadata": {"bubble_id": "bPage"}},
                    {
                        "id": "element:bHero",
                        "label": "gp_Hero",
                        "type": "element",
                        "metadata": {"bubble_id": "bHero", "properties": {"%x": "Group", "%p": {"%nm": "gp_Hero"}}},
                    },
                ],
                "edges": [{"source": "page:index", "target": "element:bHero", "type": "contains"}],
            }
        ),
        encoding="utf-8",
    )
    save_settings(
        BubbleMcpSettings(
            config_dir=tmp_path,
            default_profile=None,
            profiles={"source": BubbleProfile(name="source", app_id="source-app", appname="source-app")},
        )
    )

    assert main(
        [
            "transfer",
            "inventory",
            "--source-profile",
            "source",
            "--source-type",
            "element",
            "--source-ref",
            "gp_Hero",
        ]
    ) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["source"]["profile"] == "source"
    assert payload["counts"]["nodes"] == 1
    assert payload["counts"]["dependencies"] == 0
    assert payload["dependencies"] == []


def test_cli_framework_list_generate_and_status(tmp_path, monkeypatch, capsys) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path / "config"))

    assert main(["framework", "list"]) == 0
    listed = json.loads(capsys.readouterr().out)
    assert {item["id"] for item in listed["frameworks"]} == {"bmad", "sdd", "superpowers"}

    output_dir = tmp_path / "framework-output"
    assert (
        main(
            [
                "framework",
                "generate",
                "--framework",
                "superpowers",
                "--profile",
                "cliente2",
                "--objective",
                "Implement checkout",
                "--scope",
                "checkout page",
                "--context-summary",
                '{"pages":2}',
                "--output-dir",
                str(output_dir),
            ]
        )
        == 0
    )
    generated = json.loads(capsys.readouterr().out)
    assert generated["ok"] is True
    assert generated["framework"] == "superpowers"
    assert (output_dir / "superpowers" / "cliente2").exists()

    assert (
        main(
            [
                "framework",
                "status",
                "--framework",
                "superpowers",
                "--profile",
                "cliente2",
                "--output-dir",
                str(output_dir),
            ]
        )
        == 0
    )
    status = json.loads(capsys.readouterr().out)
    assert status["ok"] is True
    assert status["status"][0]["artifact_count"] == 1


def test_cli_language_index_query_detail_and_pack(tmp_path, monkeypatch, capsys) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path))

    assert main(["language", "index", "--profile", "cliente2"]) == 0
    index = json.loads(capsys.readouterr().out)
    assert index["registry_version"].startswith("sha256:")

    assert main(["language", "query", "create button", "--family", "visual_editor", "--limit", "5"]) == 0
    query = json.loads(capsys.readouterr().out)
    assert query["matches"]

    assert main(["language", "detail", "create_button", "--detail", "full"]) == 0
    detail = json.loads(capsys.readouterr().out)
    assert detail["tools"][0]["name"] == "create_button"
    assert "inputSchema" in detail["tools"][0]

    assert (
        main(
            [
                "language",
                "framework-pack",
                "--framework",
                "bmad",
                "--profile",
                "cliente2",
                "--scope",
                "create checkout button",
            ]
        )
        == 0
    )
    pack = json.loads(capsys.readouterr().out)
    assert pack["framework"] == "bmad"


def test_cli_language_cache_status(monkeypatch, capsys) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(
        cli_module,
        "cached_language_index",
        lambda framework, profile: {"ok": True, "framework": framework, "profile": profile},
    )

    assert main(["language", "cache-status", "--framework", "bmad", "--profile", "cliente2"]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload == {
        "ok": True,
        "language_cache": {"ok": True, "framework": "bmad", "profile": "cliente2"},
    }


def test_cli_language_text_plan_returns_program(capsys) -> None:  # type: ignore[no-untyped-def]
    assert (
        main(
            [
                "language",
                "text-plan",
                "--framework",
                "bmad",
                "--profile",
                "cliente2",
                "--text",
                "Objective: Add CTA\n- Add button labeled Start inside root",
            ]
        )
        == 0
    )

    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["framework"] == "bmad"
    assert payload["program"]["steps"][0] == {
        "intent": "create_button",
        "context": "index",
        "parent": "root",
        "text": "Start",
    }


def test_cli_language_execute_program_preview(monkeypatch, capsys) -> None:  # type: ignore[no-untyped-def]
    calls: list[dict] = []

    def fake_execute_framework_program(**kwargs):  # type: ignore[no-untyped-def]
        calls.append(kwargs)
        return {"ok": True, "mode": kwargs["mode"], "executed": False, "program": kwargs["program"]}

    monkeypatch.setattr(cli_module, "execute_framework_program", fake_execute_framework_program)

    assert (
        main(
            [
                "language",
                "execute-program",
                "--framework",
                "bmad",
                "--profile",
                "cliente2",
                "--program",
                '{"objective":"Inspect","steps":[{"intent":"verify_context","query":"page:index"}]}',
                "--mode",
                "preview",
            ]
        )
        == 0
    )

    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["mode"] == "preview"
    assert calls[0]["framework"] == "bmad"
    assert calls[0]["profile"] == "cliente2"
    assert calls[0]["program"]["steps"][0]["intent"] == "verify_context"
    assert calls[0]["approved"] is False
    assert calls[0]["artifact_dir"] is None


def test_cli_language_workspace_sync_copies_artifact(tmp_path, capsys) -> None:  # type: ignore[no-untyped-def]
    artifact_dir = tmp_path / "artifacts"
    artifact_dir.mkdir()
    (artifact_dir / "prd.md").write_text("# PRD\n", encoding="utf-8")
    workspace_dir = tmp_path / "workspace"

    assert (
        main(
            [
                "language",
                "workspace-sync",
                "--framework",
                "bmad",
                "--artifact-dir",
                str(artifact_dir),
                "--workspace-dir",
                str(workspace_dir),
            ]
        )
        == 0
    )

    payload = json.loads(capsys.readouterr().out)
    copied_path = workspace_dir / "_bmad-output" / "planning-artifacts" / "prd.md"
    assert payload["ok"] is True
    assert str(copied_path) in payload["copied"]
    assert copied_path.read_text(encoding="utf-8") == "# PRD\n"


def test_cli_plan_outputs_validated_plan(capsys) -> None:  # type: ignore[no-untyped-def]
    assert main(["plan", 'Create text saying "Hello"']) == 0

    payload = json.loads(capsys.readouterr().out)

    assert payload["validation"]["ok"] is True
    assert payload["plan"]["steps"][0]["args"]["content"] == "Hello"


def test_cli_import_html_outputs_validated_plan(capsys) -> None:  # type: ignore[no-untyped-def]
    assert main(["import", "html", "--file", "tests/fixtures/html/login-card.html"]) == 0

    payload = json.loads(capsys.readouterr().out)

    assert payload["validation"]["ok"] is True
    assert payload["plan"]["steps"][0]["tool_name"] == "create_group"


def test_cli_import_html_can_compile_to_write_payloads(capsys) -> None:  # type: ignore[no-untyped-def]
    assert (
        main(
            [
                "import",
                "html",
                "--file",
                "tests/fixtures/html/login-card.html",
                "--compile",
                "--app-id",
                "synthetic-app",
            ]
        )
        == 0
    )

    payload = json.loads(capsys.readouterr().out)

    assert payload["validation"]["ok"] is True
    assert first_change(payload["plan"]["steps"][0]["args"]["write_payload"], "CreateElement")["body"]["%x"] == "Group"


def test_cli_import_html_runtime_uses_aria_importer(monkeypatch, capsys) -> None:  # type: ignore[no-untyped-def]
    calls = []

    def fake_create_from_html_runtime(**kwargs):  # type: ignore[no-untyped-def]
        calls.append(kwargs)
        return {"ok": True, "engine": "aria_runtime", "write_count": 1, "executed": kwargs["execute"]}

    monkeypatch.setattr("bubble_mcp.cli.main.create_from_html_runtime", fake_create_from_html_runtime)

    assert (
        main(
            [
                "import",
                "html",
                "--file",
                "tests/fixtures/html/login-card.html",
                "--runtime",
                "--profile",
                "smoke",
                "--context",
                "index",
                "--parent",
                "root",
                "--execute",
                "--selector",
                "section",
                "--translate-to-existing-styles",
                "--refresh-context",
            ]
        )
        == 0
    )

    payload = json.loads(capsys.readouterr().out)
    assert payload["engine"] == "aria_runtime"
    assert calls[0]["profile"] == "smoke"
    assert calls[0]["html_file"] == "tests/fixtures/html/login-card.html"
    assert calls[0]["execute"] is True
    assert calls[0]["selector"] == "section"
    assert calls[0]["translate_to_existing_styles"] is True
    assert calls[0]["refresh_context"] is True


def test_cli_import_html_runtime_accepts_url(monkeypatch, capsys) -> None:  # type: ignore[no-untyped-def]
    calls = []

    def fake_create_from_html_runtime(**kwargs):  # type: ignore[no-untyped-def]
        calls.append(kwargs)
        return {"ok": True, "engine": "aria_runtime", "write_count": 1, "executed": kwargs["execute"]}

    monkeypatch.setattr("bubble_mcp.cli.main.create_from_html_runtime", fake_create_from_html_runtime)

    assert (
        main(
            [
                "import",
                "html",
                "--url",
                "https://example.test/page.html",
                "--profile",
                "smoke",
                "--context",
                "index",
                "--parent",
                "root",
            ]
        )
        == 0
    )

    payload = json.loads(capsys.readouterr().out)
    assert payload["engine"] == "aria_runtime"
    assert calls[0]["html_file"] == "https://example.test/page.html"


def test_cli_import_html_styles_uses_style_runtime(monkeypatch, capsys) -> None:  # type: ignore[no-untyped-def]
    calls = []

    def fake_create_styles_from_html_runtime(**kwargs):  # type: ignore[no-untyped-def]
        calls.append(kwargs)
        return {"ok": True, "style_count": 1, "operation_count": 3}

    monkeypatch.setattr("bubble_mcp.cli.main.create_styles_from_html_runtime", fake_create_styles_from_html_runtime)

    assert (
        main(
            [
                "import",
                "html-styles",
                "--file",
                "tests/fixtures/html/style-states.html",
                "--profile",
                "smoke",
                "--selector",
                ".btn-primary",
                "--style-name",
                "Primary Button",
                "--element-type",
                "Button",
                "--states",
                "hover,focus",
                "--extra-css",
                ".btn-primary:focus { border-color: #84caff; }",
            ]
        )
        == 0
    )

    payload = json.loads(capsys.readouterr().out)
    assert payload["style_count"] == 1
    assert calls[0]["profile"] == "smoke"
    assert calls[0]["html_file"] == "tests/fixtures/html/style-states.html"
    assert calls[0]["selector"] == ".btn-primary"
    assert calls[0]["style_name"] == "Primary Button"
    assert calls[0]["element_type"] == "Button"
    assert calls[0]["states"] == ["hover", "focus"]
    assert calls[0]["extra_css"] == [".btn-primary:focus { border-color: #84caff; }"]


def test_cli_import_html_styles_accepts_rendered_url(monkeypatch, capsys) -> None:  # type: ignore[no-untyped-def]
    calls = []

    def fake_create_styles_from_html_runtime(**kwargs):  # type: ignore[no-untyped-def]
        calls.append(kwargs)
        return {"ok": True, "source": {"type": "url"}, "style_count": 1}

    monkeypatch.setattr("bubble_mcp.cli.main.create_styles_from_html_runtime", fake_create_styles_from_html_runtime)

    assert (
        main(
            [
                "import",
                "html-styles",
                "--url",
                "https://example.test/button",
                "--profile",
                "smoke",
                "--selector",
                ".btn-primary",
                "--style-name",
                "Primary Button",
                "--element-type",
                "Button",
                "--rendered-html",
            ]
        )
        == 0
    )

    payload = json.loads(capsys.readouterr().out)
    assert payload["style_count"] == 1
    assert calls[0]["url"] == "https://example.test/button"
    assert calls[0]["selector"] == ".btn-primary"
    assert calls[0]["rendered_html"] is True


def test_cli_smoke_runtime_runs_coverage_suite(capsys) -> None:  # type: ignore[no-untyped-def]
    assert main(["smoke", "runtime", "--suite", "coverage"]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["summary"]["failed"] == 0
    assert [result["tool"] for result in payload["results"]] == [
        "bubble_tool_coverage",
        "bubble_catalog_quality",
    ]


def test_cli_smoke_runtime_runs_visual_repair_suite(capsys) -> None:  # type: ignore[no-untyped-def]
    assert main(["smoke", "runtime", "--suite", "visual-repair", "--profile", "cliente2", "--context", "mcp-01"]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["execute"] is False
    assert payload["summary"] == {"cases": 1, "passed": 1, "failed": 0, "skipped": 0}
    assert payload["results"][0]["tool"] == "bubble_visual_audit"


def test_cli_smoke_runtime_writes_report(tmp_path, capsys) -> None:  # type: ignore[no-untyped-def]
    report = tmp_path / "runtime-smoke.json"

    assert main(["smoke", "runtime", "--suite", "coverage", "--report", str(report)]) == 0

    payload = json.loads(capsys.readouterr().out)
    saved = json.loads(report.read_text(encoding="utf-8"))
    assert saved["ok"] is True
    assert saved["summary"] == payload["summary"]


def test_cli_smoke_runtime_execute_write_requires_execute(capsys) -> None:  # type: ignore[no-untyped-def]
    assert main(["smoke", "runtime", "--suite", "execute-write", "--profile", "cliente2"]) == 1

    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is False
    assert payload["error"] == "execute-write requires execute=true."


def test_cli_tools_guide_routes_task_without_catalog_dump(capsys) -> None:  # type: ignore[no-untyped-def]
    assert (
        main(
            [
                "tools",
                "guide",
                "--task",
                "Convert an HTML selector from a URL into a Bubble page and then inspect the changelog.",
            ]
        )
        == 0
    )

    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["direct_tool_policy"]["avoid_shell_cli_discovery"] is True
    intents = {route["intent"] for route in payload["recommended_routes"]}
    assert "import_html_component" in intents
    assert "branches_or_changelog" in intents


def test_cli_tools_search_returns_compact_matches(capsys) -> None:  # type: ignore[no-untyped-def]
    assert main(["tools", "search", "--query", "html selector import", "--limit", "5"]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["limit"] == 5
    names = [match["name"] for match in payload["matches"]]
    assert "create_from_html" in names
    match = next(match for match in payload["matches"] if match["name"] == "create_from_html")
    assert "selector" in match["properties"]
    assert match["required"] == ["profile", "context", "parent"]


def test_cli_tools_recipe_returns_operational_sequence(capsys) -> None:  # type: ignore[no-untyped-def]
    assert (
        main(
            [
                "tools",
                "recipe",
                "--task",
                "Convert #home-area from a URL into page mcp-01",
                "--profile",
                "smoke",
                "--context",
                "mcp-01",
            ]
        )
        == 0
    )

    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["recipe"] == "html_import"
    assert payload["inputs"]["profile"] == "smoke"
    assert payload["inputs"]["context"] == "mcp-01"
    assert [step["tool"] for step in payload["steps"]] == [
        "bubble_context_detect",
        "bubble_context_find",
        "create_from_html",
        "create_from_html",
        "bubble_visual_capture",
        "bubble_visual_capture_actual",
        "bubble_visual_audit",
    ]
    assert payload["steps"][1]["args"]["exact"] is True
    assert payload["steps"][1]["args"]["include_metadata"] is False


def test_cli_tools_runbook_returns_one_call_agent_plan(capsys) -> None:  # type: ignore[no-untyped-def]
    assert (
        main(
            [
                "tools",
                "runbook",
                "--task",
                "Convert #home-area from a URL into page mcp-01",
                "--profile",
                "smoke",
                "--context",
                "mcp-01",
                "--search-limit",
                "5",
            ]
        )
        == 0
    )

    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["recipe"] == "html_import"
    assert payload["inputs"]["profile"] == "smoke"
    assert "import_html_component" in payload["route_intents"]
    assert payload["tool_search"]["limit"] == 5
    assert "create_from_html" in [match["name"] for match in payload["tool_search"]["matches"]]
    assert "bubble_visual_audit" in [match["name"] for match in payload["tool_search"]["matches"]]
    assert payload["recommended_next_call"]["tool"] == "bubble_context_detect"


def test_cli_tools_runbook_routes_profile_cache_refresh_directly(capsys) -> None:  # type: ignore[no-untyped-def]
    assert (
        main(
            [
                "tools",
                "runbook",
                "--task",
                "faça o refresh do cache do profile cliente2",
                "--profile",
                "cliente2",
                "--search-limit",
                "5",
            ]
        )
        == 0
    )

    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["recipe"] == "setup_or_refresh_context"
    assert payload["recommended_next_call"]["tool"] == "bubble_profile_cache_refresh"
    assert payload["recommended_next_call"]["args"]["profile"] == "$profile"
    assert payload["recommended_next_call"]["args"]["force"] is True
    assert "bubble_profile_cache_refresh" in [match["name"] for match in payload["tool_search"]["matches"]]


def test_cli_tools_runbook_routes_project_transfer(capsys) -> None:  # type: ignore[no-untyped-def]
    assert (
        main(
            [
                "tools",
                "runbook",
                "--task",
                "copie o reusable Header do profile template para o profile cliente2",
                "--profile",
                "cliente2",
                "--search-limit",
                "5",
            ]
        )
        == 0
    )

    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["recipe"] == "project_transfer"
    assert "transfer_between_projects" in payload["route_intents"]
    assert payload["recommended_next_call"]["tool"] == "bubble_profile_status"
    assert "bubble_transfer_inventory" in [match["name"] for match in payload["tool_search"]["matches"]]
    assert "bubble_transfer_execute" in payload["matched"]["tools"]


def test_cli_tools_runbook_routes_multi_action_edits_to_batch(capsys) -> None:  # type: ignore[no-untyped-def]
    task = (
        'Na página mcp-llm do projeto cliente2, altere o texto "Bem-vindo à Aria" '
        'para "Texto atualizado via MCP". Troque a cor primary para #808F2D. '
        "Apague o elemento notes_input."
    )
    assert (
        main(
            [
                "tools",
                "runbook",
                "--task",
                task,
                "--profile",
                "cliente2",
                "--context",
                "mcp-llm",
                "--search-limit",
                "6",
            ]
        )
        == 0
    )

    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["recipe"] == "command_batch"
    assert payload["recommended_next_call"]["tool"] == "batch"
    assert payload["recommended_next_call"]["args"]["commands"] == "$commands"
    names = [match["name"] for match in payload["tool_search"]["matches"]]
    assert names[0] == "batch"
    assert "update_text" in names
    assert "update_color" in names
    assert "delete_multiline_input" in names


def test_cli_tools_coverage_reports_runtime_paths(capsys) -> None:  # type: ignore[no-untyped-def]
    assert main(["tools", "coverage"]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["aria_catalog"]["uncovered_count"] == 0
    assert payload["uncovered_count"] == 0
    assert payload["tool_count"] >= payload["aria_catalog_count"]
    assert "tools" not in payload

    assert main(["tools", "coverage", "--include-tools"]) == 0
    detailed = json.loads(capsys.readouterr().out)
    assert len(detailed["tools"]) == detailed["tool_count"]


def test_cli_tools_quality_reports_catalog_gate(capsys) -> None:  # type: ignore[no-untyped-def]
    assert main(["tools", "quality"]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["summary"]["issue_count"] == 0
    checks = {check["name"]: check for check in payload["checks"]}
    assert checks["tool_descriptions"]["ok"] is True
    assert checks["tool_annotations"]["ok"] is True
    assert checks["runtime_coverage"]["aria_uncovered_count"] == 0
    assert checks["runtime_coverage"]["uncovered_count"] == 0


def test_cli_knowledge_refresh_search_fetch_and_guidance(tmp_path, monkeypatch, capsys) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path))
    fixture = "tests/fixtures/knowledge/bubble-manual-records.jsonl"

    assert main(["knowledge", "refresh-source", "--source", "bubble_manual_gitbook", "--file", fixture]) == 0
    refreshed = json.loads(capsys.readouterr().out)
    assert refreshed["ok"] is True
    assert refreshed["imported"] == 2

    assert main(["knowledge", "search", "API Connector authentication", "--limit", "5"]) == 0
    searched = json.loads(capsys.readouterr().out)
    assert searched["ok"] is True
    assert searched["results"][0]["id"] == "bubble-manual:api-connector:authentication"

    assert main(["knowledge", "fetch", "bubble-manual:data-types:privacy"]) == 0
    fetched = json.loads(capsys.readouterr().out)
    assert fetched["ok"] is True
    assert fetched["record"]["source"] == "bubble_manual_gitbook"

    assert main(["knowledge", "guidance", "privacy rules migration"]) == 0
    guided = json.loads(capsys.readouterr().out)
    assert guided["ok"] is True
    assert guided["purpose"] == "manual_guidance"
    assert guided["cache_only"] is True


def test_cli_knowledge_search_wraps_malformed_cache_errors(tmp_path, monkeypatch, capsys) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path))
    cache_path = tmp_path / "knowledge" / "bubble_manual_gitbook" / "records.jsonl"
    cache_path.parent.mkdir(parents=True)
    cache_path.write_text('{"id":\n', encoding="utf-8")

    assert main(["knowledge", "search", "API Connector"]) == 1

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert captured.err == ""
    assert payload["ok"] is False
    assert payload["action"] == "search"
    assert payload["error_class"] == "ValueError"
    assert "records.jsonl:1" in payload["error"]


def test_cli_knowledge_fetch_wraps_malformed_cache_errors(tmp_path, monkeypatch, capsys) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path))
    cache_path = tmp_path / "knowledge" / "bubble_manual_gitbook" / "records.jsonl"
    cache_path.parent.mkdir(parents=True)
    cache_path.write_text('{"id":\n', encoding="utf-8")

    assert main(["knowledge", "fetch", "bubble-manual:api-connector:authentication"]) == 1

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert captured.err == ""
    assert payload["ok"] is False
    assert payload["action"] == "fetch"
    assert payload["error_class"] == "ValueError"
    assert "records.jsonl:1" in payload["error"]


def test_cli_knowledge_guidance_wraps_malformed_cache_errors(tmp_path, monkeypatch, capsys) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path))
    cache_path = tmp_path / "knowledge" / "bubble_manual_gitbook" / "records.jsonl"
    cache_path.parent.mkdir(parents=True)
    cache_path.write_text('{"id":\n', encoding="utf-8")

    assert main(["knowledge", "guidance", "API Connector"]) == 1

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert captured.err == ""
    assert payload["ok"] is False
    assert payload["action"] == "guidance"
    assert payload["error_class"] == "ValueError"
    assert "records.jsonl:1" in payload["error"]


def test_cli_readiness_runs_recommended_sequence(capsys) -> None:  # type: ignore[no-untyped-def]
    assert main(["readiness"]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["summary"] == {"checks": 3, "passed": 3, "failed": 0}
    assert [check["name"] for check in payload["checks"]] == [
        "health",
        "catalog_gate",
        "agent_routing",
    ]


def test_cli_tools_recipe_routes_page_creation_before_generic_create(capsys) -> None:  # type: ignore[no-untyped-def]
    assert main(["tools", "recipe", "--task", "Create a new page called mcp-02", "--profile", "smoke"]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["recipe"] == "page_or_reusable"
    assert "create_page" in payload["matched"]["tools"]
    intents = {route["intent"] for route in payload["recommended_routes"]}
    assert "manage_pages_or_reusables" in intents


def test_cli_session_import_and_list(tmp_path, monkeypatch, capsys) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path))
    session_path = tmp_path / "session.json"
    session_path.write_text(
        json.dumps(
            {
                "appId": "synthetic-app",
                "url": "https://bubble.io/page?name=synthetic-app",
                "headers": {"Cookie": "sid=secret"},
            }
        ),
        encoding="utf-8",
    )

    assert main(["session", "import", "--profile", "dev", "--file", str(session_path)]) == 0
    imported = json.loads(capsys.readouterr().out)
    assert imported["session"]["headers"]["Cookie"] == "[REDACTED]"

    assert main(["session", "list"]) == 0
    listed = json.loads(capsys.readouterr().out)
    assert listed["sessions"][0]["profile"] == "dev"

    assert main(["session", "inspect", "--profile", "dev"]) == 0
    inspected = json.loads(capsys.readouterr().out)
    assert inspected["cookie_present"] is True
    assert inspected["session"]["headers"]["Cookie"] == "[REDACTED]"
    assert inspected["computed_write_headers"]["cookie"] == "[REDACTED]"
    assert "x-bubble-appname" in inspected["computed_write_header_keys"]


def test_cli_profile_bootstrap_creates_profile(tmp_path, monkeypatch, capsys) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path))

    assert main(["profile", "bootstrap", "dev", "--app-id", "synthetic-app"]) == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["ok"] is True
    assert payload["profile"] == "dev"
    assert payload["profile_changed"] is True
    assert payload["status"]["profile"]["app_id"] == "synthetic-app"
    assert [action["tool"] for action in payload["next_actions"]] == [
        "bubble_session_login",
        "bubble_context_detect",
    ]

    assert main(["profile", "list"]) == 0
    listed = json.loads(capsys.readouterr().out)
    assert listed["profiles"][0]["name"] == "dev"
    assert listed["profiles"][0]["app_id"] == "synthetic-app"


def test_cli_profile_refresh_cache_uses_canonical_tool(tmp_path, monkeypatch, capsys) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path))
    calls: list[dict] = []

    def fake_detect_project_context(**kwargs):  # type: ignore[no-untyped-def]
        calls.append(kwargs)
        context_path = tmp_path / "contexts" / "dev" / "synthetic-app-context.json"
        context_path.parent.mkdir(parents=True)
        context_path.write_text(FIXTURE.read_text(encoding="utf-8"), encoding="utf-8")

        class FakeDetectionResult:
            ok = True
            app_id = "synthetic-app"
            source = "downloaded_bubble"
            crawler_index_path = None

            def __init__(self) -> None:
                self.context_path = context_path
                self.summary = {"app_id": "synthetic-app"}

            def to_dict(self) -> dict:
                return {
                    "ok": True,
                    "app_id": "synthetic-app",
                    "source": "downloaded_bubble",
                    "context_path": str(context_path),
                    "crawler_index_path": None,
                    "summary": self.summary,
                    "attempts": [],
                }

        return FakeDetectionResult()

    monkeypatch.setattr("bubble_mcp.server.tools.detect_project_context", fake_detect_project_context)
    monkeypatch.setattr(
        "bubble_mcp.server.tools.profile_status",
        lambda profile, max_age_hours=24: {"ok": True, "ready": True, "profile": {"name": profile}},
    )
    save_settings(
        BubbleMcpSettings(
            config_dir=tmp_path,
            default_profile="dev",
            profiles={"dev": BubbleProfile(name="dev", app_id="synthetic-app", appname="synthetic-app")},
        )
    )

    assert main(["profile", "refresh-cache", "--profile", "dev"]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["profile"] == "dev"
    assert payload["force"] is True
    assert payload["source"] == "downloaded_bubble"
    assert calls[0]["profile"] == "dev"
    assert calls[0]["app_id"] == "synthetic-app"
    assert calls[0]["force"] is True


def test_cli_session_login_reports_progress_on_stderr(tmp_path, monkeypatch, capsys) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path))

    def fake_capture_session_with_playwright(**kwargs):  # type: ignore[no-untyped-def]
        kwargs["progress"]("Session cookies detected. You can close the browser now.")
        return session_from_payload(
            {
                "appId": kwargs["app_id"],
                "url": "https://bubble.io/page?id=synthetic-app",
                "headers": {"Cookie": "sid=secret", "User-Agent": "test"},
                "appVersion": "test",
                "source": "browser",
            }
        )

    monkeypatch.setattr("bubble_mcp.cli.main.capture_session_with_playwright", fake_capture_session_with_playwright)

    assert main(["profile", "add", "dev", "--app-id", "synthetic-app"]) == 0
    capsys.readouterr()
    assert main(["session", "login", "--profile", "dev", "--app-id", "synthetic-app"]) == 0
    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert payload["ok"] is True
    assert "[bubble-mcp session] Session cookies detected." in captured.err
    assert "[bubble-mcp session] Session saved for profile 'dev'" in captured.err


def test_cli_session_login_quiet_suppresses_progress(tmp_path, monkeypatch, capsys) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path))

    def fake_capture_session_with_playwright(**kwargs):  # type: ignore[no-untyped-def]
        assert kwargs["progress"] is None
        return session_from_payload(
            {
                "appId": kwargs["app_id"],
                "url": "https://bubble.io/page?id=synthetic-app",
                "headers": {"Cookie": "sid=secret", "User-Agent": "test"},
                "appVersion": "test",
                "source": "browser",
            }
        )

    monkeypatch.setattr("bubble_mcp.cli.main.capture_session_with_playwright", fake_capture_session_with_playwright)

    assert main(["profile", "add", "dev", "--app-id", "synthetic-app"]) == 0
    capsys.readouterr()
    assert main(["session", "login", "--profile", "dev", "--app-id", "synthetic-app", "--quiet"]) == 0
    captured = capsys.readouterr()

    assert json.loads(captured.out)["ok"] is True
    assert captured.err == ""


def test_cli_branch_create_passes_sub_branch_source(monkeypatch, capsys) -> None:  # type: ignore[no-untyped-def]
    calls = []

    def fake_create_bubble_branch(**kwargs):  # type: ignore[no-untyped-def]
        calls.append(kwargs)
        return {"ok": True, "request": {"payload": kwargs}}

    monkeypatch.setattr("bubble_mcp.cli.main.create_bubble_branch", fake_create_bubble_branch)

    assert (
        main(
            [
                "branch",
                "create",
                "--profile",
                "smoke",
                "--name",
                "sub-feature",
                "--from-app-version",
                "parent-branch",
                "--description",
                "child branch",
                "--execute",
            ]
        )
        == 0
    )

    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert calls[0]["profile"] == "smoke"
    assert calls[0]["name"] == "sub-feature"


def test_cli_branch_merge_start_routes_payload(monkeypatch, capsys) -> None:  # type: ignore[no-untyped-def]
    calls = []

    def fake_start_bubble_branch_merge(**kwargs):  # type: ignore[no-untyped-def]
        calls.append(kwargs)
        return {"ok": True, "request": {"payload": kwargs}}

    monkeypatch.setattr("bubble_mcp.cli.main.start_bubble_branch_merge", fake_start_bubble_branch_merge)

    assert (
        main(
            [
                "branch",
                "merge-start",
                "--profile",
                "smoke",
                "--ours-version-id",
                "53ffs",
                "--theirs-version-id",
                "23347",
                "--savepoint-message",
                "sync:Started merging changes from staging",
                "--session-id",
                "1783611043308x32",
                "--execute",
            ]
        )
        == 0
    )

    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert calls[0]["ours_version_id"] == "53ffs"
    assert calls[0]["theirs_version_id"] == "23347"
    assert calls[0]["session_id"] == "1783611043308x32"
    assert calls[0]["execute"] is True


def test_cli_branch_merge_conflicts_describe_reads_payload_file(tmp_path, monkeypatch, capsys) -> None:  # type: ignore[no-untyped-def]
    payload_file = tmp_path / "merge-payload.json"
    payload_file.write_text(
        json.dumps(
            {
                "changes": [
                    {
                        "body": {"0": {"%x": "TriggerCustomEvent", "id": "action-1"}},
                        "path_array": ["%ed", "event-1", "%wf", "workflow-1", "actions"],
                        "intent": {"name": "MergeConflict"},
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    assert main(["branch", "merge-conflicts-describe", "--file", str(payload_file)]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["conflict_count"] == 1
    assert payload["conflicts"][0]["context"]["category"] == "workflow_actions"


def test_cli_branch_merge_finalize_routes_payload(monkeypatch, capsys) -> None:  # type: ignore[no-untyped-def]
    calls = []

    def fake_finalize_bubble_branch_merge(**kwargs):  # type: ignore[no-untyped-def]
        calls.append(kwargs)
        return {"ok": True, "request": {"payload": kwargs}}

    monkeypatch.setattr("bubble_mcp.cli.main.finalize_bubble_branch_merge", fake_finalize_bubble_branch_merge)

    assert (
        main(
            [
                "branch",
                "merge-finalize",
                "--profile",
                "smoke",
                "--merge-app-version",
                "73ftr",
                "--target-version-id",
                "53ffs",
                "--source-version-id",
                "23347",
                "--source-branch-name",
                "staging",
                "--execute",
            ]
        )
        == 0
    )

    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert calls[0]["merge_app_version"] == "73ftr"
    assert calls[0]["target_version_id"] == "53ffs"
    assert calls[0]["source_version_id"] == "23347"
    assert calls[0]["source_branch_name"] == "staging"
    assert calls[0]["execute"] is True


def test_cli_changelog_fetch_builds_filters(monkeypatch, capsys) -> None:  # type: ignore[no-untyped-def]
    calls = []

    def fake_fetch_changelog_entries(**kwargs):  # type: ignore[no-untyped-def]
        calls.append(kwargs)
        return {"ok": True, "entries": []}

    monkeypatch.setattr("bubble_mcp.cli.main.fetch_changelog_entries", fake_fetch_changelog_entries)

    assert (
        main(
            [
                "changelog",
                "fetch",
                "--profile",
                "smoke",
                "--app-version",
                "test",
                "--start-index",
                "50",
                "--num-fetch",
                "25",
                "--change-type",
                "Data",
                "--change-path",
                "user_types.user.",
                "--user-id",
                "user-1",
                "--user-id",
                "user-2",
            ]
        )
        == 0
    )

    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert calls[0]["profile"] == "smoke"
    assert calls[0]["app_version"] == "test"
    assert calls[0]["start_index"] == 50
    assert calls[0]["num_fetch"] == 25
    assert calls[0]["filters"] == {
        "type": "Data",
        "change_path": "user_types.user.",
        "user_id": ["user-1", "user-2"],
    }


def test_cli_compile_plan_outputs_write_payload(tmp_path, capsys) -> None:  # type: ignore[no-untyped-def]
    plan_path = tmp_path / "plan.json"
    plan_path.write_text(
        json.dumps(
            {
                "steps": [
                    {
                        "id": "s1",
                        "tool_name": "create_text",
                        "args": {"context": "index", "content": "Hello"},
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    assert main(["compile-plan", "--file", str(plan_path), "--app-id", "synthetic-app"]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert first_change(payload["plan"]["steps"][0]["args"]["write_payload"], "CreateElement")["body"]["%x"] == "Text"


def test_cli_compile_plan_uses_context_file_for_editor_paths(tmp_path, capsys) -> None:  # type: ignore[no-untyped-def]
    plan_path = tmp_path / "plan.json"
    context_path = tmp_path / "context.json"
    plan_path.write_text(
        json.dumps(
            {
                "steps": [
                    {
                        "id": "s1",
                        "tool_name": "create_text",
                        "args": {"context": "index", "parent": "Card", "content": "Hello"},
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    context_path.write_text(
        json.dumps(
            {
                "app_id": "synthetic-app",
                "source": "test",
                "nodes": [
                    {
                        "id": "page:index",
                        "label": "index",
                        "type": "page",
                        "metadata": {"bubble_id": "pgIndex", "path_array": ["%p3", "pgIndex"]},
                    },
                    {
                        "id": "element:elCard",
                        "label": "Card",
                        "type": "element",
                        "metadata": {"bubble_id": "elCard", "path_array": ["%p3", "pgIndex", "%el", "elCard"]},
                    },
                ],
                "edges": [],
            }
        ),
        encoding="utf-8",
    )

    assert (
        main(
            [
                "compile-plan",
                "--file",
                str(plan_path),
                "--app-id",
                "synthetic-app",
                "--context-file",
                str(context_path),
            ]
        )
        == 0
    )

    payload = json.loads(capsys.readouterr().out)
    write_payload = payload["plan"]["steps"][0]["args"]["write_payload"]
    create_change = first_change(write_payload, "CreateElement")
    assert create_change["path_array"][:4] == ["%p3", "pgIndex", "%el", "elCard"]
    assert write_payload["changes"][0]["body"].startswith("%p3.pgIndex.%el.elCard.%el.")
    assert first_change(write_payload, "Update index")["path_array"][:2] == ["_index", "id_to_path"]
    assert any(change["path_array"] == ["_index", "issues_sub", "elCard"] for change in write_payload["changes"])


def test_cli_execute_plan_compile_uses_context_file_in_preview(tmp_path, capsys) -> None:  # type: ignore[no-untyped-def]
    plan_path = tmp_path / "plan.json"
    context_path = tmp_path / "context.json"
    plan_path.write_text(
        json.dumps(
            {
                "steps": [
                    {
                        "id": "s1",
                        "tool_name": "create_text",
                        "args": {"context": "index", "content": "Hello"},
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    context_path.write_text(
        json.dumps(
            {
                "app_id": "synthetic-app",
                "source": "test",
                "nodes": [
                    {
                        "id": "page:index",
                        "label": "index",
                        "type": "page",
                        "metadata": {"bubble_id": "pgIndex", "path_array": ["%p3", "pgIndex"]},
                    }
                ],
                "edges": [],
            }
        ),
        encoding="utf-8",
    )

    assert (
        main(
            [
                "execute-plan",
                "--profile",
                "dev",
                "--file",
                str(plan_path),
                "--app-id",
                "synthetic-app",
                "--compile",
                "--context-file",
                str(context_path),
            ]
        )
        == 0
    )

    payload = json.loads(capsys.readouterr().out)
    write_payload = payload["results"][0]["payload"]
    create_change = first_change(write_payload, "CreateElement")
    assert create_change["path_array"][:2] == ["%p3", "pgIndex"]


def test_cli_extension_import_list_enable_disable(tmp_path, monkeypatch, capsys) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path))

    assert main(["extension", "import", "--path", "tests/fixtures/extensions/simple-pack"]) == 0
    imported = json.loads(capsys.readouterr().out)
    assert imported["ok"] is True
    assert imported["state"] == "pending"

    assert main(["extension", "enable", "local.simple-pack"]) == 0
    enabled = json.loads(capsys.readouterr().out)
    assert enabled["state"] == "enabled"

    assert main(["extension", "list"]) == 0
    listed = json.loads(capsys.readouterr().out)
    assert listed["extensions"][0]["extension_id"] == "local.simple-pack"
    assert listed["extensions"][0]["state"] == "enabled"

    assert main(["extension", "disable", "local.simple-pack"]) == 0
    disabled = json.loads(capsys.readouterr().out)
    assert disabled["state"] == "disabled"


def test_cli_extension_invalid_inputs_return_json_errors(tmp_path, monkeypatch, capsys) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path))

    assert main(["extension", "import", "--path", "tests/fixtures/extensions/missing-pack"]) == 1
    imported = json.loads(capsys.readouterr().out)
    assert imported["ok"] is False
    assert imported["action"] == "import"
    assert imported["error_class"] == "ValueError"
    assert "Extension pack source must be a directory" in imported["error"]

    assert main(["extension", "enable", "local.missing-pack"]) == 1
    enabled = json.loads(capsys.readouterr().out)
    assert enabled["ok"] is False
    assert enabled["action"] == "enable"
    assert enabled["error_class"] == "ValueError"
    assert enabled["error"] == "Unknown extension: local.missing-pack"

    assert main(["extension", "disable", "local.missing-pack"]) == 1
    disabled = json.loads(capsys.readouterr().out)
    assert disabled["ok"] is False
    assert disabled["action"] == "disable"
    assert disabled["error_class"] == "ValueError"
    assert disabled["error"] == "Unknown extension: local.missing-pack"


def test_cli_extension_companion_serve_passes_listener_config(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    calls = []

    def fake_serve_extension_companion(config):  # type: ignore[no-untyped-def]
        calls.append(config)
        return 0

    monkeypatch.setattr("bubble_mcp.cli.main.serve_extension_companion", fake_serve_extension_companion)

    assert (
        main(
            [
                "extension",
                "companion",
                "serve",
                "--host",
                "127.0.0.1",
                "--port",
                "3901",
                "--capture-key",
                "dev-key",
                "--tool-session-id",
                "toolwiz_20260704_api_connector_1a2b3c4d",
            ]
        )
        == 0
    )

    assert calls[0].host == "127.0.0.1"
    assert calls[0].port == 3901
    assert calls[0].capture_key == "dev-key"
    assert calls[0].tool_session_id == "toolwiz_20260704_api_connector_1a2b3c4d"


def test_cli_browser_scheduled_deploy_flow(tmp_path, monkeypatch, capsys) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path))
    save_settings(
        BubbleMcpSettings(
            config_dir=tmp_path,
            default_profile="client",
            profiles={
                "client": BubbleProfile(
                    name="client",
                    app_id="bubble-app",
                    appname="bubble-app",
                    app_version="test",
                )
            },
        )
    )

    assert (
        main(
            [
                "browser",
                "schedule-deploy",
                "--profile",
                "client",
                "--scheduled-at",
                "2026-07-09T10:30:00Z",
                "--message",
                "Main branch release",
            ]
        )
        == 0
    )
    preview = json.loads(capsys.readouterr().out)
    assert preview["mode"] == "preview"

    assert (
        main(
            [
                "browser",
                "schedule-deploy",
                "--profile",
                "client",
                "--scheduled-at",
                "2026-07-09T10:30:00Z",
                "--message",
                "Main branch release",
                "--execute",
                "--confirm",
                "--preview-id",
                preview["preview"]["preview_id"],
            ]
        )
        == 0
    )
    scheduled = json.loads(capsys.readouterr().out)
    deploy_id = scheduled["deploy"]["deploy_id"]

    assert main(["browser", "list-deploys", "--profile", "client"]) == 0
    listed = json.loads(capsys.readouterr().out)
    assert listed["scheduled"][0]["deploy_id"] == deploy_id

    assert main(["browser", "cancel-deploy", "--profile", "client", "--deploy-id", deploy_id]) == 0
    cancelled = json.loads(capsys.readouterr().out)
    assert cancelled["cancelled"] is True

    assert main(["browser", "deploy-history", "--profile", "client"]) == 0
    history = json.loads(capsys.readouterr().out)
    assert [item["event"] for item in history["history"]] == ["scheduled", "cancelled"]


def test_cli_tool_wizard_start_add_capture_and_describe(tmp_path, monkeypatch, capsys) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path))

    assert (
        main(
            [
                "tool-wizard",
                "start",
                "--intent",
                "Create an API Connector call",
                "--target",
                "api_connector",
                "--profile",
                "client",
            ]
        )
        == 0
    )
    started = json.loads(capsys.readouterr().out)
    assert started["ok"] is True
    assert started["active"] is True
    assert started["workflow"]["finish_with"] == "tool-wizard finalize <session_id>"
    session_id = started["session"]["id"]

    assert (
        main(
            [
                "tool-wizard",
                "add-capture",
                session_id,
                "--file",
                "tests/fixtures/tool-authoring/api-connector-write-capture.json",
            ]
        )
        == 0
    )
    captured = json.loads(capsys.readouterr().out)
    assert captured["classification"]["families"] == ["editor_write"]
    assert captured["classification"]["change_count"] == 1

    assert main(["tool-wizard", "describe", session_id]) == 0
    described = json.loads(capsys.readouterr().out)
    assert described["session"]["profile"] == "client"
    assert described["active"] is True
    assert described["classification"]["app_id"] == "synthetic-app"

    assert main(["tool-wizard", "finalize", session_id]) == 0
    finalized = json.loads(capsys.readouterr().out)
    assert finalized["status"] == "ready_for_review"
    assert finalized["capture_summary"]["intents"] == ["CreateApiConnectorCall"]
    assert finalized["questions"]
    assert finalized["testing_guidance"]
    assert finalized["next_mcp_calls"][0]["tool"] == "bubble_tool_wizard_generate"

    assert main(["tool-wizard", "finalize", session_id, "--generate-pack"]) == 0
    finalized_generated = json.loads(capsys.readouterr().out)
    assert finalized_generated["ok"] is True
    assert finalized_generated["validation"]["ok"] is True
    assert finalized_generated["next_mcp_calls"][3]["tool"] == "bubble_extension_call"

    assert main(["tool-wizard", "generate", session_id]) == 0
    generated = json.loads(capsys.readouterr().out)
    assert generated["ok"] is True
    assert generated["validation"]["ok"] is True
    assert generated["pack_path"]
    assert generated["next_mcp_calls"][0]["tool"] == "bubble_extension_validate"
    assert generated["next_mcp_calls"][3]["tool"] == "bubble_extension_call"

    assert main(["tool-wizard", "activate", session_id]) == 0
    activated = json.loads(capsys.readouterr().out)
    assert activated["session_id"] == session_id
    assert activated["next_mcp_calls"][0]["tool"] == "bubble_tool_wizard_generate"


def test_cli_tool_wizard_add_capture_returns_structured_errors(tmp_path, monkeypatch, capsys) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path / "config"))

    assert (
        main(
            [
                "tool-wizard",
                "start",
                "--intent",
                "Create an API Connector call",
                "--target",
                "api_connector",
                "--profile",
                "client",
            ]
        )
        == 0
    )
    session_id = json.loads(capsys.readouterr().out)["session"]["id"]

    no_payload = tmp_path / "no-payload.json"
    no_payload.write_text("{}", encoding="utf-8")
    assert main(["tool-wizard", "add-capture", session_id, "--file", str(no_payload)]) == 1
    missing_payload = json.loads(capsys.readouterr().out)
    assert missing_payload["ok"] is False
    assert missing_payload["action"] == "add-capture"
    assert missing_payload["error_class"] == "ValueError"
    assert "does not contain a Bubble editor write body" in missing_payload["error"]

    malformed = tmp_path / "malformed.json"
    malformed.write_text("{", encoding="utf-8")
    assert main(["tool-wizard", "add-capture", session_id, "--file", str(malformed)]) == 1
    malformed_payload = json.loads(capsys.readouterr().out)
    assert malformed_payload["ok"] is False
    assert malformed_payload["action"] == "add-capture"
    assert malformed_payload["error_class"] == "JSONDecodeError"
    assert "Expecting property name" in malformed_payload["error"]


def test_cli_learning_record_and_list(tmp_path, monkeypatch, capsys) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path))

    assert (
        main(
            [
                "learning",
                "record",
                "--scope",
                "project",
                "--key",
                "naming.page_language",
                "--value",
                '{"language":"pt-BR"}',
                "--source",
                "user_declared",
                "--confidence",
                "confirmed",
                "--project",
                "client-app",
            ]
        )
        == 0
    )
    recorded = json.loads(capsys.readouterr().out)
    assert recorded["ok"] is True
    assert recorded["record"]["key"] == "naming.page_language"
    assert recorded["record"]["project"] == "client-app"

    assert main(["learning", "list", "--scope", "project", "--project", "client-app"]) == 0
    listed = json.loads(capsys.readouterr().out)
    assert [record["key"] for record in listed["records"]] == ["naming.page_language"]


def test_cli_learning_record_invalid_value_returns_json_error(tmp_path, monkeypatch, capsys) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path))

    assert (
        main(
            [
                "learning",
                "record",
                "--scope",
                "global",
                "--key",
                "workflow.preview_required",
                "--value",
                "true",
                "--source",
                "user_declared",
                "--confidence",
                "confirmed",
            ]
        )
        == 1
    )
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is False
    assert payload["action"] == "record"
    assert payload["error_class"] == "ValueError"
    assert payload["error"] == "Expected a JSON object."


def test_cli_learning_record_missing_scope_discriminator_returns_json_error(
    tmp_path,
    monkeypatch,
    capsys,
) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path))

    assert (
        main(
            [
                "learning",
                "record",
                "--scope",
                "project",
                "--key",
                "naming.page_language",
                "--value",
                '{"language":"pt-BR"}',
                "--source",
                "user_declared",
                "--confidence",
                "confirmed",
            ]
        )
        == 1
    )
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is False
    assert payload["action"] == "record"
    assert payload["error_class"] == "ValueError"
    assert payload["error"] == "Learning record scope 'project' requires project."

    assert main(["learning", "list"]) == 0
    listed = json.loads(capsys.readouterr().out)
    assert listed["records"] == []


def test_add_action_reuses_workflow_it_just_auto_created_for_a_second_action(
    tmp_path, capsys
) -> None:  # type: ignore[no-untyped-def]
    """Regression test for a duplicate-workflow bug: the 2nd add_action call for
    the same trigger element+event, right after the 1st call auto-created the
    workflow, used to fail to find that workflow and silently create another one.

    Root cause: create_event() (called by add_action's auto-create path) patches
    both the in-memory discovery root and the local cache with the new workflow
    shell, but the follow-up set_event_element() call - which binds the trigger
    element (%p.%ei) - only patched the cache, never the in-memory root. A
    deliberate anti-stale-cache guard in _list_context_workflows then refused to
    let the (correct) cached binding fill in the (incomplete) in-memory one, so
    the real workflow could never be matched by element again in the same
    process, and add_action fell through to auto-creating a duplicate.
    """
    app_path = tmp_path / "app.json"
    app_path.write_text(
        json.dumps(
            {
                "pages": {
                    "pg1": {
                        "id": "pg1",
                        "name": "index",
                        "type": "Page",
                        "properties": {},
                        "custom_states": {},
                        "workflows": {},
                        "elements": {
                            "btn1": {
                                "id": "btn1",
                                "name": "Meu Botao",
                                "type": "Button",
                                "properties": {},
                            }
                        },
                    }
                },
                "user_types": {},
                "option_sets": {},
                "styles": {},
                "settings": {},
            }
        ),
        encoding="utf-8",
    )
    cli = BubbleCLI(app_json_path=str(app_path), appname="reprotest")

    assert (
        cli.add_action(
            context_name="index",
            element_name="Meu Botao",
            action_type="hide",
            action_param="Meu Botao",
            event="click",
            dry_run=True,
        )
        is True
    )
    capsys.readouterr()  # discard call 1 output

    assert (
        cli.add_action(
            context_name="index",
            element_name="Meu Botao",
            action_type="show",
            action_param="Meu Botao",
            event="click",
            dry_run=True,
        )
        is True
    )
    out = capsys.readouterr().out
    assert "No workflow found" not in out
    assert "Auto-creating workflow" not in out

    workflows = cli.discovery.data["pages"]["pg1"]["workflows"]
    assert len(workflows) == 1
