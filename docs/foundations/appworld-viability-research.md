# AppWorld agentic-axis VIABILITY research — choosing a feasible scoring protocol

**VERDICT: GO for code-as-action (Protocol C), bounded, with a harness-owned filesystem sandbox.**
The prior proof killed the one-JSON-call-per-turn protocol at `max_tool_calls=11` (gold paths need
median **34** / p90 **132** underlying API calls). This investigation measures the *right* unit —
**incremental `world.execute()` code-blocks**, AppWorld's native action mode — and finds the median
dev task needs only ~**4-5** code-blocks (p90 ~8, max 10), so a turn cap of ~16-20 makes the **whole**
dev split feasible. Code-as-action is empirically **judge-free and deterministic** (same task, two
action styles → identical fixed-assertion verdict), and a declarative bounded-batch primitive (B) is
**not expressive enough** (73% of dev solutions need conditionals/joins/parsing/arithmetic — i.e.
Turing-completeness). The one real catch: AppWorld's built-in `SafetyGuard` is **leaky** — a model
can read the gold `answer.json` off disk via `pathlib.Path(...).read_text()` (verified exploit) —
so code-as-action is only safe if **the harness adds its own sandbox** around `world.execute()`.

Date: 2026-06-23. GPU-free, endpoint-free, NON-LLM. No model loaded, `llama-server`/port 8000
untouched, no `git` commit/push, no edits to `web/`, the scorer, `axes.py`, scorecard, or
`agentic_exec/`. All numbers are from a hand-scripted deterministic driver of **real** AppWorld
(`appworld==0.1.3.post1`, WSL Python 3.12, `APPWORLD_ROOT=<appworld-root>`, determinism
trio set), identical trust boundary to the prior feasibility probe.

**Re-run command (reproduces every number below):**
```bash
wsl bash -lc 'cd /mnt/c/Users/Michael/local-bench && source <wsl-venv>/bin/activate \
  && export APPWORLD_ROOT=<appworld-root> PYTHONHASHSEED=0 TZ=UTC LC_ALL=C.UTF-8 \
  && python cli/tools/appworld_viability_probe.py'
```
Probe script: `cli/tools/appworld_viability_probe.py` (self-contained; imports only `appworld` +
stdlib). Two helper probes used during the investigation are inlined in this doc's appendix (safety
guard + answer-file exploit) and can be reconstructed from the snippets there.

---

## Point 1 — Code-block / turn budget under code-as-action (THE critical number)

**Method.** For each of the 57 dev gold `solution.py` files I parsed the `_solution(...)` body's AST
(the real logic; the outer `solution()` is just the `complete_task` wrapper) and counted what an
*incremental* agentic agent actually issues as separate `world.execute()` steps — NOT the flattened
API-call count. The model is transparent and deliberately conservative:

- **`est_blocks_upper`** (agent never fuses; every phase its own block):
  `1 (auth + peek) + pagination_sweeps + for_loops + 1 (compute & submit)`.
- **`est_blocks_fused`** (capable agent fuses reads into one block, actions into one):
  `1 (auth) + (1 if any paginated read) + (1 if any per-item loop) + 1 (finalize)`.

Here `pagination_sweeps` = calls to AppWorld's `find_*_from_pages` helper (each drives an entire
page loop), and `for_loops` = explicit per-item detail/action loops. These are exactly the two
structures that inflate the flattened API count.

**Result — distributions over the dev split (n=57), reproduced verbatim from the probe:**

| metric | min | median | p90 | max | mean |
|---|---|---|---|---|---|
| flat api-calls (gold) | 6 | **34.0** | 132.4 | 214 | 56.0 |
| WRITTEN api-call exprs (source) | 1 | 4.0 | 5.4 | 7 | 3.8 |
| **EST code-blocks (UPPER bound)** | 2 | **5.0** | **7.8** | **10** | 5.2 |
| **EST code-blocks (FUSED lower bound)** | 2 | **4.0** | 4.0 | 4 | 3.6 |

**Feasibility vs a turn cap (the decision table):**

| cap | fits (UPPER) | fits (FUSED) |
|---|---|---|
| ≤ 5  | 36/57 (63%) | 57/57 (100%) |
| ≤ 8  | 51/57 (89%) | 57/57 (100%) |
| **≤ 11** | **57/57 (100%)** | 57/57 (100%) |
| ≤ 15 | 57/57 (100%) | 57/57 (100%) |
| ≤ 20 | 57/57 (100%) | 57/57 (100%) |

**This is the headline.** Under code-as-action the *same* tasks that need a median of 34 (and up to
214) single JSON calls collapse to a median of **~5 code-blocks**, p90 **~8**, worst-case **10** —
because pagination sweeps and per-item detail loops live *inside* a code block (a `while`/`for` loop
or comprehension), not across turns. At the prior harness's own `max_tool_calls=11`, **100% of dev
tasks fit as code-blocks** (vs 16% as single JSON calls). A turn cap of **16-20** leaves a capable
model generous slack for exploration and one or two recovery turns and still admits the entire split.

**Cross-check against the flattened call log (independent of the AST model).** Clustering each heavy
task's `ground_truth/api_calls.json` into consecutive-endpoint runs confirms the inflation is pure
pagination + per-item lookups:

```
50e1ac9_1: 132 flat calls -> 32 endpoint-runs (16 are loops of >=3). Top runs:
       19x  /spotify/songs/{id}        <- per-item genre/play_count detail loop
       10x  /spotify/library/songs     <- pagination sweep (10 pages)
       10x  /spotify/library/albums    <- pagination sweep
       10x  /spotify/library/playlists <- pagination sweep
57c3486_1 (the MAX, 214 calls): 115 endpoint-runs, structurally just
       1 paginated "following_artists" read + a nested per-artist paginated song search + like-loop.
d4e9306_1 (63 calls): 9 endpoint-runs (5 loops): 2 paginated library reads + 2 per-item detail loops.
```

So the 132- and 214-call monsters are ~3-7 *written* statements and 3-5 loops — exactly what the
code-block estimate captures. The budget blocker the prior proof found is an **artifact of forcing
one API call per turn**, and code-as-action removes it.

---

## Point 2 — Multi-turn state persistence: PROVEN

Drove real dev task **`fac291d_1`** (difficulty 2, 34 flat gold calls — "How many unique songs
across my song library, albums library and all playlists?") in **4 successive `world.execute()`
blocks**, where each block depends on variables defined in earlier blocks:

| block | what it does | uses from earlier | new state |
|---|---|---|---|
| 1 | auth via `apis.supervisor.show_profile/show_account_passwords` → `apis.spotify.login`; peek page 0 | — | `token` |
| 2 | `while` loop sweeping all pages of `show_song_library`, union into a set | **`token`** | `song_ids` (16) |
| 3 | continue sweeping album + playlist libraries; `answer = len(song_ids)` | **`token`, `song_ids`** | `answer` (81) |
| 4 | `apis.supervisor.complete_task(answer=answer, status='success')` | **`answer`** (defined in block 3) | — |

`world.evaluate().to_dict()` → **`success: True`**. Python state (`token` from block 1, `song_ids`
accumulated across blocks 2→3, `answer` from block 3) **persists across `world.execute()` calls** —
the shell is a single stateful IPython session, exactly the incremental code-as-action interaction
model. Note: `main_user` and `apis.spotify.access_token_from` are **gold-solution-only** conveniences
and are *absent* from the agent's `execute()` namespace; the agent must authenticate via the
supervisor + `login` path (which it can, as shown).

---

## Point 3 — Judge-free / determinism under code-as-action: PROVEN

Solved the **same** task `fac291d_1` two ways in two fresh worlds:
- **Style C (code-as-action):** 4 incremental code-blocks (above) → `success: True`, `answer=81`.
- **Style A (one `apis.*` call per `execute()`, the JSON-protocol analogue):** 13 single calls
  (auth ×3 + paginated reads) → `success: True`, `answer=81`.

**Identical verdict** (`True == True`). The verdict comes from a fixed assertion set, not a judge:
`evaluate().to_dict()` keys are `['success','difficulty','num_tests','passes','failures']`, and the
passing requirements are the canonical strings **`"assert answers match."`** and
**`"assert no model changes."`**. There is **no LLM, no heuristic, no model-graded rubric** anywhere
in the scoring path — `success` is a deterministic boolean over DB-state assertions. This holds
**regardless of action mode**: code-as-action does NOT introduce a judge. (Confirms the prior proof's
Point 2 eval map and extends it to the code-block action style.)

---

## Point 4 — Bounded-batch (B) expressiveness: INSUFFICIENT (needs Turing-completeness)

A declarative bounded-batch primitive (pagination-over-range + map-over-ids) was assessed against
what the dev gold solutions actually compute. AST survey over the 57 dev solutions:

| pattern present in solution body | count / 57 |
|---|---|
| needs **any** Turing-complete logic (any row below) | **42 (73%)** |
| if / conditional branch | 36 |
| string parsing (`split`/`replace`/`strip`/`join`/f-string) | 15 |
| arithmetic on values (`+ - * / round`) | 9 |
| comprehension (list/dict/set/gen) | 12 |
| dict/zip **join** | 3 |
| regex | 3 |
| **expressible by PURE pagination+aggregate** (no loop, no branch) | **0 / 57** |
| expressible by pagination + **map-over-ids** (loops ok, but no branch/parse) | 15 / 57 |

**Only ~26% of dev tasks** could be served by a pagination+map primitive, and **zero** by a
pure pagination+aggregate primitive. The other ~73% need general computation that a declarative
schema cannot express without becoming a programming language. Concrete examples from real gold
solutions:

- **`50e1ac9_1` (132 calls):** three nested loops, each with a **conditional filter**
  (`if song.genre == public_data.genre`), accumulating into a dict, then **sort by play-count,
  slice top-k, join titles into a string**. A filter→group→sort→slice→format pipeline.
- **`22cc237_1` (difficulty 3):** parses a free-text note line-by-line (`split("\n")`,
  `startswith("-")`, `split("=>")`), builds `dict(zip(names, emails))`, does a **dict-comprehension
  join** between contacts and parsed shares, then an **anti-join** removing people who already paid
  (cross-referenced against venmo transactions), then requests money from the remainder.
- **`530b157_1` (difficulty 3):** uses `re.compile(r"\$(\d*)")` to extract a dollar amount from a
  text message, then arithmetic + two side-effecting calls.
- **`3c13f5a_1` (difficulty 3):** parses a bill file (`split("Total Amount => $")`), divides by
  `len(roommates)+1`, **rounds**, then requests that share from each roommate.
- **`37a8675_1`:** date arithmetic (`DateTime(...) > DateTime.now()` to filter non-expired cards) +
  a **break-on-success** payment loop.

To express these, a "bounded-batch" primitive would have to add filters, joins, arithmetic, string
manipulation, regex, sort/slice, and conditional side-effects — i.e. it **becomes code-as-action
anyway**, but in a bespoke, harder-to-audit DSL. Verdict: **B is a dead end**; if you need the
expressiveness, ship the real thing (C). (B remains theoretically usable only if the manifest is
narrowed to the ~26% map-only tasks — which guts the hard bands and fails the spread/no-floor
promotion gates, the same trap the prior proof flagged for "pick-fitting".)

---

## Point 5 — Gaming / cheating surface: answers are behind the APIs, BUT the guard is leaky (must sandbox)

**(a) Answers are not derivable without genuine API interaction — CONFIRMED.** For `50e1ac9_1`:
- `public_data` (everything the agent is told): `{"top_k": 4, "genre": "R&B"}`.
- gold `answer`: `"Mysteries of the Silent Sea,Crimson Veil,Haunted Memories,Fire and Ice"`.
- `private_data.json`: `{}` (empty — no hidden shortcut).

The answer is the result of sweeping the user's private Spotify library across three sources,
filtering by genre, ranking by play count, and taking the top 4. It **cannot** be computed from the
public parameters — the data (which songs exist, their genres, their play counts) lives behind the
authenticated APIs. Genuine interaction is required to solve.

**(b) AppWorld's `SafetyGuard` blocks the obvious escapes but is NOT a real sandbox — VERIFIED HOLE.**
Inside `world.execute()`, the guard rejects some dangerous calls but lets others through:

| operation | guard result |
|---|---|
| `open(path)` (direct builtin) | **BLOCKED** ("builtins.open not allowed") |
| `os.system`, `os.listdir`, `subprocess`, `socket` | **BLOCKED** |
| `__import__('os').getcwd()` / `os.path.exists(...)` | **ALLOWED** |
| `eval`, `exec`, `compile`, `globals()` | **ALLOWED** |
| **`pathlib.Path(path).read_text()`** | **ALLOWED** ← the hole |

**Concrete, reproduced exploit:** from inside `world.execute()`,
`pathlib.Path("<APPWORLD_ROOT>/data/tasks/50e1ac9_1/ground_truth/answer.json").read_text()`
returns **`"Mysteries of the Silent Sea,Crimson Veil,Haunted Memories,Fire and Ice"`** — the exact
gold answer, read straight off disk, **bypassing every API**. (`builtins.open` is blocked, but
pathlib's reader and `os.path` are not.) A model emitting code-as-action could therefore cheat *if*
it knew/guessed the on-disk path.

What protects us today is only that **the data path is never surfaced to the model** (it sees only
the JSON tool protocol / canonicalized observations, never `APPWORLD_ROOT` or the task layout). That
is *defense by obscurity* and is insufficient for a published leaderboard — a model trained on
AppWorld's public repo structure could reconstruct the path.

**Mitigations the harness MUST apply before any scored code-as-action run (pick one, ideally layer
two):**
1. **Make ground-truth unreadable from the worker.** Run each task's `world.execute()` in a process
   whose filesystem view cannot see `ground_truth/` — e.g. a separate worker under
   bubblewrap/`firejail`/a container with the data tree bind-mounted **read-only and with
   `ground_truth/`, `answer.json`, `private_data.json`, `*.bundle` masked out**, or chroot/seccomp.
   (AppWorld already runs in-process per task, so a per-task subprocess with a locked FS is the clean
   seam.)
2. **Restrict the `execute()` namespace.** Wrap AppWorld's executor so the agent's globals exclude
   `pathlib`, `__import__`/`importlib`, `compile`/`eval`/`exec`, `globals`, `open`, `os`, `socket`,
   `requester` (the raw HTTP object) — keep only `apis`, `re`, `json`, `math`, `datetime`/`DateTime`,
   `itertools`, `Counter`, `defaultdict`, and pure builtins. This is an allow-list on top of
   AppWorld's deny-list guard. (Note `requester` is exposed in the shell and is raw HTTP to the app
   backends — keep it out of the agent namespace so the only path to data is the whitelisted APIs.)
3. **Keep `apis.supervisor` minimal.** The supervisor surface is
   `complete_task, show_account_passwords, show_active_task, show_addresses, show_payment_cards,
   show_profile` — all legitimately the user's own data, and there is **no** `show_private_data` /
   `show_answer` / ground-truth API (good). The harness already calls `complete_task` itself; that's
   fine. No supervisor API leaks the answer, so the only gaming vector is the filesystem hole above.

Other gaming notes: exception-swallowing can't manufacture a pass (the verdict is final DB state, not
"did the code run"); and the `"assert no model changes."` assertion already penalizes collateral
mutation, so a model can't brute-force side effects to luck into success.

---

## Point 6 — Per-task cost signal (is the GPU run affordable on one RTX 5090?)

Turns ≈ code-blocks from Point 1 (median ~5, p90 ~8, max ~10). Estimating per-turn generated tokens
at a conservative **250-400 tokens** (a small Python block + brief reasoning):

| task | turns | output tokens |
|---|---|---|
| median (~5 blk) | 5 | ~1,250-2,000 |
| p90 (~8 blk) | 8 | ~2,000-3,200 |
| worst gold (~10 blk) | 10 | ~2,500-4,000 |
| at a turn cap of 20 | 20 | ~5,000-8,000 |

**For a 96-task scored run per model** (median 5 turns): ~**480 generations**, ~**120k-192k output
tokens**. At a realistic 30-60 tok/s decode for the 27-32B ladder, that's **~50-110 minutes of pure
decode per model** for output; prefill/context cost (32k window, growing transcript dominated by
repeated observation tokens) sits on top but is bounded by the per-turn token caps. **Order of
magnitude: minutes-to-low-hours of GPU per model, not days** — the Qwen ladder + gemma is affordable
on a single 5090 in a reasonable window, consistent with promotion-gate #7 ("runs in a few hours per
model"). The dominant cost lever is the **observation size** (paginated reads return many rows); the
existing `max_observation_chars_per_tool=12000` truncation keeps transcripts bounded — worth
confirming in the GPU smoke that real observations don't routinely truncate mid-pass.

---

## RECOMMENDED PROTOCOL: **C — bounded code-as-action (incremental `world.execute`), harness-sandboxed**

**Why C over A and B:**
- **vs A (raise the JSON cap):** A *can* be made feasible only by raising `max_tool_calls` to ~p90+margin
  ≈ **140+**, which (i) explodes per-task turns/tokens/wall-time (re-deriving every budget), (ii) makes a
  140-turn agentic task a very different and far more expensive GPU pilot, and (iii) tests the model's
  *patience with a crippled interface* more than its agentic competence. C reaches the same tasks in a
  median of ~5 turns. A is strictly dominated.
- **vs B (declarative bounded-batch):** B cannot express 73% of dev tasks (Point 4) without becoming a
  bespoke Turing-complete DSL — at which point it's just a worse, harder-to-audit code-as-action. Dead end.
- **C is judge-free and deterministic** (Point 3) — the spec's core constraint holds because the verdict
  is AppWorld's fixed final-state assertion set, independent of action mode. C is AppWorld's **native**
  mode (matches how the benchmark is designed and how the literature reports it), so scores are
  interpretable against external AppWorld results.

**The C configuration to adopt (a NEW scorecard identity — this is a protocol change from the stubbed
one-JSON config, exactly as the build spec flags):**
- Action = the model emits a **single Python code block per turn**; the harness runs it via
  `world.execute(block)` and returns captured stdout as the observation. Completion = the harness
  detects/permits `apis.supervisor.complete_task(answer=...)` (or a `final_answer` tool) and then calls
  `world.evaluate().to_dict()`; map `success` → `passed`, derive `collateral_damage` from the
  `"assert no model changes."` requirement (per the prior proof's eval map — Bugs 1-2 there still apply
  to the `RealAppWorld` wrapper).
- **Turn cap ≈ 16-20** (covers dev p90 upper-bound of 8 with 2x+ slack for exploration/recovery), with a
  per-turn output-token cap (~512-768) and a per-task token budget re-derived from Point 6 (~8-12k).
  These are new constants → new config hash → new scorecard id; record it as such.
- **MANDATORY sandbox** around `world.execute()` (Point 5): restrict the agent namespace to
  `apis` + safe stdlib (drop `pathlib`/`open`/`os`/`__import__`/`eval`/`exec`/`compile`/`globals`/
  `requester`), AND run the per-task world in a process that cannot read `ground_truth/`/`*.bundle`
  (read-only bind mount with those masked, or chroot/seccomp). Do not ship code-as-action without this —
  the answer-file read is a verified exploit.
- Keep the on-demand doc tools (`apis.api_docs.*`) available so the model isn't handed all 457 APIs;
  keep every supervisor/eval API except `api_docs` off the agent surface (harness owns `complete_task`).
- **Hybrid option (optional, lower-risk first cut):** ship C but **cap loop fan-out** inside a block
  (e.g. a per-turn wall-clock + max-API-calls-per-block limit, say ≤ ~40 API calls per `execute()`),
  so a single block can't issue thousands of calls. This bounds cost/abuse while preserving the
  median-5-turn feasibility. This is the recommended starting posture: **C-bounded** = code-as-action
  with (turn cap) × (per-block API-call cap) × (sandbox).

This keeps the headline v1 (Knowledge MMLU-Pro + Instruction IFBench) unchanged; agentic stays a
**candidate/parallel track (weight 0)** until a GPU-gated 12-smoke → 36-lite → 96-task run under the
C-bounded config clears the promotion gates.

---

## Open questions for the oracle

1. **Sandbox mechanism.** Is a per-task **subprocess with a read-only bind-mount that masks
   `ground_truth/`/`answer.json`/`*.bundle`** (bubblewrap/firejail/container) the right seam, or is an
   **in-process namespace allow-list** (strip `pathlib`/`__import__`/`eval`/`open`/`requester` from the
   `execute()` globals) sufficient on its own? The in-process approach is lighter but `eval`/`compile`
   are allowed by AppWorld's guard, so a determined model could re-derive `open`/`__import__` —
   argues for the process-level FS jail as the real boundary. Which is the minimal *robust* choice?
2. **Turn cap value + p-hacking.** Is **16-20** defensible as a single fixed cap across all four families
   (dev p90 code-blocks = 8 upper-bound, but test_challenge may run longer), or should the cap be set
   per-family from a measured p90 on the **test** splits — and does measuring it on test risk leaking
   selection signal into the manifest? (Selection is by ID only; the cap is a budget, not a filter — but
   confirm this isn't a backdoor information leak.)
3. **Per-block fan-out cap.** Does an explicit **≤N-API-calls-per-`execute()`** limit (the C-bounded
   hybrid) meaningfully change what the axis measures (does it reintroduce a "patience with a crippled
   interface" artifact for the 132/214-call tasks), or is it a clean abuse/cost guardrail? What N keeps
   the 214-call max solvable in ≤ the turn cap (214 / N ≤ ~10 → N ≈ 25-40)?
4. **Construct validity vs the JSON axis.** Code-as-action measures "can the model write incremental
   Python against a documented API and reason over results" — is that the agentic construct local-bench
   wants, or does the project specifically want the *tool-calling/JSON-protocol* construct (in which
   case the honest move is to **drop AppWorld** for agentic and pick a tool-calling benchmark whose gold
   paths are natively short)? This is the real fork: C makes **AppWorld** viable; it does not make the
   **one-JSON-per-turn protocol** viable.
5. **Comparability.** If we report code-as-action ASR, should we anchor against AppWorld's published
   leaderboard numbers (which use code-as-action / ReAct-style native execution) to sanity-check our
   harness, and does doing so require matching their exact prompt/agent scaffold (which would import an
   agent design we don't control) or only their environment + evaluator (which we do control)?

---

## Boundaries honored
- GPU-free, endpoint-free: no model loaded, `llama-server`/port 8000 untouched, hand-scripted
  deterministic driver only (same trust boundary as the prior probe).
- No edits to `web/`, the scorer, `axes.py`, scorecard, or `agentic_exec/`. No `git commit`/`push`.
  No changes to `cli/runs/` artifacts. Additions only: `cli/tools/appworld_viability_probe.py` and
  this doc.
- Read AppWorld gold `solution.py`/`metadata.json`/`api_calls.json`/`answer.json`/`public_data.json`
  for **dev + a few train** tasks for protocol calibration (dev/train are sanctioned for calibration;
  the test splits were not inspected). No decrypted bundles, task text, transcripts, eval traces, or
  ground truth are published in this doc beyond the single illustrative answer string already needed
  to demonstrate the gaming exploit.

---

## Appendix — auxiliary probe snippets (reconstructable)

**Safety-guard enumeration** (run in the WSL appworld venv): a loop over `world.execute("<op>")` for
`open`, `os.system`, `os.listdir`, `subprocess`, `socket`, `eval`, `exec`, `__import__`, `compile`,
`globals`, `pathlib...read_text`, `math`, `re`, `json` — printing whether each is BLOCKED ("not
allowed") or ALLOWED. Result table is in Point 5(b).

**Answer-file exploit** (the verified hole):
```python
from appworld import AppWorld
import os
gt = os.path.join(os.environ["APPWORLD_ROOT"], "data", "tasks", "50e1ac9_1", "ground_truth")
ans = os.path.join(gt, "answer.json")
with AppWorld(task_id="50e1ac9_1", experiment_name="lb_exploit") as w:
    print(w.execute(f"from pathlib import Path; print(Path({ans!r}).read_text())"))
    # -> "Mysteries of the Silent Sea,Crimson Veil,Haunted Memories,Fire and Ice"  (LEAK)
```
