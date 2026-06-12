<task>
Build the adversarial "cheat proxy" for local-bench — a deliberate attack tool that proves
server-side transcript scoring CANNOT detect model substitution / answer injection, which
is the empirical basis for the project's "trust = replication, not verification" thesis.
This lives under a clearly-marked attack/ directory and is documentation, not product.

Context: our CLI (cli/) drives an OpenAI-compatible endpoint, uploads raw transcripts +
manifest; the server scores transcripts. The suite item sets (suite/v0/*.jsonl) are PUBLIC
and INCLUDE gold answers (answer letters, math answers). The attack: a malicious user points
the CLI at a fake endpoint that returns perfect answers while claiming weak hardware.

1. attack/cheat_proxy.py — a standalone aiohttp/http.server OpenAI-compatible endpoint:
   - GET /v1/models → returns a claimed model id (configurable, default "potato-7b-q2").
   - POST /v1/chat/completions → reads the user prompt, MATCHES it against the loaded
     suite item sets to identify the item, and fabricates a response that:
     * for MCQ: emits plausible-looking short reasoning + "Answer: <gold letter>";
     * for genmath: emits short working + the gold number;
     * for IFEval: best-effort — actually satisfies the instruction if cheaply doable,
       else echoes prompt (IFEval has no gold key to look up — note this honestly).
   - Fakes usage tokens and SLEEPS to mimic a configurable target tok/s (--fake-tok-s,
     default 35) so timing looks like a slow local rig.
   - Flags: --suite-dir, --claimed-model, --fake-tok-s, --port, --inject {answers|strong-model}.
     For this P0, implement the {answers} mode fully (answer-key injection). Stub
     {strong-model} with a clear NotImplemented note (would forward to an API model;
     needs a key we don't have yet).
   - Top-of-file banner comment: THIS IS AN ADVERSARIAL TEST TOOL. Not shipped to users.

2. attack/run_attack_demo.py — orchestrates the demonstration:
   - Launches the proxy in-process (or subprocess), runs the localbench quick tier (or a
     --max-items subset) against it via the existing orchestrator API
     (localbench.orchestrate.run_localbench), and prints a before/after table:
     the cheater's composite vs a realistic honest 7B baseline (hard-code an illustrative
     honest reference like 45-55 composite, clearly labelled illustrative).
   - Prints which manifest/plausibility signals WOULD or WOULD NOT catch this:
     server-side scoring (does NOT catch — transcripts are valid), timing (does NOT catch
     — faked), hardware sanity (does NOT catch — claim is internally consistent),
     replication (WOULD catch — independent runs of a real potato-7b would not converge
     near 100%). Be precise and honest.

3. docs/threat-model.md — the findings writeup (you author this):
   - The attack and why it works (public questions + public answers + server can't see the
     real model).
   - Table: each verification-ladder layer (server scoring, timing physics, hardware
     sanity, randomized subsets, replication badge, generated-variant items, private
     rotation) → does it stop THIS attack? (most: no; replication + private/generated: yes).
   - Conclusion: the product must NEVER claim "verified"; label results "community-reported"
     vs "replicated" vs "anchor"; the only durable defenses are replication convergence and
     items whose answers the cheater cannot obtain (generated variants now, private rotation
     later). Frame honestly for an eval-literate audience.

4. Tests: cli/tests/test_cheat_proxy.py (or attack/tests/) — unit-test the item-matching +
   answer-injection logic with a tiny fixture suite (reuse cli/tests/fixtures/suite_v0):
   assert the proxy returns the gold answer for known MCQ/genmath items and that a
   localbench run against the in-process proxy yields a near-perfect MCQ+genmath score.
   Keep it fast; no real network, no GPU, no sleeps in tests (monkeypatch the delay).
</task>

<action_safety>
Create attack/ at repo root and docs/threat-model.md and the one test file. May import from
the installed localbench package (read-only use). Do NOT modify cli/src, suite/v0 item sets,
or the orchestrator. No git. The proxy must never auto-start on import.
</action_safety>

<completeness_contract>
Done = pytest green via cli/.venv (new test included); running
`cli/.venv/Scripts/python attack/run_attack_demo.py --max-items 6` prints the before/after
table and the per-signal catch/miss analysis WITHOUT needing the real model server
(answer-injection mode is self-contained); docs/threat-model.md written.
</completeness_contract>

<verification_loop>
Run the demo and the tests yourself; fix before finishing. The demo must run with NO local
model server up (it talks only to the in-proc proxy). Confirm that explicitly.
</verification_loop>

<missing_context_gating>No questions; decide and note.</missing_context_gating>

<compact_output_contract>
Final message: (1) files created, (2) pytest line, (3) the demo's printed before/after +
which signals caught/missed, (4) <=6 bullets decisions/deferred.
</compact_output_contract>
