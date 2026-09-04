"""One place that loads the aria runtime modules, by their real package path.

Three call sites used to do this themselves, and each did it the same way: insert
``src/bubble_mcp/aria_runtime`` at the FRONT of ``sys.path`` and then import the bare
top-level names ``bubble_cli`` and ``bubble_sdk``. That was not sloppiness - the runtime's own
modules imported each other the same way, 41 times across 17 files - but it had two costs.

**The name is not ours.** ``bubble_cli`` is also the package name of a separate Bubble CLI that
is installed alongside this server (see the ``data`` extra). ``sys.modules`` has one slot per
top-level name and whoever imports first wins for the life of the process, so a bare import
could hand back the other project's package and the runtime would silently drive the wrong
object. Inserting at the front of ``sys.path`` only helps if nothing imported that name first.

**Mixing the two styles splits module identity.** Loading ``bubble_sdk`` as a top-level module
in one place and as ``bubble_mcp.aria_runtime.bubble_sdk`` in another produces two distinct
objects for one file. A caller that patches ``PayloadBuilder.send_to_webhook`` on one then has
no effect on the runtime holding the other - which is a silent failure, and is exactly what an
earlier half-migration of this loader caused.

So the fix had to be both halves at once: the runtime's internal imports are now absolute
package imports, and so is this loader. There is one object per module, no ``sys.path``
mutation, and the top-level names are left to whoever else wants them.
"""

from __future__ import annotations

from typing import Any


class FakeInquirer:
    """Stand-in for the interactive prompt library the runtime expects to exist.

    The runtime was written as a terminal program; served over MCP there is nobody to answer a
    prompt, so it has to be inert rather than blocking on stdin that will never arrive.
    """

    class List:
        def __init__(self, *_args: Any, **_kwargs: Any) -> None:
            pass

    class Text:
        def __init__(self, *_args: Any, **_kwargs: Any) -> None:
            pass

    @staticmethod
    def prompt(_questions: Any) -> None:
        return None


def load_aria_runtime_modules() -> tuple[Any, Any]:
    """Return ``(bubble_cli, bubble_sdk)`` from this package, never from ``sys.path``."""

    from bubble_mcp.aria_runtime import bubble_cli, bubble_sdk

    # Attached here rather than at each call site, so every caller sees the same patched module
    # instead of it depending on which one imported first.
    setattr(bubble_cli, "inquirer", FakeInquirer())
    return bubble_cli, bubble_sdk
