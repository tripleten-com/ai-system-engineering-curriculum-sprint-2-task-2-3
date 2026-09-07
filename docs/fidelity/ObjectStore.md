# ObjectStore fidelity

The active adapter is `src/adapters/object_store/s3.py`, an S3-compatible client pointed at the
supplied LocalStack container. LocalStack S3 is an **emulator**, not managed object storage.

## What the local runtime proves

- The published `ObjectStore` port shape: `read`, `write`, and `list_keys`.
- That application code reaches stored objects only through that port. No module outside
  `src/adapters/object_store/` imports `boto3` or `botocore`, and both the authoring integrity
  check and a public contract test fail if one does.
- Bucket provisioning is idempotent, so a repeat start, a restart, and a Codespaces resume all
  converge on the same bucket and the same corpus artifacts.
- Provider errors are translated at the boundary: a missing key becomes `ObjectNotFound` and any
  other provider or transport error becomes `ObjectStoreUnavailable`.
- The corpus and its custody record are read from object storage rather than from the container
  filesystem, which is why the Task 2.1 boundary is observable rather than asserted.

## What the local runtime does not prove

LocalStack answering a request establishes nothing about managed S3. In particular this runtime
does **not** prove:

| Not proven | Why it matters |
|---|---|
| IAM and bucket-policy evaluation | The local endpoint accepts development credentials and evaluates no least-privilege policy. A call that succeeds here can be denied in a managed account. |
| Durability and replication | There is no multi-facility storage, no versioning guarantee, and no restore path behind this container. |
| Listing behavior at scale | Amazon S3 caps a `ListObjectsV2` response at 1000 keys and sets `IsTruncated` with a continuation token. This corpus is two objects, so the adapter's pagination loop exits on its first page and is never exercised here. |
| Multipart upload and large-object handling | The corpus artifacts are small; no multipart path is exercised. |
| Encryption at rest, key management, access logging, or object lock | None of these are configured or emulated. |
| Throughput, latency, request cost, or throttling | The container shares one host; no measurement here is a managed-service figure. |

Object contents are deliberately **not persisted** between runs. The initializer re-uploads the
supplied artifacts on every start, so no state accumulates and no run depends on a previous one.

## Credentials

The values in `compose.yaml` are LocalStack development strings. They are not secrets, they grant
nothing outside the local Compose network, and they must never be replaced with a real account
credential in this repository. A managed deployment supplies credentials through its own protected
configuration, never through a file in a student repository.
