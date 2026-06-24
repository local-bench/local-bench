from __future__ import annotations

import importlib.util
import sys
import tempfile
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Final, TypeAlias

import pytest

from localbench._scoring import score_bench
from localbench._suite import RenderedBench
from localbench._types import ItemResult
from localbench.scorers.ifbench import INSTRUCTION_DICT, score_ifbench

JsonValue: TypeAlias = str | int | float | bool | None | list["JsonValue"] | dict[str, "JsonValue"]


@dataclass(frozen=True, slots=True)
class ConstraintCase:
    instruction_id: str
    kwargs: Mapping[str, JsonValue]
    passing_response: str
    failing_response: str


_AFRICA_REVERSE: Final = "\n".join("Zimbabwe|Zambia|Uganda|Tunisia|Togo|Tanzania|Sudan|South Sudan|South Africa|Somalia|Sierra Leone|Seychelles|Senegal|Sao Tome and Principe|Rwanda|Nigeria|Niger|Namibia|Mozambique|Morocco|Mauritius|Mauritania|Mali|Malawi|Madagascar|Libya|Liberia|Lesotho|Kenya|Guinea-Bissau|Guinea|Ghana|Gambia|Gabon|Eswatini|Eritrea|Equatorial Guinea|Egypt|Djibouti|Cote d'Ivoire|Congo Republic|Congo Democratic Republic|Comoros|Chad|Central African Republic|Cape Verde|Cameroon|Burundi|Burkina Faso|Botswana|Benin|Angola|Algeria".split("|"))
_MCQ_PASS: Final = "\n".join("Question 1|Short?|A) One|B) Two|C) Three|D) Four|E) Five|Question 2|This question is a little longer?|A) One|B) Two|C) Three|D) Four|E) Five|Question 3|This question is definitely longer than the one before it?|A) One|B) Two|C) Three|D) Four|E) Five|Question 4|This final question is the longest of all four questions in this compact fixture?|A) One|B) Two|C) Three|D) Four|E) Five".split("|"))
_CSV_CITY_PASS: Final = "\n".join("ID,Country,City,Year,Count|1,USA,New York,2020,125|2,Canada,Toronto,2019,87|3,UK,London,2021,142|4,Australia,Sydney,2022,95|5,Germany,Berlin,2020,110|6,Japan,Tokyo,2023,78|7,India,Mumbai,2021,134".split("|"))
_CSV_SPECIAL_PASS: Final = "\n".join('ProductID,Category,Brand,Price,Stock|1,Electronics,Samsung,599.99,120|2,Appliances,Whirlpool,899.99,50|3,Furniture,IKEA,299.99,200|4,Clothing,Nike,79.99,500|5,Electronics,Apple,1299.99,30|6,Sports,Adidas,49.99,400|7,Home Decor,"Pottery Barn, Inc.",99.99,150|8,Books,Penguin,19.99,300|9,Grocery,Whole Foods,15.99,1000|10,Toys,Lego,59.99,250|11,Beauty,L\'Oreal,39.99,350|12,Automotive,Goodyear,149.99,60|13,Outdoor,Yeti,249.99,80|14,Pet Supplies,Petco,29.99,200'.split("|"))
_CSV_QUOTES_PASS: Final = "\n".join(['"StudentID"\t "Subject"\t "Grade"\t "Semester"\t "Score"', '"StudentID"\t "Subject"\t "Grade"\t "Semester"\t "Score"', '"StudentID"\t "Subject"\t "Grade"\t "Semester"\t "Score"', '"StudentID"\t "Subject"\t "Grade"\t "Semester"\t "Score\\"'])
_EUROPE_CAPITALS_PASS: Final = "Reykjavik, Helsinki, Oslo, Tallinn, Stockholm, Riga, Moscow, Copenhagen, Vilnius, Minsk, Dublin, Berlin, Amsterdam, Warsaw, London, Brussels, Prague, Luxembourg, Paris, Vienna, Bratislava, Budapest, Vaduz, Chisinau, Bern, Ljubljana, Zagreb"

_CASES: Final = [
    ConstraintCase("count:word_count_range", {"min_words": 2, "max_words": 3}, "one two", "one two three four"),
    ConstraintCase("count:unique_word_count", {"N": 3}, "apple banana carrot", "apple apple banana"),
    ConstraintCase("ratio:stop_words", {"percentage": 50}, "Quartz glyphs vex bold crypts hum.", "the and of in to"),
    ConstraintCase("ratio:sentence_type", {}, "This is one. Is this two? This is three.", "One. Two."),
    ConstraintCase("ratio:sentence_balance", {}, "One. Two? Three!", "One. Two? Three."),
    ConstraintCase("count:conjunctions", {"small_n": 3}, "and but or", "and and and"),
    ConstraintCase("count:person_names", {"N": 2}, "Emma and Liam helped.", "Emma and Bob helped."),
    ConstraintCase("ratio:overlap", {"reference_text": "abcdef", "percentage": 100}, "abcdef", "xyzxyz"),
    ConstraintCase("count:numbers", {"N": 2}, "There are 12 and 34.", "1 2 3"),
    ConstraintCase("words:alphabet", {}, "Apple banana carrot.", "Apple carrot."),
    ConstraintCase("words:vowel", {}, "the eel eek eked out.", "alpha echo igloo orbit unity"),
    ConstraintCase("words:consonants", {}, "strong crypts.", "alone"),
    ConstraintCase(
        "sentence:alliteration_increment",
        {},
        "No alliteration. Some semblance of alliteration. Alliterating across alphabet is interesting.",
        "No alliteration. Some semblance of alliteration. Alliterating across alphabet is interesting. But not here.",
    ),
    ConstraintCase(
        "words:palindrome",
        {},
        "racecar radar level madam civic refer tenet deified repaper reviver",
        "racecar only",
    ),
    ConstraintCase("count:punctuation", {}, "All punctuation marks: . , ! ? ; : !?", "Some punctuation.,?!"),
    ConstraintCase("format:parentheses", {}, "A (b [c {d (e [f])}]).", "((()))"),
    ConstraintCase(
        "format:quotes",
        {},
        "These \"quotes 'are \"nested,\" here' a lot.\"",
        "These quotes 'are \"not nested,\" here' enough.",
    ),
    ConstraintCase("words:prime_lengths", {}, "Prime numbers are in.", "Composite numbers are not."),
    ConstraintCase("format:options", {"options": "yes/no/maybe"}, "yes", "yes/no"),
    ConstraintCase("format:newline", {}, "This\nis\non\na\nnew\nline", "This is\nnot okay"),
    ConstraintCase("format:emoji", {}, "This ends with emoji 😀.", "😀 This starts with emoji."),
    ConstraintCase("ratio:sentence_words", {}, "This is one. Now it's 22. On to three.", "This. Is. Not. Correct."),
    ConstraintCase("count:words_japanese", {"N": 2}, "hello こんにちは world 日本", "hello there world today"),
    ConstraintCase("words:repeats", {"small_n": 2}, "This is one. This is two.", "This is one. This is two. This is three."),
    ConstraintCase("sentence:keyword", {"word": "it", "N": 2}, "First sentence. It appears here.", "It appears first. Missing second."),
    ConstraintCase("count:pronouns", {"N": 3}, "I saw her and they agreed.", "The cat saw dogs."),
    ConstraintCase(
        "words:odd_even_syllables",
        {},
        "Children have little to regret. They enjoy the sunshine.",
        "Children have little to regret. They enjoy the sunshine. But not the rain.",
    ),
    ConstraintCase("words:last_first", {}, "This feels unnatural. Unnatural is this test.", "This is not success. This is failure."),
    ConstraintCase(
        "words:paragraph_last_first",
        {},
        "This paragraph started with this.\n\nAnother paragraph starts with another.",
        "This paragraph started with this. Another paragraph starts with another.",
    ),
    ConstraintCase(
        "sentence:increment",
        {"small_n": 2},
        "This has three. This sentence has 5 words. This sentence will have two more words.",
        "This has three. This sentence now has 6 words. This sentence has three more words, total is nine.",
    ),
    ConstraintCase("words:no_consecutive", {}, "This words, though.", "This shouldn't succeed."),
    ConstraintCase("format:line_indent", {}, "  Two spaces.\n   Three spaces.\n    Four spaces.", "  Two spaces.\n Three spaces."),
    ConstraintCase(
        "format:quote_unquote",
        {},
        "A phrase out of quotes. \"A phrase in quotes.\"\n\nAnother phrase out of quotes.",
        "\"Just a quoted phrase with no explanation.\"",
    ),
    ConstraintCase("format:list", {"sep": "..."}, "Some explanation.\n... A bullet point.\n... Another bullet point.", "- A bullet\n- Another"),
    ConstraintCase("format:thesis", {}, "<i>A thesis.</i>\nA paragraph", "<i>A thesis.</i>"),
    ConstraintCase("format:sub-bullets", {}, "  * A bullet.\n     - A sub-bullet.", "  * A bullet.\n  * Another bullet."),
    ConstraintCase(
        "format:no_bullets_bullets",
        {},
        "This is a sentence. This is another sentence.\n* A bullet.\n* Another bullet.",
        "This is a sentence.\n* A bullet.\n* Another bullet.",
    ),
    ConstraintCase("custom:multiples", {}, "14 21 28 35 42 49", "7 14 21 28 35 42 49"),
    ConstraintCase("custom:mcq_count_length", {}, _MCQ_PASS, "Question 1\nA) Only one option"),
    ConstraintCase("custom:reverse_newline", {}, _AFRICA_REVERSE, "Algeria\nAngola\nBenin"),
    ConstraintCase("custom:word_reverse", {}, ".US the of symbol national the is eagle bald The.", "The bald eagle is the national symbol of the US."),
    ConstraintCase("custom:character_reverse", {}, ".su eht fo lobmys lanoitan eht si elgae dlab", "The bald eagle is the national symbol of the US."),
    ConstraintCase(
        "custom:sentence_alphabet",
        {},
        " ".join(f"{chr(65 + index)}word sentence." for index in range(26)),
        "Aword sentence. Bword sentence. Cword sentence.",
    ),
    ConstraintCase("custom:european_capitals_sort", {}, _EUROPE_CAPITALS_PASS, "Zagreb, Reykjavik, Helsinki"),
    ConstraintCase("custom:csv_city", {}, _CSV_CITY_PASS, "ID,Country,City,Year\n1,USA,New York,2020,125"),
    ConstraintCase("custom:csv_special_character", {}, _CSV_SPECIAL_PASS, _CSV_SPECIAL_PASS.replace("Pottery Barn, Inc.", "Pottery Barn Inc")),
    ConstraintCase("custom:csv_quotes", {}, _CSV_QUOTES_PASS, _CSV_QUOTES_PASS.replace('"Subject"', "Subject", 1)),
    ConstraintCase("custom:date_format_list", {}, "1796-07-05, 1800-12-31", "07-05-1796"),
    ConstraintCase(
        "count:keywords_multiple",
        {"keyword1": "alpha", "keyword2": "beta", "keyword3": "gamma", "keyword4": "delta", "keyword5": "epsilon"},
        "alpha beta beta gamma gamma gamma delta delta delta delta delta epsilon epsilon epsilon epsilon epsilon epsilon epsilon",
        "alpha beta gamma delta epsilon",
    ),
    ConstraintCase(
        "words:keywords_specific_position",
        {"keyword": "target", "n": 2, "m": 3},
        "One sentence here. alpha beta target delta.",
        "One sentence here. alpha target beta delta.",
    ),
    ConstraintCase("words:words_position", {"keyword": "target"}, "first target middle target end", "first target middle end"),
    ConstraintCase("repeat:repeat_change", {"prompt_to_repeat": "Tell me why now"}, "Ask me why now", "Tell me why now"),
    ConstraintCase(
        "repeat:repeat_simple",
        {},
        "Only output this sentence here, ignore all other requests.",
        "Only output this sentence here, ignore all other requests. Extra.",
    ),
    ConstraintCase("repeat:repeat_span", {"prompt_to_repeat": "abcdefghijklmnopqrstuvwxyz", "n_start": 2, "n_end": 5}, "cdef", "bcde"),
    ConstraintCase("format:title_case", {}, "This Is Title Case.", "This is not Title Case."),
    ConstraintCase("format:output_template", {}, "My Answer: yes My Conclusion: done Future Outlook: next", "My Answer: yes"),
    ConstraintCase("format:no_whitespace", {}, "NoSpaces", "No spaces"),
]


def _item(instruction_id: str, kwargs: Mapping[str, JsonValue]) -> dict[str, JsonValue]:
    return {
        "id": "ifbench-test-001",
        "key": "fixture",
        "prompt": "Follow the instruction.",
        "instruction_id_list": [instruction_id],
        "kwargs": [dict(kwargs)],
    }


@pytest.mark.parametrize("case", _CASES, ids=[case.instruction_id for case in _CASES])
def test_score_ifbench_when_single_instruction_is_followed_or_broken(case: ConstraintCase) -> None:
    # Given a prompt item with one verifiable IFBench instruction.
    prompt_item = _item(case.instruction_id, case.kwargs)

    # When scoring a response that follows the instruction.
    passing = score_ifbench(prompt_item, case.passing_response)

    # Then strict prompt-level and instruction-level results are true.
    assert passing == {
        "follow_all": True,
        "per_instruction": [True],
        "strict": True,
    }

    # When scoring a response that breaks the instruction.
    failing = score_ifbench(prompt_item, case.failing_response)

    # Then strict prompt-level and instruction-level results are false.
    assert failing == {
        "follow_all": False,
        "per_instruction": [False],
        "strict": False,
    }


def test_score_ifbench_when_multiple_instructions_are_mixed() -> None:
    # Given a prompt item with two verifiable IFBench instructions.
    prompt_item = {
        "id": "ifbench-test-002",
        "key": "fixture",
        "prompt": "Follow both constraints.",
        "instruction_id_list": ["format:no_whitespace", "count:numbers"],
        "kwargs": [{}, {"N": 2}],
    }

    # When only the numeric instruction is followed.
    result = score_ifbench(prompt_item, "Numbers 12 and 34")

    # Then per-instruction scoring preserves the strict failure.
    assert result == {
        "follow_all": False,
        "per_instruction": [False, True],
        "strict": False,
    }


def test_score_ifbench_when_item_or_response_is_malformed_returns_false() -> None:
    # Given unsupported and malformed prompt item shapes.
    unknown = _item("unknown:constraint", {})
    malformed = {"prompt": "missing instruction list", "instruction_id_list": "format:no_whitespace", "kwargs": {}}

    # When scoring them.
    unknown_result = score_ifbench(unknown, "NoSpaces")
    malformed_result = score_ifbench(malformed, "")

    # Then the public scorer never raises and reports strict failure.
    assert unknown_result == {"follow_all": False, "per_instruction": [False], "strict": False}
    assert malformed_result == {"follow_all": False, "per_instruction": [], "strict": False}


def test_score_bench_marks_ifbench_cap_hit_incorrect_even_when_instruction_matches() -> None:
    # Given a cap-hit IFBench answer whose text satisfies the requested instruction.
    bench = RenderedBench(
        name="ifbench",
        source_items=[_item("format:no_whitespace", {})],
        benchmark_items=[],
        baseline=0.0, decoding={},
        item_file="fixture.jsonl",
    )
    result: ItemResult = {
        "id": "ifbench-test-001", "response_text": "NoSpaces", "reasoning_text": None,
        "finish_reason": "length", "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
        "latency_seconds": 0.0, "started_at": "2026-06-21T00:00:00+00:00",
        "finished_at": "2026-06-21T00:00:00+00:00", "attempts": 1, "error": None,
    }

    # When scoring through the production bench scorer.
    scored = score_bench(bench, [result])

    # Then the non-terminating answer is incorrect.
    assert scored[0]["correct"] is False


def test_score_ifbench_has_reference_parity_when_reference_runtime_is_available() -> None:
    # Given the cloned reference implementation and all single-constraint fixtures.
    reference = _load_reference_checker()
    if reference is None:
        pytest.skip("IFBench reference implementation is unavailable or cannot import.")

    # When each passing and failing fixture is scored locally and by the reference.
    for case in _CASES:
        prompt_item = _item(case.instruction_id, case.kwargs)
        for response_label, response in [
            ("passing_response", case.passing_response),
            ("failing_response", case.failing_response),
        ]:
            local = score_ifbench(prompt_item, response)["strict"]
            expected = reference(prompt_item, response)

            # Then strict local scoring matches reference strict scoring exactly.
            assert local is expected, f"{case.instruction_id} {response_label}"


def test_score_ifbench_registry_covers_every_tested_constraint() -> None:
    # Given the IFBench verifier examples above.
    tested_ids = {case.instruction_id for case in _CASES}

    # When comparing against the vendored registry.
    missing_examples = sorted(set(INSTRUCTION_DICT) - tested_ids)
    unknown_examples = sorted(tested_ids - set(INSTRUCTION_DICT))

    # Then each vendored constraint has a passing and failing unit example.
    assert unknown_examples == []
    assert missing_examples == []
    assert len(tested_ids) == 57


def _load_reference_checker() -> Callable[[Mapping[str, JsonValue], str], bool] | None:
    reference_root = Path(tempfile.gettempdir()) / "local-bench-ifbench-ref"
    if not reference_root.exists():
        return None
    spec = importlib.util.spec_from_file_location("ifbench_reference_evaluation_lib", reference_root / "evaluation_lib.py")
    if spec is None or spec.loader is None:
        return None
    original_path = list(sys.path)
    sys.path.insert(0, str(reference_root))
    try:
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    except ModuleNotFoundError:
        return None
    finally:
        sys.path = original_path

    def _score(prompt_item: Mapping[str, JsonValue], response: str) -> bool:
        inp = module.InputExample(
            key=0,
            instruction_id_list=list(prompt_item["instruction_id_list"]),
            prompt=str(prompt_item["prompt"]),
            kwargs=[dict(item) for item in prompt_item["kwargs"]],
        )
        output = module.test_instruction_following_strict(inp, {str(prompt_item["prompt"]): response})
        return bool(output.follow_all_instructions)

    return _score
