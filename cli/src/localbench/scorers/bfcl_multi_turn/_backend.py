from __future__ import annotations

import copy
import importlib
import sys
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Final

from localbench.scorers.bfcl_multi_turn._types import JsonObject, JsonValue

_REPO_ROOT: Final = Path(__file__).resolve().parents[5]
_BFCL_ROOT: Final = (
    _REPO_ROOT / "cli" / ".venv" / "bfcl-eval-ref" / "berkeley-function-call-leaderboard"
)
_BACKEND_PREFIX: Final = "bfcl_eval.eval_checker.multi_turn_eval.func_source_code"
_STATELESS_CLASSES: Final = {"MathAPI"}


@dataclass(frozen=True, slots=True)
class BackendSpec:
    module_name: str
    class_name: str


_ALLOWED_BACKENDS: Final[dict[str, BackendSpec]] = {
    "GorillaFileSystem": BackendSpec(f"{_BACKEND_PREFIX}.gorilla_file_system", "GorillaFileSystem"),
    "MathAPI": BackendSpec(f"{_BACKEND_PREFIX}.math_api", "MathAPI"),
    "MessageAPI": BackendSpec(f"{_BACKEND_PREFIX}.message_api", "MessageAPI"),
    "TwitterAPI": BackendSpec(f"{_BACKEND_PREFIX}.posting_api", "TwitterAPI"),
    "TicketAPI": BackendSpec(f"{_BACKEND_PREFIX}.ticket_api", "TicketAPI"),
    "TradingBot": BackendSpec(f"{_BACKEND_PREFIX}.trading_bot", "TradingBot"),
    "TravelAPI": BackendSpec(f"{_BACKEND_PREFIX}.travel_booking", "TravelAPI"),
    "VehicleControlAPI": BackendSpec(f"{_BACKEND_PREFIX}.vehicle_control", "VehicleControlAPI"),
}


class BackendLoadError(RuntimeError):
    pass


def allowed_backend_names() -> set[str]:
    return set(_ALLOWED_BACKENDS)


def load_backend_instances(
    involved_classes: list[str],
    initial_config: Mapping[str, JsonValue],
    *,
    long_context: bool,
) -> dict[str, object]:
    _ensure_vendor_path()
    _freeze_travel_datetime()
    instances: dict[str, object] = {}
    for class_name in involved_classes:
        spec = _ALLOWED_BACKENDS.get(class_name)
        if spec is None:
            raise BackendLoadError(f"Backend class is not allowlisted: {class_name}")
        class_type = _load_class(spec)
        instance = class_type()
        if class_name not in _STATELESS_CLASSES:
            config = initial_config.get(class_name, {})
            if not isinstance(config, dict):
                config = {}
            load_scenario = getattr(instance, "_load_scenario")
            load_scenario(copy.deepcopy(config), long_context=long_context)
        instances[class_name] = instance
    return instances


def public_method_map(instances: Mapping[str, object]) -> dict[str, tuple[str, Callable[..., object]]]:
    methods: dict[str, tuple[str, Callable[..., object]]] = {}
    for class_name, instance in instances.items():
        for method_name in dir(instance):
            if method_name.startswith("_"):
                continue
            method = getattr(instance, method_name)
            if callable(method):
                methods[method_name] = (class_name, method)
    return methods


def _ensure_vendor_path() -> None:
    if not _BFCL_ROOT.exists():
        raise BackendLoadError(f"Missing vendored BFCL evaluator at {_BFCL_ROOT}")
    path_text = str(_BFCL_ROOT)
    if path_text not in sys.path:
        sys.path.insert(0, path_text)


def _load_class(spec: BackendSpec) -> type:
    module = importlib.import_module(spec.module_name)
    class_type = getattr(module, spec.class_name)
    if not isinstance(class_type, type):
        raise BackendLoadError(f"{spec.module_name}.{spec.class_name} is not a class")
    return class_type


def _freeze_travel_datetime() -> None:
    module_name = f"{_BACKEND_PREFIX}.travel_booking"
    try:
        module = importlib.import_module(module_name)
    except ModuleNotFoundError:
        return
    module.datetime = _FrozenDateTime


class _FrozenDateTime(datetime):
    @classmethod
    def today(cls) -> "_FrozenDateTime":
        return cls(2026, 1, 1)
