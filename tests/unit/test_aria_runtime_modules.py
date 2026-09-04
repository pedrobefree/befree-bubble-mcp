"""The aria runtime is loaded by package path, never by the bare name ``bubble_cli``.

``bubble_cli`` is also the package name of a separate Bubble CLI installed alongside this
server through the ``data`` extra. ``sys.modules`` has one slot per top-level name, so a loader
importing the bare name hands back whichever project got there first - and nothing announces
it: the runtime would call methods on somebody else's module.

The second test here guards the failure mode that made an earlier attempt at this fix worse
than the bug. Migrating only the loaders, and leaving the runtime's own internal imports bare,
produced TWO module objects for ``bubble_sdk``: the runtime held the top-level one while
callers were handed the package one, so a caller patching ``PayloadBuilder`` had no effect on
the code that runs. Identity is the property that has to hold, not merely the import style.
"""

from __future__ import annotations

import sys
import types

import pytest

from bubble_mcp.aria_runtime_modules import FakeInquirer, load_aria_runtime_modules


def test_modules_are_loaded_from_this_package() -> None:
    bubble_cli, bubble_sdk = load_aria_runtime_modules()

    assert bubble_cli.__name__ == "bubble_mcp.aria_runtime.bubble_cli"
    assert bubble_sdk.__name__ == "bubble_mcp.aria_runtime.bubble_sdk"


def test_the_runtime_and_its_callers_share_one_sdk_object() -> None:
    # The identity that a half-migration breaks. If these ever diverge, a test that patches
    # PayloadBuilder passes while the runtime keeps calling the unpatched one.
    bubble_cli, bubble_sdk = load_aria_runtime_modules()

    assert bubble_cli.PayloadBuilder is bubble_sdk.PayloadBuilder


def test_loading_does_not_claim_the_global_bubble_cli_name() -> None:
    # Squatting the name would break the other project for the rest of the process, in exactly
    # the environments where both are installed.
    sys.modules.pop("bubble_cli", None)
    sys.modules.pop("bubble_sdk", None)

    load_aria_runtime_modules()

    assert "bubble_cli" not in sys.modules
    assert "bubble_sdk" not in sys.modules


def test_an_unrelated_bubble_cli_package_does_not_win(monkeypatch: pytest.MonkeyPatch) -> None:
    # The collision itself: another project already occupies the top-level name.
    impostor = types.ModuleType("bubble_cli")
    impostor.__file__ = "/somewhere/else/bubble_cli/__init__.py"
    monkeypatch.setitem(sys.modules, "bubble_cli", impostor)

    bubble_cli, _ = load_aria_runtime_modules()

    assert bubble_cli is not impostor
    assert bubble_cli.__name__ == "bubble_mcp.aria_runtime.bubble_cli"


def test_every_call_site_gets_the_same_module_object() -> None:
    from bubble_mcp.aria_dispatch import _load_aria_runtime_modules as from_dispatch
    from bubble_mcp.figma_bridge import _load_aria_runtime_modules as from_figma
    from bubble_mcp.html_runtime import _load_aria_runtime_modules as from_html

    first_cli, first_sdk = from_dispatch()
    second_cli, second_sdk = from_figma()
    third_cli, third_sdk = from_html()

    assert first_cli is second_cli is third_cli
    assert first_sdk is second_sdk is third_sdk


def test_the_inquirer_stub_is_attached_for_every_caller() -> None:
    # The runtime was written as a terminal program; over MCP nobody can answer a prompt, so it
    # must be inert rather than blocking on stdin that never arrives.
    bubble_cli, _ = load_aria_runtime_modules()

    assert isinstance(bubble_cli.inquirer, FakeInquirer)
    assert bubble_cli.inquirer.prompt([{"anything": True}]) is None


def test_no_bare_sibling_imports_remain_in_the_runtime() -> None:
    # The loaders alone are not enough: one bare `from bubble_sdk import ...` left inside the
    # runtime reintroduces both the collision and the split identity. This is the check that
    # would have caught the earlier broken attempt before the suite did.
    import re
    from pathlib import Path

    import bubble_mcp.aria_runtime as runtime_package

    root = Path(runtime_package.__file__).parent
    local_modules = sorted(path.stem for path in root.glob("*.py") if path.stem != "__init__")
    bare = re.compile(r"^\s*(?:from|import)\s+(" + "|".join(local_modules) + r")(?:\s|$|\.)", re.MULTILINE)

    offenders = [
        f"{path.relative_to(root).as_posix()}:{match.group(1)}"
        for path in root.rglob("*.py")
        for match in bare.finditer(path.read_text(encoding="utf-8"))
    ]

    assert offenders == [], (
        "these imports resolve a runtime module by its bare top-level name, which collides "
        f"with any installed package of the same name: {offenders}"
    )
