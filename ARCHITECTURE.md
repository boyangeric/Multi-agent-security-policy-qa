# Architecture — Multi-Agent Security Policy Q&A

## System design

The system answers security-policy questions over 1,014 NIST SP 800-53 Rev 5
controls stored in Azure AI Search. Microsoft Agent Framework orchestrates the
planning, retrieval, and response stages, with moderation and grounding gates.
The project explores how these components work together in a bounded RAG workflow.
All model-backed nodes use the framework's Azure OpenAI chat client against a
pinned Azure OpenAI deployment. The model deployment is configurable, while
prompts, structured output contracts, and inference options are centralized.

```text
User
  │
  ▼
Moderation ──blocked──────────────────────────────────────┐
  │ allowed                                               │
  ▼                                                       │
Planner Agent ──QueryPlan (1–3 focused search steps)      │
  │                                                       │
  ▼                                                       │
Retrieval Agent ──parallel hybrid Azure AI Search         │
  │                                                       │
  ▼                                                       │
Context relevance ──no useful evidence───────────────────-┤
  │ reranked evidence                                     │
  ▼                                                       │
Response Agent ──DraftAnswer                              │
  │                                                       │
  ▼                                                       │
Faithfulness gate ──failed───────────────────────────────-┤
  │ passed                                                │
  ▼                                                       ▼
FinalAnswer                                           Fallback
```

The Planner interprets broad technology questions in terms of the
technology-neutral control catalog and emits one to three structured
`SearchStep` records. The Retrieval Agent executes every step directly and
concurrently. It reserves evidence from each step before filling the remaining
top-five slots by Azure's ranked order, preventing one topic from crowding out a
multi-topic plan.

Every stage is a first-class Microsoft Agent Framework `Executor` node wired
into the workflow graph. Planner, Response, and the graders reason with the LLM;
Retrieval is a *deliberately deterministic* Executor. Because the Planner has
already produced structured `SearchStep` queries, letting an LLM re-decide what
to search would only add latency and nondeterminism with no extra reasoning —
so the Retrieval Agent applies the plan to Azure AI Search exactly and returns
typed results. The Planner → Retrieval → Response pipeline uses typed Pydantic
messages to keep stage boundaries explicit and testable.

Azure AI Search combines keyword and HNSW vector search, then applies the native
L2 semantic ranker through the index's `semantic-default` configuration. The
provisioned service uses Basic tier and `USE_SEMANTIC_RANKER=true` is the runtime
default. Azure owns candidate retrieval and ordering; the application does not
compute a second client-side similarity score. If semantic ranking is unavailable,
the client logs the condition and retries as plain hybrid search. When semantic
scores are returned, `RERANKER_THRESHOLD` provides an early relevance gate. A
single batched context grader then scores all selected candidates against the
original question, removes irrelevant evidence, and orders the survivors before
response generation.

The Response Agent sees only numbered retrieved controls and must return a
schema-constrained `FinalAnswer`. Citations are validated against the evidence.
A single faithfulness grader checks every answer against that same evidence.
Failure at moderation, retrieval, citation validation, or faithfulness produces
a deterministic fallback without further model calls.

## Structured interaction and determinism

Agent Framework edges carry Pydantic models including `QueryPlan`,
`RetrievalResult`, `RerankedContext`, `DraftAnswer`, and `FinalAnswer`. Search
results are assembled from Azure AI Search responses, never from model text.

Determinism is improved through:

- fixed prompts and schema-constrained outputs;
- a fixed model seed in the shared options where supported;
- a pinned Azure model deployment;
- deterministic citation validation and fallback behavior;
- bounded workflow execution with no quality-regeneration loops.

Model inference is not guaranteed to be bit-identical, so committed evaluation
results measure both retrieval relevance and answer grounding.

## Security and governance

- Secrets are supplied through environment variables and excluded from source
  control. Production deployments should use managed identity and Key Vault.
- Direct prompt injection is checked by the first moderation node. A blocked
  request routes immediately to a deterministic fallback, before planning,
  retrieval, or response generation.
- Retrieved text is treated as untrusted data. A shared prompt-block builder
  XML-escapes content and metadata, then wraps each result in an explicit,
  numbered `<document>` delimiter. Responder and grader system prompts prohibit
  following directives found inside these boundaries. Escaping prevents indexed
  text from closing or forging a boundary; focused tests cover closing-tag and
  attribute-breakout payloads.
- Azure OpenAI model content filtering provides an additional platform-level
  layer beneath the application moderation gate.
- Answers cite NIST control IDs, providing evidence lineage.
- Structured JSONL logs capture stage inputs, outputs, latency, and correlation
  IDs in `logs/policy-qa.jsonl`; log files rotate and are excluded from Git.
- The evaluation suite checks citations, evidence overlap, expected fallback
  behavior, retrieval relevance, and groundedness.
- Runtime and ingestion identities should be separated in production so the
  query service has search-read and inference permissions only.

## Scalability and operations

The workflow is stateless per request and can be hosted behind an API or queue
and scaled horizontally. Azure AI Search scales independently through replicas
and partitions. Ingestion batches embeddings and document uploads.

Planner search steps run concurrently, reducing query latency. Normal requests
make five bounded model calls: moderation, planning, context relevance,
response, and faithfulness. There are no retry-generation loops. Azure search
and embedding calls use transient-error retry policies; any unhandled pipeline
failure is converted to a safe typed response.

Configuration is environment-driven, including deployments, index name, top-k,
the native semantic reranker threshold, 0–1 grader thresholds, semantic ranker
use, workflow bounds, and logging. Production infrastructure should be managed
declaratively with Terraform or Bicep through a reviewed CI/CD workflow; this
research prototype documents the required Azure resources without including imperative
provisioning or destructive teardown scripts.
