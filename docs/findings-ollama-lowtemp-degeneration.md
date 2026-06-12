# Finding: Ollama + qwen2.5 degenerates at low temperature (blocks local quant runs)

**Date:** 2026-06-12 (overnight autonomous run)
**Status:** OPEN — blocks driving local models through Ollama at our default (greedy) settings.
**Why it matters:** Ollama is the #1 local runtime our target users run. The CLI must work
against it cleanly. Right now a temp-0 run via Ollama's OpenAI-compat endpoint produces garbage.

## Symptom
Running the suite via `--provider local --endpoint http://localhost:11434/v1 --lane answer-only`
(temperature 0) against `qwen2.5:7b-instruct-q4_K_M` returned degenerate output for every item:
`extracted=None`, `correct=False`, composite 0.0. Sample response_text:
`"The letter that best fits 0.fits describesdesD ... \0\0\0\0..."` (repetition + literal `\0`).

## Isolation (Ollama endpoint is fine; low temp is the trigger)
Direct `curl` to `/v1/chat/completions`:
- Trivial prompt, temp 0 → clean (`"S"`), proper usage. Endpoint works.
- MMLU-style "think step by step" prompt:
  - q4 temp 0 → garbage (`"A The 0.The the Treynzy Ratio ... p�rdida p�rdida"`)
  - q4 temp 0 + frequency_penalty 0.5 → still garbage
  - q8 temp 0 → garbage (`"To To\nTo Treynor Ratio is is is is calculated calculated ..."`)
  - q8 temp 0.3 → still garbage (encoding artifacts: `p�rdida`, `n�`)
  - **q4 temp 0.7 + top_p 0.9 → COHERENT (`"B."`)**

So it is NOT quant-specific (q4 and q8 both fail) and NOT fixed by frequency_penalty. It is a
LOW-TEMPERATURE serving problem: greedy/near-greedy decoding of qwen2.5 via Ollama's `/v1` path
produces repetition + non-ASCII (`�`) garbage over reasoning-length generations. The replacement
chars suggest a tokenizer/template/sampler issue in Ollama's serving at low temperature, not plain
greedy repetition. (Note our existing Qwen3.5-9B runs were via **vLLM** at temp 0 and were clean,
so this is an Ollama-path issue.)

## Why it blocked tonight's simulated quant runs
Our methodology fixes temperature 0 for determinism, and the CLI has no `--temperature` override
(the lane sets temp). A clean quant scatter needs greedy runs; those degenerate here. Running at
temp 0.7 would (a) deviate from methodology, (b) add run-to-run noise to the quant signal, and
(c) risk residual garbage — not acceptable for an honesty-first prototype without caveats.

## Next steps (morning)
1. Reproduce minimally and check Ollama version / known issues for qwen2.5 low-temp (`ollama` 0.30.6).
2. Test whether OTHER models degenerate at temp 0 on Ollama (llama3.1:8b, qwen3) — is it qwen2.5-specific?
3. Try Ollama's native `/api/chat` with `options.repeat_penalty` / explicit `top_k`,`top_p`, or a
   tiny temperature floor for local runtimes; decide a principled local-runtime sampling policy.
4. Add a `--temperature` (and maybe `--top-p`) override to the CLI for local runs regardless.
5. Once clean, run the deferred quant-degradation study (one model x q4/q8/fp16) for the model-page scatter.
