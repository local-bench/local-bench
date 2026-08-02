# Bundle mining results — v2 check-set grounding

Generated 2026-08-02 from lb-rung0 v1 bundles (suite full-exec-6axis-v1, lane bounded-final-v2,
exec profile generic_think_tags_8192_v1, thinking_budget 8192, max_tokens 16384).
Bundles: base=qwen36-27b-q5km-0411, q6k=qwen36-27b-q6k-046, udq2=qwen36-27b-udq2-045, fusion=qwopus-fusion-q5km-0413.
BCB pairing excludes the 7 pinned sandbox-unscoreable ids: bcbh-006, bcbh-007, bcbh-014, bcbh-035, bcbh-074, bcbh-096, bcbh-104.

## Summary report (as printed)

```
## Integrity checks
- all 4 bundles: scored id sets == suite id sets; item_hashes identical across bundles;
  scored_items.correct == run.json final correct on all non-coding benches (BCB differs by design: exec verdict lands in run.json).

## Accuracy recomputation vs recorded aggregates
- base_q5km (qwen36-27b-q5km-0411): bigcodebench_hard=27.66%; ifbench=67.01%; olymmath_hard=30.00%; amo=15.38%; tc_json_v1=73.03%
- q6k (qwen36-27b-q6k-046): bigcodebench_hard=33.33%; ifbench=63.27%; olymmath_hard=29.00%; amo=17.95%; tc_json_v1=73.33%
- udq2 (qwen36-27b-udq2-045): bigcodebench_hard=25.53%; ifbench=65.65%; olymmath_hard=18.00%; amo=17.95%; tc_json_v1=73.33%
- fusion (qwopus-fusion-q5km-0413): bigcodebench_hard=29.08%; ifbench=57.14%; olymmath_hard=33.00%; amo=23.08%; tc_json_v1=74.24%

## Paired per-item measures (candidate vs base q5km)

### bigcodebench_hard  (n_paired=141, base_acc=27.66%)
| pair | n | base_acc% | cand_acc% | net_delta_pp | n_drop | drop% | n_leap | leap% | rho_d% |
|---|---|---|---|---|---|---|---|---|---|
| q6k | 141 | 27.66 | 33.33 | +5.67 | 3 | 2.13 | 11 | 7.80 | 9.93 |
| udq2 | 141 | 27.66 | 25.53 | -2.13 | 9 | 6.38 | 6 | 4.26 | 10.64 |
| fusion | 141 | 27.66 | 29.08 | +1.42 | 11 | 7.80 | 13 | 9.22 | 17.02 |

### ifbench  (n_paired=294, base_acc=67.01%)
| pair | n | base_acc% | cand_acc% | net_delta_pp | n_drop | drop% | n_leap | leap% | rho_d% |
|---|---|---|---|---|---|---|---|---|---|
| q6k | 294 | 67.01 | 63.27 | -3.74 | 20 | 6.80 | 9 | 3.06 | 9.86 |
| udq2 | 294 | 67.01 | 65.65 | -1.36 | 24 | 8.16 | 20 | 6.80 | 14.97 |
| fusion | 294 | 67.01 | 57.14 | -9.86 | 41 | 13.95 | 12 | 4.08 | 18.03 |

### olymmath_hard  (n_paired=100, base_acc=30.00%)
| pair | n | base_acc% | cand_acc% | net_delta_pp | n_drop | drop% | n_leap | leap% | rho_d% |
|---|---|---|---|---|---|---|---|---|---|
| q6k | 100 | 30.00 | 29.00 | -1.00 | 11 | 11.00 | 10 | 10.00 | 21.00 |
| udq2 | 100 | 30.00 | 18.00 | -12.00 | 17 | 17.00 | 5 | 5.00 | 22.00 |
| fusion | 100 | 30.00 | 33.00 | +3.00 | 13 | 13.00 | 16 | 16.00 | 29.00 |

### amo  (n_paired=39, base_acc=15.38%)
| pair | n | base_acc% | cand_acc% | net_delta_pp | n_drop | drop% | n_leap | leap% | rho_d% |
|---|---|---|---|---|---|---|---|---|---|
| q6k | 39 | 15.38 | 17.95 | +2.56 | 2 | 5.13 | 3 | 7.69 | 12.82 |
| udq2 | 39 | 15.38 | 17.95 | +2.56 | 2 | 5.13 | 3 | 7.69 | 12.82 |
| fusion | 39 | 15.38 | 23.08 | +7.69 | 2 | 5.13 | 5 | 12.82 | 17.95 |

### tc_json_v1  (n_paired=330, base_acc=73.03%)
| pair | n | base_acc% | cand_acc% | net_delta_pp | n_drop | drop% | n_leap | leap% | rho_d% |
|---|---|---|---|---|---|---|---|---|---|
| q6k | 330 | 73.03 | 73.33 | +0.30 | 2 | 0.61 | 3 | 0.91 | 1.52 |
| udq2 | 330 | 73.03 | 73.33 | +0.30 | 6 | 1.82 | 7 | 2.12 | 3.94 |
| fusion | 330 | 73.03 | 74.24 | +1.21 | 4 | 1.21 | 8 | 2.42 | 3.64 |

## Degenerate items across the 4 same-profile models (base, q6k, udq2, fusion-0413)
(bonsai-27b-ternary / qwen3-5-9b per-item bundles NOT FOUND anywhere under lb-rung0 or local-bench —
 only static web pages exist for them; fusion-0411 excluded: answer_only_v1 profile, thinking_budget=0.)

| bench | n_used | floor (all 4 wrong) | ceiling (all 4 right) | degenerate% | 1-3 models correct (informative) |
|---|---|---|---|---|---|
| bigcodebench_hard | 141 | 83 | 20 | 73.0% | 38 |
| ifbench | 294 | 68 | 144 | 72.1% | 82 |
| olymmath_hard | 100 | 45 | 9 | 54.0% | 46 |
| amo | 39 | 26 | 4 | 76.9% | 9 |
| tc_json_v1 | 330 | 76 | 231 | 93.0% | 23 |

Models-correct histogram per bench (k of 4 models correct -> item count):
- bigcodebench_hard: k=0:83, k=1:11, k=2:9, k=3:18, k=4:20
- ifbench: k=0:68, k=1:29, k=2:20, k=3:33, k=4:144
- olymmath_hard: k=0:45, k=1:26, k=2:12, k=3:8, k=4:9
- amo: k=0:26, k=1:6, k=2:2, k=3:1, k=4:4
- tc_json_v1: k=0:76, k=1:9, k=2:5, k=3:9, k=4:231

## IFBench constraint-type stratification (suite/v2/ifbench.jsonl, 294 items)
- items carry `instruction_id_list` (multi-label). Constraints per item: 1 constraint(s): 251 items, 2 constraint(s): 43 items
- 57 distinct constraint types; type -> count (of constraint instances):
    sentence:keyword: 15
    words:consonants: 15
    format:sub-bullets: 12
    ratio:stop_words: 12
    ratio:overlap: 12
    count:word_count_range: 11
    words:vowel: 10
    count:unique_word_count: 9
    format:list: 9
    format:emoji: 9
    format:line_indent: 9
    format:thesis: 9
    words:odd_even_syllables: 9
    count:numbers: 8
    count:pronouns: 8
    words:no_consecutive: 8
    format:parentheses: 8
    format:quotes: 8
    sentence:increment: 8
    count:conjunctions: 7
    ratio:sentence_words: 7
    ratio:sentence_balance: 7
    words:palindrome: 7
    count:punctuation: 6
    format:newline: 6
    format:options: 6
    ratio:sentence_type: 6
    words:alphabet: 6
    words:paragraph_last_first: 6
    count:keywords_multiple: 5
    count:person_names: 5
    count:words_japanese: 5
    format:no_bullets_bullets: 5
    format:quote_unquote: 5
    sentence:alliteration_increment: 5
    words:last_first: 5
    words:prime_lengths: 5
    words:repeats: 5
    words:keywords_specific_position: 4
    repeat:repeat_span: 4
    format:title_case: 4
    format:output_template: 4
    format:no_whitespace: 4
    words:words_position: 3
    repeat:repeat_change: 3
    repeat:repeat_simple: 2
    custom:character_reverse: 1
    custom:csv_city: 1
    custom:csv_quotes: 1
    custom:csv_special_character: 1
    custom:date_format_list: 1
    custom:european_capitals_sort: 1
    custom:mcq_count_length: 1
    custom:multiples: 1
    custom:reverse_newline: 1
    custom:sentence_alphabet: 1
    custom:word_reverse: 1
- family rollup (prefix): format=98, words=83, count=64, ratio=44, sentence=28, custom=11, repeat=9

## Timing / token cost (BASE run qwen36-27b-q5km-0411, from scored_items payload)
| bench | n | med_total_tok | p90_total_tok | med_final_tok | p90_final_tok | med_reason_tok | p90_reason_tok | med_s | p90_s | sum_h |
|---|---|---|---|---|---|---|---|---|---|---|
| bigcodebench_hard | 148 | 3830 | 6751 | 185 | 314 | 3656 | 6475 | 52.9 | 93.7 | 2.23 |
| ifbench | 294 | 4550 | 8428 | 206 | 776 | 4205 | 8192 | 62.6 | 115.2 | 5.80 |
| olymmath_hard | 100 | 9211 | 9772 | 1019 | 1580 | 8192 | 8192 | 125.2 | 134.3 | 3.63 |
| amo | 39 | 9365 | 11704 | 1173 | 3512 | 8192 | 8192 | 128.2 | 160.8 | 1.49 |
| tc_json_v1 | 330 | 708 | 1500 | 49 | 117 | 632 | 1416 | 10.0 | 20.9 | 1.06 |
- items missing generated_tokens in base: [('ifbench', 'ifbench-214')]
- non-null payload.error counts: {('base_q5km', 'ifbench'): 1}
- finish_reason=length counts (base): bigcodebench_hard:0, ifbench:5, olymmath_hard:2, amo:2, tc_json_v1:0

## tc_json_v1 stratification fields (suite/v2/tc_json_v1.jsonl, 330 items)
- `stratum` -> count: bfcl_backbone=300, fresh_common_tools=30
- `source` -> count: bfcl=300, hand-authored=30
- tools-per-item dist: 1 tools:158, 2 tools:92, 3 tools:64, 4 tools:16
- gold-calls-per-item dist: 0 calls:6, 1 calls:166, 2 calls:74, 3 calls:42, 4 calls:40, 8 calls:2
- base-run failure_kind dist (scored_items): None=241, call_or_arg_mismatch=83, wrong_call_count=5, extra_text_or_multiple_json_objects=1

## olymmath_hard / amo difficulty & base accuracy distribution
- suite items carry NO difficulty/category fields (only id, statement, answer, max_tokens, sampling_params).
- olymmath_hard: base correct 30/100 (30.0%)
- amo: base correct 6/39 (15.4%)
- combined 139 math items: base correct on 36/139 (25.9%)
- models-correct histograms above give the difficulty spread; per-item correctness matrix in the md file.
```

## Paired detail: bigcodebench_hard

### q6k vs base — bigcodebench_hard
- drops (base-correct -> cand-wrong), n=3: bcbh-039, bcbh-097, bcbh-102
- leapfrogs (base-wrong -> cand-correct), n=11: bcbh-003, bcbh-016, bcbh-025, bcbh-029, bcbh-050, bcbh-051, bcbh-075, bcbh-079, bcbh-084, bcbh-111, bcbh-123

### udq2 vs base — bigcodebench_hard
- drops (base-correct -> cand-wrong), n=9: bcbh-039, bcbh-068, bcbh-095, bcbh-097, bcbh-110, bcbh-114, bcbh-118, bcbh-122, bcbh-132
- leapfrogs (base-wrong -> cand-correct), n=6: bcbh-030, bcbh-032, bcbh-087, bcbh-092, bcbh-111, bcbh-123

### fusion vs base — bigcodebench_hard
- drops (base-correct -> cand-wrong), n=11: bcbh-005, bcbh-020, bcbh-021, bcbh-027, bcbh-052, bcbh-067, bcbh-071, bcbh-097, bcbh-109, bcbh-119, bcbh-132
- leapfrogs (base-wrong -> cand-correct), n=13: bcbh-002, bcbh-004, bcbh-025, bcbh-029, bcbh-050, bcbh-051, bcbh-064, bcbh-075, bcbh-079, bcbh-092, bcbh-111, bcbh-123, bcbh-139

## Paired detail: ifbench

### q6k vs base — ifbench
- drops (base-correct -> cand-wrong), n=20: ifbench-017, ifbench-020, ifbench-039, ifbench-047, ifbench-056, ifbench-063, ifbench-090, ifbench-122, ifbench-158, ifbench-170, ifbench-180, ifbench-185, ifbench-216, ifbench-221, ifbench-246, ifbench-249, ifbench-253, ifbench-262, ifbench-266, ifbench-268
- leapfrogs (base-wrong -> cand-correct), n=9: ifbench-004, ifbench-040, ifbench-049, ifbench-088, ifbench-094, ifbench-204, ifbench-242, ifbench-267, ifbench-284

### udq2 vs base — ifbench
- drops (base-correct -> cand-wrong), n=24: ifbench-014, ifbench-036, ifbench-038, ifbench-047, ifbench-063, ifbench-066, ifbench-081, ifbench-090, ifbench-122, ifbench-123, ifbench-144, ifbench-158, ifbench-170, ifbench-179, ifbench-180, ifbench-184, ifbench-185, ifbench-188, ifbench-216, ifbench-236, ifbench-246, ifbench-249, ifbench-262, ifbench-266
- leapfrogs (base-wrong -> cand-correct), n=20: ifbench-004, ifbench-012, ifbench-040, ifbench-041, ifbench-061, ifbench-065, ifbench-094, ifbench-121, ifbench-128, ifbench-154, ifbench-162, ifbench-168, ifbench-228, ifbench-242, ifbench-251, ifbench-256, ifbench-258, ifbench-275, ifbench-284, ifbench-293

### fusion vs base — ifbench
- drops (base-correct -> cand-wrong), n=41: ifbench-005, ifbench-011, ifbench-014, ifbench-037, ifbench-038, ifbench-057, ifbench-058, ifbench-060, ifbench-063, ifbench-081, ifbench-089, ifbench-090, ifbench-107, ifbench-109, ifbench-112, ifbench-120, ifbench-126, ifbench-144, ifbench-166, ifbench-170, ifbench-174, ifbench-179, ifbench-180, ifbench-184, ifbench-185, ifbench-186, ifbench-187, ifbench-188, ifbench-199, ifbench-216, ifbench-221, ifbench-223, ifbench-225, ifbench-238, ifbench-246, ifbench-249, ifbench-253, ifbench-262, ifbench-266, ifbench-274, ifbench-294
- leapfrogs (base-wrong -> cand-correct), n=12: ifbench-012, ifbench-040, ifbench-041, ifbench-094, ifbench-146, ifbench-154, ifbench-167, ifbench-205, ifbench-240, ifbench-256, ifbench-275, ifbench-286

## Paired detail: olymmath_hard

### q6k vs base — olymmath_hard
- drops (base-correct -> cand-wrong), n=11: olymmath-hard-013, olymmath-hard-026, olymmath-hard-036, olymmath-hard-049, olymmath-hard-056, olymmath-hard-058, olymmath-hard-075, olymmath-hard-077, olymmath-hard-078, olymmath-hard-090, olymmath-hard-092
- leapfrogs (base-wrong -> cand-correct), n=10: olymmath-hard-020, olymmath-hard-021, olymmath-hard-028, olymmath-hard-030, olymmath-hard-054, olymmath-hard-062, olymmath-hard-069, olymmath-hard-076, olymmath-hard-083, olymmath-hard-091

### udq2 vs base — olymmath_hard
- drops (base-correct -> cand-wrong), n=17: olymmath-hard-013, olymmath-hard-017, olymmath-hard-019, olymmath-hard-036, olymmath-hard-045, olymmath-hard-049, olymmath-hard-056, olymmath-hard-058, olymmath-hard-059, olymmath-hard-061, olymmath-hard-064, olymmath-hard-072, olymmath-hard-077, olymmath-hard-078, olymmath-hard-090, olymmath-hard-092, olymmath-hard-093
- leapfrogs (base-wrong -> cand-correct), n=5: olymmath-hard-020, olymmath-hard-048, olymmath-hard-071, olymmath-hard-076, olymmath-hard-085

### fusion vs base — olymmath_hard
- drops (base-correct -> cand-wrong), n=13: olymmath-hard-013, olymmath-hard-017, olymmath-hard-018, olymmath-hard-022, olymmath-hard-049, olymmath-hard-056, olymmath-hard-058, olymmath-hard-059, olymmath-hard-072, olymmath-hard-075, olymmath-hard-078, olymmath-hard-090, olymmath-hard-092
- leapfrogs (base-wrong -> cand-correct), n=16: olymmath-hard-006, olymmath-hard-008, olymmath-hard-009, olymmath-hard-025, olymmath-hard-030, olymmath-hard-040, olymmath-hard-041, olymmath-hard-044, olymmath-hard-048, olymmath-hard-054, olymmath-hard-057, olymmath-hard-074, olymmath-hard-087, olymmath-hard-089, olymmath-hard-091, olymmath-hard-096

## Paired detail: amo

### q6k vs base — amo
- drops (base-correct -> cand-wrong), n=2: amo-022, amo-029
- leapfrogs (base-wrong -> cand-correct), n=3: amo-016, amo-017, amo-020

### udq2 vs base — amo
- drops (base-correct -> cand-wrong), n=2: amo-022, amo-029
- leapfrogs (base-wrong -> cand-correct), n=3: amo-009, amo-020, amo-026

### fusion vs base — amo
- drops (base-correct -> cand-wrong), n=2: amo-022, amo-029
- leapfrogs (base-wrong -> cand-correct), n=5: amo-009, amo-017, amo-018, amo-020, amo-027

## Paired detail: tc_json_v1

### q6k vs base — tc_json_v1
- drops (base-correct -> cand-wrong), n=2: tc-json-bfcl-053, tc-json-bfcl-191
- leapfrogs (base-wrong -> cand-correct), n=3: tc-json-bfcl-037, tc-json-bfcl-144, tc-json-bfcl-246

### udq2 vs base — tc_json_v1
- drops (base-correct -> cand-wrong), n=6: tc-json-bfcl-034, tc-json-bfcl-053, tc-json-bfcl-057, tc-json-bfcl-127, tc-json-bfcl-176, tc-json-bfcl-220
- leapfrogs (base-wrong -> cand-correct), n=7: tc-json-bfcl-037, tc-json-bfcl-051, tc-json-bfcl-075, tc-json-bfcl-125, tc-json-bfcl-154, tc-json-bfcl-231, tc-json-bfcl-287

### fusion vs base — tc_json_v1
- drops (base-correct -> cand-wrong), n=4: tc-json-bfcl-025, tc-json-bfcl-034, tc-json-bfcl-215, tc-json-bfcl-251
- leapfrogs (base-wrong -> cand-correct), n=8: tc-json-bfcl-037, tc-json-bfcl-039, tc-json-bfcl-137, tc-json-bfcl-147, tc-json-bfcl-154, tc-json-bfcl-184, tc-json-bfcl-231, tc-json-bfcl-246

## Degenerate item ids (across base_q5km, q6k, udq2, fusion-0413; BCB excludes the 7 sandbox-unscoreable)

### bigcodebench_hard
- FLOOR (0/4 correct), n=83: bcbh-001, bcbh-009, bcbh-010, bcbh-012, bcbh-013, bcbh-015, bcbh-017, bcbh-018, bcbh-022, bcbh-023, bcbh-024, bcbh-026, bcbh-028, bcbh-031, bcbh-034, bcbh-037, bcbh-040, bcbh-041, bcbh-042, bcbh-043, bcbh-044, bcbh-045, bcbh-046, bcbh-047, bcbh-048, bcbh-049, bcbh-053, bcbh-054, bcbh-055, bcbh-057, bcbh-058, bcbh-059, bcbh-061, bcbh-063, bcbh-066, bcbh-069, bcbh-070, bcbh-072, bcbh-073, bcbh-076, bcbh-077, bcbh-078, bcbh-080, bcbh-081, bcbh-082, bcbh-083, bcbh-085, bcbh-086, bcbh-088, bcbh-089, bcbh-090, bcbh-091, bcbh-093, bcbh-094, bcbh-098, bcbh-099, bcbh-100, bcbh-101, bcbh-103, bcbh-105, bcbh-107, bcbh-108, bcbh-112, bcbh-113, bcbh-115, bcbh-116, bcbh-117, bcbh-121, bcbh-125, bcbh-126, bcbh-128, bcbh-129, bcbh-130, bcbh-131, bcbh-134, bcbh-135, bcbh-136, bcbh-137, bcbh-138, bcbh-140, bcbh-143, bcbh-144, bcbh-147
- CEILING (4/4 correct), n=20: bcbh-008, bcbh-011, bcbh-019, bcbh-033, bcbh-036, bcbh-038, bcbh-056, bcbh-060, bcbh-062, bcbh-065, bcbh-106, bcbh-120, bcbh-124, bcbh-127, bcbh-133, bcbh-141, bcbh-142, bcbh-145, bcbh-146, bcbh-148

### ifbench
- FLOOR (0/4 correct), n=68: ifbench-050, ifbench-051, ifbench-062, ifbench-068, ifbench-070, ifbench-082, ifbench-106, ifbench-145, ifbench-147, ifbench-148, ifbench-149, ifbench-150, ifbench-151, ifbench-152, ifbench-153, ifbench-159, ifbench-160, ifbench-169, ifbench-171, ifbench-181, ifbench-182, ifbench-183, ifbench-189, ifbench-190, ifbench-191, ifbench-192, ifbench-197, ifbench-201, ifbench-202, ifbench-203, ifbench-206, ifbench-207, ifbench-208, ifbench-209, ifbench-210, ifbench-211, ifbench-212, ifbench-213, ifbench-214, ifbench-215, ifbench-217, ifbench-218, ifbench-219, ifbench-224, ifbench-227, ifbench-229, ifbench-230, ifbench-231, ifbench-232, ifbench-233, ifbench-234, ifbench-248, ifbench-250, ifbench-252, ifbench-254, ifbench-259, ifbench-260, ifbench-261, ifbench-263, ifbench-264, ifbench-265, ifbench-273, ifbench-279, ifbench-280, ifbench-281, ifbench-282, ifbench-283, ifbench-285
- CEILING (4/4 correct), n=144: ifbench-001, ifbench-002, ifbench-003, ifbench-006, ifbench-007, ifbench-008, ifbench-009, ifbench-010, ifbench-013, ifbench-015, ifbench-016, ifbench-018, ifbench-019, ifbench-021, ifbench-022, ifbench-023, ifbench-024, ifbench-025, ifbench-026, ifbench-027, ifbench-028, ifbench-029, ifbench-030, ifbench-031, ifbench-032, ifbench-033, ifbench-034, ifbench-035, ifbench-042, ifbench-043, ifbench-044, ifbench-045, ifbench-046, ifbench-048, ifbench-052, ifbench-053, ifbench-054, ifbench-055, ifbench-059, ifbench-064, ifbench-067, ifbench-069, ifbench-071, ifbench-072, ifbench-073, ifbench-074, ifbench-075, ifbench-076, ifbench-077, ifbench-078, ifbench-079, ifbench-080, ifbench-083, ifbench-084, ifbench-085, ifbench-086, ifbench-087, ifbench-091, ifbench-092, ifbench-093, ifbench-095, ifbench-096, ifbench-097, ifbench-098, ifbench-099, ifbench-100, ifbench-101, ifbench-102, ifbench-103, ifbench-104, ifbench-105, ifbench-108, ifbench-110, ifbench-111, ifbench-113, ifbench-114, ifbench-115, ifbench-116, ifbench-117, ifbench-118, ifbench-119, ifbench-124, ifbench-125, ifbench-127, ifbench-129, ifbench-130, ifbench-131, ifbench-132, ifbench-133, ifbench-134, ifbench-135, ifbench-136, ifbench-137, ifbench-138, ifbench-139, ifbench-140, ifbench-141, ifbench-142, ifbench-143, ifbench-155, ifbench-156, ifbench-157, ifbench-161, ifbench-163, ifbench-164, ifbench-165, ifbench-172, ifbench-173, ifbench-175, ifbench-176, ifbench-177, ifbench-178, ifbench-193, ifbench-194, ifbench-195, ifbench-196, ifbench-198, ifbench-200, ifbench-220, ifbench-222, ifbench-226, ifbench-235, ifbench-237, ifbench-239, ifbench-241, ifbench-243, ifbench-244, ifbench-245, ifbench-247, ifbench-255, ifbench-257, ifbench-269, ifbench-270, ifbench-271, ifbench-272, ifbench-276, ifbench-277, ifbench-278, ifbench-287, ifbench-288, ifbench-289, ifbench-290, ifbench-291, ifbench-292

### olymmath_hard
- FLOOR (0/4 correct), n=45: olymmath-hard-001, olymmath-hard-002, olymmath-hard-004, olymmath-hard-007, olymmath-hard-010, olymmath-hard-014, olymmath-hard-015, olymmath-hard-016, olymmath-hard-024, olymmath-hard-027, olymmath-hard-029, olymmath-hard-031, olymmath-hard-033, olymmath-hard-034, olymmath-hard-035, olymmath-hard-037, olymmath-hard-038, olymmath-hard-039, olymmath-hard-042, olymmath-hard-043, olymmath-hard-046, olymmath-hard-047, olymmath-hard-050, olymmath-hard-051, olymmath-hard-053, olymmath-hard-055, olymmath-hard-060, olymmath-hard-063, olymmath-hard-065, olymmath-hard-066, olymmath-hard-067, olymmath-hard-068, olymmath-hard-073, olymmath-hard-079, olymmath-hard-080, olymmath-hard-081, olymmath-hard-082, olymmath-hard-084, olymmath-hard-088, olymmath-hard-094, olymmath-hard-095, olymmath-hard-097, olymmath-hard-098, olymmath-hard-099, olymmath-hard-100
- CEILING (4/4 correct), n=9: olymmath-hard-003, olymmath-hard-005, olymmath-hard-011, olymmath-hard-012, olymmath-hard-023, olymmath-hard-032, olymmath-hard-052, olymmath-hard-070, olymmath-hard-086

### amo
- FLOOR (0/4 correct), n=26: amo-001, amo-003, amo-004, amo-005, amo-006, amo-007, amo-008, amo-010, amo-011, amo-013, amo-014, amo-015, amo-021, amo-023, amo-024, amo-025, amo-028, amo-030, amo-031, amo-032, amo-033, amo-034, amo-036, amo-037, amo-038, amo-039
- CEILING (4/4 correct), n=4: amo-002, amo-012, amo-019, amo-035

### tc_json_v1
- FLOOR (0/4 correct), n=76: tc-json-bfcl-004, tc-json-bfcl-018, tc-json-bfcl-020, tc-json-bfcl-026, tc-json-bfcl-028, tc-json-bfcl-030, tc-json-bfcl-036, tc-json-bfcl-044, tc-json-bfcl-046, tc-json-bfcl-054, tc-json-bfcl-061, tc-json-bfcl-063, tc-json-bfcl-065, tc-json-bfcl-067, tc-json-bfcl-069, tc-json-bfcl-072, tc-json-bfcl-079, tc-json-bfcl-094, tc-json-bfcl-098, tc-json-bfcl-099, tc-json-bfcl-104, tc-json-bfcl-106, tc-json-bfcl-110, tc-json-bfcl-126, tc-json-bfcl-133, tc-json-bfcl-136, tc-json-bfcl-139, tc-json-bfcl-140, tc-json-bfcl-141, tc-json-bfcl-145, tc-json-bfcl-158, tc-json-bfcl-159, tc-json-bfcl-161, tc-json-bfcl-162, tc-json-bfcl-166, tc-json-bfcl-170, tc-json-bfcl-178, tc-json-bfcl-188, tc-json-bfcl-189, tc-json-bfcl-195, tc-json-bfcl-198, tc-json-bfcl-203, tc-json-bfcl-206, tc-json-bfcl-207, tc-json-bfcl-210, tc-json-bfcl-218, tc-json-bfcl-219, tc-json-bfcl-221, tc-json-bfcl-222, tc-json-bfcl-233, tc-json-bfcl-242, tc-json-bfcl-245, tc-json-bfcl-250, tc-json-bfcl-252, tc-json-bfcl-253, tc-json-bfcl-254, tc-json-bfcl-258, tc-json-bfcl-262, tc-json-bfcl-274, tc-json-bfcl-279, tc-json-bfcl-282, tc-json-bfcl-286, tc-json-bfcl-288, tc-json-bfcl-290, tc-json-bfcl-291, tc-json-fresh-001, tc-json-fresh-004, tc-json-fresh-005, tc-json-fresh-010, tc-json-fresh-011, tc-json-fresh-019, tc-json-fresh-020, tc-json-fresh-024, tc-json-fresh-028, tc-json-fresh-029, tc-json-fresh-030
- CEILING (4/4 correct), n=231: tc-json-bfcl-001, tc-json-bfcl-002, tc-json-bfcl-003, tc-json-bfcl-005, tc-json-bfcl-006, tc-json-bfcl-007, tc-json-bfcl-008, tc-json-bfcl-009, tc-json-bfcl-010, tc-json-bfcl-011, tc-json-bfcl-012, tc-json-bfcl-013, tc-json-bfcl-014, tc-json-bfcl-015, tc-json-bfcl-016, tc-json-bfcl-017, tc-json-bfcl-019, tc-json-bfcl-021, tc-json-bfcl-022, tc-json-bfcl-023, tc-json-bfcl-024, tc-json-bfcl-027, tc-json-bfcl-029, tc-json-bfcl-031, tc-json-bfcl-032, tc-json-bfcl-033, tc-json-bfcl-035, tc-json-bfcl-038, tc-json-bfcl-040, tc-json-bfcl-041, tc-json-bfcl-042, tc-json-bfcl-043, tc-json-bfcl-045, tc-json-bfcl-047, tc-json-bfcl-048, tc-json-bfcl-049, tc-json-bfcl-050, tc-json-bfcl-052, tc-json-bfcl-055, tc-json-bfcl-056, tc-json-bfcl-058, tc-json-bfcl-059, tc-json-bfcl-060, tc-json-bfcl-062, tc-json-bfcl-064, tc-json-bfcl-066, tc-json-bfcl-068, tc-json-bfcl-070, tc-json-bfcl-071, tc-json-bfcl-073, tc-json-bfcl-074, tc-json-bfcl-076, tc-json-bfcl-077, tc-json-bfcl-078, tc-json-bfcl-080, tc-json-bfcl-081, tc-json-bfcl-082, tc-json-bfcl-083, tc-json-bfcl-084, tc-json-bfcl-085, tc-json-bfcl-086, tc-json-bfcl-087, tc-json-bfcl-088, tc-json-bfcl-089, tc-json-bfcl-090, tc-json-bfcl-091, tc-json-bfcl-092, tc-json-bfcl-093, tc-json-bfcl-095, tc-json-bfcl-096, tc-json-bfcl-097, tc-json-bfcl-100, tc-json-bfcl-101, tc-json-bfcl-102, tc-json-bfcl-103, tc-json-bfcl-105, tc-json-bfcl-107, tc-json-bfcl-108, tc-json-bfcl-109, tc-json-bfcl-111, tc-json-bfcl-112, tc-json-bfcl-113, tc-json-bfcl-114, tc-json-bfcl-115, tc-json-bfcl-116, tc-json-bfcl-117, tc-json-bfcl-118, tc-json-bfcl-119, tc-json-bfcl-120, tc-json-bfcl-121, tc-json-bfcl-122, tc-json-bfcl-123, tc-json-bfcl-124, tc-json-bfcl-128, tc-json-bfcl-129, tc-json-bfcl-130, tc-json-bfcl-131, tc-json-bfcl-132, tc-json-bfcl-134, tc-json-bfcl-135, tc-json-bfcl-138, tc-json-bfcl-142, tc-json-bfcl-143, tc-json-bfcl-146, tc-json-bfcl-148, tc-json-bfcl-149, tc-json-bfcl-150, tc-json-bfcl-151, tc-json-bfcl-152, tc-json-bfcl-153, tc-json-bfcl-155, tc-json-bfcl-156, tc-json-bfcl-157, tc-json-bfcl-160, tc-json-bfcl-163, tc-json-bfcl-164, tc-json-bfcl-165, tc-json-bfcl-167, tc-json-bfcl-168, tc-json-bfcl-169, tc-json-bfcl-171, tc-json-bfcl-172, tc-json-bfcl-173, tc-json-bfcl-174, tc-json-bfcl-175, tc-json-bfcl-177, tc-json-bfcl-179, tc-json-bfcl-180, tc-json-bfcl-181, tc-json-bfcl-182, tc-json-bfcl-183, tc-json-bfcl-185, tc-json-bfcl-186, tc-json-bfcl-187, tc-json-bfcl-190, tc-json-bfcl-192, tc-json-bfcl-193, tc-json-bfcl-194, tc-json-bfcl-196, tc-json-bfcl-197, tc-json-bfcl-199, tc-json-bfcl-200, tc-json-bfcl-201, tc-json-bfcl-202, tc-json-bfcl-204, tc-json-bfcl-205, tc-json-bfcl-208, tc-json-bfcl-209, tc-json-bfcl-211, tc-json-bfcl-212, tc-json-bfcl-213, tc-json-bfcl-214, tc-json-bfcl-216, tc-json-bfcl-217, tc-json-bfcl-223, tc-json-bfcl-224, tc-json-bfcl-225, tc-json-bfcl-226, tc-json-bfcl-227, tc-json-bfcl-228, tc-json-bfcl-229, tc-json-bfcl-230, tc-json-bfcl-232, tc-json-bfcl-234, tc-json-bfcl-235, tc-json-bfcl-236, tc-json-bfcl-237, tc-json-bfcl-238, tc-json-bfcl-239, tc-json-bfcl-240, tc-json-bfcl-241, tc-json-bfcl-243, tc-json-bfcl-244, tc-json-bfcl-247, tc-json-bfcl-248, tc-json-bfcl-249, tc-json-bfcl-255, tc-json-bfcl-256, tc-json-bfcl-257, tc-json-bfcl-259, tc-json-bfcl-260, tc-json-bfcl-261, tc-json-bfcl-263, tc-json-bfcl-264, tc-json-bfcl-265, tc-json-bfcl-266, tc-json-bfcl-267, tc-json-bfcl-268, tc-json-bfcl-269, tc-json-bfcl-270, tc-json-bfcl-271, tc-json-bfcl-272, tc-json-bfcl-273, tc-json-bfcl-275, tc-json-bfcl-276, tc-json-bfcl-277, tc-json-bfcl-278, tc-json-bfcl-280, tc-json-bfcl-281, tc-json-bfcl-283, tc-json-bfcl-284, tc-json-bfcl-285, tc-json-bfcl-289, tc-json-bfcl-292, tc-json-bfcl-293, tc-json-bfcl-294, tc-json-bfcl-295, tc-json-bfcl-296, tc-json-bfcl-297, tc-json-bfcl-298, tc-json-bfcl-299, tc-json-bfcl-300, tc-json-fresh-002, tc-json-fresh-003, tc-json-fresh-006, tc-json-fresh-007, tc-json-fresh-008, tc-json-fresh-009, tc-json-fresh-012, tc-json-fresh-013, tc-json-fresh-014, tc-json-fresh-015, tc-json-fresh-016, tc-json-fresh-017, tc-json-fresh-018, tc-json-fresh-021, tc-json-fresh-022, tc-json-fresh-023, tc-json-fresh-025, tc-json-fresh-026, tc-json-fresh-027

## IFBench per-item constraint types
- ifbench-001: ['count:keywords_multiple']
- ifbench-002: ['count:keywords_multiple']
- ifbench-003: ['count:keywords_multiple']
- ifbench-004: ['count:keywords_multiple']
- ifbench-005: ['count:keywords_multiple']
- ifbench-006: ['count:conjunctions']
- ifbench-007: ['count:conjunctions']
- ifbench-008: ['count:conjunctions']
- ifbench-009: ['count:conjunctions']
- ifbench-010: ['count:conjunctions']
- ifbench-011: ['words:keywords_specific_position']
- ifbench-012: ['words:keywords_specific_position']
- ifbench-013: ['words:keywords_specific_position']
- ifbench-014: ['words:keywords_specific_position']
- ifbench-015: ['words:words_position']
- ifbench-016: ['words:words_position']
- ifbench-017: ['words:words_position']
- ifbench-018: ['count:numbers']
- ifbench-019: ['count:numbers']
- ifbench-020: ['count:numbers']
- ifbench-021: ['count:numbers']
- ifbench-022: ['count:numbers']
- ifbench-023: ['count:numbers', 'count:conjunctions']
- ifbench-024: ['count:numbers', 'count:conjunctions']
- ifbench-025: ['count:numbers', 'count:unique_word_count']
- ifbench-026: ['count:person_names']
- ifbench-027: ['count:person_names']
- ifbench-028: ['count:person_names']
- ifbench-029: ['count:person_names']
- ifbench-030: ['count:person_names']
- ifbench-031: ['count:pronouns']
- ifbench-032: ['count:pronouns']
- ifbench-033: ['count:pronouns']
- ifbench-034: ['count:pronouns']
- ifbench-035: ['count:pronouns']
- ifbench-036: ['count:punctuation']
- ifbench-037: ['count:punctuation']
- ifbench-038: ['count:punctuation']
- ifbench-039: ['count:punctuation']
- ifbench-040: ['count:punctuation']
- ifbench-041: ['count:punctuation']
- ifbench-042: ['count:word_count_range']
- ifbench-043: ['count:word_count_range']
- ifbench-044: ['count:word_count_range']
- ifbench-045: ['count:word_count_range']
- ifbench-046: ['count:word_count_range']
- ifbench-047: ['count:word_count_range', 'format:list']
- ifbench-048: ['count:words_japanese']
- ifbench-049: ['count:words_japanese']
- ifbench-050: ['count:words_japanese']
- ifbench-051: ['count:words_japanese']
- ifbench-052: ['count:words_japanese']
- ifbench-053: ['count:unique_word_count']
- ifbench-054: ['count:unique_word_count']
- ifbench-055: ['count:unique_word_count']
- ifbench-056: ['count:unique_word_count']
- ifbench-057: ['count:unique_word_count']
- ifbench-058: ['count:unique_word_count']
- ifbench-059: ['count:unique_word_count']
- ifbench-060: ['count:unique_word_count']
- ifbench-061: ['repeat:repeat_change']
- ifbench-062: ['repeat:repeat_change']
- ifbench-063: ['repeat:repeat_change']
- ifbench-064: ['repeat:repeat_simple']
- ifbench-065: ['repeat:repeat_simple']
- ifbench-066: ['format:emoji']
- ifbench-067: ['format:emoji']
- ifbench-068: ['format:emoji']
- ifbench-069: ['format:emoji']
- ifbench-070: ['format:emoji']
- ifbench-071: ['format:emoji']
- ifbench-072: ['format:emoji', 'sentence:keyword']
- ifbench-073: ['format:emoji', 'sentence:keyword']
- ifbench-074: ['format:line_indent']
- ifbench-075: ['format:line_indent']
- ifbench-076: ['format:line_indent']
- ifbench-077: ['format:line_indent']
- ifbench-078: ['format:line_indent']
- ifbench-079: ['format:line_indent']
- ifbench-080: ['format:line_indent']
- ifbench-081: ['format:line_indent', 'ratio:sentence_words']
- ifbench-082: ['format:line_indent', 'ratio:sentence_words']
- ifbench-083: ['format:list']
- ifbench-084: ['format:list']
- ifbench-085: ['format:list']
- ifbench-086: ['format:list']
- ifbench-087: ['format:list']
- ifbench-088: ['format:list', 'words:no_consecutive']
- ifbench-089: ['format:list', 'words:no_consecutive']
- ifbench-090: ['format:list', 'words:no_consecutive']
- ifbench-091: ['format:newline']
- ifbench-092: ['format:newline']
- ifbench-093: ['format:newline']
- ifbench-094: ['format:newline']
- ifbench-095: ['format:newline']
- ifbench-096: ['format:no_bullets_bullets']
- ifbench-097: ['format:no_bullets_bullets']
- ifbench-098: ['format:no_bullets_bullets']
- ifbench-099: ['format:no_bullets_bullets']
- ifbench-100: ['format:no_bullets_bullets']
- ifbench-101: ['format:options']
- ifbench-102: ['format:options']
- ifbench-103: ['format:options']
- ifbench-104: ['format:options']
- ifbench-105: ['format:options']
- ifbench-106: ['format:options', 'format:newline']
- ifbench-107: ['format:parentheses']
- ifbench-108: ['format:parentheses']
- ifbench-109: ['format:parentheses']
- ifbench-110: ['format:parentheses']
- ifbench-111: ['format:parentheses']
- ifbench-112: ['format:parentheses']
- ifbench-113: ['format:parentheses']
- ifbench-114: ['format:quote_unquote']
- ifbench-115: ['format:quote_unquote']
- ifbench-116: ['format:quote_unquote']
- ifbench-117: ['format:quote_unquote']
- ifbench-118: ['format:quote_unquote']
- ifbench-119: ['format:quotes']
- ifbench-120: ['format:quotes']
- ifbench-121: ['format:quotes']
- ifbench-122: ['format:quotes']
- ifbench-123: ['format:quotes']
- ifbench-124: ['format:quotes']
- ifbench-125: ['format:quotes']
- ifbench-126: ['format:quotes', 'format:emoji']
- ifbench-127: ['format:sub-bullets']
- ifbench-128: ['format:sub-bullets']
- ifbench-129: ['format:sub-bullets']
- ifbench-130: ['format:sub-bullets']
- ifbench-131: ['format:sub-bullets']
- ifbench-132: ['format:sub-bullets']
- ifbench-133: ['format:sub-bullets']
- ifbench-134: ['format:sub-bullets', 'ratio:stop_words']
- ifbench-135: ['format:sub-bullets', 'ratio:stop_words']
- ifbench-136: ['format:sub-bullets', 'ratio:stop_words']
- ifbench-137: ['format:sub-bullets', 'ratio:stop_words']
- ifbench-138: ['format:sub-bullets', 'ratio:stop_words']
- ifbench-139: ['format:thesis']
- ifbench-140: ['format:thesis']
- ifbench-141: ['format:thesis']
- ifbench-142: ['format:thesis']
- ifbench-143: ['format:thesis']
- ifbench-144: ['format:thesis', 'count:word_count_range']
- ifbench-145: ['ratio:overlap']
- ifbench-146: ['ratio:overlap']
- ifbench-147: ['ratio:overlap']
- ifbench-148: ['ratio:overlap']
- ifbench-149: ['ratio:overlap']
- ifbench-150: ['ratio:overlap', 'sentence:keyword']
- ifbench-151: ['ratio:overlap', 'sentence:keyword']
- ifbench-152: ['ratio:overlap', 'sentence:keyword']
- ifbench-153: ['ratio:overlap', 'sentence:keyword']
- ifbench-154: ['ratio:sentence_balance']
- ifbench-155: ['ratio:sentence_balance']
- ifbench-156: ['ratio:sentence_balance']
- ifbench-157: ['ratio:sentence_balance']
- ifbench-158: ['ratio:sentence_balance']
- ifbench-159: ['ratio:sentence_balance', 'words:consonants']
- ifbench-160: ['ratio:sentence_balance', 'words:consonants']
- ifbench-161: ['ratio:sentence_type']
- ifbench-162: ['ratio:sentence_type']
- ifbench-163: ['ratio:sentence_type']
- ifbench-164: ['ratio:sentence_type']
- ifbench-165: ['ratio:sentence_type']
- ifbench-166: ['ratio:sentence_type']
- ifbench-167: ['ratio:sentence_words']
- ifbench-168: ['ratio:sentence_words']
- ifbench-169: ['ratio:sentence_words']
- ifbench-170: ['ratio:sentence_words']
- ifbench-171: ['ratio:sentence_words']
- ifbench-172: ['ratio:stop_words']
- ifbench-173: ['ratio:stop_words']
- ifbench-174: ['ratio:stop_words']
- ifbench-175: ['ratio:stop_words']
- ifbench-176: ['ratio:stop_words']
- ifbench-177: ['ratio:stop_words']
- ifbench-178: ['ratio:stop_words']
- ifbench-179: ['sentence:alliteration_increment']
- ifbench-180: ['sentence:alliteration_increment']
- ifbench-181: ['sentence:alliteration_increment']
- ifbench-182: ['sentence:alliteration_increment']
- ifbench-183: ['sentence:alliteration_increment']
- ifbench-184: ['sentence:increment']
- ifbench-185: ['sentence:increment']
- ifbench-186: ['sentence:increment']
- ifbench-187: ['sentence:increment']
- ifbench-188: ['sentence:increment']
- ifbench-189: ['sentence:increment', 'format:thesis']
- ifbench-190: ['sentence:increment', 'format:thesis']
- ifbench-191: ['sentence:increment', 'format:thesis']
- ifbench-192: ['sentence:keyword']
- ifbench-193: ['sentence:keyword']
- ifbench-194: ['sentence:keyword']
- ifbench-195: ['sentence:keyword']
- ifbench-196: ['sentence:keyword']
- ifbench-197: ['sentence:keyword', 'count:word_count_range']
- ifbench-198: ['sentence:keyword', 'count:word_count_range']
- ifbench-199: ['sentence:keyword', 'count:word_count_range']
- ifbench-200: ['sentence:keyword', 'count:word_count_range']
- ifbench-201: ['words:alphabet']
- ifbench-202: ['words:alphabet']
- ifbench-203: ['words:alphabet']
- ifbench-204: ['words:alphabet']
- ifbench-205: ['words:alphabet']
- ifbench-206: ['words:alphabet', 'format:parentheses']
- ifbench-207: ['words:consonants']
- ifbench-208: ['words:consonants']
- ifbench-209: ['words:consonants']
- ifbench-210: ['words:consonants']
- ifbench-211: ['words:consonants']
- ifbench-212: ['words:consonants']
- ifbench-213: ['words:consonants', 'ratio:overlap']
- ifbench-214: ['words:consonants', 'ratio:overlap']
- ifbench-215: ['words:consonants', 'ratio:overlap']
- ifbench-216: ['words:consonants', 'words:odd_even_syllables']
- ifbench-217: ['words:consonants', 'words:odd_even_syllables']
- ifbench-218: ['words:consonants', 'words:odd_even_syllables']
- ifbench-219: ['words:consonants', 'words:odd_even_syllables']
- ifbench-220: ['words:last_first']
- ifbench-221: ['words:last_first']
- ifbench-222: ['words:last_first']
- ifbench-223: ['words:last_first']
- ifbench-224: ['words:last_first']
- ifbench-225: ['words:no_consecutive']
- ifbench-226: ['words:no_consecutive']
- ifbench-227: ['words:no_consecutive']
- ifbench-228: ['words:no_consecutive']
- ifbench-229: ['words:no_consecutive']
- ifbench-230: ['words:odd_even_syllables']
- ifbench-231: ['words:odd_even_syllables']
- ifbench-232: ['words:odd_even_syllables']
- ifbench-233: ['words:odd_even_syllables']
- ifbench-234: ['words:odd_even_syllables']
- ifbench-235: ['words:palindrome']
- ifbench-236: ['words:palindrome']
- ifbench-237: ['words:palindrome']
- ifbench-238: ['words:palindrome']
- ifbench-239: ['words:palindrome']
- ifbench-240: ['words:palindrome']
- ifbench-241: ['words:palindrome']
- ifbench-242: ['words:paragraph_last_first']
- ifbench-243: ['words:paragraph_last_first']
- ifbench-244: ['words:paragraph_last_first']
- ifbench-245: ['words:paragraph_last_first']
- ifbench-246: ['words:paragraph_last_first']
- ifbench-247: ['words:paragraph_last_first']
- ifbench-248: ['words:prime_lengths']
- ifbench-249: ['words:prime_lengths']
- ifbench-250: ['words:prime_lengths']
- ifbench-251: ['words:prime_lengths']
- ifbench-252: ['words:prime_lengths']
- ifbench-253: ['words:repeats']
- ifbench-254: ['words:repeats']
- ifbench-255: ['words:repeats']
- ifbench-256: ['words:repeats']
- ifbench-257: ['words:repeats']
- ifbench-258: ['words:vowel']
- ifbench-259: ['words:vowel']
- ifbench-260: ['words:vowel']
- ifbench-261: ['words:vowel']
- ifbench-262: ['words:vowel']
- ifbench-263: ['words:vowel']
- ifbench-264: ['words:vowel']
- ifbench-265: ['words:vowel', 'count:pronouns']
- ifbench-266: ['words:vowel', 'count:pronouns']
- ifbench-267: ['words:vowel', 'count:pronouns']
- ifbench-268: ['custom:character_reverse']
- ifbench-269: ['custom:csv_city']
- ifbench-270: ['custom:csv_quotes']
- ifbench-271: ['custom:csv_special_character']
- ifbench-272: ['custom:date_format_list']
- ifbench-273: ['custom:european_capitals_sort']
- ifbench-274: ['custom:mcq_count_length']
- ifbench-275: ['custom:multiples']
- ifbench-276: ['custom:reverse_newline']
- ifbench-277: ['custom:sentence_alphabet']
- ifbench-278: ['custom:word_reverse']
- ifbench-279: ['repeat:repeat_span']
- ifbench-280: ['repeat:repeat_span']
- ifbench-281: ['repeat:repeat_span']
- ifbench-282: ['repeat:repeat_span']
- ifbench-283: ['format:title_case']
- ifbench-284: ['format:title_case']
- ifbench-285: ['format:title_case']
- ifbench-286: ['format:title_case']
- ifbench-287: ['format:output_template']
- ifbench-288: ['format:output_template']
- ifbench-289: ['format:output_template']
- ifbench-290: ['format:output_template']
- ifbench-291: ['format:no_whitespace']
- ifbench-292: ['format:no_whitespace']
- ifbench-293: ['format:no_whitespace']
- ifbench-294: ['format:no_whitespace']

## Base-run per-item cost (bench, id, total_tokens, latency_s) — for cost-aware selection

### bigcodebench_hard
- bcbh-001: tok_total=1600, tok_final=165, latency_s=22.1
- bcbh-002: tok_total=1052, tok_final=166, latency_s=14.6
- bcbh-003: tok_total=1036, tok_final=130, latency_s=14.4
- bcbh-004: tok_total=4898, tok_final=234, latency_s=67.7
- bcbh-005: tok_total=2617, tok_final=128, latency_s=36.2
- bcbh-006: tok_total=8162, tok_final=179, latency_s=113.4
- bcbh-007: tok_total=1799, tok_final=222, latency_s=24.8
- bcbh-008: tok_total=1213, tok_final=182, latency_s=16.8
- bcbh-009: tok_total=6616, tok_final=294, latency_s=91.7
- bcbh-010: tok_total=8427, tok_final=235, latency_s=114.9
- bcbh-011: tok_total=3825, tok_final=160, latency_s=52.8
- bcbh-012: tok_total=4206, tok_final=177, latency_s=58.4
- bcbh-013: tok_total=5091, tok_final=200, latency_s=70.5
- bcbh-014: tok_total=2457, tok_final=650, latency_s=33.7
- bcbh-015: tok_total=3219, tok_final=200, latency_s=44.3
- bcbh-016: tok_total=7816, tok_final=370, latency_s=108.7
- bcbh-017: tok_total=7502, tok_final=171, latency_s=104.6
- bcbh-018: tok_total=4350, tok_final=173, latency_s=60.2
- bcbh-019: tok_total=6781, tok_final=271, latency_s=94.2
- bcbh-020: tok_total=5299, tok_final=110, latency_s=73.4
- bcbh-021: tok_total=4601, tok_final=213, latency_s=63.7
- bcbh-022: tok_total=2502, tok_final=151, latency_s=34.6
- bcbh-023: tok_total=5239, tok_final=218, latency_s=72.6
- bcbh-024: tok_total=4896, tok_final=185, latency_s=67.8
- bcbh-025: tok_total=5296, tok_final=184, latency_s=73.3
- bcbh-026: tok_total=5371, tok_final=230, latency_s=74.4
- bcbh-027: tok_total=4854, tok_final=336, latency_s=67.2
- bcbh-028: tok_total=4934, tok_final=277, latency_s=68.4
- bcbh-029: tok_total=2211, tok_final=151, latency_s=30.6
- bcbh-030: tok_total=3864, tok_final=181, latency_s=53.4
- bcbh-031: tok_total=4152, tok_final=246, latency_s=57.4
- bcbh-032: tok_total=6075, tok_final=271, latency_s=84.2
- bcbh-033: tok_total=1402, tok_final=108, latency_s=19.4
- bcbh-034: tok_total=2573, tok_final=114, latency_s=35.5
- bcbh-035: tok_total=6357, tok_final=159, latency_s=88.2
- bcbh-036: tok_total=5802, tok_final=476, latency_s=80.5
- bcbh-037: tok_total=962, tok_final=247, latency_s=13.3
- bcbh-038: tok_total=3540, tok_final=141, latency_s=48.9
- bcbh-039: tok_total=4604, tok_final=451, latency_s=63.8
- bcbh-040: tok_total=7115, tok_final=266, latency_s=98.8
- bcbh-041: tok_total=724, tok_final=94, latency_s=10.1
- bcbh-042: tok_total=3723, tok_final=129, latency_s=51.4
- bcbh-043: tok_total=3594, tok_final=235, latency_s=49.7
- bcbh-044: tok_total=1453, tok_final=255, latency_s=20.1
- bcbh-045: tok_total=3134, tok_final=101, latency_s=43.3
- bcbh-046: tok_total=2607, tok_final=102, latency_s=36.0
- bcbh-047: tok_total=6247, tok_final=364, latency_s=86.7
- bcbh-048: tok_total=5838, tok_final=408, latency_s=80.9
- bcbh-049: tok_total=1761, tok_final=143, latency_s=24.4
- bcbh-050: tok_total=3392, tok_final=161, latency_s=46.9
- bcbh-051: tok_total=3723, tok_final=170, latency_s=51.5
- bcbh-052: tok_total=1637, tok_final=240, latency_s=22.6
- bcbh-053: tok_total=5749, tok_final=185, latency_s=79.6
- bcbh-054: tok_total=944, tok_final=44, latency_s=13.1
- bcbh-055: tok_total=2662, tok_final=113, latency_s=36.7
- bcbh-056: tok_total=2525, tok_final=118, latency_s=34.8
- bcbh-057: tok_total=2276, tok_final=141, latency_s=31.5
- bcbh-058: tok_total=3361, tok_final=99, latency_s=46.5
- bcbh-059: tok_total=1791, tok_final=294, latency_s=24.7
- bcbh-060: tok_total=1100, tok_final=180, latency_s=15.2
- bcbh-061: tok_total=662, tok_final=108, latency_s=9.3
- bcbh-062: tok_total=2960, tok_final=186, latency_s=40.9
- bcbh-063: tok_total=1946, tok_final=143, latency_s=26.9
- bcbh-064: tok_total=8478, tok_final=286, latency_s=115.8
- bcbh-065: tok_total=2266, tok_final=228, latency_s=31.3
- bcbh-066: tok_total=1600, tok_final=157, latency_s=22.1
- bcbh-067: tok_total=5402, tok_final=227, latency_s=74.9
- bcbh-068: tok_total=4539, tok_final=293, latency_s=62.7
- bcbh-069: tok_total=6200, tok_final=222, latency_s=86.1
- bcbh-070: tok_total=5727, tok_final=209, latency_s=79.4
- bcbh-071: tok_total=1010, tok_final=166, latency_s=14.0
- bcbh-072: tok_total=3348, tok_final=170, latency_s=46.2
- bcbh-073: tok_total=5172, tok_final=254, latency_s=71.6
- bcbh-074: tok_total=6310, tok_final=359, latency_s=87.6
- bcbh-075: tok_total=4781, tok_final=224, latency_s=66.2
- bcbh-076: tok_total=1083, tok_final=128, latency_s=15.1
- bcbh-077: tok_total=1918, tok_final=241, latency_s=26.5
- bcbh-078: tok_total=5930, tok_final=167, latency_s=82.2
- bcbh-079: tok_total=4629, tok_final=212, latency_s=64.0
- bcbh-080: tok_total=4428, tok_final=124, latency_s=61.2
- bcbh-081: tok_total=8180, tok_final=312, latency_s=113.9
- bcbh-082: tok_total=2456, tok_final=176, latency_s=33.9
- bcbh-083: tok_total=4130, tok_final=224, latency_s=57.1
- bcbh-084: tok_total=2760, tok_final=133, latency_s=38.2
- bcbh-085: tok_total=2070, tok_final=209, latency_s=28.6
- bcbh-086: tok_total=5237, tok_final=265, latency_s=72.5
- bcbh-087: tok_total=3974, tok_final=206, latency_s=55.0
- bcbh-088: tok_total=2227, tok_final=90, latency_s=30.8
- bcbh-089: tok_total=7676, tok_final=99, latency_s=106.7
- bcbh-090: tok_total=2657, tok_final=118, latency_s=36.7
- bcbh-091: tok_total=3074, tok_final=194, latency_s=42.4
- bcbh-092: tok_total=5675, tok_final=237, latency_s=78.7
- bcbh-093: tok_total=981, tok_final=150, latency_s=13.6
- bcbh-094: tok_total=4472, tok_final=194, latency_s=61.9
- bcbh-095: tok_total=4709, tok_final=318, latency_s=65.2
- bcbh-096: tok_total=6351, tok_final=207, latency_s=88.1
- bcbh-097: tok_total=1192, tok_final=228, latency_s=16.5
- bcbh-098: tok_total=1739, tok_final=319, latency_s=24.0
- bcbh-099: tok_total=2243, tok_final=256, latency_s=30.9
- bcbh-100: tok_total=1556, tok_final=185, latency_s=21.5
- bcbh-101: tok_total=2291, tok_final=114, latency_s=31.6
- bcbh-102: tok_total=2655, tok_final=173, latency_s=36.6
- bcbh-103: tok_total=1183, tok_final=173, latency_s=16.4
- bcbh-104: tok_total=6519, tok_final=247, latency_s=90.6
- bcbh-105: tok_total=4971, tok_final=166, latency_s=68.8
- bcbh-106: tok_total=2427, tok_final=170, latency_s=33.5
- bcbh-107: tok_total=2783, tok_final=199, latency_s=38.4
- bcbh-108: tok_total=3385, tok_final=197, latency_s=46.7
- bcbh-109: tok_total=6740, tok_final=280, latency_s=93.6
- bcbh-110: tok_total=8539, tok_final=347, latency_s=117.0
- bcbh-111: tok_total=1004, tok_final=250, latency_s=13.9
- bcbh-112: tok_total=3773, tok_final=127, latency_s=52.1
- bcbh-113: tok_total=3569, tok_final=139, latency_s=49.3
- bcbh-114: tok_total=4437, tok_final=137, latency_s=61.4
- bcbh-115: tok_total=858, tok_final=124, latency_s=11.9
- bcbh-116: tok_total=4005, tok_final=117, latency_s=55.4
- bcbh-117: tok_total=4686, tok_final=476, latency_s=64.8
- bcbh-118: tok_total=3887, tok_final=146, latency_s=53.7
- bcbh-119: tok_total=7231, tok_final=325, latency_s=100.5
- bcbh-120: tok_total=4591, tok_final=145, latency_s=63.6
- bcbh-121: tok_total=4650, tok_final=200, latency_s=64.3
- bcbh-122: tok_total=1745, tok_final=116, latency_s=24.1
- bcbh-123: tok_total=8389, tok_final=197, latency_s=114.6
- bcbh-124: tok_total=6206, tok_final=210, latency_s=86.1
- bcbh-125: tok_total=4963, tok_final=283, latency_s=68.8
- bcbh-126: tok_total=2668, tok_final=170, latency_s=36.8
- bcbh-127: tok_total=4631, tok_final=153, latency_s=64.0
- bcbh-128: tok_total=2803, tok_final=257, latency_s=38.8
- bcbh-129: tok_total=3224, tok_final=132, latency_s=44.6
- bcbh-130: tok_total=2341, tok_final=114, latency_s=32.3
- bcbh-131: tok_total=3943, tok_final=173, latency_s=54.5
- bcbh-132: tok_total=3834, tok_final=222, latency_s=53.0
- bcbh-133: tok_total=3921, tok_final=137, latency_s=54.2
- bcbh-134: tok_total=5972, tok_final=181, latency_s=82.8
- bcbh-135: tok_total=2808, tok_final=233, latency_s=38.8
- bcbh-136: tok_total=1408, tok_final=236, latency_s=19.5
- bcbh-137: tok_total=4080, tok_final=197, latency_s=56.4
- bcbh-138: tok_total=6776, tok_final=154, latency_s=94.1
- bcbh-139: tok_total=4697, tok_final=201, latency_s=65.0
- bcbh-140: tok_total=7114, tok_final=349, latency_s=98.9
- bcbh-141: tok_total=4706, tok_final=153, latency_s=65.2
- bcbh-142: tok_total=3738, tok_final=152, latency_s=51.7
- bcbh-143: tok_total=7214, tok_final=500, latency_s=100.2
- bcbh-144: tok_total=3112, tok_final=168, latency_s=43.0
- bcbh-145: tok_total=2307, tok_final=127, latency_s=31.9
- bcbh-146: tok_total=5673, tok_final=197, latency_s=78.7
- bcbh-147: tok_total=1212, tok_final=234, latency_s=16.8
- bcbh-148: tok_total=3034, tok_final=155, latency_s=41.9

### ifbench
- ifbench-001: tok_total=4087, tok_final=518, latency_s=56.2
- ifbench-002: tok_total=4611, tok_final=276, latency_s=63.4
- ifbench-003: tok_total=5954, tok_final=549, latency_s=82.1
- ifbench-004: tok_total=7219, tok_final=737, latency_s=99.8
- ifbench-005: tok_total=6608, tok_final=460, latency_s=91.3
- ifbench-006: tok_total=4379, tok_final=554, latency_s=60.2
- ifbench-007: tok_total=3740, tok_final=604, latency_s=51.3
- ifbench-008: tok_total=8439, tok_final=247, latency_s=114.7
- ifbench-009: tok_total=1412, tok_final=389, latency_s=19.3
- ifbench-010: tok_total=2110, tok_final=101, latency_s=29.0
- ifbench-011: tok_total=5259, tok_final=253, latency_s=72.4
- ifbench-012: tok_total=6632, tok_final=360, latency_s=91.6
- ifbench-013: tok_total=5131, tok_final=336, latency_s=70.7
- ifbench-014: tok_total=8506, tok_final=314, latency_s=115.9
- ifbench-015: tok_total=5100, tok_final=476, latency_s=70.3
- ifbench-016: tok_total=2951, tok_final=18, latency_s=40.6
- ifbench-017: tok_total=3411, tok_final=13, latency_s=46.9
- ifbench-018: tok_total=1250, tok_final=148, latency_s=17.2
- ifbench-019: tok_total=1742, tok_final=74, latency_s=24.0
- ifbench-020: tok_total=8424, tok_final=232, latency_s=114.7
- ifbench-021: tok_total=1542, tok_final=34, latency_s=21.2
- ifbench-022: tok_total=1950, tok_final=141, latency_s=26.8
- ifbench-023: tok_total=2975, tok_final=175, latency_s=40.9
- ifbench-024: tok_total=2542, tok_final=128, latency_s=34.9
- ifbench-025: tok_total=6233, tok_final=432, latency_s=86.2
- ifbench-026: tok_total=2552, tok_final=351, latency_s=35.1
- ifbench-027: tok_total=2550, tok_final=649, latency_s=34.9
- ifbench-028: tok_total=1735, tok_final=243, latency_s=23.8
- ifbench-029: tok_total=1655, tok_final=332, latency_s=22.7
- ifbench-030: tok_total=3547, tok_final=722, latency_s=48.7
- ifbench-031: tok_total=3789, tok_final=250, latency_s=52.1
- ifbench-032: tok_total=6517, tok_final=957, latency_s=90.0
- ifbench-033: tok_total=2945, tok_final=393, latency_s=40.5
- ifbench-034: tok_total=2502, tok_final=64, latency_s=34.4
- ifbench-035: tok_total=5143, tok_final=571, latency_s=70.9
- ifbench-036: tok_total=12032, tok_final=3840, latency_s=164.5
- ifbench-037: tok_total=5179, tok_final=1677, latency_s=71.1
- ifbench-038: tok_total=5178, tok_final=72, latency_s=71.4
- ifbench-039: tok_total=7574, tok_final=1180, latency_s=104.7
- ifbench-040: tok_total=3349, tok_final=151, latency_s=46.1
- ifbench-041: tok_total=8821, tok_final=629, latency_s=120.2
- ifbench-042: tok_total=3360, tok_final=84, latency_s=46.3
- ifbench-043: tok_total=4146, tok_final=69, latency_s=57.1
- ifbench-044: tok_total=4404, tok_final=35, latency_s=60.7
- ifbench-045: tok_total=3546, tok_final=118, latency_s=48.8
- ifbench-046: tok_total=2343, tok_final=84, latency_s=32.2
- ifbench-047: tok_total=4356, tok_final=148, latency_s=60.1
- ifbench-048: tok_total=6212, tok_final=38, latency_s=85.9
- ifbench-049: tok_total=8728, tok_final=536, latency_s=119.0
- ifbench-050: tok_total=8390, tok_final=198, latency_s=114.2
- ifbench-051: tok_total=8892, tok_final=700, latency_s=123.4
- ifbench-052: tok_total=8359, tok_final=167, latency_s=113.7
- ifbench-053: tok_total=4991, tok_final=289, latency_s=68.9
- ifbench-054: tok_total=2783, tok_final=100, latency_s=38.3
- ifbench-055: tok_total=2749, tok_final=217, latency_s=37.8
- ifbench-056: tok_total=5847, tok_final=215, latency_s=80.8
- ifbench-057: tok_total=3694, tok_final=207, latency_s=50.9
- ifbench-058: tok_total=3733, tok_final=403, latency_s=51.4
- ifbench-059: tok_total=5155, tok_final=188, latency_s=71.2
- ifbench-060: tok_total=3208, tok_final=298, latency_s=44.1
- ifbench-061: tok_total=1610, tok_final=60, latency_s=22.2
- ifbench-062: tok_total=2062, tok_final=76, latency_s=28.4
- ifbench-063: tok_total=2076, tok_final=87, latency_s=28.6
- ifbench-064: tok_total=755, tok_final=12, latency_s=10.5
- ifbench-065: tok_total=1499, tok_final=11, latency_s=20.6
- ifbench-066: tok_total=1573, tok_final=68, latency_s=21.7
- ifbench-067: tok_total=2165, tok_final=52, latency_s=29.8
- ifbench-068: tok_total=7585, tok_final=946, latency_s=104.9
- ifbench-069: tok_total=2207, tok_final=193, latency_s=30.3
- ifbench-070: tok_total=3741, tok_final=426, latency_s=51.4
- ifbench-071: tok_total=2376, tok_final=285, latency_s=32.6
- ifbench-072: tok_total=3095, tok_final=206, latency_s=42.6
- ifbench-073: tok_total=2519, tok_final=145, latency_s=34.6
- ifbench-074: tok_total=3196, tok_final=305, latency_s=43.9
- ifbench-075: tok_total=2985, tok_final=218, latency_s=41.0
- ifbench-076: tok_total=2815, tok_final=479, latency_s=38.6
- ifbench-077: tok_total=3090, tok_final=212, latency_s=42.5
- ifbench-078: tok_total=2800, tok_final=149, latency_s=38.5
- ifbench-079: tok_total=3351, tok_final=335, latency_s=46.1
- ifbench-080: tok_total=3696, tok_final=408, latency_s=50.8
- ifbench-081: tok_total=5740, tok_final=31, latency_s=79.3
- ifbench-082: tok_total=8225, tok_final=33, latency_s=111.9
- ifbench-083: tok_total=3052, tok_final=181, latency_s=42.0
- ifbench-084: tok_total=1025, tok_final=161, latency_s=14.1
- ifbench-085: tok_total=3791, tok_final=707, latency_s=52.0
- ifbench-086: tok_total=2718, tok_final=271, latency_s=37.3
- ifbench-087: tok_total=1809, tok_final=393, latency_s=24.8
- ifbench-088: tok_total=6552, tok_final=202, latency_s=90.7
- ifbench-089: tok_total=3872, tok_final=55, latency_s=53.3
- ifbench-090: tok_total=4838, tok_final=132, latency_s=66.7
- ifbench-091: tok_total=5175, tok_final=667, latency_s=71.2
- ifbench-092: tok_total=8347, tok_final=155, latency_s=115.8
- ifbench-093: tok_total=3419, tok_final=503, latency_s=46.9
- ifbench-094: tok_total=4136, tok_final=1342, latency_s=56.6
- ifbench-095: tok_total=1480, tok_final=93, latency_s=20.4
- ifbench-096: tok_total=3107, tok_final=212, latency_s=42.7
- ifbench-097: tok_total=2121, tok_final=165, latency_s=29.1
- ifbench-098: tok_total=3726, tok_final=303, latency_s=51.2
- ifbench-099: tok_total=1255, tok_final=131, latency_s=17.3
- ifbench-100: tok_total=2483, tok_final=148, latency_s=34.1
- ifbench-101: tok_total=406, tok_final=2, latency_s=5.7
- ifbench-102: tok_total=680, tok_final=3, latency_s=9.5
- ifbench-103: tok_total=1522, tok_final=3, latency_s=21.0
- ifbench-104: tok_total=585, tok_final=2, latency_s=8.2
- ifbench-105: tok_total=448, tok_final=3, latency_s=6.3
- ifbench-106: tok_total=864, tok_final=4, latency_s=12.0
- ifbench-107: tok_total=5285, tok_final=363, latency_s=72.9
- ifbench-108: tok_total=3773, tok_final=943, latency_s=51.7
- ifbench-109: tok_total=3868, tok_final=1395, latency_s=52.9
- ifbench-110: tok_total=4948, tok_final=148, latency_s=68.2
- ifbench-111: tok_total=3966, tok_final=153, latency_s=54.6
- ifbench-112: tok_total=4076, tok_final=122, latency_s=56.1
- ifbench-113: tok_total=2774, tok_final=93, latency_s=38.1
- ifbench-114: tok_total=5168, tok_final=1115, latency_s=71.0
- ifbench-115: tok_total=6629, tok_final=1316, latency_s=91.4
- ifbench-116: tok_total=2079, tok_final=82, latency_s=28.6
- ifbench-117: tok_total=2716, tok_final=131, latency_s=37.4
- ifbench-118: tok_total=5048, tok_final=182, latency_s=69.6
- ifbench-119: tok_total=2172, tok_final=142, latency_s=29.8
- ifbench-120: tok_total=4370, tok_final=752, latency_s=60.0
- ifbench-121: tok_total=2002, tok_final=259, latency_s=27.5
- ifbench-122: tok_total=4987, tok_final=782, latency_s=68.6
- ifbench-123: tok_total=2792, tok_final=365, latency_s=38.3
- ifbench-124: tok_total=5596, tok_final=914, latency_s=77.1
- ifbench-125: tok_total=5930, tok_final=1252, latency_s=81.6
- ifbench-126: tok_total=3935, tok_final=37, latency_s=54.3
- ifbench-127: tok_total=1921, tok_final=252, latency_s=26.4
- ifbench-128: tok_total=1601, tok_final=426, latency_s=21.9
- ifbench-129: tok_total=4070, tok_final=463, latency_s=56.0
- ifbench-130: tok_total=2804, tok_final=211, latency_s=38.5
- ifbench-131: tok_total=3770, tok_final=106, latency_s=51.9
- ifbench-132: tok_total=956, tok_final=73, latency_s=13.2
- ifbench-133: tok_total=1239, tok_final=308, latency_s=17.0
- ifbench-134: tok_total=8538, tok_final=346, latency_s=116.2
- ifbench-135: tok_total=5161, tok_final=91, latency_s=71.2
- ifbench-136: tok_total=6856, tok_final=216, latency_s=94.9
- ifbench-137: tok_total=7431, tok_final=147, latency_s=103.0
- ifbench-138: tok_total=6267, tok_final=78, latency_s=86.7
- ifbench-139: tok_total=3506, tok_final=850, latency_s=48.1
- ifbench-140: tok_total=3198, tok_final=721, latency_s=43.8
- ifbench-141: tok_total=3573, tok_final=1030, latency_s=48.9
- ifbench-142: tok_total=3566, tok_final=783, latency_s=48.9
- ifbench-143: tok_total=2574, tok_final=626, latency_s=35.2
- ifbench-144: tok_total=6145, tok_final=283, latency_s=84.9
- ifbench-145: tok_total=3540, tok_final=573, latency_s=48.6
- ifbench-146: tok_total=3030, tok_final=423, latency_s=41.6
- ifbench-147: tok_total=3542, tok_final=523, latency_s=48.6
- ifbench-148: tok_total=4455, tok_final=139, latency_s=61.4
- ifbench-149: tok_total=2750, tok_final=76, latency_s=37.9
- ifbench-150: tok_total=2760, tok_final=154, latency_s=38.0
- ifbench-151: tok_total=8312, tok_final=120, latency_s=113.1
- ifbench-152: tok_total=6255, tok_final=609, latency_s=86.3
- ifbench-153: tok_total=2616, tok_final=126, latency_s=35.9
- ifbench-154: tok_total=11275, tok_final=3083, latency_s=154.0
- ifbench-155: tok_total=2374, tok_final=86, latency_s=32.7
- ifbench-156: tok_total=2436, tok_final=147, latency_s=33.5
- ifbench-157: tok_total=2240, tok_final=92, latency_s=30.8
- ifbench-158: tok_total=2800, tok_final=172, latency_s=38.6
- ifbench-159: tok_total=16384, tok_final=8192, latency_s=225.3
- ifbench-160: tok_total=8262, tok_final=70, latency_s=112.5
- ifbench-161: tok_total=5866, tok_final=175, latency_s=81.1
- ifbench-162: tok_total=2379, tok_final=159, latency_s=32.7
- ifbench-163: tok_total=4550, tok_final=280, latency_s=62.7
- ifbench-164: tok_total=1478, tok_final=41, latency_s=20.3
- ifbench-165: tok_total=5899, tok_final=288, latency_s=81.5
- ifbench-166: tok_total=3134, tok_final=61, latency_s=43.2
- ifbench-167: tok_total=8261, tok_final=69, latency_s=112.4
- ifbench-168: tok_total=8232, tok_final=40, latency_s=112.0
- ifbench-169: tok_total=8264, tok_final=72, latency_s=112.5
- ifbench-170: tok_total=8214, tok_final=22, latency_s=111.8
- ifbench-171: tok_total=8234, tok_final=42, latency_s=112.1
- ifbench-172: tok_total=8195, tok_final=108, latency_s=113.8
- ifbench-173: tok_total=5021, tok_final=104, latency_s=69.2
- ifbench-174: tok_total=6504, tok_final=94, latency_s=90.0
- ifbench-175: tok_total=7516, tok_final=206, latency_s=104.2
- ifbench-176: tok_total=5523, tok_final=119, latency_s=76.3
- ifbench-177: tok_total=8798, tok_final=606, latency_s=119.8
- ifbench-178: tok_total=7794, tok_final=93, latency_s=108.1
- ifbench-179: tok_total=5090, tok_final=53, latency_s=70.3
- ifbench-180: tok_total=4931, tok_final=48, latency_s=68.0
- ifbench-181: tok_total=6930, tok_final=305, latency_s=95.9
- ifbench-182: tok_total=7187, tok_final=252, latency_s=99.5
- ifbench-183: tok_total=8280, tok_final=88, latency_s=112.5
- ifbench-184: tok_total=5890, tok_final=183, latency_s=81.5
- ifbench-185: tok_total=8369, tok_final=177, latency_s=113.9
- ifbench-186: tok_total=4042, tok_final=85, latency_s=55.6
- ifbench-187: tok_total=8282, tok_final=90, latency_s=112.7
- ifbench-188: tok_total=6057, tok_final=81, latency_s=83.7
- ifbench-189: tok_total=8356, tok_final=164, latency_s=113.7
- ifbench-190: tok_total=8461, tok_final=269, latency_s=115.1
- ifbench-191: tok_total=8409, tok_final=217, latency_s=114.5
- ifbench-192: tok_total=10614, tok_final=2422, latency_s=144.9
- ifbench-193: tok_total=3782, tok_final=480, latency_s=52.0
- ifbench-194: tok_total=2199, tok_final=266, latency_s=30.2
- ifbench-195: tok_total=2964, tok_final=329, latency_s=40.7
- ifbench-196: tok_total=5616, tok_final=526, latency_s=77.5
- ifbench-197: tok_total=8723, tok_final=531, latency_s=118.9
- ifbench-198: tok_total=3416, tok_final=104, latency_s=47.0
- ifbench-199: tok_total=5458, tok_final=111, latency_s=75.3
- ifbench-200: tok_total=7321, tok_final=292, latency_s=101.3
- ifbench-201: tok_total=8597, tok_final=405, latency_s=117.0
- ifbench-202: tok_total=16384, tok_final=8192, latency_s=225.1
- ifbench-203: tok_total=8333, tok_final=141, latency_s=113.4
- ifbench-204: tok_total=8247, tok_final=55, latency_s=112.2
- ifbench-205: tok_total=8270, tok_final=78, latency_s=112.5
- ifbench-206: tok_total=8261, tok_final=69, latency_s=112.4
- ifbench-207: tok_total=8262, tok_final=70, latency_s=112.7
- ifbench-208: tok_total=8714, tok_final=522, latency_s=118.8
- ifbench-209: tok_total=8229, tok_final=37, latency_s=112.1
- ifbench-210: tok_total=8230, tok_final=38, latency_s=112.0
- ifbench-211: tok_total=8377, tok_final=185, latency_s=114.1
- ifbench-212: tok_total=8250, tok_final=58, latency_s=112.4
- ifbench-213: tok_total=8333, tok_final=141, latency_s=113.4
- ifbench-214: tok_total=None, tok_final=None, latency_s=335.8
- ifbench-215: tok_total=8429, tok_final=237, latency_s=117.0
- ifbench-216: tok_total=8223, tok_final=31, latency_s=114.1
- ifbench-217: tok_total=16384, tok_final=8192, latency_s=225.1
- ifbench-218: tok_total=8205, tok_final=13, latency_s=113.9
- ifbench-219: tok_total=8391, tok_final=199, latency_s=114.2
- ifbench-220: tok_total=6148, tok_final=244, latency_s=84.9
- ifbench-221: tok_total=4909, tok_final=319, latency_s=67.6
- ifbench-222: tok_total=3968, tok_final=159, latency_s=54.7
- ifbench-223: tok_total=4945, tok_final=284, latency_s=68.1
- ifbench-224: tok_total=8989, tok_final=797, latency_s=122.3
- ifbench-225: tok_total=4850, tok_final=34, latency_s=66.8
- ifbench-226: tok_total=3012, tok_final=12, latency_s=41.4
- ifbench-227: tok_total=8501, tok_final=309, latency_s=115.5
- ifbench-228: tok_total=8479, tok_final=287, latency_s=115.3
- ifbench-229: tok_total=8537, tok_final=345, latency_s=116.1
- ifbench-230: tok_total=8457, tok_final=265, latency_s=117.2
- ifbench-231: tok_total=16384, tok_final=8192, latency_s=227.1
- ifbench-232: tok_total=16384, tok_final=8192, latency_s=227.1
- ifbench-233: tok_total=8318, tok_final=126, latency_s=113.1
- ifbench-234: tok_total=8305, tok_final=113, latency_s=112.9
- ifbench-235: tok_total=2842, tok_final=188, latency_s=39.0
- ifbench-236: tok_total=4579, tok_final=547, latency_s=62.9
- ifbench-237: tok_total=2483, tok_final=418, latency_s=34.0
- ifbench-238: tok_total=5931, tok_final=951, latency_s=81.6
- ifbench-239: tok_total=4551, tok_final=927, latency_s=62.5
- ifbench-240: tok_total=7078, tok_final=430, latency_s=97.9
- ifbench-241: tok_total=8506, tok_final=314, latency_s=115.7
- ifbench-242: tok_total=2161, tok_final=131, latency_s=29.6
- ifbench-243: tok_total=3600, tok_final=219, latency_s=49.5
- ifbench-244: tok_total=3514, tok_final=305, latency_s=48.3
- ifbench-245: tok_total=5187, tok_final=397, latency_s=71.4
- ifbench-246: tok_total=3763, tok_final=257, latency_s=51.7
- ifbench-247: tok_total=6378, tok_final=159, latency_s=88.1
- ifbench-248: tok_total=8290, tok_final=98, latency_s=112.6
- ifbench-249: tok_total=8214, tok_final=22, latency_s=111.6
- ifbench-250: tok_total=8514, tok_final=322, latency_s=115.7
- ifbench-251: tok_total=8262, tok_final=70, latency_s=112.3
- ifbench-252: tok_total=8194, tok_final=2, latency_s=111.4
- ifbench-253: tok_total=8521, tok_final=329, latency_s=115.8
- ifbench-254: tok_total=8779, tok_final=587, latency_s=121.6
- ifbench-255: tok_total=4812, tok_final=67, latency_s=66.3
- ifbench-256: tok_total=3053, tok_final=103, latency_s=42.0
- ifbench-257: tok_total=5535, tok_final=221, latency_s=76.3
- ifbench-258: tok_total=4193, tok_final=249, latency_s=57.6
- ifbench-259: tok_total=8580, tok_final=388, latency_s=118.9
- ifbench-260: tok_total=8322, tok_final=130, latency_s=113.1
- ifbench-261: tok_total=2993, tok_final=244, latency_s=41.1
- ifbench-262: tok_total=8317, tok_final=125, latency_s=113.1
- ifbench-263: tok_total=4647, tok_final=796, latency_s=64.0
- ifbench-264: tok_total=8410, tok_final=218, latency_s=114.3
- ifbench-265: tok_total=8395, tok_final=203, latency_s=114.2
- ifbench-266: tok_total=7774, tok_final=67, latency_s=107.8
- ifbench-267: tok_total=8357, tok_final=165, latency_s=113.6
- ifbench-268: tok_total=1332, tok_final=20, latency_s=18.3
- ifbench-269: tok_total=1522, tok_final=121, latency_s=20.9
- ifbench-270: tok_total=1453, tok_final=105, latency_s=19.9
- ifbench-271: tok_total=3228, tok_final=293, latency_s=44.3
- ifbench-272: tok_total=6407, tok_final=443, latency_s=88.4
- ifbench-273: tok_total=7455, tok_final=74, latency_s=103.2
- ifbench-274: tok_total=2739, tok_final=351, latency_s=37.5
- ifbench-275: tok_total=514, tok_final=40, latency_s=7.2
- ifbench-276: tok_total=5263, tok_final=201, latency_s=72.5
- ifbench-277: tok_total=3582, tok_final=327, latency_s=49.2
- ifbench-278: tok_total=2471, tok_final=11, latency_s=33.9
- ifbench-279: tok_total=3514, tok_final=1026, latency_s=48.0
- ifbench-280: tok_total=5250, tok_final=408, latency_s=72.3
- ifbench-281: tok_total=2222, tok_final=69, latency_s=30.5
- ifbench-282: tok_total=2447, tok_final=4, latency_s=33.7
- ifbench-283: tok_total=8101, tok_final=1560, latency_s=111.9
- ifbench-284: tok_total=4063, tok_final=341, latency_s=55.8
- ifbench-285: tok_total=5346, tok_final=936, latency_s=73.5
- ifbench-286: tok_total=4464, tok_final=202, latency_s=61.4
- ifbench-287: tok_total=1405, tok_final=321, latency_s=19.3
- ifbench-288: tok_total=1679, tok_final=521, latency_s=22.9
- ifbench-289: tok_total=3280, tok_final=381, latency_s=45.0
- ifbench-290: tok_total=2498, tok_final=443, latency_s=34.2
- ifbench-291: tok_total=1494, tok_final=2, latency_s=20.5
- ifbench-292: tok_total=1762, tok_final=87, latency_s=24.2
- ifbench-293: tok_total=4436, tok_final=27, latency_s=61.0
- ifbench-294: tok_total=8266, tok_final=74, latency_s=114.6

### olymmath_hard
- olymmath-hard-001: tok_total=9068, tok_final=876, latency_s=123.4
- olymmath-hard-002: tok_total=9038, tok_final=846, latency_s=122.8
- olymmath-hard-003: tok_total=9020, tok_final=828, latency_s=122.7
- olymmath-hard-004: tok_total=8900, tok_final=708, latency_s=120.9
- olymmath-hard-005: tok_total=9200, tok_final=1008, latency_s=125.2
- olymmath-hard-006: tok_total=9562, tok_final=1370, latency_s=130.2
- olymmath-hard-007: tok_total=8860, tok_final=668, latency_s=120.5
- olymmath-hard-008: tok_total=9056, tok_final=864, latency_s=123.1
- olymmath-hard-009: tok_total=8966, tok_final=774, latency_s=122.1
- olymmath-hard-010: tok_total=9179, tok_final=987, latency_s=125.0
- olymmath-hard-011: tok_total=9484, tok_final=1292, latency_s=129.1
- olymmath-hard-012: tok_total=9323, tok_final=1131, latency_s=126.9
- olymmath-hard-013: tok_total=9298, tok_final=1106, latency_s=126.6
- olymmath-hard-014: tok_total=9189, tok_final=997, latency_s=124.8
- olymmath-hard-015: tok_total=8892, tok_final=700, latency_s=121.3
- olymmath-hard-016: tok_total=9347, tok_final=1155, latency_s=127.0
- olymmath-hard-017: tok_total=9182, tok_final=990, latency_s=124.9
- olymmath-hard-018: tok_total=9055, tok_final=863, latency_s=123.2
- olymmath-hard-019: tok_total=9056, tok_final=864, latency_s=123.0
- olymmath-hard-020: tok_total=9726, tok_final=1534, latency_s=132.3
- olymmath-hard-021: tok_total=9049, tok_final=857, latency_s=122.9
- olymmath-hard-022: tok_total=9360, tok_final=1168, latency_s=127.2
- olymmath-hard-023: tok_total=9009, tok_final=817, latency_s=122.6
- olymmath-hard-024: tok_total=8931, tok_final=739, latency_s=121.3
- olymmath-hard-025: tok_total=9321, tok_final=1129, latency_s=126.8
- olymmath-hard-026: tok_total=9451, tok_final=1259, latency_s=128.5
- olymmath-hard-027: tok_total=16384, tok_final=8192, latency_s=227.0
- olymmath-hard-028: tok_total=9340, tok_final=1148, latency_s=126.9
- olymmath-hard-029: tok_total=9708, tok_final=1516, latency_s=132.0
- olymmath-hard-030: tok_total=9411, tok_final=1219, latency_s=127.9
- olymmath-hard-031: tok_total=9301, tok_final=1109, latency_s=126.4
- olymmath-hard-032: tok_total=9200, tok_final=1008, latency_s=125.0
- olymmath-hard-033: tok_total=9209, tok_final=1017, latency_s=125.1
- olymmath-hard-034: tok_total=10029, tok_final=1837, latency_s=136.4
- olymmath-hard-035: tok_total=9185, tok_final=993, latency_s=124.8
- olymmath-hard-036: tok_total=9273, tok_final=1081, latency_s=126.0
- olymmath-hard-037: tok_total=9090, tok_final=898, latency_s=123.5
- olymmath-hard-038: tok_total=8993, tok_final=801, latency_s=122.3
- olymmath-hard-039: tok_total=8947, tok_final=755, latency_s=121.5
- olymmath-hard-040: tok_total=9487, tok_final=1295, latency_s=128.9
- olymmath-hard-041: tok_total=9759, tok_final=1567, latency_s=132.7
- olymmath-hard-042: tok_total=9236, tok_final=1044, latency_s=125.5
- olymmath-hard-043: tok_total=9213, tok_final=1021, latency_s=125.2
- olymmath-hard-044: tok_total=10178, tok_final=1986, latency_s=138.5
- olymmath-hard-045: tok_total=9017, tok_final=825, latency_s=122.6
- olymmath-hard-046: tok_total=8908, tok_final=716, latency_s=121.0
- olymmath-hard-047: tok_total=9209, tok_final=1017, latency_s=125.2
- olymmath-hard-048: tok_total=9141, tok_final=949, latency_s=124.2
- olymmath-hard-049: tok_total=9618, tok_final=1426, latency_s=130.8
- olymmath-hard-050: tok_total=14534, tok_final=6342, latency_s=198.9
- olymmath-hard-051: tok_total=9165, tok_final=973, latency_s=124.5
- olymmath-hard-052: tok_total=9089, tok_final=897, latency_s=123.5
- olymmath-hard-053: tok_total=9058, tok_final=866, latency_s=123.1
- olymmath-hard-054: tok_total=8931, tok_final=739, latency_s=121.4
- olymmath-hard-055: tok_total=9137, tok_final=945, latency_s=124.2
- olymmath-hard-056: tok_total=9251, tok_final=1059, latency_s=125.7
- olymmath-hard-057: tok_total=9321, tok_final=1129, latency_s=126.7
- olymmath-hard-058: tok_total=9251, tok_final=1059, latency_s=125.7
- olymmath-hard-059: tok_total=9215, tok_final=1023, latency_s=125.2
- olymmath-hard-060: tok_total=9125, tok_final=933, latency_s=124.0
- olymmath-hard-061: tok_total=9072, tok_final=880, latency_s=123.3
- olymmath-hard-062: tok_total=8977, tok_final=785, latency_s=122.0
- olymmath-hard-063: tok_total=9224, tok_final=1032, latency_s=125.4
- olymmath-hard-064: tok_total=9330, tok_final=1138, latency_s=126.8
- olymmath-hard-065: tok_total=8952, tok_final=760, latency_s=121.7
- olymmath-hard-066: tok_total=9279, tok_final=1087, latency_s=126.1
- olymmath-hard-067: tok_total=9164, tok_final=972, latency_s=124.5
- olymmath-hard-068: tok_total=10399, tok_final=2207, latency_s=141.4
- olymmath-hard-069: tok_total=9135, tok_final=943, latency_s=124.2
- olymmath-hard-070: tok_total=8917, tok_final=725, latency_s=121.1
- olymmath-hard-071: tok_total=9065, tok_final=873, latency_s=123.1
- olymmath-hard-072: tok_total=9162, tok_final=970, latency_s=124.5
- olymmath-hard-073: tok_total=9613, tok_final=1421, latency_s=130.7
- olymmath-hard-074: tok_total=9129, tok_final=937, latency_s=124.1
- olymmath-hard-075: tok_total=9421, tok_final=1229, latency_s=128.0
- olymmath-hard-076: tok_total=9058, tok_final=866, latency_s=123.1
- olymmath-hard-077: tok_total=9468, tok_final=1276, latency_s=130.7
- olymmath-hard-078: tok_total=9492, tok_final=1300, latency_s=133.7
- olymmath-hard-079: tok_total=9322, tok_final=1130, latency_s=130.5
- olymmath-hard-080: tok_total=16384, tok_final=8192, latency_s=229.3
- olymmath-hard-081: tok_total=9037, tok_final=845, latency_s=124.0
- olymmath-hard-082: tok_total=9026, tok_final=834, latency_s=122.7
- olymmath-hard-083: tok_total=9352, tok_final=1160, latency_s=128.7
- olymmath-hard-084: tok_total=9755, tok_final=1563, latency_s=134.2
- olymmath-hard-085: tok_total=13635, tok_final=5443, latency_s=189.1
- olymmath-hard-086: tok_total=9452, tok_final=1260, latency_s=128.8
- olymmath-hard-087: tok_total=9460, tok_final=1268, latency_s=128.8
- olymmath-hard-088: tok_total=9298, tok_final=1106, latency_s=126.5
- olymmath-hard-089: tok_total=8891, tok_final=699, latency_s=120.9
- olymmath-hard-090: tok_total=9068, tok_final=876, latency_s=123.3
- olymmath-hard-091: tok_total=9295, tok_final=1103, latency_s=126.4
- olymmath-hard-092: tok_total=9324, tok_final=1132, latency_s=126.9
- olymmath-hard-093: tok_total=9328, tok_final=1136, latency_s=127.1
- olymmath-hard-094: tok_total=14248, tok_final=6056, latency_s=195.0
- olymmath-hard-095: tok_total=14928, tok_final=6736, latency_s=204.6
- olymmath-hard-096: tok_total=9138, tok_final=946, latency_s=124.3
- olymmath-hard-097: tok_total=8936, tok_final=744, latency_s=121.6
- olymmath-hard-098: tok_total=9320, tok_final=1128, latency_s=126.8
- olymmath-hard-099: tok_total=8745, tok_final=553, latency_s=119.0
- olymmath-hard-100: tok_total=9889, tok_final=1697, latency_s=134.6

### amo
- amo-001: tok_total=9221, tok_final=1029, latency_s=125.5
- amo-002: tok_total=9413, tok_final=1221, latency_s=128.2
- amo-003: tok_total=9134, tok_final=942, latency_s=124.3
- amo-004: tok_total=9231, tok_final=1039, latency_s=125.6
- amo-005: tok_total=8932, tok_final=740, latency_s=121.5
- amo-006: tok_total=16320, tok_final=8128, latency_s=224.0
- amo-007: tok_total=9134, tok_final=942, latency_s=124.3
- amo-008: tok_total=9568, tok_final=1376, latency_s=130.3
- amo-009: tok_total=9413, tok_final=1221, latency_s=128.2
- amo-010: tok_total=16384, tok_final=8192, latency_s=224.8
- amo-011: tok_total=9511, tok_final=1319, latency_s=129.6
- amo-012: tok_total=9889, tok_final=1697, latency_s=134.8
- amo-013: tok_total=9473, tok_final=1281, latency_s=129.1
- amo-014: tok_total=9285, tok_final=1093, latency_s=126.4
- amo-015: tok_total=9353, tok_final=1161, latency_s=127.5
- amo-016: tok_total=9054, tok_final=862, latency_s=123.1
- amo-017: tok_total=9015, tok_final=823, latency_s=122.8
- amo-018: tok_total=10461, tok_final=2269, latency_s=144.2
- amo-019: tok_total=9365, tok_final=1173, latency_s=128.7
- amo-020: tok_total=9421, tok_final=1229, latency_s=130.9
- amo-021: tok_total=9159, tok_final=967, latency_s=126.3
- amo-022: tok_total=9406, tok_final=1214, latency_s=131.7
- amo-023: tok_total=9170, tok_final=978, latency_s=127.5
- amo-024: tok_total=9764, tok_final=1572, latency_s=136.2
- amo-025: tok_total=9669, tok_final=1477, latency_s=134.8
- amo-026: tok_total=9872, tok_final=1680, latency_s=139.2
- amo-027: tok_total=16384, tok_final=8192, latency_s=231.4
- amo-028: tok_total=9012, tok_final=820, latency_s=125.3
- amo-029: tok_total=8925, tok_final=733, latency_s=123.5
- amo-030: tok_total=9186, tok_final=994, latency_s=126.9
- amo-031: tok_total=8988, tok_final=796, latency_s=122.9
- amo-032: tok_total=8745, tok_final=553, latency_s=119.8
- amo-033: tok_total=10524, tok_final=2332, latency_s=145.4
- amo-034: tok_total=9494, tok_final=1302, latency_s=130.3
- amo-035: tok_total=8921, tok_final=729, latency_s=122.0
- amo-036: tok_total=12856, tok_final=4664, latency_s=177.9
- amo-037: tok_total=8908, tok_final=716, latency_s=121.4
- amo-038: tok_total=9197, tok_final=1005, latency_s=125.4
- amo-039: tok_total=11416, tok_final=3224, latency_s=156.5

### tc_json_v1
- tc-json-bfcl-001: tok_total=1065, tok_final=31, latency_s=15.0
- tc-json-bfcl-002: tok_total=960, tok_final=40, latency_s=13.5
- tc-json-bfcl-003: tok_total=242, tok_final=31, latency_s=3.6
- tc-json-bfcl-004: tok_total=797, tok_final=34, latency_s=11.2
- tc-json-bfcl-005: tok_total=232, tok_final=34, latency_s=3.5
- tc-json-bfcl-006: tok_total=904, tok_final=36, latency_s=12.7
- tc-json-bfcl-007: tok_total=269, tok_final=33, latency_s=4.0
- tc-json-bfcl-008: tok_total=1181, tok_final=49, latency_s=16.5
- tc-json-bfcl-009: tok_total=220, tok_final=34, latency_s=3.3
- tc-json-bfcl-010: tok_total=218, tok_final=31, latency_s=3.3
- tc-json-bfcl-011: tok_total=714, tok_final=29, latency_s=10.0
- tc-json-bfcl-012: tok_total=303, tok_final=40, latency_s=4.4
- tc-json-bfcl-013: tok_total=1263, tok_final=55, latency_s=17.6
- tc-json-bfcl-014: tok_total=827, tok_final=38, latency_s=11.6
- tc-json-bfcl-015: tok_total=410, tok_final=45, latency_s=5.9
- tc-json-bfcl-016: tok_total=231, tok_final=42, latency_s=3.4
- tc-json-bfcl-017: tok_total=705, tok_final=46, latency_s=9.9
- tc-json-bfcl-018: tok_total=272, tok_final=38, latency_s=4.0
- tc-json-bfcl-019: tok_total=220, tok_final=26, latency_s=3.3
- tc-json-bfcl-020: tok_total=263, tok_final=36, latency_s=3.9
- tc-json-bfcl-021: tok_total=366, tok_final=42, latency_s=5.3
- tc-json-bfcl-022: tok_total=1288, tok_final=41, latency_s=17.9
- tc-json-bfcl-023: tok_total=453, tok_final=67, latency_s=6.5
- tc-json-bfcl-024: tok_total=627, tok_final=46, latency_s=8.8
- tc-json-bfcl-025: tok_total=426, tok_final=43, latency_s=6.1
- tc-json-bfcl-026: tok_total=787, tok_final=39, latency_s=11.0
- tc-json-bfcl-027: tok_total=281, tok_final=44, latency_s=4.1
- tc-json-bfcl-028: tok_total=457, tok_final=40, latency_s=6.5
- tc-json-bfcl-029: tok_total=853, tok_final=42, latency_s=11.9
- tc-json-bfcl-030: tok_total=768, tok_final=44, latency_s=10.7
- tc-json-bfcl-031: tok_total=575, tok_final=39, latency_s=8.1
- tc-json-bfcl-032: tok_total=848, tok_final=40, latency_s=11.8
- tc-json-bfcl-033: tok_total=359, tok_final=33, latency_s=5.2
- tc-json-bfcl-034: tok_total=641, tok_final=36, latency_s=9.1
- tc-json-bfcl-035: tok_total=306, tok_final=32, latency_s=4.5
- tc-json-bfcl-036: tok_total=239, tok_final=34, latency_s=3.5
- tc-json-bfcl-037: tok_total=1143, tok_final=35, latency_s=15.9
- tc-json-bfcl-038: tok_total=234, tok_final=34, latency_s=3.5
- tc-json-bfcl-039: tok_total=438, tok_final=40, latency_s=6.2
- tc-json-bfcl-040: tok_total=360, tok_final=33, latency_s=5.2
- tc-json-bfcl-041: tok_total=372, tok_final=28, latency_s=5.3
- tc-json-bfcl-042: tok_total=197, tok_final=30, latency_s=3.0
- tc-json-bfcl-043: tok_total=465, tok_final=40, latency_s=6.6
- tc-json-bfcl-044: tok_total=1102, tok_final=49, latency_s=15.3
- tc-json-bfcl-045: tok_total=567, tok_final=45, latency_s=8.0
- tc-json-bfcl-046: tok_total=287, tok_final=33, latency_s=4.2
- tc-json-bfcl-047: tok_total=562, tok_final=43, latency_s=8.0
- tc-json-bfcl-048: tok_total=366, tok_final=38, latency_s=5.2
- tc-json-bfcl-049: tok_total=597, tok_final=38, latency_s=8.4
- tc-json-bfcl-050: tok_total=297, tok_final=37, latency_s=4.3
- tc-json-bfcl-051: tok_total=787, tok_final=49, latency_s=11.0
- tc-json-bfcl-052: tok_total=419, tok_final=36, latency_s=6.0
- tc-json-bfcl-053: tok_total=1366, tok_final=34, latency_s=18.9
- tc-json-bfcl-054: tok_total=1650, tok_final=38, latency_s=22.8
- tc-json-bfcl-055: tok_total=499, tok_final=32, latency_s=7.1
- tc-json-bfcl-056: tok_total=840, tok_final=44, latency_s=11.7
- tc-json-bfcl-057: tok_total=623, tok_final=31, latency_s=8.8
- tc-json-bfcl-058: tok_total=475, tok_final=44, latency_s=6.8
- tc-json-bfcl-059: tok_total=265, tok_final=35, latency_s=3.9
- tc-json-bfcl-060: tok_total=964, tok_final=44, latency_s=13.4
- tc-json-bfcl-061: tok_total=231, tok_final=34, latency_s=3.4
- tc-json-bfcl-062: tok_total=593, tok_final=37, latency_s=8.4
- tc-json-bfcl-063: tok_total=435, tok_final=50, latency_s=6.2
- tc-json-bfcl-064: tok_total=310, tok_final=35, latency_s=4.5
- tc-json-bfcl-065: tok_total=340, tok_final=46, latency_s=4.9
- tc-json-bfcl-066: tok_total=353, tok_final=37, latency_s=5.1
- tc-json-bfcl-067: tok_total=1015, tok_final=38, latency_s=14.1
- tc-json-bfcl-068: tok_total=565, tok_final=37, latency_s=8.0
- tc-json-bfcl-069: tok_total=347, tok_final=40, latency_s=5.0
- tc-json-bfcl-070: tok_total=1122, tok_final=39, latency_s=15.6
- tc-json-bfcl-071: tok_total=402, tok_final=31, latency_s=5.8
- tc-json-bfcl-072: tok_total=583, tok_final=40, latency_s=8.2
- tc-json-bfcl-073: tok_total=332, tok_final=38, latency_s=4.8
- tc-json-bfcl-074: tok_total=980, tok_final=38, latency_s=13.6
- tc-json-bfcl-075: tok_total=1022, tok_final=45, latency_s=14.2
- tc-json-bfcl-076: tok_total=264, tok_final=37, latency_s=4.0
- tc-json-bfcl-077: tok_total=649, tok_final=38, latency_s=9.2
- tc-json-bfcl-078: tok_total=471, tok_final=58, latency_s=6.8
- tc-json-bfcl-079: tok_total=485, tok_final=60, latency_s=7.0
- tc-json-bfcl-080: tok_total=302, tok_final=38, latency_s=4.5
- tc-json-bfcl-081: tok_total=1156, tok_final=43, latency_s=16.1
- tc-json-bfcl-082: tok_total=988, tok_final=43, latency_s=14.0
- tc-json-bfcl-083: tok_total=498, tok_final=36, latency_s=7.2
- tc-json-bfcl-084: tok_total=231, tok_final=34, latency_s=3.5
- tc-json-bfcl-085: tok_total=591, tok_final=38, latency_s=8.4
- tc-json-bfcl-086: tok_total=307, tok_final=43, latency_s=4.6
- tc-json-bfcl-087: tok_total=277, tok_final=30, latency_s=4.1
- tc-json-bfcl-088: tok_total=530, tok_final=32, latency_s=7.6
- tc-json-bfcl-089: tok_total=329, tok_final=36, latency_s=4.8
- tc-json-bfcl-090: tok_total=541, tok_final=34, latency_s=7.8
- tc-json-bfcl-091: tok_total=947, tok_final=39, latency_s=13.4
- tc-json-bfcl-092: tok_total=447, tok_final=39, latency_s=6.5
- tc-json-bfcl-093: tok_total=637, tok_final=33, latency_s=9.1
- tc-json-bfcl-094: tok_total=412, tok_final=41, latency_s=6.0
- tc-json-bfcl-095: tok_total=757, tok_final=40, latency_s=10.7
- tc-json-bfcl-096: tok_total=360, tok_final=35, latency_s=5.3
- tc-json-bfcl-097: tok_total=864, tok_final=32, latency_s=12.2
- tc-json-bfcl-098: tok_total=999, tok_final=34, latency_s=13.9
- tc-json-bfcl-099: tok_total=333, tok_final=41, latency_s=4.8
- tc-json-bfcl-100: tok_total=523, tok_final=34, latency_s=7.5
- tc-json-bfcl-101: tok_total=889, tok_final=39, latency_s=12.5
- tc-json-bfcl-102: tok_total=487, tok_final=35, latency_s=7.0
- tc-json-bfcl-103: tok_total=200, tok_final=31, latency_s=3.0
- tc-json-bfcl-104: tok_total=550, tok_final=28, latency_s=7.9
- tc-json-bfcl-105: tok_total=394, tok_final=44, latency_s=5.7
- tc-json-bfcl-106: tok_total=444, tok_final=43, latency_s=6.4
- tc-json-bfcl-107: tok_total=682, tok_final=38, latency_s=9.7
- tc-json-bfcl-108: tok_total=290, tok_final=34, latency_s=4.3
- tc-json-bfcl-109: tok_total=770, tok_final=42, latency_s=10.9
- tc-json-bfcl-110: tok_total=1303, tok_final=31, latency_s=18.1
- tc-json-bfcl-111: tok_total=417, tok_final=46, latency_s=6.1
- tc-json-bfcl-112: tok_total=403, tok_final=27, latency_s=5.8
- tc-json-bfcl-113: tok_total=252, tok_final=34, latency_s=3.8
- tc-json-bfcl-114: tok_total=1269, tok_final=39, latency_s=17.7
- tc-json-bfcl-115: tok_total=723, tok_final=31, latency_s=10.2
- tc-json-bfcl-116: tok_total=1090, tok_final=33, latency_s=15.2
- tc-json-bfcl-117: tok_total=525, tok_final=35, latency_s=7.5
- tc-json-bfcl-118: tok_total=523, tok_final=45, latency_s=7.6
- tc-json-bfcl-119: tok_total=734, tok_final=33, latency_s=10.4
- tc-json-bfcl-120: tok_total=629, tok_final=41, latency_s=9.0
- tc-json-bfcl-121: tok_total=1088, tok_final=31, latency_s=15.2
- tc-json-bfcl-122: tok_total=984, tok_final=36, latency_s=13.8
- tc-json-bfcl-123: tok_total=884, tok_final=46, latency_s=12.4
- tc-json-bfcl-124: tok_total=331, tok_final=46, latency_s=4.9
- tc-json-bfcl-125: tok_total=806, tok_final=45, latency_s=11.4
- tc-json-bfcl-126: tok_total=598, tok_final=44, latency_s=8.6
- tc-json-bfcl-127: tok_total=928, tok_final=49, latency_s=13.0
- tc-json-bfcl-128: tok_total=608, tok_final=38, latency_s=8.7
- tc-json-bfcl-129: tok_total=978, tok_final=65, latency_s=13.8
- tc-json-bfcl-130: tok_total=369, tok_final=42, latency_s=5.4
- tc-json-bfcl-131: tok_total=556, tok_final=34, latency_s=7.9
- tc-json-bfcl-132: tok_total=957, tok_final=42, latency_s=13.5
- tc-json-bfcl-133: tok_total=956, tok_final=32, latency_s=13.4
- tc-json-bfcl-134: tok_total=880, tok_final=43, latency_s=12.4
- tc-json-bfcl-135: tok_total=836, tok_final=39, latency_s=11.8
- tc-json-bfcl-136: tok_total=1421, tok_final=43, latency_s=19.8
- tc-json-bfcl-137: tok_total=366, tok_final=42, latency_s=5.4
- tc-json-bfcl-138: tok_total=1087, tok_final=47, latency_s=15.3
- tc-json-bfcl-139: tok_total=1120, tok_final=32, latency_s=15.6
- tc-json-bfcl-140: tok_total=1043, tok_final=35, latency_s=14.7
- tc-json-bfcl-141: tok_total=839, tok_final=34, latency_s=11.9
- tc-json-bfcl-142: tok_total=530, tok_final=39, latency_s=7.6
- tc-json-bfcl-143: tok_total=327, tok_final=37, latency_s=4.9
- tc-json-bfcl-144: tok_total=729, tok_final=38, latency_s=10.3
- tc-json-bfcl-145: tok_total=688, tok_final=40, latency_s=9.7
- tc-json-bfcl-146: tok_total=334, tok_final=44, latency_s=5.0
- tc-json-bfcl-147: tok_total=1260, tok_final=64, latency_s=17.7
- tc-json-bfcl-148: tok_total=536, tok_final=36, latency_s=7.7
- tc-json-bfcl-149: tok_total=509, tok_final=33, latency_s=7.4
- tc-json-bfcl-150: tok_total=977, tok_final=39, latency_s=13.7
- tc-json-bfcl-151: tok_total=712, tok_final=51, latency_s=10.0
- tc-json-bfcl-152: tok_total=1045, tok_final=100, latency_s=14.5
- tc-json-bfcl-153: tok_total=1197, tok_final=79, latency_s=16.6
- tc-json-bfcl-154: tok_total=1256, tok_final=101, latency_s=17.4
- tc-json-bfcl-155: tok_total=382, tok_final=57, latency_s=5.5
- tc-json-bfcl-156: tok_total=1454, tok_final=86, latency_s=20.1
- tc-json-bfcl-157: tok_total=933, tok_final=68, latency_s=13.0
- tc-json-bfcl-158: tok_total=1851, tok_final=109, latency_s=25.6
- tc-json-bfcl-159: tok_total=874, tok_final=66, latency_s=12.2
- tc-json-bfcl-160: tok_total=1090, tok_final=75, latency_s=15.1
- tc-json-bfcl-161: tok_total=1283, tok_final=78, latency_s=17.8
- tc-json-bfcl-162: tok_total=613, tok_final=78, latency_s=8.6
- tc-json-bfcl-163: tok_total=891, tok_final=52, latency_s=12.4
- tc-json-bfcl-164: tok_total=1270, tok_final=74, latency_s=17.6
- tc-json-bfcl-165: tok_total=429, tok_final=65, latency_s=6.1
- tc-json-bfcl-166: tok_total=589, tok_final=78, latency_s=8.3
- tc-json-bfcl-167: tok_total=1759, tok_final=121, latency_s=24.3
- tc-json-bfcl-168: tok_total=458, tok_final=101, latency_s=6.6
- tc-json-bfcl-169: tok_total=449, tok_final=51, latency_s=6.4
- tc-json-bfcl-170: tok_total=866, tok_final=44, latency_s=12.1
- tc-json-bfcl-171: tok_total=616, tok_final=75, latency_s=8.7
- tc-json-bfcl-172: tok_total=1391, tok_final=120, latency_s=19.3
- tc-json-bfcl-173: tok_total=414, tok_final=68, latency_s=5.9
- tc-json-bfcl-174: tok_total=897, tok_final=61, latency_s=12.5
- tc-json-bfcl-175: tok_total=1189, tok_final=92, latency_s=16.5
- tc-json-bfcl-176: tok_total=417, tok_final=52, latency_s=6.0
- tc-json-bfcl-177: tok_total=1632, tok_final=92, latency_s=22.6
- tc-json-bfcl-178: tok_total=1148, tok_final=85, latency_s=15.9
- tc-json-bfcl-179: tok_total=854, tok_final=63, latency_s=11.9
- tc-json-bfcl-180: tok_total=271, tok_final=59, latency_s=4.0
- tc-json-bfcl-181: tok_total=631, tok_final=117, latency_s=8.9
- tc-json-bfcl-182: tok_total=969, tok_final=83, latency_s=13.6
- tc-json-bfcl-183: tok_total=463, tok_final=60, latency_s=6.6
- tc-json-bfcl-184: tok_total=405, tok_final=195, latency_s=5.8
- tc-json-bfcl-185: tok_total=440, tok_final=175, latency_s=6.2
- tc-json-bfcl-186: tok_total=990, tok_final=49, latency_s=13.8
- tc-json-bfcl-187: tok_total=1245, tok_final=95, latency_s=17.3
- tc-json-bfcl-188: tok_total=464, tok_final=62, latency_s=6.6
- tc-json-bfcl-189: tok_total=1113, tok_final=62, latency_s=15.4
- tc-json-bfcl-190: tok_total=2183, tok_final=88, latency_s=30.2
- tc-json-bfcl-191: tok_total=487, tok_final=55, latency_s=6.9
- tc-json-bfcl-192: tok_total=559, tok_final=72, latency_s=7.9
- tc-json-bfcl-193: tok_total=637, tok_final=119, latency_s=9.0
- tc-json-bfcl-194: tok_total=1686, tok_final=80, latency_s=23.3
- tc-json-bfcl-195: tok_total=462, tok_final=93, latency_s=6.6
- tc-json-bfcl-196: tok_total=516, tok_final=73, latency_s=7.3
- tc-json-bfcl-197: tok_total=592, tok_final=216, latency_s=8.3
- tc-json-bfcl-198: tok_total=992, tok_final=68, latency_s=13.8
- tc-json-bfcl-199: tok_total=1423, tok_final=161, latency_s=19.7
- tc-json-bfcl-200: tok_total=511, tok_final=102, latency_s=7.2
- tc-json-bfcl-201: tok_total=1274, tok_final=109, latency_s=17.7
- tc-json-bfcl-202: tok_total=1694, tok_final=245, latency_s=23.4
- tc-json-bfcl-203: tok_total=1322, tok_final=79, latency_s=18.3
- tc-json-bfcl-204: tok_total=527, tok_final=68, latency_s=7.5
- tc-json-bfcl-205: tok_total=502, tok_final=83, latency_s=7.1
- tc-json-bfcl-206: tok_total=1381, tok_final=93, latency_s=19.1
- tc-json-bfcl-207: tok_total=480, tok_final=85, latency_s=6.9
- tc-json-bfcl-208: tok_total=666, tok_final=71, latency_s=9.4
- tc-json-bfcl-209: tok_total=711, tok_final=133, latency_s=10.0
- tc-json-bfcl-210: tok_total=677, tok_final=97, latency_s=9.5
- tc-json-bfcl-211: tok_total=916, tok_final=111, latency_s=12.7
- tc-json-bfcl-212: tok_total=917, tok_final=73, latency_s=12.8
- tc-json-bfcl-213: tok_total=1349, tok_final=89, latency_s=18.7
- tc-json-bfcl-214: tok_total=546, tok_final=87, latency_s=7.8
- tc-json-bfcl-215: tok_total=1827, tok_final=95, latency_s=25.3
- tc-json-bfcl-216: tok_total=605, tok_final=232, latency_s=8.5
- tc-json-bfcl-217: tok_total=262, tok_final=88, latency_s=3.8
- tc-json-bfcl-218: tok_total=985, tok_final=426, latency_s=13.6
- tc-json-bfcl-219: tok_total=546, tok_final=51, latency_s=7.7
- tc-json-bfcl-220: tok_total=1074, tok_final=67, latency_s=14.9
- tc-json-bfcl-221: tok_total=1177, tok_final=92, latency_s=16.4
- tc-json-bfcl-222: tok_total=1422, tok_final=95, latency_s=19.7
- tc-json-bfcl-223: tok_total=1515, tok_final=100, latency_s=21.0
- tc-json-bfcl-224: tok_total=1037, tok_final=81, latency_s=14.4
- tc-json-bfcl-225: tok_total=1067, tok_final=112, latency_s=14.8
- tc-json-bfcl-226: tok_total=514, tok_final=63, latency_s=7.3
- tc-json-bfcl-227: tok_total=1314, tok_final=61, latency_s=18.3
- tc-json-bfcl-228: tok_total=530, tok_final=53, latency_s=7.6
- tc-json-bfcl-229: tok_total=380, tok_final=64, latency_s=5.5
- tc-json-bfcl-230: tok_total=950, tok_final=59, latency_s=13.3
- tc-json-bfcl-231: tok_total=1376, tok_final=92, latency_s=19.1
- tc-json-bfcl-232: tok_total=296, tok_final=43, latency_s=4.4
- tc-json-bfcl-233: tok_total=1069, tok_final=71, latency_s=14.9
- tc-json-bfcl-234: tok_total=1422, tok_final=57, latency_s=19.8
- tc-json-bfcl-235: tok_total=459, tok_final=53, latency_s=6.6
- tc-json-bfcl-236: tok_total=815, tok_final=58, latency_s=11.4
- tc-json-bfcl-237: tok_total=1762, tok_final=75, latency_s=24.4
- tc-json-bfcl-238: tok_total=991, tok_final=80, latency_s=13.9
- tc-json-bfcl-239: tok_total=745, tok_final=86, latency_s=10.5
- tc-json-bfcl-240: tok_total=599, tok_final=109, latency_s=8.5
- tc-json-bfcl-241: tok_total=554, tok_final=97, latency_s=7.9
- tc-json-bfcl-242: tok_total=1326, tok_final=98, latency_s=18.5
- tc-json-bfcl-243: tok_total=430, tok_final=51, latency_s=6.2
- tc-json-bfcl-244: tok_total=220, tok_final=43, latency_s=3.3
- tc-json-bfcl-245: tok_total=1658, tok_final=81, latency_s=23.0
- tc-json-bfcl-246: tok_total=1956, tok_final=49, latency_s=27.0
- tc-json-bfcl-247: tok_total=422, tok_final=70, latency_s=6.1
- tc-json-bfcl-248: tok_total=1076, tok_final=79, latency_s=15.1
- tc-json-bfcl-249: tok_total=748, tok_final=137, latency_s=10.6
- tc-json-bfcl-250: tok_total=1324, tok_final=281, latency_s=18.4
- tc-json-bfcl-251: tok_total=624, tok_final=262, latency_s=8.8
- tc-json-bfcl-252: tok_total=1941, tok_final=148, latency_s=27.0
- tc-json-bfcl-253: tok_total=1775, tok_final=222, latency_s=24.6
- tc-json-bfcl-254: tok_total=1104, tok_final=133, latency_s=15.5
- tc-json-bfcl-255: tok_total=1743, tok_final=95, latency_s=24.2
- tc-json-bfcl-256: tok_total=558, tok_final=79, latency_s=8.0
- tc-json-bfcl-257: tok_total=1537, tok_final=93, latency_s=21.4
- tc-json-bfcl-258: tok_total=847, tok_final=240, latency_s=11.9
- tc-json-bfcl-259: tok_total=1638, tok_final=171, latency_s=22.8
- tc-json-bfcl-260: tok_total=263, tok_final=65, latency_s=3.9
- tc-json-bfcl-261: tok_total=1045, tok_final=65, latency_s=14.6
- tc-json-bfcl-262: tok_total=450, tok_final=149, latency_s=6.4
- tc-json-bfcl-263: tok_total=1572, tok_final=102, latency_s=21.8
- tc-json-bfcl-264: tok_total=1498, tok_final=75, latency_s=20.8
- tc-json-bfcl-265: tok_total=609, tok_final=85, latency_s=8.7
- tc-json-bfcl-266: tok_total=963, tok_final=62, latency_s=13.5
- tc-json-bfcl-267: tok_total=1304, tok_final=119, latency_s=18.1
- tc-json-bfcl-268: tok_total=1443, tok_final=138, latency_s=20.1
- tc-json-bfcl-269: tok_total=686, tok_final=181, latency_s=9.7
- tc-json-bfcl-270: tok_total=553, tok_final=219, latency_s=7.8
- tc-json-bfcl-271: tok_total=449, tok_final=67, latency_s=6.5
- tc-json-bfcl-272: tok_total=1602, tok_final=141, latency_s=22.2
- tc-json-bfcl-273: tok_total=1393, tok_final=72, latency_s=19.4
- tc-json-bfcl-274: tok_total=1246, tok_final=101, latency_s=17.4
- tc-json-bfcl-275: tok_total=1620, tok_final=74, latency_s=22.6
- tc-json-bfcl-276: tok_total=790, tok_final=68, latency_s=11.1
- tc-json-bfcl-277: tok_total=1084, tok_final=93, latency_s=15.3
- tc-json-bfcl-278: tok_total=2223, tok_final=132, latency_s=31.0
- tc-json-bfcl-279: tok_total=1150, tok_final=98, latency_s=16.2
- tc-json-bfcl-280: tok_total=1477, tok_final=112, latency_s=20.5
- tc-json-bfcl-281: tok_total=1440, tok_final=119, latency_s=20.2
- tc-json-bfcl-282: tok_total=1350, tok_final=96, latency_s=18.9
- tc-json-bfcl-283: tok_total=1603, tok_final=90, latency_s=22.3
- tc-json-bfcl-284: tok_total=1602, tok_final=107, latency_s=22.3
- tc-json-bfcl-285: tok_total=1464, tok_final=147, latency_s=20.4
- tc-json-bfcl-286: tok_total=1042, tok_final=73, latency_s=14.6
- tc-json-bfcl-287: tok_total=3287, tok_final=62, latency_s=45.5
- tc-json-bfcl-288: tok_total=1902, tok_final=109, latency_s=26.5
- tc-json-bfcl-289: tok_total=1470, tok_final=102, latency_s=20.5
- tc-json-bfcl-290: tok_total=1747, tok_final=235, latency_s=24.2
- tc-json-bfcl-291: tok_total=1875, tok_final=122, latency_s=26.0
- tc-json-bfcl-292: tok_total=1871, tok_final=151, latency_s=26.2
- tc-json-bfcl-293: tok_total=1245, tok_final=89, latency_s=17.4
- tc-json-bfcl-294: tok_total=1817, tok_final=101, latency_s=25.3
- tc-json-bfcl-295: tok_total=832, tok_final=129, latency_s=11.7
- tc-json-bfcl-296: tok_total=1240, tok_final=95, latency_s=17.3
- tc-json-bfcl-297: tok_total=1446, tok_final=101, latency_s=20.2
- tc-json-bfcl-298: tok_total=1210, tok_final=139, latency_s=17.0
- tc-json-bfcl-299: tok_total=1092, tok_final=86, latency_s=15.3
- tc-json-bfcl-300: tok_total=1722, tok_final=89, latency_s=24.0
- tc-json-fresh-001: tok_total=533, tok_final=62, latency_s=7.6
- tc-json-fresh-002: tok_total=723, tok_final=36, latency_s=10.2
- tc-json-fresh-003: tok_total=369, tok_final=36, latency_s=5.3
- tc-json-fresh-004: tok_total=662, tok_final=42, latency_s=9.4
- tc-json-fresh-005: tok_total=316, tok_final=40, latency_s=4.6
- tc-json-fresh-006: tok_total=363, tok_final=32, latency_s=5.2
- tc-json-fresh-007: tok_total=419, tok_final=33, latency_s=6.0
- tc-json-fresh-008: tok_total=700, tok_final=35, latency_s=9.9
- tc-json-fresh-009: tok_total=947, tok_final=35, latency_s=13.2
- tc-json-fresh-010: tok_total=1261, tok_final=81, latency_s=17.6
- tc-json-fresh-011: tok_total=434, tok_final=42, latency_s=6.2
- tc-json-fresh-012: tok_total=418, tok_final=51, latency_s=6.0
- tc-json-fresh-013: tok_total=89, tok_final=14, latency_s=1.5
- tc-json-fresh-014: tok_total=119, tok_final=14, latency_s=1.9
- tc-json-fresh-015: tok_total=181, tok_final=14, latency_s=2.8
- tc-json-fresh-016: tok_total=136, tok_final=14, latency_s=2.2
- tc-json-fresh-017: tok_total=184, tok_final=14, latency_s=2.9
- tc-json-fresh-018: tok_total=121, tok_final=14, latency_s=2.0
- tc-json-fresh-019: tok_total=1601, tok_final=94, latency_s=22.2
- tc-json-fresh-020: tok_total=1053, tok_final=50, latency_s=14.6
- tc-json-fresh-021: tok_total=235, tok_final=49, latency_s=3.5
- tc-json-fresh-022: tok_total=366, tok_final=31, latency_s=5.3
- tc-json-fresh-023: tok_total=1565, tok_final=57, latency_s=21.7
- tc-json-fresh-024: tok_total=1149, tok_final=48, latency_s=16.0
- tc-json-fresh-025: tok_total=406, tok_final=38, latency_s=5.8
- tc-json-fresh-026: tok_total=529, tok_final=26, latency_s=7.5
- tc-json-fresh-027: tok_total=411, tok_final=29, latency_s=5.9
- tc-json-fresh-028: tok_total=635, tok_final=52, latency_s=9.0
- tc-json-fresh-029: tok_total=1218, tok_final=14, latency_s=16.9
- tc-json-fresh-030: tok_total=1618, tok_final=72, latency_s=22.5

## tc_json_v1 per-item stratum/source/tools/calls
- tc-json-bfcl-001: stratum=bfcl_backbone, source=bfcl, n_tools=1, n_gold_calls=1
- tc-json-bfcl-002: stratum=bfcl_backbone, source=bfcl, n_tools=1, n_gold_calls=1
- tc-json-bfcl-003: stratum=bfcl_backbone, source=bfcl, n_tools=1, n_gold_calls=1
- tc-json-bfcl-004: stratum=bfcl_backbone, source=bfcl, n_tools=1, n_gold_calls=1
- tc-json-bfcl-005: stratum=bfcl_backbone, source=bfcl, n_tools=1, n_gold_calls=1
- tc-json-bfcl-006: stratum=bfcl_backbone, source=bfcl, n_tools=1, n_gold_calls=1
- tc-json-bfcl-007: stratum=bfcl_backbone, source=bfcl, n_tools=1, n_gold_calls=1
- tc-json-bfcl-008: stratum=bfcl_backbone, source=bfcl, n_tools=1, n_gold_calls=1
- tc-json-bfcl-009: stratum=bfcl_backbone, source=bfcl, n_tools=1, n_gold_calls=1
- tc-json-bfcl-010: stratum=bfcl_backbone, source=bfcl, n_tools=1, n_gold_calls=1
- tc-json-bfcl-011: stratum=bfcl_backbone, source=bfcl, n_tools=1, n_gold_calls=1
- tc-json-bfcl-012: stratum=bfcl_backbone, source=bfcl, n_tools=1, n_gold_calls=1
- tc-json-bfcl-013: stratum=bfcl_backbone, source=bfcl, n_tools=1, n_gold_calls=1
- tc-json-bfcl-014: stratum=bfcl_backbone, source=bfcl, n_tools=1, n_gold_calls=1
- tc-json-bfcl-015: stratum=bfcl_backbone, source=bfcl, n_tools=1, n_gold_calls=1
- tc-json-bfcl-016: stratum=bfcl_backbone, source=bfcl, n_tools=1, n_gold_calls=1
- tc-json-bfcl-017: stratum=bfcl_backbone, source=bfcl, n_tools=1, n_gold_calls=1
- tc-json-bfcl-018: stratum=bfcl_backbone, source=bfcl, n_tools=1, n_gold_calls=1
- tc-json-bfcl-019: stratum=bfcl_backbone, source=bfcl, n_tools=1, n_gold_calls=1
- tc-json-bfcl-020: stratum=bfcl_backbone, source=bfcl, n_tools=1, n_gold_calls=1
- tc-json-bfcl-021: stratum=bfcl_backbone, source=bfcl, n_tools=1, n_gold_calls=1
- tc-json-bfcl-022: stratum=bfcl_backbone, source=bfcl, n_tools=1, n_gold_calls=1
- tc-json-bfcl-023: stratum=bfcl_backbone, source=bfcl, n_tools=1, n_gold_calls=1
- tc-json-bfcl-024: stratum=bfcl_backbone, source=bfcl, n_tools=1, n_gold_calls=1
- tc-json-bfcl-025: stratum=bfcl_backbone, source=bfcl, n_tools=1, n_gold_calls=1
- tc-json-bfcl-026: stratum=bfcl_backbone, source=bfcl, n_tools=1, n_gold_calls=1
- tc-json-bfcl-027: stratum=bfcl_backbone, source=bfcl, n_tools=1, n_gold_calls=1
- tc-json-bfcl-028: stratum=bfcl_backbone, source=bfcl, n_tools=1, n_gold_calls=1
- tc-json-bfcl-029: stratum=bfcl_backbone, source=bfcl, n_tools=1, n_gold_calls=1
- tc-json-bfcl-030: stratum=bfcl_backbone, source=bfcl, n_tools=1, n_gold_calls=1
- tc-json-bfcl-031: stratum=bfcl_backbone, source=bfcl, n_tools=1, n_gold_calls=1
- tc-json-bfcl-032: stratum=bfcl_backbone, source=bfcl, n_tools=1, n_gold_calls=1
- tc-json-bfcl-033: stratum=bfcl_backbone, source=bfcl, n_tools=1, n_gold_calls=1
- tc-json-bfcl-034: stratum=bfcl_backbone, source=bfcl, n_tools=1, n_gold_calls=1
- tc-json-bfcl-035: stratum=bfcl_backbone, source=bfcl, n_tools=1, n_gold_calls=1
- tc-json-bfcl-036: stratum=bfcl_backbone, source=bfcl, n_tools=1, n_gold_calls=1
- tc-json-bfcl-037: stratum=bfcl_backbone, source=bfcl, n_tools=1, n_gold_calls=1
- tc-json-bfcl-038: stratum=bfcl_backbone, source=bfcl, n_tools=1, n_gold_calls=1
- tc-json-bfcl-039: stratum=bfcl_backbone, source=bfcl, n_tools=1, n_gold_calls=1
- tc-json-bfcl-040: stratum=bfcl_backbone, source=bfcl, n_tools=1, n_gold_calls=1
- tc-json-bfcl-041: stratum=bfcl_backbone, source=bfcl, n_tools=1, n_gold_calls=1
- tc-json-bfcl-042: stratum=bfcl_backbone, source=bfcl, n_tools=1, n_gold_calls=1
- tc-json-bfcl-043: stratum=bfcl_backbone, source=bfcl, n_tools=1, n_gold_calls=1
- tc-json-bfcl-044: stratum=bfcl_backbone, source=bfcl, n_tools=1, n_gold_calls=1
- tc-json-bfcl-045: stratum=bfcl_backbone, source=bfcl, n_tools=1, n_gold_calls=1
- tc-json-bfcl-046: stratum=bfcl_backbone, source=bfcl, n_tools=1, n_gold_calls=1
- tc-json-bfcl-047: stratum=bfcl_backbone, source=bfcl, n_tools=1, n_gold_calls=1
- tc-json-bfcl-048: stratum=bfcl_backbone, source=bfcl, n_tools=1, n_gold_calls=1
- tc-json-bfcl-049: stratum=bfcl_backbone, source=bfcl, n_tools=1, n_gold_calls=1
- tc-json-bfcl-050: stratum=bfcl_backbone, source=bfcl, n_tools=1, n_gold_calls=1
- tc-json-bfcl-051: stratum=bfcl_backbone, source=bfcl, n_tools=1, n_gold_calls=1
- tc-json-bfcl-052: stratum=bfcl_backbone, source=bfcl, n_tools=1, n_gold_calls=1
- tc-json-bfcl-053: stratum=bfcl_backbone, source=bfcl, n_tools=1, n_gold_calls=1
- tc-json-bfcl-054: stratum=bfcl_backbone, source=bfcl, n_tools=1, n_gold_calls=1
- tc-json-bfcl-055: stratum=bfcl_backbone, source=bfcl, n_tools=1, n_gold_calls=1
- tc-json-bfcl-056: stratum=bfcl_backbone, source=bfcl, n_tools=1, n_gold_calls=1
- tc-json-bfcl-057: stratum=bfcl_backbone, source=bfcl, n_tools=1, n_gold_calls=1
- tc-json-bfcl-058: stratum=bfcl_backbone, source=bfcl, n_tools=1, n_gold_calls=1
- tc-json-bfcl-059: stratum=bfcl_backbone, source=bfcl, n_tools=1, n_gold_calls=1
- tc-json-bfcl-060: stratum=bfcl_backbone, source=bfcl, n_tools=1, n_gold_calls=1
- tc-json-bfcl-061: stratum=bfcl_backbone, source=bfcl, n_tools=1, n_gold_calls=1
- tc-json-bfcl-062: stratum=bfcl_backbone, source=bfcl, n_tools=1, n_gold_calls=1
- tc-json-bfcl-063: stratum=bfcl_backbone, source=bfcl, n_tools=1, n_gold_calls=1
- tc-json-bfcl-064: stratum=bfcl_backbone, source=bfcl, n_tools=1, n_gold_calls=1
- tc-json-bfcl-065: stratum=bfcl_backbone, source=bfcl, n_tools=1, n_gold_calls=1
- tc-json-bfcl-066: stratum=bfcl_backbone, source=bfcl, n_tools=1, n_gold_calls=1
- tc-json-bfcl-067: stratum=bfcl_backbone, source=bfcl, n_tools=1, n_gold_calls=1
- tc-json-bfcl-068: stratum=bfcl_backbone, source=bfcl, n_tools=1, n_gold_calls=1
- tc-json-bfcl-069: stratum=bfcl_backbone, source=bfcl, n_tools=1, n_gold_calls=1
- tc-json-bfcl-070: stratum=bfcl_backbone, source=bfcl, n_tools=1, n_gold_calls=1
- tc-json-bfcl-071: stratum=bfcl_backbone, source=bfcl, n_tools=1, n_gold_calls=1
- tc-json-bfcl-072: stratum=bfcl_backbone, source=bfcl, n_tools=1, n_gold_calls=1
- tc-json-bfcl-073: stratum=bfcl_backbone, source=bfcl, n_tools=1, n_gold_calls=1
- tc-json-bfcl-074: stratum=bfcl_backbone, source=bfcl, n_tools=1, n_gold_calls=1
- tc-json-bfcl-075: stratum=bfcl_backbone, source=bfcl, n_tools=1, n_gold_calls=1
- tc-json-bfcl-076: stratum=bfcl_backbone, source=bfcl, n_tools=2, n_gold_calls=1
- tc-json-bfcl-077: stratum=bfcl_backbone, source=bfcl, n_tools=2, n_gold_calls=1
- tc-json-bfcl-078: stratum=bfcl_backbone, source=bfcl, n_tools=3, n_gold_calls=1
- tc-json-bfcl-079: stratum=bfcl_backbone, source=bfcl, n_tools=2, n_gold_calls=1
- tc-json-bfcl-080: stratum=bfcl_backbone, source=bfcl, n_tools=3, n_gold_calls=1
- tc-json-bfcl-081: stratum=bfcl_backbone, source=bfcl, n_tools=2, n_gold_calls=1
- tc-json-bfcl-082: stratum=bfcl_backbone, source=bfcl, n_tools=3, n_gold_calls=1
- tc-json-bfcl-083: stratum=bfcl_backbone, source=bfcl, n_tools=3, n_gold_calls=1
- tc-json-bfcl-084: stratum=bfcl_backbone, source=bfcl, n_tools=3, n_gold_calls=1
- tc-json-bfcl-085: stratum=bfcl_backbone, source=bfcl, n_tools=2, n_gold_calls=1
- tc-json-bfcl-086: stratum=bfcl_backbone, source=bfcl, n_tools=2, n_gold_calls=1
- tc-json-bfcl-087: stratum=bfcl_backbone, source=bfcl, n_tools=3, n_gold_calls=1
- tc-json-bfcl-088: stratum=bfcl_backbone, source=bfcl, n_tools=2, n_gold_calls=1
- tc-json-bfcl-089: stratum=bfcl_backbone, source=bfcl, n_tools=2, n_gold_calls=1
- tc-json-bfcl-090: stratum=bfcl_backbone, source=bfcl, n_tools=2, n_gold_calls=1
- tc-json-bfcl-091: stratum=bfcl_backbone, source=bfcl, n_tools=2, n_gold_calls=1
- tc-json-bfcl-092: stratum=bfcl_backbone, source=bfcl, n_tools=3, n_gold_calls=1
- tc-json-bfcl-093: stratum=bfcl_backbone, source=bfcl, n_tools=3, n_gold_calls=1
- tc-json-bfcl-094: stratum=bfcl_backbone, source=bfcl, n_tools=2, n_gold_calls=1
- tc-json-bfcl-095: stratum=bfcl_backbone, source=bfcl, n_tools=3, n_gold_calls=1
- tc-json-bfcl-096: stratum=bfcl_backbone, source=bfcl, n_tools=2, n_gold_calls=1
- tc-json-bfcl-097: stratum=bfcl_backbone, source=bfcl, n_tools=3, n_gold_calls=1
- tc-json-bfcl-098: stratum=bfcl_backbone, source=bfcl, n_tools=2, n_gold_calls=1
- tc-json-bfcl-099: stratum=bfcl_backbone, source=bfcl, n_tools=2, n_gold_calls=1
- tc-json-bfcl-100: stratum=bfcl_backbone, source=bfcl, n_tools=3, n_gold_calls=1
- tc-json-bfcl-101: stratum=bfcl_backbone, source=bfcl, n_tools=3, n_gold_calls=1
- tc-json-bfcl-102: stratum=bfcl_backbone, source=bfcl, n_tools=3, n_gold_calls=1
- tc-json-bfcl-103: stratum=bfcl_backbone, source=bfcl, n_tools=2, n_gold_calls=1
- tc-json-bfcl-104: stratum=bfcl_backbone, source=bfcl, n_tools=3, n_gold_calls=1
- tc-json-bfcl-105: stratum=bfcl_backbone, source=bfcl, n_tools=2, n_gold_calls=1
- tc-json-bfcl-106: stratum=bfcl_backbone, source=bfcl, n_tools=2, n_gold_calls=1
- tc-json-bfcl-107: stratum=bfcl_backbone, source=bfcl, n_tools=3, n_gold_calls=1
- tc-json-bfcl-108: stratum=bfcl_backbone, source=bfcl, n_tools=2, n_gold_calls=1
- tc-json-bfcl-109: stratum=bfcl_backbone, source=bfcl, n_tools=3, n_gold_calls=1
- tc-json-bfcl-110: stratum=bfcl_backbone, source=bfcl, n_tools=2, n_gold_calls=1
- tc-json-bfcl-111: stratum=bfcl_backbone, source=bfcl, n_tools=3, n_gold_calls=1
- tc-json-bfcl-112: stratum=bfcl_backbone, source=bfcl, n_tools=2, n_gold_calls=1
- tc-json-bfcl-113: stratum=bfcl_backbone, source=bfcl, n_tools=2, n_gold_calls=1
- tc-json-bfcl-114: stratum=bfcl_backbone, source=bfcl, n_tools=3, n_gold_calls=1
- tc-json-bfcl-115: stratum=bfcl_backbone, source=bfcl, n_tools=3, n_gold_calls=1
- tc-json-bfcl-116: stratum=bfcl_backbone, source=bfcl, n_tools=2, n_gold_calls=1
- tc-json-bfcl-117: stratum=bfcl_backbone, source=bfcl, n_tools=2, n_gold_calls=1
- tc-json-bfcl-118: stratum=bfcl_backbone, source=bfcl, n_tools=4, n_gold_calls=1
- tc-json-bfcl-119: stratum=bfcl_backbone, source=bfcl, n_tools=2, n_gold_calls=1
- tc-json-bfcl-120: stratum=bfcl_backbone, source=bfcl, n_tools=3, n_gold_calls=1
- tc-json-bfcl-121: stratum=bfcl_backbone, source=bfcl, n_tools=3, n_gold_calls=1
- tc-json-bfcl-122: stratum=bfcl_backbone, source=bfcl, n_tools=3, n_gold_calls=1
- tc-json-bfcl-123: stratum=bfcl_backbone, source=bfcl, n_tools=3, n_gold_calls=1
- tc-json-bfcl-124: stratum=bfcl_backbone, source=bfcl, n_tools=2, n_gold_calls=1
- tc-json-bfcl-125: stratum=bfcl_backbone, source=bfcl, n_tools=3, n_gold_calls=1
- tc-json-bfcl-126: stratum=bfcl_backbone, source=bfcl, n_tools=4, n_gold_calls=1
- tc-json-bfcl-127: stratum=bfcl_backbone, source=bfcl, n_tools=3, n_gold_calls=1
- tc-json-bfcl-128: stratum=bfcl_backbone, source=bfcl, n_tools=2, n_gold_calls=1
- tc-json-bfcl-129: stratum=bfcl_backbone, source=bfcl, n_tools=4, n_gold_calls=1
- tc-json-bfcl-130: stratum=bfcl_backbone, source=bfcl, n_tools=3, n_gold_calls=1
- tc-json-bfcl-131: stratum=bfcl_backbone, source=bfcl, n_tools=2, n_gold_calls=1
- tc-json-bfcl-132: stratum=bfcl_backbone, source=bfcl, n_tools=3, n_gold_calls=1
- tc-json-bfcl-133: stratum=bfcl_backbone, source=bfcl, n_tools=3, n_gold_calls=1
- tc-json-bfcl-134: stratum=bfcl_backbone, source=bfcl, n_tools=3, n_gold_calls=1
- tc-json-bfcl-135: stratum=bfcl_backbone, source=bfcl, n_tools=3, n_gold_calls=1
- tc-json-bfcl-136: stratum=bfcl_backbone, source=bfcl, n_tools=3, n_gold_calls=1
- tc-json-bfcl-137: stratum=bfcl_backbone, source=bfcl, n_tools=4, n_gold_calls=1
- tc-json-bfcl-138: stratum=bfcl_backbone, source=bfcl, n_tools=3, n_gold_calls=1
- tc-json-bfcl-139: stratum=bfcl_backbone, source=bfcl, n_tools=2, n_gold_calls=1
- tc-json-bfcl-140: stratum=bfcl_backbone, source=bfcl, n_tools=4, n_gold_calls=1
- tc-json-bfcl-141: stratum=bfcl_backbone, source=bfcl, n_tools=4, n_gold_calls=1
- tc-json-bfcl-142: stratum=bfcl_backbone, source=bfcl, n_tools=3, n_gold_calls=1
- tc-json-bfcl-143: stratum=bfcl_backbone, source=bfcl, n_tools=4, n_gold_calls=1
- tc-json-bfcl-144: stratum=bfcl_backbone, source=bfcl, n_tools=3, n_gold_calls=1
- tc-json-bfcl-145: stratum=bfcl_backbone, source=bfcl, n_tools=2, n_gold_calls=1
- tc-json-bfcl-146: stratum=bfcl_backbone, source=bfcl, n_tools=4, n_gold_calls=1
- tc-json-bfcl-147: stratum=bfcl_backbone, source=bfcl, n_tools=4, n_gold_calls=1
- tc-json-bfcl-148: stratum=bfcl_backbone, source=bfcl, n_tools=4, n_gold_calls=1
- tc-json-bfcl-149: stratum=bfcl_backbone, source=bfcl, n_tools=4, n_gold_calls=1
- tc-json-bfcl-150: stratum=bfcl_backbone, source=bfcl, n_tools=2, n_gold_calls=1
- tc-json-bfcl-151: stratum=bfcl_backbone, source=bfcl, n_tools=1, n_gold_calls=2
- tc-json-bfcl-152: stratum=bfcl_backbone, source=bfcl, n_tools=1, n_gold_calls=3
- tc-json-bfcl-153: stratum=bfcl_backbone, source=bfcl, n_tools=1, n_gold_calls=2
- tc-json-bfcl-154: stratum=bfcl_backbone, source=bfcl, n_tools=1, n_gold_calls=4
- tc-json-bfcl-155: stratum=bfcl_backbone, source=bfcl, n_tools=1, n_gold_calls=2
- tc-json-bfcl-156: stratum=bfcl_backbone, source=bfcl, n_tools=1, n_gold_calls=2
- tc-json-bfcl-157: stratum=bfcl_backbone, source=bfcl, n_tools=1, n_gold_calls=2
- tc-json-bfcl-158: stratum=bfcl_backbone, source=bfcl, n_tools=1, n_gold_calls=3
- tc-json-bfcl-159: stratum=bfcl_backbone, source=bfcl, n_tools=1, n_gold_calls=4
- tc-json-bfcl-160: stratum=bfcl_backbone, source=bfcl, n_tools=1, n_gold_calls=2
- tc-json-bfcl-161: stratum=bfcl_backbone, source=bfcl, n_tools=1, n_gold_calls=2
- tc-json-bfcl-162: stratum=bfcl_backbone, source=bfcl, n_tools=1, n_gold_calls=2
- tc-json-bfcl-163: stratum=bfcl_backbone, source=bfcl, n_tools=1, n_gold_calls=2
- tc-json-bfcl-164: stratum=bfcl_backbone, source=bfcl, n_tools=1, n_gold_calls=2
- tc-json-bfcl-165: stratum=bfcl_backbone, source=bfcl, n_tools=1, n_gold_calls=2
- tc-json-bfcl-166: stratum=bfcl_backbone, source=bfcl, n_tools=1, n_gold_calls=2
- tc-json-bfcl-167: stratum=bfcl_backbone, source=bfcl, n_tools=1, n_gold_calls=4
- tc-json-bfcl-168: stratum=bfcl_backbone, source=bfcl, n_tools=1, n_gold_calls=4
- tc-json-bfcl-169: stratum=bfcl_backbone, source=bfcl, n_tools=1, n_gold_calls=2
- tc-json-bfcl-170: stratum=bfcl_backbone, source=bfcl, n_tools=1, n_gold_calls=2
- tc-json-bfcl-171: stratum=bfcl_backbone, source=bfcl, n_tools=1, n_gold_calls=2
- tc-json-bfcl-172: stratum=bfcl_backbone, source=bfcl, n_tools=1, n_gold_calls=2
- tc-json-bfcl-173: stratum=bfcl_backbone, source=bfcl, n_tools=1, n_gold_calls=2
- tc-json-bfcl-174: stratum=bfcl_backbone, source=bfcl, n_tools=1, n_gold_calls=2
- tc-json-bfcl-175: stratum=bfcl_backbone, source=bfcl, n_tools=1, n_gold_calls=4
- tc-json-bfcl-176: stratum=bfcl_backbone, source=bfcl, n_tools=1, n_gold_calls=2
- tc-json-bfcl-177: stratum=bfcl_backbone, source=bfcl, n_tools=1, n_gold_calls=4
- tc-json-bfcl-178: stratum=bfcl_backbone, source=bfcl, n_tools=1, n_gold_calls=2
- tc-json-bfcl-179: stratum=bfcl_backbone, source=bfcl, n_tools=1, n_gold_calls=3
- tc-json-bfcl-180: stratum=bfcl_backbone, source=bfcl, n_tools=1, n_gold_calls=2
- tc-json-bfcl-181: stratum=bfcl_backbone, source=bfcl, n_tools=1, n_gold_calls=4
- tc-json-bfcl-182: stratum=bfcl_backbone, source=bfcl, n_tools=1, n_gold_calls=3
- tc-json-bfcl-183: stratum=bfcl_backbone, source=bfcl, n_tools=1, n_gold_calls=2
- tc-json-bfcl-184: stratum=bfcl_backbone, source=bfcl, n_tools=1, n_gold_calls=3
- tc-json-bfcl-185: stratum=bfcl_backbone, source=bfcl, n_tools=1, n_gold_calls=3
- tc-json-bfcl-186: stratum=bfcl_backbone, source=bfcl, n_tools=1, n_gold_calls=2
- tc-json-bfcl-187: stratum=bfcl_backbone, source=bfcl, n_tools=1, n_gold_calls=2
- tc-json-bfcl-188: stratum=bfcl_backbone, source=bfcl, n_tools=1, n_gold_calls=4
- tc-json-bfcl-189: stratum=bfcl_backbone, source=bfcl, n_tools=1, n_gold_calls=2
- tc-json-bfcl-190: stratum=bfcl_backbone, source=bfcl, n_tools=1, n_gold_calls=3
- tc-json-bfcl-191: stratum=bfcl_backbone, source=bfcl, n_tools=1, n_gold_calls=2
- tc-json-bfcl-192: stratum=bfcl_backbone, source=bfcl, n_tools=1, n_gold_calls=2
- tc-json-bfcl-193: stratum=bfcl_backbone, source=bfcl, n_tools=1, n_gold_calls=4
- tc-json-bfcl-194: stratum=bfcl_backbone, source=bfcl, n_tools=1, n_gold_calls=3
- tc-json-bfcl-195: stratum=bfcl_backbone, source=bfcl, n_tools=1, n_gold_calls=3
- tc-json-bfcl-196: stratum=bfcl_backbone, source=bfcl, n_tools=1, n_gold_calls=2
- tc-json-bfcl-197: stratum=bfcl_backbone, source=bfcl, n_tools=1, n_gold_calls=4
- tc-json-bfcl-198: stratum=bfcl_backbone, source=bfcl, n_tools=1, n_gold_calls=2
- tc-json-bfcl-199: stratum=bfcl_backbone, source=bfcl, n_tools=1, n_gold_calls=2
- tc-json-bfcl-200: stratum=bfcl_backbone, source=bfcl, n_tools=1, n_gold_calls=4
- tc-json-bfcl-201: stratum=bfcl_backbone, source=bfcl, n_tools=1, n_gold_calls=4
- tc-json-bfcl-202: stratum=bfcl_backbone, source=bfcl, n_tools=1, n_gold_calls=8
- tc-json-bfcl-203: stratum=bfcl_backbone, source=bfcl, n_tools=1, n_gold_calls=2
- tc-json-bfcl-204: stratum=bfcl_backbone, source=bfcl, n_tools=1, n_gold_calls=3
- tc-json-bfcl-205: stratum=bfcl_backbone, source=bfcl, n_tools=1, n_gold_calls=3
- tc-json-bfcl-206: stratum=bfcl_backbone, source=bfcl, n_tools=1, n_gold_calls=3
- tc-json-bfcl-207: stratum=bfcl_backbone, source=bfcl, n_tools=1, n_gold_calls=3
- tc-json-bfcl-208: stratum=bfcl_backbone, source=bfcl, n_tools=1, n_gold_calls=2
- tc-json-bfcl-209: stratum=bfcl_backbone, source=bfcl, n_tools=1, n_gold_calls=4
- tc-json-bfcl-210: stratum=bfcl_backbone, source=bfcl, n_tools=1, n_gold_calls=3
- tc-json-bfcl-211: stratum=bfcl_backbone, source=bfcl, n_tools=1, n_gold_calls=3
- tc-json-bfcl-212: stratum=bfcl_backbone, source=bfcl, n_tools=1, n_gold_calls=2
- tc-json-bfcl-213: stratum=bfcl_backbone, source=bfcl, n_tools=1, n_gold_calls=2
- tc-json-bfcl-214: stratum=bfcl_backbone, source=bfcl, n_tools=1, n_gold_calls=2
- tc-json-bfcl-215: stratum=bfcl_backbone, source=bfcl, n_tools=1, n_gold_calls=2
- tc-json-bfcl-216: stratum=bfcl_backbone, source=bfcl, n_tools=1, n_gold_calls=3
- tc-json-bfcl-217: stratum=bfcl_backbone, source=bfcl, n_tools=1, n_gold_calls=4
- tc-json-bfcl-218: stratum=bfcl_backbone, source=bfcl, n_tools=1, n_gold_calls=8
- tc-json-bfcl-219: stratum=bfcl_backbone, source=bfcl, n_tools=1, n_gold_calls=3
- tc-json-bfcl-220: stratum=bfcl_backbone, source=bfcl, n_tools=1, n_gold_calls=2
- tc-json-bfcl-221: stratum=bfcl_backbone, source=bfcl, n_tools=1, n_gold_calls=3
- tc-json-bfcl-222: stratum=bfcl_backbone, source=bfcl, n_tools=1, n_gold_calls=3
- tc-json-bfcl-223: stratum=bfcl_backbone, source=bfcl, n_tools=1, n_gold_calls=3
- tc-json-bfcl-224: stratum=bfcl_backbone, source=bfcl, n_tools=1, n_gold_calls=2
- tc-json-bfcl-225: stratum=bfcl_backbone, source=bfcl, n_tools=1, n_gold_calls=4
- tc-json-bfcl-226: stratum=bfcl_backbone, source=bfcl, n_tools=2, n_gold_calls=2
- tc-json-bfcl-227: stratum=bfcl_backbone, source=bfcl, n_tools=2, n_gold_calls=2
- tc-json-bfcl-228: stratum=bfcl_backbone, source=bfcl, n_tools=3, n_gold_calls=2
- tc-json-bfcl-229: stratum=bfcl_backbone, source=bfcl, n_tools=2, n_gold_calls=2
- tc-json-bfcl-230: stratum=bfcl_backbone, source=bfcl, n_tools=2, n_gold_calls=2
- tc-json-bfcl-231: stratum=bfcl_backbone, source=bfcl, n_tools=2, n_gold_calls=2
- tc-json-bfcl-232: stratum=bfcl_backbone, source=bfcl, n_tools=3, n_gold_calls=2
- tc-json-bfcl-233: stratum=bfcl_backbone, source=bfcl, n_tools=2, n_gold_calls=2
- tc-json-bfcl-234: stratum=bfcl_backbone, source=bfcl, n_tools=2, n_gold_calls=2
- tc-json-bfcl-235: stratum=bfcl_backbone, source=bfcl, n_tools=2, n_gold_calls=2
- tc-json-bfcl-236: stratum=bfcl_backbone, source=bfcl, n_tools=2, n_gold_calls=2
- tc-json-bfcl-237: stratum=bfcl_backbone, source=bfcl, n_tools=2, n_gold_calls=2
- tc-json-bfcl-238: stratum=bfcl_backbone, source=bfcl, n_tools=3, n_gold_calls=3
- tc-json-bfcl-239: stratum=bfcl_backbone, source=bfcl, n_tools=2, n_gold_calls=4
- tc-json-bfcl-240: stratum=bfcl_backbone, source=bfcl, n_tools=2, n_gold_calls=2
- tc-json-bfcl-241: stratum=bfcl_backbone, source=bfcl, n_tools=3, n_gold_calls=4
- tc-json-bfcl-242: stratum=bfcl_backbone, source=bfcl, n_tools=3, n_gold_calls=3
- tc-json-bfcl-243: stratum=bfcl_backbone, source=bfcl, n_tools=2, n_gold_calls=2
- tc-json-bfcl-244: stratum=bfcl_backbone, source=bfcl, n_tools=2, n_gold_calls=2
- tc-json-bfcl-245: stratum=bfcl_backbone, source=bfcl, n_tools=2, n_gold_calls=2
- tc-json-bfcl-246: stratum=bfcl_backbone, source=bfcl, n_tools=3, n_gold_calls=2
- tc-json-bfcl-247: stratum=bfcl_backbone, source=bfcl, n_tools=2, n_gold_calls=3
- tc-json-bfcl-248: stratum=bfcl_backbone, source=bfcl, n_tools=2, n_gold_calls=2
- tc-json-bfcl-249: stratum=bfcl_backbone, source=bfcl, n_tools=2, n_gold_calls=4
- tc-json-bfcl-250: stratum=bfcl_backbone, source=bfcl, n_tools=2, n_gold_calls=4
- tc-json-bfcl-251: stratum=bfcl_backbone, source=bfcl, n_tools=3, n_gold_calls=3
- tc-json-bfcl-252: stratum=bfcl_backbone, source=bfcl, n_tools=3, n_gold_calls=4
- tc-json-bfcl-253: stratum=bfcl_backbone, source=bfcl, n_tools=2, n_gold_calls=4
- tc-json-bfcl-254: stratum=bfcl_backbone, source=bfcl, n_tools=3, n_gold_calls=3
- tc-json-bfcl-255: stratum=bfcl_backbone, source=bfcl, n_tools=3, n_gold_calls=4
- tc-json-bfcl-256: stratum=bfcl_backbone, source=bfcl, n_tools=3, n_gold_calls=3
- tc-json-bfcl-257: stratum=bfcl_backbone, source=bfcl, n_tools=2, n_gold_calls=3
- tc-json-bfcl-258: stratum=bfcl_backbone, source=bfcl, n_tools=2, n_gold_calls=4
- tc-json-bfcl-259: stratum=bfcl_backbone, source=bfcl, n_tools=3, n_gold_calls=3
- tc-json-bfcl-260: stratum=bfcl_backbone, source=bfcl, n_tools=2, n_gold_calls=2
- tc-json-bfcl-261: stratum=bfcl_backbone, source=bfcl, n_tools=2, n_gold_calls=2
- tc-json-bfcl-262: stratum=bfcl_backbone, source=bfcl, n_tools=2, n_gold_calls=2
- tc-json-bfcl-263: stratum=bfcl_backbone, source=bfcl, n_tools=2, n_gold_calls=4
- tc-json-bfcl-264: stratum=bfcl_backbone, source=bfcl, n_tools=2, n_gold_calls=2
- tc-json-bfcl-265: stratum=bfcl_backbone, source=bfcl, n_tools=3, n_gold_calls=4
- tc-json-bfcl-266: stratum=bfcl_backbone, source=bfcl, n_tools=3, n_gold_calls=3
- tc-json-bfcl-267: stratum=bfcl_backbone, source=bfcl, n_tools=2, n_gold_calls=4
- tc-json-bfcl-268: stratum=bfcl_backbone, source=bfcl, n_tools=2, n_gold_calls=4
- tc-json-bfcl-269: stratum=bfcl_backbone, source=bfcl, n_tools=3, n_gold_calls=3
- tc-json-bfcl-270: stratum=bfcl_backbone, source=bfcl, n_tools=2, n_gold_calls=4
- tc-json-bfcl-271: stratum=bfcl_backbone, source=bfcl, n_tools=2, n_gold_calls=2
- tc-json-bfcl-272: stratum=bfcl_backbone, source=bfcl, n_tools=2, n_gold_calls=4
- tc-json-bfcl-273: stratum=bfcl_backbone, source=bfcl, n_tools=2, n_gold_calls=2
- tc-json-bfcl-274: stratum=bfcl_backbone, source=bfcl, n_tools=3, n_gold_calls=3
- tc-json-bfcl-275: stratum=bfcl_backbone, source=bfcl, n_tools=2, n_gold_calls=2
- tc-json-bfcl-276: stratum=bfcl_backbone, source=bfcl, n_tools=2, n_gold_calls=2
- tc-json-bfcl-277: stratum=bfcl_backbone, source=bfcl, n_tools=4, n_gold_calls=4
- tc-json-bfcl-278: stratum=bfcl_backbone, source=bfcl, n_tools=4, n_gold_calls=4
- tc-json-bfcl-279: stratum=bfcl_backbone, source=bfcl, n_tools=3, n_gold_calls=3
- tc-json-bfcl-280: stratum=bfcl_backbone, source=bfcl, n_tools=2, n_gold_calls=4
- tc-json-bfcl-281: stratum=bfcl_backbone, source=bfcl, n_tools=4, n_gold_calls=4
- tc-json-bfcl-282: stratum=bfcl_backbone, source=bfcl, n_tools=3, n_gold_calls=3
- tc-json-bfcl-283: stratum=bfcl_backbone, source=bfcl, n_tools=3, n_gold_calls=3
- tc-json-bfcl-284: stratum=bfcl_backbone, source=bfcl, n_tools=3, n_gold_calls=4
- tc-json-bfcl-285: stratum=bfcl_backbone, source=bfcl, n_tools=3, n_gold_calls=4
- tc-json-bfcl-286: stratum=bfcl_backbone, source=bfcl, n_tools=2, n_gold_calls=2
- tc-json-bfcl-287: stratum=bfcl_backbone, source=bfcl, n_tools=2, n_gold_calls=2
- tc-json-bfcl-288: stratum=bfcl_backbone, source=bfcl, n_tools=3, n_gold_calls=3
- tc-json-bfcl-289: stratum=bfcl_backbone, source=bfcl, n_tools=2, n_gold_calls=2
- tc-json-bfcl-290: stratum=bfcl_backbone, source=bfcl, n_tools=2, n_gold_calls=4
- tc-json-bfcl-291: stratum=bfcl_backbone, source=bfcl, n_tools=2, n_gold_calls=4
- tc-json-bfcl-292: stratum=bfcl_backbone, source=bfcl, n_tools=4, n_gold_calls=4
- tc-json-bfcl-293: stratum=bfcl_backbone, source=bfcl, n_tools=3, n_gold_calls=3
- tc-json-bfcl-294: stratum=bfcl_backbone, source=bfcl, n_tools=3, n_gold_calls=3
- tc-json-bfcl-295: stratum=bfcl_backbone, source=bfcl, n_tools=2, n_gold_calls=4
- tc-json-bfcl-296: stratum=bfcl_backbone, source=bfcl, n_tools=3, n_gold_calls=3
- tc-json-bfcl-297: stratum=bfcl_backbone, source=bfcl, n_tools=3, n_gold_calls=3
- tc-json-bfcl-298: stratum=bfcl_backbone, source=bfcl, n_tools=4, n_gold_calls=4
- tc-json-bfcl-299: stratum=bfcl_backbone, source=bfcl, n_tools=3, n_gold_calls=3
- tc-json-bfcl-300: stratum=bfcl_backbone, source=bfcl, n_tools=2, n_gold_calls=3
- tc-json-fresh-001: stratum=fresh_common_tools, source=hand-authored, n_tools=2, n_gold_calls=1
- tc-json-fresh-002: stratum=fresh_common_tools, source=hand-authored, n_tools=2, n_gold_calls=1
- tc-json-fresh-003: stratum=fresh_common_tools, source=hand-authored, n_tools=2, n_gold_calls=1
- tc-json-fresh-004: stratum=fresh_common_tools, source=hand-authored, n_tools=2, n_gold_calls=1
- tc-json-fresh-005: stratum=fresh_common_tools, source=hand-authored, n_tools=2, n_gold_calls=1
- tc-json-fresh-006: stratum=fresh_common_tools, source=hand-authored, n_tools=2, n_gold_calls=1
- tc-json-fresh-007: stratum=fresh_common_tools, source=hand-authored, n_tools=2, n_gold_calls=1
- tc-json-fresh-008: stratum=fresh_common_tools, source=hand-authored, n_tools=2, n_gold_calls=1
- tc-json-fresh-009: stratum=fresh_common_tools, source=hand-authored, n_tools=2, n_gold_calls=1
- tc-json-fresh-010: stratum=fresh_common_tools, source=hand-authored, n_tools=2, n_gold_calls=2
- tc-json-fresh-011: stratum=fresh_common_tools, source=hand-authored, n_tools=2, n_gold_calls=2
- tc-json-fresh-012: stratum=fresh_common_tools, source=hand-authored, n_tools=2, n_gold_calls=2
- tc-json-fresh-013: stratum=fresh_common_tools, source=hand-authored, n_tools=2, n_gold_calls=0
- tc-json-fresh-014: stratum=fresh_common_tools, source=hand-authored, n_tools=2, n_gold_calls=0
- tc-json-fresh-015: stratum=fresh_common_tools, source=hand-authored, n_tools=2, n_gold_calls=0
- tc-json-fresh-016: stratum=fresh_common_tools, source=hand-authored, n_tools=3, n_gold_calls=0
- tc-json-fresh-017: stratum=fresh_common_tools, source=hand-authored, n_tools=3, n_gold_calls=0
- tc-json-fresh-018: stratum=fresh_common_tools, source=hand-authored, n_tools=3, n_gold_calls=0
- tc-json-fresh-019: stratum=fresh_common_tools, source=hand-authored, n_tools=2, n_gold_calls=3
- tc-json-fresh-020: stratum=fresh_common_tools, source=hand-authored, n_tools=2, n_gold_calls=2
- tc-json-fresh-021: stratum=fresh_common_tools, source=hand-authored, n_tools=1, n_gold_calls=2
- tc-json-fresh-022: stratum=fresh_common_tools, source=hand-authored, n_tools=1, n_gold_calls=1
- tc-json-fresh-023: stratum=fresh_common_tools, source=hand-authored, n_tools=1, n_gold_calls=1
- tc-json-fresh-024: stratum=fresh_common_tools, source=hand-authored, n_tools=1, n_gold_calls=1
- tc-json-fresh-025: stratum=fresh_common_tools, source=hand-authored, n_tools=1, n_gold_calls=1
- tc-json-fresh-026: stratum=fresh_common_tools, source=hand-authored, n_tools=1, n_gold_calls=1
- tc-json-fresh-027: stratum=fresh_common_tools, source=hand-authored, n_tools=1, n_gold_calls=1
- tc-json-fresh-028: stratum=fresh_common_tools, source=hand-authored, n_tools=2, n_gold_calls=2
- tc-json-fresh-029: stratum=fresh_common_tools, source=hand-authored, n_tools=1, n_gold_calls=1
- tc-json-fresh-030: stratum=fresh_common_tools, source=hand-authored, n_tools=2, n_gold_calls=2

## Math per-item correctness matrix (base,q6k,udq2,fusion)

### olymmath_hard
- olymmath-hard-001: 0000
- olymmath-hard-002: 0000
- olymmath-hard-003: 1111
- olymmath-hard-004: 0000
- olymmath-hard-005: 1111
- olymmath-hard-006: 0001
- olymmath-hard-007: 0000
- olymmath-hard-008: 0001
- olymmath-hard-009: 0001
- olymmath-hard-010: 0000
- olymmath-hard-011: 1111
- olymmath-hard-012: 1111
- olymmath-hard-013: 1000
- olymmath-hard-014: 0000
- olymmath-hard-015: 0000
- olymmath-hard-016: 0000
- olymmath-hard-017: 1100
- olymmath-hard-018: 1110
- olymmath-hard-019: 1101
- olymmath-hard-020: 0110
- olymmath-hard-021: 0100
- olymmath-hard-022: 1110
- olymmath-hard-023: 1111
- olymmath-hard-024: 0000
- olymmath-hard-025: 0001
- olymmath-hard-026: 1011
- olymmath-hard-027: 0000
- olymmath-hard-028: 0100
- olymmath-hard-029: 0000
- olymmath-hard-030: 0101
- olymmath-hard-031: 0000
- olymmath-hard-032: 1111
- olymmath-hard-033: 0000
- olymmath-hard-034: 0000
- olymmath-hard-035: 0000
- olymmath-hard-036: 1001
- olymmath-hard-037: 0000
- olymmath-hard-038: 0000
- olymmath-hard-039: 0000
- olymmath-hard-040: 0001
- olymmath-hard-041: 0001
- olymmath-hard-042: 0000
- olymmath-hard-043: 0000
- olymmath-hard-044: 0001
- olymmath-hard-045: 1101
- olymmath-hard-046: 0000
- olymmath-hard-047: 0000
- olymmath-hard-048: 0011
- olymmath-hard-049: 1000
- olymmath-hard-050: 0000
- olymmath-hard-051: 0000
- olymmath-hard-052: 1111
- olymmath-hard-053: 0000
- olymmath-hard-054: 0101
- olymmath-hard-055: 0000
- olymmath-hard-056: 1000
- olymmath-hard-057: 0001
- olymmath-hard-058: 1000
- olymmath-hard-059: 1100
- olymmath-hard-060: 0000
- olymmath-hard-061: 1101
- olymmath-hard-062: 0100
- olymmath-hard-063: 0000
- olymmath-hard-064: 1101
- olymmath-hard-065: 0000
- olymmath-hard-066: 0000
- olymmath-hard-067: 0000
- olymmath-hard-068: 0000
- olymmath-hard-069: 0100
- olymmath-hard-070: 1111
- olymmath-hard-071: 0010
- olymmath-hard-072: 1100
- olymmath-hard-073: 0000
- olymmath-hard-074: 0001
- olymmath-hard-075: 1010
- olymmath-hard-076: 0110
- olymmath-hard-077: 1001
- olymmath-hard-078: 1000
- olymmath-hard-079: 0000
- olymmath-hard-080: 0000
- olymmath-hard-081: 0000
- olymmath-hard-082: 0000
- olymmath-hard-083: 0100
- olymmath-hard-084: 0000
- olymmath-hard-085: 0010
- olymmath-hard-086: 1111
- olymmath-hard-087: 0001
- olymmath-hard-088: 0000
- olymmath-hard-089: 0001
- olymmath-hard-090: 1000
- olymmath-hard-091: 0101
- olymmath-hard-092: 1000
- olymmath-hard-093: 1101
- olymmath-hard-094: 0000
- olymmath-hard-095: 0000
- olymmath-hard-096: 0001
- olymmath-hard-097: 0000
- olymmath-hard-098: 0000
- olymmath-hard-099: 0000
- olymmath-hard-100: 0000

### amo
- amo-001: 0000
- amo-002: 1111
- amo-003: 0000
- amo-004: 0000
- amo-005: 0000
- amo-006: 0000
- amo-007: 0000
- amo-008: 0000
- amo-009: 0011
- amo-010: 0000
- amo-011: 0000
- amo-012: 1111
- amo-013: 0000
- amo-014: 0000
- amo-015: 0000
- amo-016: 0100
- amo-017: 0101
- amo-018: 0001
- amo-019: 1111
- amo-020: 0111
- amo-021: 0000
- amo-022: 1000
- amo-023: 0000
- amo-024: 0000
- amo-025: 0000
- amo-026: 0010
- amo-027: 0001
- amo-028: 0000
- amo-029: 1000
- amo-030: 0000
- amo-031: 0000
- amo-032: 0000
- amo-033: 0000
- amo-034: 0000
- amo-035: 1111
- amo-036: 0000
- amo-037: 0000
- amo-038: 0000
- amo-039: 0000
