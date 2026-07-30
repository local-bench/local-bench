from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Final, Literal, TypeAlias, assert_never

from localbench._types import JsonObject, JsonValue
from localbench.prompt_rendering import TemplateIntrospection, derive_template_introspection

ProfileCandidateState: TypeAlias = Literal["thinking", "nonthinking", "unresolved"]
GgufTemplateSource: TypeAlias = Literal["gguf-default", "gguf-tool-use-only", "absent"]

GGUF_GENERIC_THINK_CONFIRMED: Final = "gguf_generic_think_confirmed"
GGUF_NONTHINKING_CONFIRMED: Final = "gguf_nonthinking_confirmed"
LLAMA_BUILTIN_CHATML_NONTHINKING: Final = "llama_builtin_chatml_nonthinking"
UNSUPPORTED_GEMMA_CHANNEL: Final = "unsupported_gemma_channel"
THINKING_STOP_UNRESOLVED: Final = "thinking_stop_unresolved"
TEMPLATE_METADATA_MALFORMED: Final = "template_metadata_malformed"
_DEFAULT_TEMPLATE_KEY: Final = "tokenizer.chat_template"
_NAMED_TEMPLATE_PREFIXES: Final = (
    "tokenizer.chat_template.",
    "chat_template.",
)
_JINJA_BLOCK_PATTERN: Final = re.compile(
    r"{%-?\s*(?P<tag>[a-zA-Z_]+)\b[^%]*-?%}",
)
_JINJA_BLOCK_STARTS: Final = frozenset(
    {"block", "call", "filter", "for", "if", "macro", "raw", "with"},
)


@dataclass(frozen=True, slots=True)
class GgufTemplateFacade:
    chat_template: str
    eos_token: str | None
    eot_token: str | None


@dataclass(frozen=True, slots=True)
class StaticProfileCandidate:
    state: ProfileCandidateState
    reason_code: str
    template_source: GgufTemplateSource
    template_sha256: str | None
    introspection: TemplateIntrospection | None


def load_gguf_template_facade(
    metadata: JsonObject,
) -> tuple[GgufTemplateFacade | None, GgufTemplateSource]:
    """Expose embedded GGUF chat-template metadata to existing introspection."""
    template, source, _ = _select_template(metadata)
    if template is None:
        return None, source
    eos_token, _ = _resolved_token(metadata, "tokenizer.ggml.eos_token_id")
    eot_token, _ = _resolved_token(metadata, "tokenizer.ggml.eot_token_id")
    return (
        GgufTemplateFacade(
            chat_template=template,
            eos_token=eos_token,
            eot_token=eot_token if eot_token != eos_token else None,
        ),
        source,
    )


def static_profile_candidate(metadata: JsonObject) -> StaticProfileCandidate:
    facade, source = load_gguf_template_facade(metadata)
    template, _, template_valid = _select_template(metadata)
    if facade is None:
        match source:
            case "absent":
                reason_code = (
                    LLAMA_BUILTIN_CHATML_NONTHINKING
                    if template_valid
                    else TEMPLATE_METADATA_MALFORMED
                )
            case "gguf-default" | "gguf-tool-use-only":
                reason_code = TEMPLATE_METADATA_MALFORMED
            case unreachable:
                assert_never(unreachable)
        return StaticProfileCandidate(
            state="unresolved",
            reason_code=reason_code,
            template_source=source,
            template_sha256=None,
            introspection=None,
        )

    template_sha256 = hashlib.sha256(facade.chat_template.encode("utf-8")).hexdigest()
    if not template_valid or not _token_metadata_is_valid(metadata):
        return StaticProfileCandidate(
            state="unresolved",
            reason_code=TEMPLATE_METADATA_MALFORMED,
            template_source=source,
            template_sha256=template_sha256,
            introspection=None,
        )

    introspection = derive_template_introspection(facade)
    match source:
        case "gguf-tool-use-only":
            return StaticProfileCandidate(
                state="unresolved",
                reason_code=TEMPLATE_METADATA_MALFORMED,
                template_source=source,
                template_sha256=template_sha256,
                introspection=introspection,
            )
        case "absent":
            return StaticProfileCandidate(
                state="unresolved",
                reason_code=LLAMA_BUILTIN_CHATML_NONTHINKING,
                template_source=source,
                template_sha256=template_sha256,
                introspection=introspection,
            )
        case "gguf-default":
            pass
        case unreachable:
            assert_never(unreachable)
    if introspection.supports_gemma_channel:
        return StaticProfileCandidate(
            state="unresolved",
            reason_code=UNSUPPORTED_GEMMA_CHANNEL,
            template_source=source,
            template_sha256=template_sha256,
            introspection=introspection,
        )

    safe_answer_stops = bool(introspection.answer_stop) and all(
        "`" not in stop for stop in introspection.answer_stop
    )
    if introspection.supports_generic_thinking:
        return StaticProfileCandidate(
            state="thinking" if safe_answer_stops else "unresolved",
            reason_code=(
                GGUF_GENERIC_THINK_CONFIRMED
                if safe_answer_stops
                else THINKING_STOP_UNRESOLVED
            ),
            template_source=source,
            template_sha256=template_sha256,
            introspection=introspection,
        )
    return StaticProfileCandidate(
        state="nonthinking" if safe_answer_stops else "unresolved",
        reason_code=(
            GGUF_NONTHINKING_CONFIRMED
            if safe_answer_stops
            else TEMPLATE_METADATA_MALFORMED
        ),
        template_source=source,
        template_sha256=template_sha256,
        introspection=introspection,
    )


def _select_template(
    metadata: JsonObject,
) -> tuple[str | None, GgufTemplateSource, bool]:
    if _DEFAULT_TEMPLATE_KEY in metadata:
        default = _nonempty_string(metadata[_DEFAULT_TEMPLATE_KEY])
        valid = default is not None and _jinja_structure_is_valid(default)
        return default, "gguf-default", valid

    named = sorted(
        (key, value)
        for key, value in metadata.items()
        if key.startswith(_NAMED_TEMPLATE_PREFIXES)
    )
    if not named:
        return None, "absent", True
    selected = next(
        ((key, value) for key, value in named if "tool_use" in key),
        named[0],
    )
    template = _nonempty_string(selected[1])
    valid = (
        all(_nonempty_string(value) is not None for _, value in named)
        and template is not None
        and _jinja_structure_is_valid(template)
    )
    return template, "gguf-tool-use-only", valid


def _resolved_token(metadata: JsonObject, token_id_key: str) -> tuple[str | None, bool]:
    if token_id_key not in metadata:
        return None, True
    token_id = _token_id(metadata[token_id_key])
    tokens = _json_array(metadata.get("tokenizer.ggml.tokens"))
    if token_id is None or tokens is None or token_id < 0 or token_id >= len(tokens):
        return None, False
    token = _nonempty_string(tokens[token_id])
    return (token, token is not None)


def _token_metadata_is_valid(metadata: JsonObject) -> bool:
    _, eos_valid = _resolved_token(metadata, "tokenizer.ggml.eos_token_id")
    _, eot_valid = _resolved_token(metadata, "tokenizer.ggml.eot_token_id")
    return eos_valid and eot_valid


def _nonempty_string(value: JsonValue) -> str | None:
    match value:
        case str() as text if text:
            return text
        case str() | bool() | int() | float() | None | list() | dict():
            return None
        case unreachable:
            assert_never(unreachable)


def _token_id(value: JsonValue) -> int | None:
    match value:
        case bool():
            return None
        case int() as token_id:
            return token_id
        case str() | float() | None | list() | dict():
            return None
        case unreachable:
            assert_never(unreachable)


def _json_array(value: JsonValue | None) -> list[JsonValue] | None:
    match value:
        case list() as items:
            return items
        case str() | bool() | int() | float() | None | dict():
            return None
        case unreachable:
            assert_never(unreachable)


def _jinja_structure_is_valid(template: str) -> bool:
    if template.count("{{") != template.count("}}"):
        return False
    if template.count("{#") != template.count("#}"):
        return False
    stack: list[str] = []
    for match in _JINJA_BLOCK_PATTERN.finditer(template):
        tag = match.group("tag")
        if tag in _JINJA_BLOCK_STARTS:
            stack.append(tag)
            continue
        if not tag.startswith("end"):
            continue
        if not stack or stack.pop() != tag[3:]:
            return False
    return not stack
