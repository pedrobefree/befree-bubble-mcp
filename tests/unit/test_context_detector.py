import json
from pathlib import Path

from bubble_mcp.core.config import BubbleMcpSettings, BubbleProfile, save_settings, with_profile
from bubble_mcp.context.detector import (
    default_bubble_export_path,
    default_bubble_modules_dir,
    detect_project_context,
)
from bubble_mcp.context.source import load_context
from bubble_mcp.sessions.store import save_session, session_from_payload


def test_detect_context_imports_local_bubble_file(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path / "config"))
    bubble_file = tmp_path / "app.bubble"
    bubble_file.write_text(
        json.dumps(
            {
                "appname": "synthetic-app",
                "pages": {
                    "pgIndex": {
                        "id": "rootIndex",
                        "%p": {"%nm": "index"},
                        "%el": {"elTitle": {"%x": "Text", "%p": {"%nm": "Title"}}},
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    result = detect_project_context(profile="dev", app_id="synthetic-app", bubble_file=bubble_file)

    assert result.ok is True
    assert result.source == "bubble_file"
    context = load_context(result.context_path)
    page = next(node for node in context.nodes if node.type == "page")
    assert page.metadata["bubble_id"] == "pgIndex"
    assert page.metadata["root_id"] == "rootIndex"
    assert page.metadata["children"] == ["elTitle"]


def test_detect_context_imports_wrapped_bubble_export(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path / "config"))
    bubble_file = tmp_path / "wrapped.bubble"
    bubble_file.write_text(
        json.dumps(
            {
                "app": {
                    "id": "synthetic-app",
                    "pages": {
                        "pgWrapped": {
                            "id": "rootWrapped",
                            "%p": {"%nm": "index"},
                            "%el": {"elWrapped": {"%x": "Text", "%p": {"%nm": "Wrapped"}}},
                        }
                    },
                    "user_types": {"typeUser": {"%p": {"%nm": "User"}}},
                },
                "deployment": {},
            }
        ),
        encoding="utf-8",
    )

    result = detect_project_context(profile="dev", app_id="synthetic-app", bubble_file=bubble_file)
    context = load_context(result.context_path)

    assert result.source == "bubble_file"
    assert any(node.id == "page:index" and node.metadata["bubble_id"] == "pgWrapped" for node in context.nodes)
    assert any(node.id == "element:elWrapped" for node in context.nodes)
    assert any(node.id == "datatype:typeUser" for node in context.nodes)


def test_detect_context_uses_profile_bubble_file_before_crawler(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    config_dir = tmp_path / "config"
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(config_dir))
    bubble_file = tmp_path / "profile-app.bubble"
    bubble_file.write_text(
        json.dumps(
            {
                "appname": "synthetic-app",
                "pages": {
                    "pgProfile": {
                        "id": "rootProfile",
                        "%p": {"%nm": "index"},
                        "%el": {"elFromBubble": {"%x": "Text", "%p": {"%nm": "From Bubble"}}},
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    settings = BubbleMcpSettings(config_dir=config_dir, default_profile=None, profiles={})
    save_settings(
        with_profile(
            settings,
            BubbleProfile(
                name="dev",
                app_id="synthetic-app",
                appname="synthetic-app",
                app_json_path=str(bubble_file),
            ),
        )
    )
    save_session("dev", session_from_payload({"appId": "synthetic-app", "headers": {"Cookie": "sid=secret"}}))

    result = detect_project_context(profile="dev", app_id="synthetic-app", force=True)

    assert result.source == "profile_app_json_path"
    context = load_context(result.context_path)
    assert any(node.id == "element:elFromBubble" for node in context.nodes)


def test_detect_context_downloads_bubble_export_before_crawler(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    config_dir = tmp_path / "config"
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(config_dir))
    save_session(
        "dev",
        session_from_payload(
            {
                "appId": "synthetic-app",
                "headers": {"Cookie": "sid=secret", "content-length": "10", "host": "bubble.io"},
            }
        ),
    )
    payload = {
        "appname": "synthetic-app",
        "pages": {
            "pgDownloaded": {
                "id": "rootDownloaded",
                "%p": {"%nm": "index"},
                "%el": {"elDownloaded": {"%x": "Text", "%p": {"%nm": "Downloaded"}}},
            }
        },
    }
    calls = []

    class Response:
        status_code = 200
        content = json.dumps(payload).encode("utf-8")
        encoding = "utf-8"

    def fake_get(url, *, headers, timeout):  # type: ignore[no-untyped-def]
        calls.append({"url": url, "headers": headers, "timeout": timeout})
        return Response()

    def unexpected_crawl(**_kwargs):  # type: ignore[no-untyped-def]
        raise AssertionError("crawler must not run when .bubble export succeeds")

    monkeypatch.setattr("bubble_mcp.context.detector.requests.get", fake_get)
    monkeypatch.setattr("bubble_mcp.context.detector.crawl_project_index", unexpected_crawl)

    result = detect_project_context(profile="dev", app_id="synthetic-app", app_version="test", force=True)
    context = load_context(result.context_path)

    assert result.source == "downloaded_bubble"
    assert calls[0]["url"] == "https://bubble.io/appeditor/export/test/synthetic-app.bubble"
    assert "content-length" not in calls[0]["headers"]
    assert "host" not in calls[0]["headers"]
    assert default_bubble_export_path("dev", "synthetic-app").exists()
    assert (default_bubble_modules_dir("dev", "synthetic-app") / "root.json").exists()
    assert (default_bubble_modules_dir("dev", "synthetic-app") / "pages" / "pgDownloaded.json").exists()
    assert any(node.id == "element:elDownloaded" for node in context.nodes)


def test_detect_context_download_ignores_bogus_response_encoding_guess(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    # requests/urllib3 falls back to guessing ISO-8859-1 for a response
    # without an explicit charset, even though the export is JSON (which
    # RFC 8259 mandates is UTF-8). Trusting that guess corrupts every
    # non-ASCII byte (e.g. accented element names) instead of decoding them
    # correctly.
    config_dir = tmp_path / "config"
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(config_dir))
    save_session(
        "dev",
        session_from_payload({"appId": "synthetic-app", "headers": {"Cookie": "sid=secret"}}),
    )
    payload = {
        "appname": "synthetic-app",
        "pages": {
            "pgDownloaded": {
                "id": "rootDownloaded",
                "%p": {"%nm": "index"},
                "%el": {"elDownloaded": {"%x": "Text", "%p": {"%nm": "Botão Login"}}},
            }
        },
    }

    class Response:
        status_code = 200
        content = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        encoding = "ISO-8859-1"

    monkeypatch.setattr("bubble_mcp.context.detector.requests.get", lambda *args, **kwargs: Response())

    result = detect_project_context(profile="dev", app_id="synthetic-app", app_version="test", force=True)

    assert result.source == "downloaded_bubble"
    saved = json.loads(default_bubble_export_path("dev", "synthetic-app").read_text(encoding="utf-8"))
    assert saved["pages"]["pgDownloaded"]["%el"]["elDownloaded"]["%p"]["%nm"] == "Botão Login"


def test_detect_context_force_refreshes_default_profile_bubble_cache(
    tmp_path,
    monkeypatch,
) -> None:  # type: ignore[no-untyped-def]
    config_dir = tmp_path / "config"
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(config_dir))
    cached = default_bubble_export_path("dev", "synthetic-app")
    cached.parent.mkdir(parents=True, exist_ok=True)
    cached.write_text(
        json.dumps(
            {
                "appname": "synthetic-app",
                "pages": {
                    "pgCached": {
                        "%p": {"%nm": "index"},
                        "%el": {"elCached": {"%x": "Text", "%p": {"%nm": "Cached"}}},
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    save_settings(
        with_profile(
            BubbleMcpSettings(config_dir=config_dir, default_profile=None, profiles={}),
            BubbleProfile(
                name="dev",
                app_id="synthetic-app",
                appname="synthetic-app",
                app_json_path="contexts/dev/synthetic-app.bubble",
            ),
        )
    )
    save_session("dev", session_from_payload({"appId": "synthetic-app", "headers": {"Cookie": "sid=secret"}}))
    downloaded_payload = {
        "appname": "synthetic-app",
        "pages": {
            "pgDownloaded": {
                "%p": {"%nm": "index"},
                "%el": {"elDownloaded": {"%x": "Text", "%p": {"%nm": "Downloaded"}}},
            }
        },
    }

    class Response:
        status_code = 200
        content = json.dumps(downloaded_payload).encode("utf-8")
        encoding = "utf-8"

    monkeypatch.setattr("bubble_mcp.context.detector.requests.get", lambda *args, **kwargs: Response())

    result = detect_project_context(profile="dev", app_id="synthetic-app", app_version="test", force=True)
    context = load_context(result.context_path)

    assert result.source == "downloaded_bubble"
    assert any(node.id == "element:elDownloaded" for node in context.nodes)
    assert not any(node.id == "element:elCached" for node in context.nodes)


def test_detect_context_uses_cached_compact_context(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path / "config"))
    first_source = tmp_path / "app.bubble"
    first_source.write_text(
        json.dumps({"appname": "synthetic-app", "pages": {"pgIndex": {"%p": {"%nm": "index"}}}}),
        encoding="utf-8",
    )

    first = detect_project_context(profile="dev", app_id="synthetic-app", bubble_file=first_source)
    second = detect_project_context(profile="dev", app_id="synthetic-app")

    assert second.source == "cached_context"
    assert second.context_path == first.context_path


def test_detect_context_extracts_consolelog_app_file(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path / "config"))
    consolelog_file = tmp_path / "console.txt"
    consolelog_file.write_text(
        'console.log(app) {"appname":"synthetic-app","pages":{"pgIndex":{"%p":{"%nm":"index"}}}}',
        encoding="utf-8",
    )

    result = detect_project_context(
        profile="dev",
        app_id="synthetic-app",
        consolelog_file=consolelog_file,
    )

    assert result.source == "consolelog_file"
    assert load_context(result.context_path).summary()["counts"]["page"] == 1


def test_detect_context_falls_back_to_editor_crawler(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path / "config"))
    session = session_from_payload({"appId": "synthetic-app", "headers": {"Cookie": "sid=secret"}})
    save_session("dev", session)

    def fake_crawl(**_kwargs):  # type: ignore[no-untyped-def]
        return {
            "appId": "synthetic-app",
            "pages": [
                {
                    "id": "pgIndex",
                    "name": "index",
                    "rootId": "rootIndex",
                    "elements": {"elTitle": {"%x": "Text", "%p": {"%nm": "Title"}}},
                    "workflows": {},
                }
            ],
            "reusables": [],
            "backendWorkflows": [],
            "pageIndex": {"index": "pgIndex"},
            "reusableIndex": {},
            "apiIndex": {},
            "idToPath": {"elTitle": "%p3.pgIndex.%el.elTitle"},
            "source": "full_crawl",
        }

    monkeypatch.setattr("bubble_mcp.context.detector.crawl_project_index", fake_crawl)

    result = detect_project_context(profile="dev", app_id="synthetic-app", force=True)

    assert result.source == "editor_crawler"
    assert result.crawler_index_path is not None
    assert Path(result.crawler_index_path).exists()
    context = load_context(result.context_path)
    assert any(node.metadata.get("path_array") == ["%p3", "pgIndex", "%el", "elTitle"] for node in context.nodes)


def test_detect_context_merges_editor_network_capture_when_path_api_is_sparse(
    tmp_path,
    monkeypatch,
) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path / "config"))
    save_session(
        "dev",
        session_from_payload({"appId": "synthetic-app", "headers": {"Cookie": "sid=secret"}}),
    )

    def sparse_crawl(**_kwargs):  # type: ignore[no-untyped-def]
        return {
            "appId": "synthetic-app",
            "pages": [{"id": "catalogIndex", "name": "index", "elements": {}, "workflows": {}}],
            "reusables": [],
            "backendWorkflows": [],
            "pageIndex": {"index": "catalogIndex"},
            "reusableIndex": {},
            "apiIndex": {},
            "idToPath": {},
            "source": "full_crawl",
        }

    def network_capture(**_kwargs):  # type: ignore[no-untyped-def]
        return {
            "appId": "synthetic-app",
            "pages": [
                {
                    "id": "pgIndex",
                    "name": "index",
                    "rootId": "rootIndex",
                    "elements": {"elTitle": {"id": "elTitle"}},
                    "workflows": {},
                }
            ],
            "reusables": [],
            "backendWorkflows": [],
            "pageIndex": {"index": "pgIndex"},
            "reusableIndex": {},
            "apiIndex": {},
            "idToPath": {"rootIndex": "%p3.pgIndex", "elTitle": "%p3.pgIndex.%el.elTitle"},
            "source": "editor_network_capture",
        }

    monkeypatch.setattr("bubble_mcp.context.detector.crawl_project_index", sparse_crawl)
    monkeypatch.setattr("bubble_mcp.context.detector._try_capture_editor_network_index", network_capture)

    result = detect_project_context(profile="dev", app_id="synthetic-app", force=True)
    context = load_context(result.context_path)

    page = next(node for node in context.nodes if node.type == "page")
    assert page.metadata["bubble_id"] == "pgIndex"
    assert page.metadata["root_id"] == "rootIndex"
    assert page.metadata["children"] == ["elTitle"]
    assert any(node.id == "element:elTitle" for node in context.nodes)
