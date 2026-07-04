# Direct-finalize provenance and trust-tier note

Agentic AppWorld-C runs that use the direct env-host finalize path should record this additive
provenance block in the per-task agentic record:

```json
{
  "finalization": {
    "path": "orchestrator-direct-envhost-stdin-v1",
    "runner_in_verdict_path": false,
    "finalize_correlation": "finalize_id+pinned_task+one_shot",
    "answer_hash": "<sha256 of the orchestrator read-back answer bytes>"
  }
}
```

The trust-tier note/string for this agentic harness should append `+direct-finalize-v1`. This means
the untrusted runner is excluded from the verdict path: the orchestrator sends its own read-back
answer to the pinned env-host over the env-host stdin control channel, and scoring accepts only the
matching `authoritative_verdict` stdout line correlated by `finalize_id`.
