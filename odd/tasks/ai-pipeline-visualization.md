# AI pipeline observability and frontend visualization

Cross-repository implementation tracked from `backend`; frontend and ML changes
are intentionally included in this work unit. No Engram mirror is created per
user instruction.

## Specs

1. Persist and expose the runtime pipeline stages without breaking the existing
   `ProcessingRun` status or result contract.
2. Show the real stage status, semantic result status, and human-review state
   in the frontend instead of using generic JSON as the primary view.
3. Preserve provisional-result safety labels and distinguish omitted stages from
   failed stages.
4. Send stage progress from the ML orchestrator to the backend callback.

## Tasks

- T1 — S1,S3: Add normalized pipeline-stage contract and GraphQL exposure. Route: inline. Status: completed.
- T2 — S4: Emit and callback ML stage progress. Route: inline. Status: completed.
- T3 — S2,S3: Render the pipeline graph in the frontend. Route: inline. Status: completed.
- T4 — S1-S4: Run focused backend, ML, and frontend checks. Route: inline. Status: partial; runtime test dependencies are unavailable in backend and ML environments.
- T5 — S1,S3: Materialize positive temporal predictions as idempotent annotation cases. Route: inline. Status: completed.
- T6 — S1: Reject invalid processing status transitions while preserving legacy queued-to-terminal callbacks. Route: inline. Status: completed.
- T7 — S2,S3: Remove fabricated DEMUCA summary values from the frontend and derive cards from real evaluations. Route: inline. Status: completed.
- T8 — S1: Persist ML operational snapshots and retry dispatch/callback delivery with bounded backoff. Route: inline. Status: completed.
- T9 — S2,S3: Expose individual DEMUCA evidence windows and render an interactive score breakdown. Route: inline. Status: completed.
- T10 — S2: Replace the compact pipeline grid with a connected interactive stage diagram and detail panel. Route: inline. Status: completed.
- T11 — S2,S3: Add a temporal evidence timeline with video seeking and signal filters. Route: inline. Status: completed.
- T12 — S2,S3: Add accept/reject actions for each temporal evidence case. Route: inline. Status: completed.

## Log

- L1: "hazlo"
- L2: Implemented stage persistence in `result_json`, GraphQL fields, ML callback progress, and a responsive frontend pipeline view.
- L3: Backend contract smoke test, frontend TypeScript check, lint, and production build passed. Backend Django tests could not start because Django is unavailable; ML tests could not collect because scikit-learn and soundfile are unavailable.
- L4: Callback-created annotation cases use the existing unique `(run, window_id, label)` constraint and never reset an already reviewed case.
- L5: DEMUCA overview cards now show evaluation count, real score delta, latest date, and highest scored subscale; unavailable values render honestly.
- L6: ML run snapshots are atomically persisted and dispatch/callback delivery retries three times; the backend remains the clinical system of record.
- L7: DEMUCA evidence now includes per-window signal probabilities and contributions, while legacy results continue rendering without individual windows.
- L8: The pipeline UI now presents every stage as a connected clickable card and shows real timing, progress, messages, and artifacts for the selected stage.
- L9: Evidence windows can now be filtered and selected to seek a reproducible HTTP video source; non-reproducible local paths remain visible without pretending they are playable.
- L10: Evidence review actions reuse the existing annotation-case mutation and preserve pending, accepted, rejected, and adjudication states in the timeline.
