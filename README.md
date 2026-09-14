# Coldline Task 2.3 — Implement a data layer

[![Open in GitHub Codespaces](https://github.com/codespaces/badge.svg)](https://codespaces.new/tripleten-com/ai-system-engineering-curriculum-sprint-2-task-2-3/tree/main)

## Start the system

Prerequisites are Python 3.12 and Docker with Compose v2. The supplied bootstrap supports macOS
arm64/x86-64, Windows x86-64, and Linux x86-64/aarch64, and installs pinned uv 0.11.8 under
`.tools/bin`. If your computer cannot run the stack locally, use the Codespaces button above.

On macOS and most Linux distributions the interpreter is `python3`; substitute it wherever these
commands say `python`.

```shell
python infra/scripts/bootstrap.py
./.tools/bin/uv sync --frozen
./.tools/bin/uv run --frozen poe preflight
./.tools/bin/uv run --frozen poe start
./.tools/bin/uv run --frozen poe ready
./.tools/bin/uv run --frozen poe ingest
./.tools/bin/uv run --frozen poe baseline
```

PowerShell and POSIX wrappers are available under `infra/scripts/`. After uv is on `PATH`, the
shorter `uv run --frozen poe <task>` form works.

| Service | Local URL | Purpose |
|---|---|---|
| API | `http://localhost:8000` | Submit exception workflows and retrieval queries |
| Grafana | `http://localhost:3000` | Use the focused diagnostics dashboard |
| Prometheus | `http://localhost:9090` | Query bounded metrics |
| Jaeger | `http://localhost:16686` | Inspect local traces |
| LocalStack S3 | `http://localhost:4566` | Inspect the emulated object-storage endpoint |

Each of these ports can be overridden by setting the matching `COLDLINE_API_HOST_PORT`,
`COLDLINE_GRAFANA_HOST_PORT`, `COLDLINE_PROMETHEUS_HOST_PORT`, `COLDLINE_JAEGER_HOST_PORT`, or
`COLDLINE_LOCALSTACK_HOST_PORT` environment variable in your shell environment or a local `.env`
file (copy `.env.example`) if a default collides with something already running on your machine.
Keep the override in place for every `poe` command.

If you change the API port, also set `COLDLINE_API_HOST_PORT` in the shell that runs
`poe load-test`: this command does not read `.env`. Use the same port for startup and load testing.
For example, to use port 8001, run the command for your shell before starting the system:

| Shell | Set the API host port |
|---|---|
| PowerShell | `$env:COLDLINE_API_HOST_PORT = "8001"` |
| macOS/Linux (POSIX) | `export COLDLINE_API_HOST_PORT=8001` |

PostgreSQL, Redis, worker metrics, and OTLP remain inside the Compose network. Codespaces uses the
same `compose.yaml` and keeps every forwarded port private.

## Command path

For a fresh investigation, run the supplied commands in this order:

```text
poe start
poe ready
poe ingest
poe baseline
poe verify
```

| Command | Use |
|---|---|
| `poe ingest` | Run the supplied baseline corpus ingestion inside the API container |
| `poe baseline` | Run every published query and print the baseline evaluation report |
| `poe data-layer` | Run this Task's data-layer checks |
| `poe student-tests` | Run your own tests under `tests/student/` |
| `poe unit` | Run fast isolated behavior tests |
| `poe contract` | Check interfaces, boundaries, submissions, and repository structure |
| `poe smoke` | Check the initialized running platform |
| `poe e2e` | Run the external API-to-worker workflow |
| `poe verify` | Run the public student verification path |
| `poe scenario` | Run the supplied exception-workflow walkthrough |
| `poe load-test` | Run this repository's supplied traffic profile |
| `poe reset-baseline` | Clear exception and Redis data, then restart the worker between load runs |
| `poe restart` | Restart the existing API and worker containers **without rebuilding**; run `poe start` instead after editing source |
| `poe stop` | Remove containers and the network, keeping named volumes |
| `poe reset` | Remove containers, the network, and local named volumes |

`poe ingest` is idempotent: running it twice produces the same rows, the same counts, and the same
corpus digest. `poe reset` removes the database volume, so run `poe ingest` again after a reset.

For Task 2.3, `poe verify` runs readiness, smoke tests, the end-to-end exception workflow, the
answer-sheet check, the data-layer checks, and your own tests under `tests/student/`.

The full `poe data-layer` gate needs the started stack and the ingested corpus. Its checks run
real SQL against PostgreSQL, open a second connection to confirm a write committed, induce a mid-write failure to
confirm nothing partial survives, and drive the live document API while cross-checking the rows
directly in the database.

The focused commands name every check result and can be run as you implement each stage:

| Command | Checks | Implementation needed |
|---|---|---|
| `poe data-layer-mapping` | domain and chunk mapping; parameter safety | parameterized save, document read, and chunk read with complete field mapping |
| `poe data-layer-scope` | SQL scope at the driver boundary; committed-write visibility | working save and all scoped reads, including the ordered listing |
| `poe data-layer-atomicity` | rollback after a failed chunk; duplicate-write consistency | document-plus-chunks transaction handling |
| `poe data-layer-integration` | application HTTP persistence; corpus retrieval regression | completed repository and application wiring; ingested corpus |

Before each focused runtime command, run `poe start` and `poe ready` so the API container uses your
current source and PostgreSQL is ready. After source edits, repeat `poe start` to rebuild it.
The first three groups instantiate the repository directly inside the API container and create
and clean their own fixture rows. They do not require application wiring or corpus ingestion.
The mapping group can pass before SQL scope filtering and atomic rollback are implemented; the
scope group can pass before atomic rollback or application wiring. Run `poe ingest` before the
integration group. Each repository case uses a fresh pool and repository instance; one failed
case does not stop the remaining cases from reporting.

`poe data-layer` retains the full path: rebuild/start, ingest, and all four groups, including the
HTTP and corpus checks. `poe verify` remains the complete public submission gate. Passing a
focused group alone is not Task completion.

## Folder map

```text
repository root/
├── docs/                Student guidance, public contracts, and fidelity notes
│   ├── contracts/       Machine-readable public contracts
│   ├── fidelity/        Local-runtime boundary notes
│   ├── retrieval/       Supplied retrieval pipeline reference
│   └── student/         This Task's student contract
├── infra/               Local setup and runtime configuration
│   ├── corpus/          Supplied synthetic corpus, custody record, and query set
│   └── postgres/        Database initialization
├── loadtest/            Supplied traffic profile and provider-latency harness
├── src/
│   ├── api/             HTTP application code, the retrieval and document paths, student wiring
│   ├── worker/          Background application code
│   ├── domain/          Shared domain code, contracts, service and repository contracts
│   ├── ports/           Application interfaces
│   └── adapters/        Technology-specific implementations
└── tests/
    ├── unit/            Isolated behavior checks
    ├── contract/        Interface, retrieval, data-layer, and repository checks
    ├── doubles/         Supplied deterministic test doubles
    ├── student/         Your own tests
    ├── smoke/           Running-platform checks
    └── e2e/             Supplied workflow tools and checks
```

## Overview

Use the Task 2.3 lesson to decide what to do. This README covers local setup and repository
orientation.

1. `README.md` — local setup, commands, and permitted changes.
2. [`docs/student/task-2-3-contract.md`](docs/student/task-2-3-contract.md) — the four
   requirements, the scoped-read rule, and what each check looks at.
3. `src/domain/repositories.py` — the interface you implement, requirement by requirement.
4. `src/adapters/persistence/document_repository.py` — the file you implement.
5. `src/api/extensions/wiring.py` — where you wire it in.
6. `infra/postgres/002_retrieval_corpus.sql` — the supplied schema you write against.
7. `src/adapters/persistence/corpus_loader.py` — the supplied baseline loader, for reference:
   it shows how the same tables are written, and it is *not* your repository.

The application source lives in five flat packages:

| Package | Responsibility |
|---|---|
| `api` | HTTP delivery, API use cases, the retrieval workflow, student wiring, configuration, and composition |
| `worker` | Background processing, retries, configuration, and composition |
| `domain` | Provider-neutral contracts, state rules, identity, redaction, embedding, chunking, fusion, access constraints, service and repository contracts |
| `ports` | Exactly five visible application interfaces |
| `adapters` | PostgreSQL, pgvector retrieval, Redis Streams, S3-compatible object storage, deterministic model, logs, traces |

`src/api/bootstrap.py` and `src/worker/bootstrap.py` compose each process from its settings and
adapters. Process settings live in `src/api/config.py` and `src/worker/config.py`; other modules
receive settings or collaborators through function and constructor arguments.

## Inspect database and object-store evidence

After `poe ingest`, use the PostgreSQL client already installed in the supplied container.
These read-only commands show the table definitions and the stored chunk representations:

```shell
docker compose exec -T postgres psql -U coldline -d coldline -c "\d documents"
docker compose exec -T postgres psql -U coldline -d coldline -c "\d chunks"
docker compose exec -T postgres psql -U coldline -d coldline -c "SELECT chunk_id, document_id, chunk_index, vector_dims(embedding), search_document, tenant_id, access_tier FROM chunks ORDER BY chunk_id;"
```

Compare the results with `infra/postgres/002_retrieval_corpus.sql` and the supplied corpus
fixtures. For object-store evidence, use `GET /api/v1/corpus/objects?prefix=corpus/`
at the API URL above and inspect `docker compose logs localstack`. The initializer provisions
resources and uploads the supplied objects; `poe ingest` loads the searchable database rows.
Use the Task lesson to decide which observations to collect and which changes are permitted.

## The five ports

Find the available interfaces in `src/ports/`. A port describes an application capability; an
adapter provides it using a concrete technology. Determine which ports are active from your own
runtime evidence rather than from this guide.

| Port | General responsibility |
|---|---|
| `ModelProvider` | Call an AI model service |
| `Retriever` | Look up relevant context or documents |
| `ObjectStore` | Store large binary objects or files |
| `JobQueue` | Publish and consume background work |
| `SecretProvider` | Read API keys and credentials |

## Document API

Task 2.3 activates the application document surface. The routes and the service are supplied; the
repository behind them is yours.

```text
POST /api/v1/documents                        -> persist one document and its chunks atomically
GET  /api/v1/documents?tenant_id=&clearance=  -> list the documents one scope may read
GET  /api/v1/documents/{id}?tenant_id=&clearance=         -> one document, or 404 when out of scope
GET  /api/v1/documents/{id}/chunks?tenant_id=&clearance=  -> that document's readable chunks
```

Every one of them answers 503 until `build_document_repository` returns an implementation.

## Retrieval API

Both endpoints are supplied and are not student work.

```text
POST /api/v1/retrieval/search
  {"query_id": "...", "text": "...",
   "authorization": {"tenant_id": "...", "clearance": "standard"},
   "explain": false}
  -> ranked results, per-stage evidence, prompt context, citations

GET  /api/v1/corpus/objects?prefix=corpus/
  -> the object keys visible through the published ObjectStore port
```

Set `"explain": true` to add the authorization stage's readable pool to the evidence. That costs
one extra query, so ordinary requests leave it off.

## Test levels

| Level | Requires Compose | Main question |
|---|---:|---|
| Unit | No | Does one responsibility behave correctly, including failures? |
| Contract | Some | Do interfaces, schemas, paths, and dependency rules stay compatible? |
| Smoke | Yes | Did the complete local platform initialize and become observable? |
| E2E | Yes | Can an external client complete the supplied workflow? |

Contract checks marked `runtime` need the running stack. `poe contract` skips them; `poe verify`
and `poe runtime-contract` run them.

## Submission checks

Run `poe verify` locally before opening your student pull request. Public GitHub CI repeats
the student checks. The course platform (CMS) runs the required protected grading separately
and associates its results with your submission commit. A green template-export check, or a
skipped student check on an `export/` branch, is not a passing grade. You do not configure
GitHub grading secrets. Follow the Task lesson's instructor-review and progression policy.

## Task boundary

Task 2.3 asks you to implement the application-facing document and chunk data layer against the
supplied PostgreSQL schema, and to wire it into the application. Real persistence is required: a
mock, an in-memory store, or a call into the supplied baseline loader does not satisfy the checks.

These paths are student-editable:

- `src/adapters/persistence/document_repository.py`
- `src/api/extensions/wiring.py`
- anything you add under `tests/student/`
- `submission.yaml`, which stays the empty mapping it ships as

`document_repository.py` is the only file inside `src/adapters/` that any Task permits you to
change; persistence needs a concrete driver, and `domain` may not import one. Everything else in
`src/adapters/` is protected and must keep working, including the corpus loader and the retrieval
adapter. Read
[`docs/student/task-2-3-contract.md`](docs/student/task-2-3-contract.md) for the requirements and
the checks.

### No answers to record

`submission.yaml` asks for nothing, and adding a field fails verification. The deliverable is the
working repository; the checks read PostgreSQL and the running application rather than a claim
that it works.

The supplied defaults are `top_k = 3` and `dense_weight = 0.5`. Each arm returns a fixed
candidate pool of 12 rows before fusion, so the two parameters change what fusion selects without
changing what the arms see.

### Student walkthrough

See **Task 2.3: Implement a data layer** in your course platform for the full walkthrough. In
outline: start the stack and ingest the corpus, read the repository contract and the supplied
schema, implement mapping and parameterized reads and writes, add the scope constraints, wrap the
document-plus-chunks write in one transaction, wire the repository in
`src/api/extensions/wiring.py`, run `poe data-layer` and then `poe verify`, and open your pull
request.

## Operational limits

This local system does not authenticate users, terminate TLS, or manage production secrets.
A retrieval request states its own tenancy and clearance, so that context is an asserted
identity rather than a verified one. The Compose PostgreSQL password and the LocalStack access keys
are local-only non-secret credentials. Never place real credentials, personal data, or production
records in this repository, including in `infra/corpus/`.

Named volumes preserve local PostgreSQL, Redis, Prometheus, Grafana, and Jaeger state across
`poe stop`. LocalStack object contents are deliberately not persisted; the initializer re-uploads
the supplied corpus artifacts on every start. The `poe reset` command deletes the named volumes.
This topology makes no backup, replication, high-availability, disaster-recovery, capacity,
latency-SLO, or availability claim.

See [JobQueue fidelity](docs/fidelity/JobQueue.md),
[ModelProvider fidelity](docs/fidelity/ModelProvider.md),
[ObjectStore fidelity](docs/fidelity/ObjectStore.md), and
[Retriever fidelity](docs/fidelity/Retriever.md) for the active adapter boundaries. The
[local runtime evidence](docs/fidelity/local-runtime.md) records the current measurement and its
qualification limits.
