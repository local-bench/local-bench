# local-bench Threat Model: Answer-Injection Cheat Proxy

## Summary

The adversarial proxy in `attack/` demonstrates a specific failure mode: server-side
transcript scoring cannot prove which model produced a response. A malicious submitter can
point the CLI at an OpenAI-compatible endpoint that reads the public suite files, looks up
public gold answers, fabricates plausible transcripts, and claims weak local hardware.

This is not a product feature. It is an attack harness used to validate the project thesis:
trust comes from replication, not from transcript verification alone.

## Why The Attack Works

local-bench intentionally keeps the client thin: the CLI renders prompts, sends them to an
OpenAI-compatible endpoint, records transcripts and manifest data, and the server scores the
transcripts. That design makes runs easy to reproduce, but it also means the server observes
only submitted text plus self-reported runtime metadata.

The public `suite/v0/*.jsonl` item sets include both prompts and gold answers for MCQ and
genmath items. A fake endpoint can match incoming prompts against those files and return the
gold answer without running the claimed model at all. The returned transcript is syntactically
valid and semantically correct, so server-side scoring has no local signal that distinguishes
the fake endpoint from a surprisingly strong model response.

IFEval is different: it has instructions rather than a public answer key. The proxy can satisfy
cheap constraints such as JSON formatting, bullet counts, word-count bounds, keyword frequency,
or highlighted sections, but there is no single gold answer to inject. That distinction should
be stated honestly in any analysis of the attack.

## Verification Ladder

| Layer | Stops this attack? | Reason |
| --- | --- | --- |
| Server scoring | No | The transcripts are valid and contain the expected answers. The scorer cannot see the real generator. |
| Timing physics | No | The proxy can sleep to fake a slow local tokens-per-second profile. Timing is useful for plausibility, not identity. |
| Hardware sanity | No | A fake endpoint can claim a weak model/runtime profile that is internally consistent. |
| Randomized subsets | No | If the subset is drawn from public items with public answers, the proxy can still look them up. |
| Replication badge | Yes | Independent runs on real comparable hardware should converge to the real model distribution, not the injected near-perfect result. |
| Generated-variant items | Yes | Fresh generated variants with withheld answers remove the lookup table the proxy depends on. |
| Private rotation | Yes | Private or delayed-release items make answer-key injection materially harder until the items leak. |

## Product Implications

local-bench must never label a submitted result as "verified" merely because the transcript
scores well and the manifest looks plausible. Better labels are:

- "community-reported" for ordinary submitted runs.
- "replicated" for results independently reproduced by trusted or sufficiently diverse runners.
- "anchor" for project-maintained reference runs with controlled hardware, software, and item flow.

The durable defenses are replication convergence and items whose answers the cheater cannot
obtain. Generated variants are the near-term defense because they break static answer lookup.
Private rotation can strengthen the ladder later, but it adds operational burden and should not
be treated as a substitute for independent replication.

For an eval-literate audience, the honest claim is narrow: transcript scoring verifies that a
submitted transcript answers a submitted prompt. It does not verify model identity, model
weights, runtime honesty, or hardware provenance.
