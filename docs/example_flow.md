# MAS-Flow in Action: A Practical Example

A concrete walk through one story. The project is a **Laravel (PHP)** API with **Python** media scripts, running MAS-Flow on Claude Code; the Human wants **video uploads with thumbnail generation**.

Lines starting with `masflow` are deterministic commands (`python3 MAS-Flow/scripts/masflow.py …`) run by the orchestrator; everything else is an agent or the Human.

## 1. Goal → options → story

```
/masflow Add video uploads with automatic thumbnail generation
```

- **Planner** reads the maps and the architecture and classifies the goal as `full` (new contract, a queue job, file upload = security surface). It returns three scored options:
  - A — synchronous thumbnail in the request (simple, blocks the API);
  - B — upload + queued job that calls the existing Python FFmpeg script (recommended, 4 slices);
  - C — external transcoding service (more capability, new dependency and cost).
- **Human** picks **B**.
- **Planner** writes `HU-045` in handoff §1 with `AC1` (a valid upload is stored and answers 202), `AC2` (a thumbnail exists after the job runs), `AC3` (non-video or oversized files are rejected with 422), `AC4` (only the owner can upload to their library).

## 2. Research

- **Researcher** returns pointers: `ImageService.php` (the existing upload pattern), the storage config, `scripts/media/` (Python scripts), the queue setup, the existing upload tests. It also reports an existing equivalent: `MediaStorage` already wraps S3.

## 3. Design, reviewed before any code

- **Architect** writes the plan in handoff §3 and one spec per slice:

  | # | Title | Layer | Wave | Risk |
  |---|---|---|---|---|
  | 1 | `videos` table + model | persistence | 1 | low |
  | 2 | `ThumbnailGenerator` contract + Python adapter | infrastructure | 1 | low |
  | 3 | `StoreVideo` action + `GenerateThumbnail` job | domain | 2 | low |
  | 4 | Upload endpoint: request validation + policy | interface | 3 | **high** |

  `slices/slice-4.md` names the route, the Form Request rules (mime, size), the policy method, and the tests `test_owner_can_upload` (AC1, AC4), `test_other_user_gets_403` (AC4), `test_rejects_non_video` (AC3) — signatures and test names, no method bodies.
- In parallel: **Guard** `plan_review` approves (every AC mapped, slice 4 correctly marked high-risk); **Security** `threat_model` rejects: the plan has no control for a file whose extension lies about its content. The **Architect** revises slice 4 (validate by content sniffing, add `test_rejects_disguised_executable`); both reviews pass.

## 4. Slices

```
masflow git create-branch --project api                     → masflow/HU-045
executor_laravel (slice 1)                                  → migration, model, tests; self-check green
masflow git commit-slice --project api --slice 1 --files …
masflow checks --project api --slice 1 --files …            → formatter + static analysis: pass
masflow log … --slice 1 --slice-status closed
```

Slice 2 (same wave) and slice 3 follow the same four steps — no model reads them again until the story close. Slice 4 is high-risk, so after its checks:

- **Guard** `code_audit` rejects: the controller checks ownership inline instead of through the policy. Back to **executor_laravel** with the finding; it fixes it; commit, checks, and the Guard approves.

## 5. Story close — three gates in parallel

- **Security** `story_audit` reads the whole diff: no new dependencies, no secrets, the Python script is invoked with an argument array (no shell injection). Approves with one residual risk (very large uploads rely on the web server limit).
- **Guard** `story_audit`: plan conformance holds; AC proof finds `AC2` **weak** — its test asserts that the job was dispatched, not that a thumbnail exists. A warning, logged as an open issue and a follow-up card.
- **Tester**: capability group + related tests, 58 passed; acceptance command (a real upload against the local stack) passes.

```
masflow git push-branch --project api
masflow git merge-story --project api --validated          → PR opened and merged into main
```

## 6. Consolidation

- **Documenter** appends `HU-045` to `history.md`, registers `StoreVideo`, `GenerateThumbnail` and `ThumbnailGenerator` in the functional map, adds the capability `CAP-MEDIA-02` to the product map, moves the card to Done and adds an Inbox card for the weak `AC2` test. The inline-ownership-check rejection has now been seen twice, so it proposes `CHECK-7`: an architecture test that forbids ownership comparisons in controllers.
- `masflow archive-story` moves the handoff and the slice specs to `archive/HU-045/`. The next story starts in a fresh session.

## 7. End of day

```
/masflow verify     → masflow verify: api 1 412 tests, failures = baseline, green
/masflow stats      → lead time 3.1 h; guard code_audit 1 run / 1 rejected; architect 21 % of agent time
```

## What the Human did

Chose option B. Everything else ran without waiting — and would have stopped for a decision if a slice had failed twice, a gate had escalated, or the merge had not been clean.
