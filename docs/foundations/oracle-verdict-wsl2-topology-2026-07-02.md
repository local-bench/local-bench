# Oracle verdict: WSL2 canonical-runner topology (2026-07-02)

Consultant: GPT-5.5 Pro (oracle, browser engine, session `wsl2-agentic-topology`,
7m20s, model verified `Pro Extended`). Brief: self-contained topology fork (A1/A2 x
B1/B2/B3) + supporting attachments (sandbox build results, live plan). The plan's P4
lean (B2, agentic out-of-band + merge) was presented as the incumbent to attack.

Adopted with one refinement (see `agentic-lane-b1-spec-2026-07-03.md`): B1' keeps the
protocol-C loop ON WINDOWS (model calls stay 127.0.0.1-local; only the sandbox is
proxied to WSL over stdio), which stays inside the A1+B1 envelope and makes the NAT
bridge - and its five failure-mode tests - moot.

Verbatim verdict follows.

---

## Recommendation: **A1 + B1**

Run **one Windows `localbench bench` campaign** as the only scorecard authority, reuse the existing pinned Windows `llama-server.exe` for **all five axes**, and invoke AppWorld-C inside WSL2 as a worker that returns per-task agentic records into the same run directory/checkpoint stream.

Inside A1, I would keep the Windows `llama-server` itself bound to `127.0.0.1` and expose it to WSL through a narrowly managed, per-run NAT bridge if possible, rather than widening the server bind to `0.0.0.0` or switching WSL to mirrored networking for row one. The WSL worker should be persistent over stdio/socket, but every AppWorld task should still get a fresh `env_host` + fresh bubblewrap runner.

B2 should be rejected. It is not “just a pack-time convenience”; it creates a new benchmark artifact type: a composite scorecard made from two campaigns. That directly collides with the current ranked-row constraint that all five axes must be present in one curated source’s axes, with no merge mechanism today.

---

# 1. Ranking of the A × B combinations

|  Rank | Combo       | Verdict                                                                                                                                                                                                                   |
| ----: | ----------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **1** | **A1 + B1** | **Best first ranked-row topology.** One campaign, one result-bundle shape, one serving runtime identity, proven Windows teardown, WSL used only for the Linux-required AppWorld execution seam.                           |
| **2** | **A2 + B1** | Best fallback if A1 networking proves unacceptable. It preserves one campaign, but creates a runtime split inside one scorecard and requires new WSL CUDA serving + teardown hardening.                                   |
| **3** | **A1 + B2** | The incumbent lean. It keeps the good serving choice, but the B2 merge step is a benchmark-integrity hazard and touches the frozen scorecard identity surface.                                                            |
| **4** | **A2 + B3** | Potentially clean someday as an all-WSL stack, but it is effectively a platform migration before row one: new llama.cpp artifact, new teardown, duplicated orchestration, unproven 4-axis path.                           |
| **5** | **A1 + B3** | Worst of both root-control worlds: WSL becomes campaign authority while the model endpoint still crosses into Windows. It duplicates the Windows orchestrator and makes every axis depend on the cross-boundary endpoint. |
| **6** | **A2 + B2** | Avoid. It combines the two most damaging choices: a second serving runtime plus a two-campaign merge mechanism.                                                                                                           |

## Why **A1 + B1** wins

### Benchmark integrity / provenance

**A1 + B1** keeps the scorecard boring: one `bench` invocation, one run directory, one checkpoint lineage, one pack path, one validator-facing bundle shape. The agentic axis becomes another axis producer under the same campaign authority.

That matters more than the network inconvenience. The ranked gate already says there is no merge-two-runs mechanism. B2 would require inventing one, and any honest merge mechanism would need to prove that the 4-axis run and the agentic run shared the same model artifact, lane, sampler pins, suite identity, runner build, dirty tree, runtime identity, and conformance rules. That is not a small implementation detail; it is a new trust boundary.

A2 also weakens integrity because the text/code axes would use the proven Windows llama.cpp binary while the agentic axis would use a different WSL llama.cpp binary. Even if both are called “b9852”, the binary hash and runtime environment differ. A skeptical reviewer would reasonably ask whether one scorecard is silently mixing runtime identities.

### Determinism

**A1 + B1** has one nondeterminism addition: the WSL-to-Windows model-client hop. That hop is measurable and testable. It does not change tokenizer rendering, sampler pins, capped-thinking enforcement, server binary, or model artifact identity.

**A2** adds a second serving runtime, WSL CUDA paravirt behavior, WSL VRAM/process cleanup behavior, and potentially different performance under long context or concurrent teardown. That is a much larger determinism surface than a local NAT bridge.

**B2** adds campaign-selection nondeterminism: two independent runs can succeed, fail, resume, or be retried independently. Without a very strict merge validator, B2 permits accidental or intentional Franken-scorecards.

### Failure modes

**A1 + B1** has clear failure boundaries:

Windows owns campaign lifecycle, server lifecycle, run directory, checkpoints, packing, and scorecard assembly. WSL owns only the AppWorld worker and sandbox children. If the WSL worker fails, the Windows campaign records a failed/invalid agentic task or aborts fail-closed.

**B2** creates hour-11 ambiguity. A 4-axis run can finish while the WSL agentic run dies, or the agentic run can finish against a slightly different config, then the merge step becomes the place where trust is either enforced or lost. That is exactly the kind of infrastructure seam that produces unverifiable leaderboard rows.

**A2** creates new orphan classes: WSL llama-server processes, WSL CUDA contexts, pgroup/cgroup teardown failures, stale GPU allocations, and duplicated orchestrator hardening. The existing Windows Job Object teardown is already proven; throwing it away for the riskiest axis is the wrong trade.

### Build cost to first ranked row

**A1 + B1** requires building:

1. a Windows-to-WSL AppWorld axis adapter;
2. a WSL worker protocol;
3. a narrow WSL-to-Windows endpoint bridge;
4. provenance additions for the cross-boundary topology;
5. bundle integration so AppWorld-C records land in the normal result-bundle shape.

That is real work, but it extends the existing campaign model.

**B2** looks cheaper only if the merge step is treated as informal. A publishable version is not cheap: it needs new scorecard identity semantics, validator rules, anti-Franken-run checks, and probably a new bundle schema story. That is riskier than plumbing AppWorld-C into the existing run directory.

## Two strongest reasons A1+B1 beats the runner-up, A2+B1

1. **It preserves one serving runtime identity across all five axes.**
   A2+B1 would put different llama.cpp binaries inside one scorecard. Even if the model artifact hash is identical, the runtime identity is not. A1+B1 avoids that reviewer objection completely.

2. **It reuses the already-hardened Windows lifecycle.**
   The existing Windows server path has pinned argv, Job Object kill-on-close, and GPU PID drain. A2+B1 would require rebuilding comparable WSL process/GPU teardown under pgroups/cgroups before trusting a 13h ranked run.

---

# 2. Failure modes that must be tested before a ranked run

| Failure mode                                                                           | Required test                               | Pass condition                                                                                                                                                                                |
| -------------------------------------------------------------------------------------- | ------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| WSL cannot reliably reach the Windows-hosted model endpoint under NAT.                 | **`A1_WSL_ModelEndpoint_Reachability`**     | From the trusted WSL worker, repeated `/v1/models` and tiny `/v1/completions` calls succeed against the run-owned endpoint bridge. Gateway IP, port, and latency stats are recorded.          |
| The endpoint is accidentally exposed beyond WSL.                                       | **`A1_Endpoint_Scope_Firewall`**            | Windows server remains loopback-bound or vEthernet-scoped; bridge/firewall allows only the WSL NAT subnet; no LAN-wide listener; run fails closed if scope cannot be proven.                  |
| Untrusted AppWorld code can reach the model server or network.                         | **`AppWorld_Bwrap_NoNet_To_Model`**         | A malicious code block inside bubblewrap attempting AF_INET to the host gateway/model port fails. Only the trusted WSL agent loop can call the model.                                         |
| WSL NAT gateway/subnet changes after restart.                                          | **`WSL_NAT_Gateway_Drift_Reinit`**          | After `wsl --shutdown` and restart, the Windows campaign recomputes gateway/subnet/bridge config and does not reuse stale IPs.                                                                |
| Portproxy/firewall/listener survives a failed run.                                     | **`A1_Bridge_Teardown_Idempotence`**        | Normal exit, Ctrl-C, worker crash, and exception paths remove or safely supersede the bridge/firewall rule. A subsequent run starts cleanly.                                                  |
| Windows llama-server becomes orphaned.                                                 | **`Windows_Server_JobObject_KillDrain`**    | Killing the campaign at multiple lifecycle points leaves no `llama-server.exe`, no listening model port, and no NVIDIA PID after drain. Include the Popen→Job assignment window.              |
| WSL worker or AppWorld children become orphaned.                                       | **`B1_WSL_Worker_ParentDeath_Cleanup`**     | Killing the Windows campaign leaves no persistent WSL worker, `env_host.py`, bubblewrap runner, stale RPC socket dir, or task-local scratch directory.                                        |
| Bubblewrap `--die-with-parent` does not behave as expected under the WSL launch shape. | **`Bwrap_DieWithParent_Under_B1`**          | If the trusted WSL worker dies mid-task, the untrusted runner dies too; no child continues executing model code.                                                                              |
| Agentic task hangs on model call, RPC, env-host startup, or code block.                | **`AppWorld_PerEvent_Timeouts_FailClosed`** | Simulated hangs at model call, `READY`, RPC call, `run_block`, and `finalize` produce bounded timeout records and cleanup, not indefinite campaign stall.                                     |
| Half-written agentic records get packed.                                               | **`Agentic_Record_Atomicity_CrashResume`**  | Crashes during task execution, finalize, and record write leave either no task record or a complete task record. Pack refuses partial agentic records.                                        |
| Campaign resumes into a mixed or corrupt state.                                        | **`FiveAxis_Checkpoint_Resume_FailClosed`** | Resume from checkpoints preserves one run identity and one config. Changing lane, endpoint, WSL identity, suite, sampler pins, or model artifact causes fail-closed resume rejection.         |
| WSL worker drifts from required determinism env.                                       | **`WSL_Determinism_EnvPins`**               | Worker and sandbox record and enforce `PYTHONHASHSEED=0`, `TZ=UTC`, `LC_ALL=C.UTF-8`; no Windows locale/timezone leakage.                                                                     |
| AppWorld sandbox regresses under the B1 invocation path.                               | **`AppWorld_Sandbox_Gates_Under_B1`**       | The same B1-launched WSL worker passes the 55-canary gate with `SUCCEEDED=0 / BLOCKED=55 / ERROR=0` and the scripted 2-task solve with `2/2 success`.                                         |
| AppWorld data accidentally runs from `/mnt/c` or the wrong tree.                       | **`AppWorld_DataPath_Ext4_Assertion`**      | `APPWORLD_ROOT` is `<appworld-root>`, filesystem is WSL ext4, and the data tree digest/version is recorded.                                                                                   |
| WSL model client does not enforce capped-thinking exactly like the Windows text axes.  | **`Agentic_CappedThinking_ClientParity`**   | The AppWorld model client uses the same HF tokenizer/chat-template digest, `gemma4` reasoning activation, stop tokens, 8192 thinking cap, sampler pins, and raw `/v1/completions` path.       |
| Network bridge latency causes false task failures.                                     | **`A1_Bridge_Soak_With_ModelCalls`**        | A representative AppWorld shakeout with many model calls records no connection resets, no unexplained HTTP failures, and latency within the configured per-event budget.                      |
| Validator cannot rescore the agentic transcripts.                                      | **`Agentic_Transcript_Rescore_RoundTrip`**  | Tiny 5-axis bundle packs in the normal shape; validator can read agentic transcripts/per-task records and recompute ASR/Wilson inputs.                                                        |
| The scorecard accidentally behaves like B2.                                            | **`No_Merged_Run_Scorecard_Guard`**         | Pack refuses any scorecard whose axes come from different campaign IDs/run roots unless a future explicit schema version exists. For row one, all five axes must share the same run identity. |

---

# 3. Minimal additive provenance fields for A1+B1

A skeptical reviewer does not need a whole new schema, but they do need enough fields to reconstruct the cross-boundary topology and prove the agentic axis used the same model-serving runtime as the other axes.

I would add these fields, without changing the existing manifest identity fields.

## `topology`

```json
{
  "topology_id": "windows-bench__windows-llama-server__wsl2-appworld-worker__nat-bridge-v1",
  "campaign_driver_os": "windows",
  "model_server_os": "windows",
  "agentic_worker_os": "wsl2-linux",
  "scorecard_assembly": "single-campaign-no-merge",
  "axis_driver": {
    "appworld_c": "windows_bench_invokes_wsl_worker",
    "mmlu_pro": "windows_bench_native",
    "ifbench": "windows_bench_native",
    "tc_json_v1": "windows_bench_native",
    "lcb": "windows_bench_native"
  }
}
```

## `wsl_identity`

```json
{
  "wsl_distro": "...",
  "wsl_kernel": "6.6.87.2-microsoft",
  "wsl_networking_mode": "NAT",
  "wsl_os_release": "...",
  "wsl_python": "...",
  "wsl_worker_entrypoint": "...",
  "wsl_worker_git_commit": "...",
  "wsl_worker_dirty_tree": true
}
```

The key point is that the WSL worker’s code identity must be tied back to the same localbench commit/dirty tree story, not treated as an opaque external script.

## `cross_boundary_model_endpoint`

```json
{
  "mechanism": "nat_bridge_or_portproxy",
  "server_bind": "127.0.0.1",
  "windows_target": "127.0.0.1:<port>",
  "wsl_visible_base_url": "http://<windows-gateway-or-bridge-ip>:<port>",
  "wsl_nat_subnet": "...",
  "windows_gateway_ip_seen_from_wsl": "...",
  "firewall_scope": "wsl-vethernet-subnet-only",
  "bridge_created_by_run": true,
  "bridge_removed_at_teardown": true
}
```

Do not just record the URL. Record the mechanism and scope. Otherwise the reviewer cannot tell whether this was a narrow local bridge or an accidental LAN-exposed server.

## `axis_model_server_binding`

```json
{
  "server_instance_id": "...",
  "llama_cpp_binary_sha256": "...",
  "llama_cpp_source_tag": "b9852",
  "server_argv_digest": "...",
  "server_start_time_utc": "...",
  "gpu_identity": {
    "gpu_name": "RTX 5090",
    "gpu_uuid": "...",
    "driver_version": "...",
    "cuda_runtime_reported": "..."
  },
  "axes_using_this_server_instance": [
    "appworld_c",
    "mmlu_pro",
    "ifbench",
    "tc_json_v1",
    "lcb"
  ]
}
```

This is the anti-A2 proof: the agentic axis did not use a second hidden llama.cpp runtime.

## `agentic_sandbox_identity`

```json
{
  "appworld_root": "<appworld-root>",
  "appworld_root_filesystem": "wsl2-ext4",
  "appworld_data_digest_or_release_id": "...",
  "bubblewrap_version": "0.9.0",
  "bubblewrap_path": "~/.local/bin/bwrap",
  "bubblewrap_sha256": "...",
  "bwrap_argv_digest": "...",
  "sandbox_network_namespace": "unshared",
  "sandbox_canary_result": {
    "succeeded": 0,
    "blocked": 55,
    "error": 0
  }
}
```

The reviewer needs to know not only that WSL was used, but that the specific WSL sandbox was the proven one.

## `agentic_client_identity`

```json
{
  "model_call_location": "trusted_wsl_worker",
  "untrusted_runner_has_network": false,
  "api_path": "/v1/completions",
  "thinking_cap_tokens": 8192,
  "reasoning_activation": "gemma4",
  "hf_model_id": "unsloth/gemma-4-12b-it",
  "tokenizer_digest": "...",
  "chat_template_digest": "...",
  "stop_tokens": ["..."],
  "sampler_pins_digest": "..."
}
```

This prevents a subtle failure where the Windows text axes use the corrected capped-thinking client but the WSL agent loop silently uses stale Qwen/Gemma rendering or a chat endpoint.

## `boundary_health`

```json
{
  "preflight_model_probe_from_wsl": "pass",
  "postrun_model_probe_from_wsl": "pass",
  "http_error_count": 0,
  "model_connection_reset_count": 0,
  "model_request_timeout_count": 0,
  "bridge_latency_summary": {
    "count": 0,
    "p50_ms": 0,
    "p95_ms": 0,
    "max_ms": 0
  },
  "windows_wsl_clock_skew_ms_start": 0,
  "windows_wsl_clock_skew_ms_end": 0
}
```

Exact latency values can be filled by the implementation. The important part is that cross-boundary failures are counted as infrastructure events, not silently mixed into model quality.

## `single_campaign_integrity`

```json
{
  "run_id": "...",
  "scorecard_assembly_mode": "single_run",
  "merge_step_used": false,
  "axis_run_ids": {
    "appworld_c": "...",
    "mmlu_pro": "...",
    "ifbench": "...",
    "tc_json_v1": "...",
    "lcb": "..."
  }
}
```

For A1+B1, all `axis_run_ids` should collapse to the same campaign identity or to child IDs under the same campaign root. This field explicitly proves the row is not a B2-style composite.

---

# 4. Is WSL2-on-this-box disqualifying?

**No — not disqualifying for a first publishable ranked row, provided it is explicitly flagged in the trust tier and the tests above pass.**

WSL2 is not the same as a native Linux host, and the row should not pretend otherwise. The publishable claim should be:

> The agentic Linux-required axis ran in WSL2 with a validated bubblewrap sandbox; the model server remained the same pinned Windows llama.cpp runtime used by the other axes; the WSL trusted worker crossed a scoped NAT bridge to that server.

That is good enough for a first ranked row because the actual AppWorld isolation boundary has already passed the important gates: 55/55 escape canaries blocked, 2/2 real scripted tasks solved, no network in the untrusted runner, native ext4 AppWorld data, deterministic env pins, and fresh sandbox per task.

The thing to avoid is overclaiming native-Linux equivalence. A later native Linux host should be allowed to produce a cleaner trust tier, but WSL2 does not invalidate this row if the infrastructure is transparent.

Recommended flag wording:

```text
trust_tier: orchestrated-pinned-artifacts-v1+agentic-wsl2-bwrap-nat-bridge-v1
```

And a more human-readable board note:

```text
Agentic axis ran under WSL2: validated bubblewrap sandbox, native ext4 AppWorld data,
Windows-hosted pinned llama.cpp model server reached via scoped WSL2 NAT bridge.
Native-Linux parity not claimed.
```

That wording is honest, reviewer-friendly, and does not bury the topology choice.
