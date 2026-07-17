"""JCS/ECMA canonicalization must byte-match the Worker's canonicalJson.

The server (web/functions/_lib/submission-canonical.ts) re-derives projection
digests from JSON.parse'd values, so the client's canonical bytes must survive
a JSON round-trip through ECMAScript: integral floats render as integers,
exponent switchover follows Number::toString, keys sort by UTF-16 code units.
Pinned strings/digests below were produced by the TS algorithm via node
(fixtures/jcs_reference.js, 2026-07-17).
"""

from __future__ import annotations

import pytest

from localbench.submissions.canon import _ecma_number_str, jcs_json_bytes, jcs_json_hash

ECMA_NUMBER_CASES = [
    (0.0, "0"),
    (-0.0, "0"),
    (1.0, "1"),
    (123.0, "123"),
    (10.0, "10"),
    (-1.5, "-1.5"),
    (0.5, "0.5"),
    (2 / 3, "0.6666666666666666"),
    (0.07692307692307693, "0.07692307692307693"),
    (1e16, "10000000000000000"),
    (1e21, "1e+21"),
    (1e-6, "0.000001"),
    (1e-7, "1e-7"),
    (5e-324, "5e-324"),
    (1e300, "1e+300"),
    (1234567890123.4, "1234567890123.4"),
    (7, "7"),
    (-42, "-42"),
]


@pytest.mark.parametrize(("value", "expected"), ECMA_NUMBER_CASES)
def test_ecma_number_formatting(value: float, expected: str) -> None:
    assert _ecma_number_str(value) == expected


def test_ecma_number_rejects_non_finite() -> None:
    with pytest.raises(ValueError):
        _ecma_number_str(float("nan"))
    with pytest.raises(ValueError):
        _ecma_number_str(float("inf"))


def test_ecma_number_rejects_unsafe_integers() -> None:
    with pytest.raises(ValueError):
        _ecma_number_str(2**53)


def test_jcs_bytes_match_worker_canonical_json() -> None:
    value = {
        "zeta": [0.0, 1.0, 0.07692307692307693, 1e16, 1e-7, None, True, False],
        "alpha": {"nested": {"rate": 0.0, "count": 1311, "label": "a\"b\\c\nend\u001f"}},
        "Beta": "unicode é中文 raw",
        "empty_obj": {},
        "empty_arr": [],
    }
    expected = (
        '{"Beta":"unicode é中文 raw",'
        '"alpha":{"nested":{"count":1311,"label":"a\\"b\\\\c\\nend\\u001f","rate":0}},'
        '"empty_arr":[],"empty_obj":{},'
        '"zeta":[0,1,0.07692307692307693,10000000000000000,1e-7,null,true,false]}'
    )
    assert jcs_json_bytes(value).decode("utf-8") == expected
    assert jcs_json_hash(value) == "8bffebbd1ca56763f91182e63ecf469d068d9459da49b14d67e9d0cb977827ac"


def test_jcs_hash_pinned_against_worker() -> None:
    value = {"rate": 0.0, "score": 73.75, "n": 400, "ok": True, "tag": "x"}
    assert jcs_json_bytes(value).decode("utf-8") == '{"n":400,"ok":true,"rate":0,"score":73.75,"tag":"x"}'
    assert jcs_json_hash(value) == "2f01166664bc5b8b39a0f358d10994e029640d2ab0bab5e6e6e5e0c6fc4a018f"


def test_jcs_integral_float_and_int_collide() -> None:
    # JSON.parse cannot distinguish 1.0 from 1; the canonical form must not either.
    assert jcs_json_bytes({"v": 1.0}) == jcs_json_bytes({"v": 1})
