# B2a static publication operations

The production community pages are static files baked under `web/public/data/community`.
The build must use `web/publication_export.py`; that exporter records D1's active snapshot,
publication revision, activation state, and suppression set. `web/publication_merge.py`
fails closed unless the bundle is the active, completed snapshot at that revision, and it
excludes every submission in the exported suppression set.

## Suppression and the 300-second eviction SLA

Suppressing a submission synchronously marks it suppressed, adds its D1 edge block,
increments the publication revision, and clears an affected active snapshot. Those D1
effects prevent a stale snapshot from being exported or rebuilt immediately.

Removing bytes that are already served from the static deployment is not performed by
this repository. The production deployment pipeline must treat a successful suppression
as a mandatory rebuild-and-redeploy trigger and complete static asset/cache replacement
within 300 seconds of `publication_edge_blocks.blocked_at`. The trigger, deployment job,
CDN purge, credentials, and SLA monitor live in deployment infrastructure that is not
present in this repository. A release is not compliant until maintainers wire and monitor
that external trigger; the in-repository code does not claim to purge an existing deploy.

The rebuild sequence is:

1. Create and activate a new snapshot after suppression.
2. Run the production exporter against that active snapshot.
3. Set `LOCALBENCH_PUBLICATION_ADMIN_SECRET`, then run
   `web/build_data.py --publication-bundle <export-dir> --publication-base-url <worker-url>`.
   The merge re-reads live D1 control immediately before materialization; any stale/non-active
   bundle or changed revision fails, and the current suppression set is authoritative.
4. Deploy the newly generated static site and invalidate the prior static assets.
5. Verify the suppressed submission is absent from the served community group and that
   elapsed time from `blocked_at` is no more than 300 seconds.
