# Task 2.3 contract — implement the application data layer

Implement `PostgresDocumentRepository` in
`src/adapters/persistence/document_repository.py` and wire it in
`src/api/extensions/wiring.py`. The interface you are implementing is
`DocumentRepository` in `src/domain/repositories.py`; read that file first, because it states
each requirement and why it exists.

## What is already supplied

| Supplied | Where | Note |
|---|---|---|
| `documents` and `chunks` schema, with `pgvector` and text search | `infra/postgres/002_retrieval_corpus.sql` | protected; a schema change belongs to Task 2.6 |
| connection pool, one per process | `src/api/bootstrap.py` | it arrives in your factory; do not make another |
| baseline corpus loader | `src/adapters/persistence/corpus_loader.py` | stays operational and is **not** your repository |
| supplied retrieval adapter | `src/adapters/retriever/postgres_hybrid.py` | keeps reading the same tables |
| deterministic chunking | `src/domain/chunking.py` | the application uses it before your write, so an application write and an ingested document produce identical chunk identifiers |
| the document API and its service | `src/api/routes.py`, `src/api/document_service.py` | already calls your repository; it answers 503 until you wire one |
| the scoped-read rule, stated once | `domain.repositories.readable` | express the same rule as SQL constraints |

## The four requirements

**1. Real persistence.** A committed write is visible to a *separate* PostgreSQL connection. The
check opens its own connection rather than reusing the pool, because reading your own uncommitted
transaction back through the same connection proves nothing.

**2. Domain mapping.** A row becomes a `DocumentRecord` or `ChunkRecord` with the access label and
the whole provenance record intact — source URI, custodian, revision, and timestamp. The check
compares the mapped record against the record that was written, field for field. Dropping a
custodian or a timestamp fails.

**3. Scoped reads.** Every read is constrained inside the SQL:

```text
tenant_id = <scope tenancy>
AND (access_tier = 'standard' OR <scope clearance> = 'restricted')
```

A read that fetches every row and filters in Python is not a scoped read: the other tenancy's rows
still travelled through the process. An out-of-scope document returns `None`, not an error —
telling a caller that a document exists but is out of reach is itself a leak.

**4. Atomic multi-record writes.** A document and its chunks commit together. The check induces a
failure part-way through the chunk inserts and then asserts, from a separate connection, that
**zero** document rows and **zero** chunk rows survive. Committing the document before attempting
the chunks makes that impossible to satisfy.

## The published isolation and transaction setup

What the visibility check proves depends on how it reads, so the setup is published here rather
than left implicit.

| Side | Setup |
|---|---|
| The write | Your `save_document`, through the initialized pool, in one transaction |
| The read | A **second, independent** `asyncpg` connection, opened for the check |
| Isolation | `read committed` — the PostgreSQL default, and nothing in this repository changes it |
| The reader's transaction | **None opened.** Each statement runs in its own implicit transaction |

The point of each row:

- A **separate connection** is what makes this a visibility check at all. Reading the write back
  through the same pool connection would also succeed *inside an uncommitted transaction*, so it
  would prove nothing about committing.
- **No explicit transaction on the reader** means every statement takes a fresh snapshot. At
  `read committed` that snapshot includes everything committed before the statement began, so a row
  the reader can see is a row your write actually committed.
- The check **asserts** the isolation level and that no transaction is open, rather than assuming
  them. In an explicit `repeatable read` or `serializable` transaction, successive reads
  share a transaction snapshot and can miss a commit that landed after that snapshot.
  The snapshot belongs to the transaction, not the whole connection; without an explicit
  transaction, each statement still runs in a separate transaction. See PostgreSQL's
  [transaction isolation documentation](https://www.postgresql.org/docs/16/transaction-iso.html).

This is a **committed-write visibility** check, and that is all it is. It is not a durability or
crash-recovery exercise: nothing here kills the server, pulls a volume, or makes any claim about
what survives a restart. The separate check for rollback injects a failure part-way through a
multi-row write and asserts that no partial update remains.

## Parameterized queries

Bind every value as a parameter. The checks write a document whose title contains an apostrophe, a
semicolon, a SQL comment marker, a dollar-quote, and non-ASCII text, then read it back and compare
byte for byte. They also look up a document by an identifier containing an injected predicate and
require zero rows. A string-formatted query fails at least one of those.

`domain.embedding.format_vector` produces the textual `vector` literal PostgreSQL expects. Bind it
as a parameter and cast it in SQL with `$n::vector`, the way the supplied loader does.

## Wiring

```python
def build_document_repository(pool: asyncpg.Pool) -> DocumentRepository | None:
    return PostgresDocumentRepository(pool)
```

Until that returns an instance, `POST /api/v1/documents` answers 503 and the
application-integration check fails with that reason.

## What the checks verify

| Check | Where it looks |
|---|---|
| committed-write visibility | a second PostgreSQL connection, not the pool |
| domain mapping and provenance | the mapped record compared against the written record |
| scoped reads | another tenancy and a restricted tier, at both document and chunk level |
| parameterized queries | adversarial title text, round-tripped exactly |
| atomic rollback | row counts after an induced mid-write failure |
| application integration | the live HTTP path, cross-checked directly in PostgreSQL |
| regression | the ingested corpus and the retrieval API still answer |

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

## Permitted paths

- `src/adapters/persistence/document_repository.py`
- `src/api/extensions/wiring.py`
- anything you add under `tests/student/`
- `submission.yaml` — which stays the empty mapping it ships as

`document_repository.py` is the only file inside `src/adapters/` that any Task lets you change.
Everything else there, including the corpus loader and the retrieval adapter, is protected and
must keep working.

## No answers to record

`submission.yaml` asks for nothing, and adding a field fails verification. The deliverable is the
working repository; the checks read PostgreSQL and the running application rather than a claim that
it works.
