from __future__ import annotations

from types import SimpleNamespace

from localbench.manifest import _provenance


def test_production_manifest_emits_installed_package_version() -> None:
    context = SimpleNamespace(runner_build_id=None)
    provenance = _provenance(context, {})  # type: ignore[arg-type]

    import importlib.metadata

    assert provenance["cli_version"] == importlib.metadata.version("local-bench-ai")
