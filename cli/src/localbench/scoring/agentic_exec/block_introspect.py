"""Static introspection of a model code block for diagnostics (no execution).

The loop needs, per executed block, two counts for the axis-falsification diagnostics:

  * how many ``apis.<app>.<api>(...)`` call expressions it contains (total API-call count), and
  * how many of those are ``apis.api_docs.*`` (on-demand doc usage).

We count these by parsing the block's AST on the TRUSTED orchestrator side (the block also
runs inside the jail, but the jail returns only stdout, not a call count). AST parsing here
is pure analysis — we never ``exec`` the code on this side. If the block does not parse
(SyntaxError), counts are 0 and the loop records the syntax error from the sandbox result.

Also hosts the observation truncation helper so the loop and tests share one definition.

Pure / import-safe: stdlib only.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class BlockCounts:
    """API-call counts statically extracted from one code block."""

    api_calls: int       # total apis.<app>.<api>(...) call expressions (incl. api_docs)
    api_docs_calls: int  # subset that are apis.api_docs.<fn>(...)


def count_api_calls(code: str) -> BlockCounts:
    """Count ``apis.*`` call expressions in ``code`` via AST (no execution).

    Recognises the canonical Protocol C call shapes:
      * ``apis.<app>.<api>(...)``           -> 1 api_call
      * ``apis.api_docs.<fn>(...)``         -> 1 api_call AND 1 api_docs_call

    A bare attribute access without a call (``apis.spotify``) is not counted; only call
    expressions count, matching "API-call count". Unparseable code yields zero counts.
    """
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return BlockCounts(api_calls=0, api_docs_calls=0)

    api_calls = 0
    api_docs_calls = 0
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        # We want Attribute chains rooted at the Name ``apis``: apis.<x>.<y>
        if not isinstance(func, ast.Attribute):
            continue
        inner = func.value
        if not isinstance(inner, ast.Attribute):
            continue
        root = inner.value
        if isinstance(root, ast.Name) and root.id == "apis":
            api_calls += 1
            if inner.attr == "api_docs":
                api_docs_calls += 1
    return BlockCounts(api_calls=api_calls, api_docs_calls=api_docs_calls)


@dataclass(frozen=True, slots=True)
class TruncatedText:
    """An observation string after the loop's hard char cap."""

    text: str
    truncated: bool


def truncate_observation(text: str, max_chars: int) -> TruncatedText:
    """Hard-cap an observation to ``max_chars`` with a visible marker when cut."""
    if max_chars <= 0 or len(text) <= max_chars:
        return TruncatedText(text=text, truncated=False)
    marker = "\n...[observation truncated]"
    keep = max(0, max_chars - len(marker))
    return TruncatedText(text=text[:keep] + marker, truncated=True)
