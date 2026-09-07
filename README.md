# Multi-Agent Security Policy Q&A

Personal R&D project by Eric Li, exploring **Microsoft Agent Framework**,
**Azure AI Search**, and **Azure OpenAI** for grounded security-policy Q&A.

A multi-agent RAG system that answers questions about enterprise security policies.
A **Microsoft Agent Framework** workflow routes typed Pydantic messages through
moderation, planning, retrieval, context reranking, answer generation, and one
faithfulness gate, grounded on **1,014 NIST SP 800-53 Rev 5 security controls** indexed in
**Azure AI Search**. Every LLM agent runs through **Azure OpenAI**
using the framework's native chat client, with explicit determinism controls
and a safe fallback on every failure path.

## Research focus

- Explore typed agent workflows with explicit routing and bounded execution.
- Study hybrid keyword/vector retrieval and semantic ranking in Azure AI Search.
- Evaluate citation validity, context relevance, and answer faithfulness.
- Investigate prompt-injection defences and fallback behavior when evidence is weak.

```
question ─► Moderation ─► Planner ─► Retrieval ─► ContextRelevance ─► Response ─► Faithfulness ─► answer
             │ blocked                  │ no relevant                         │ failed
             └──────────────────────────┴─────────────────────────────────────┴────► Fallback
```

Every stage is a Microsoft Agent Framework `Executor` node. Planner, Response,
and the graders are LLM agents; Retrieval is a deliberately deterministic
Executor — the Planner already emits structured search steps, so an LLM there
would add latency and nondeterminism without extra reasoning. The core pipeline
(Planner → Retrieval → Response) communicates through
typed Pydantic messages.

See [ARCHITECTURE.md](ARCHITECTURE.md) for the full design, security, scalability and
governance discussion. Sample outputs live in [evaluation/results/](evaluation/results/).

## Dataset

The **NIST SP 800-53 Rev 5 control catalog** provides a public, structured corpus
for experimenting with security-policy retrieval and evidence-based answers.
The project fetches the official OSCAL JSON from
[usnistgov/oscal-content](https://github.com/usnistgov/oscal-content). After excluding
withdrawn controls, **1,014 records** (controls + enhancements, 20 families) are
ingested, each with a title, description and control-family category. An ingestion
sanity check rejects catalogs yielding fewer than 500 records to catch incomplete
downloads or transformation regressions.

## Prerequisites

- Python 3.11+
- An Azure subscription

## Setup

### 1. Create the Azure resources

Create the following resources in your own Azure subscription, preferably in a
dedicated resource group so costs and cleanup remain isolated:

| Resource | Required configuration |
|---|---|
| Azure OpenAI | Deploy `gpt-5-mini` for chat and `text-embedding-3-small` for 1,536-dimension embeddings |
| Azure AI Search | Basic tier, with the semantic ranker's free plan enabled; the application creates the `security-policies` index during ingestion |

Model availability and supported versions vary by Azure region. Deployment names
may differ, provided the names are copied into `.env`.

From the Azure portal, collect the Azure OpenAI endpoint and key, and the Azure AI
Search endpoint and admin key. Copy `.env.example` to `.env` and supply those
values locally. Do not commit the resulting file.

> **Semantic search is enabled by default.** `.env.example` sets
> `USE_SEMANTIC_RANKER=true`. Each planner step runs a hybrid BM25 + vector query,
> and Azure applies its L2 semantic reranker to that initial result set. The free
> semantic plan provides 1,000 semantic queries per month; select the standard plan
> in Azure if sustained pay-as-you-go usage is required. If semantic ranking is
> unavailable, the search client logs the condition and retries as plain hybrid
> search; set `USE_SEMANTIC_RANKER=false` to select that mode explicitly.

### 2. Install and configure

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"         # installs the application and test dependencies
cp .env.example .env            # fill in your Azure endpoints and keys
```

`.env.example` is a template only. Real Azure credentials stay in local
`.env`, which is gitignored and must not be committed.

### 3. Ingest the dataset

```bash
policy-qa ingest
# Ingested 1014 records into index 'security-policies'.
```

## Usage

All runtime commands load configuration from `.env`. Run `policy-qa --help` or
`policy-qa <command> --help` for the generated Typer help.

### Ask one question

```bash
policy-qa ask "What controls apply to API security?"
```

By default, `ask` prints a human-readable answer with citations, grounding
status, confidence, latency, and available quality scores. Add `--json` to print
the complete query trace instead:

```bash
policy-qa ask "Summarise the requirements for access control" --json
```

### Interactive session

Both forms below start a session that reuses the same Azure clients across
questions. Enter `exit`, `quit`, or `q` to stop.

```bash
policy-qa
# equivalent to:
policy-qa interactive
```

### Ingest and evaluate

```bash
policy-qa ingest      # download, transform, embed, and upload the NIST catalog
policy-qa evaluate    # run evaluation/test_queries.json and rewrite evaluation/results/
```

### Reproducing experiments

Create the Azure resources described above and configure your local `.env` using
`.env.example`. Run ingestion, then use `policy-qa evaluate` to capture a new set
of results. The committed traces and report in `evaluation/results/` provide a
reference run for comparing retrieval, grounding, and latency. Sample CLI output
is also available in [evaluation/sample_usage/](evaluation/sample_usage/).

Record deployment names, prompt versions, and retrieval thresholds when comparing
runs. Keep Azure credentials local and out of source control.

### Example output

Human-readable `ask` output (abridged):

```
================================================================================
MULTI-AGENT SECURITY POLICY Q&A
================================================================================
User Query : What controls apply to API security?
Status     : SUCCESS
--------------------------------------------------------------------------------

ANSWER:

Controls from the provided set that apply to API security (supported aspects only):
- Protect API traffic confidentiality and integrity with cryptography ... (SC-8(1)).
- Log, review, and analyze API-related audit activity ... (AU-6).
- Apply least privilege to API access, components, and interfaces ...
  (AC-6, SA-8(14), SA-17(7)).

--------------------------------------------------------------------------------
📊 RETRIEVAL & GROUNDING TELEMETRY
--------------------------------------------------------------------------------
[+] Source Citations : SC-8(1), AU-6, AC-6, SA-8(14), SA-17(7)
[+] Grounding Status : VERIFIED (Grounded: True)
[+] Confidence Level : HIGH
[+] Latency Profile  : 45,347 ms
[+] Quality Metrics  :
    - Context Relevance : 0.94 (avg graded relevance)
    - Faithfulness Score: 1.00 (higher is more grounded)
```

This abridged example uses content and metrics from the committed evaluation
run, formatted as the CLI presents them. Latency and model wording can vary with
Azure model capacity.

Structured JSON logs are written to `logs/policy-qa.jsonl` by default, one line per
agent hop and tagged with a per-query correlation ID. This keeps CLI output clean while
retaining an input/output audit trail for debugging and experiment analysis:

```bash
tail -f logs/policy-qa.jsonl
```

Set `LOG_TO_CONSOLE=true` to also emit the same JSON logs to stderr.

### Prompt-injection defence

The project handles both direct and indirect prompt injection. The first
moderation node rejects user attempts to override or extract system instructions
before planning or search runs. Retrieved index text is also treated as untrusted:
one shared builder XML-escapes every field, encloses each result in a numbered
`<document>` boundary, and labels the block as reference data. The responder and
grading prompts explicitly prohibit following instructions inside those boundaries.
Escaping prevents a malicious indexed value from closing its boundary and becoming
an apparent instruction. Azure OpenAI's platform content filter remains an
additional layer, and focused tests exercise tag and attribute breakout payloads.

### Quality gates

Thresholds are environment-tunable. Azure's semantic reranker uses its native
0–4 score; the LLM graders use 0–1 scores.

| Variable | Default | Scale | Gate |
|---|---:|---:|---|
| `RERANKER_THRESHOLD` | 1.5 | 0–4 | when semantic scores are present, no result at or above this value short-circuits context grading |
| `CONTEXT_RELEVANCE_SCORE_THRESHOLD` | 0.5 | 0–1 | documents graded below this value are dropped; none left → safe fallback |
| `FAITHFULNESS_SCORE_THRESHOLD` | 0.7 | 0–1 | an answer below this value is withheld → safe fallback |

## Evaluation

`policy-qa evaluate` runs the five test queries in
[evaluation/test_queries.json](evaluation/test_queries.json) — the four use-case
queries covering API security, cloud data protection, access control, and logging,
plus one out-of-scope query that must trigger the safe
fallback. Each query is scored by:

1. **Deterministic checks** — citation validity (citations ⊆ retrieved controls) and
   answer/evidence token overlap.
2. **LLM judge** (fixed structured rubric) — retrieval relevance and
   groundedness, 1–5.

Committed results: [evaluation/results/report.md](evaluation/results/report.md).
These five queries are a small exploratory baseline; they do not establish
performance across the full catalog or production workloads.

## Tests

```bash
pytest        # OSCAL transform (≥500 records, schema completeness), contracts,
              # fallback paths, and every conditional edge in the graph (test_routing.py)
```

## Project layout

```
.
├── .env.example                         # credential-free configuration template
├── .gitignore
├── ARCHITECTURE.md                      # design, security and scalability notes
├── README.md
├── evaluation/
│   ├── test_queries.json                # five baseline evaluation queries
│   ├── results/                         # committed JSON traces + Markdown report
│   └── sample_usage/                    # CLI examples from recorded outputs
├── src/policy_qa/
│   ├── agents/
│   │   ├── llm/                         # model-backed workflow executors
│   │   │   ├── moderation.py
│   │   │   ├── planner.py
│   │   │   ├── relevance_grader.py
│   │   │   ├── responder.py
│   │   │   └── faithfulness_grader.py
│   │   ├── deterministic/               # executors that make no LLM call
│   │   │   ├── retrieval.py
│   │   │   ├── meta_knowledge.py
│   │   │   └── safe_fallback.py
│   │   └── shared/
│   │       ├── agent_factory.py         # common Agent Framework construction
│   │       └── prompt_blocks.py         # escaped, delimited untrusted context
│   ├── ingestion/
│   │   ├── catalog_download.py          # fetch and cache the OSCAL catalog
│   │   ├── catalog_transform.py         # OSCAL JSON → policy records
│   │   └── pipeline.py                  # index creation, embedding and upload
│   ├── prompts/                         # versioned agent and grader prompts
│   ├── schemas/                         # typed inter-agent Pydantic contracts
│   │   ├── answers.py
│   │   ├── grading.py
│   │   ├── moderation.py
│   │   ├── planning.py
│   │   ├── records.py
│   │   └── retrieval.py
│   ├── search/
│   │   ├── embeddings.py                # Azure OpenAI embeddings
│   │   ├── index_schema.py              # vector + semantic index definition
│   │   └── search_service.py            # hybrid search and semantic reranking
│   ├── utils/
│   │   ├── logging_setup.py             # rotating structured JSONL logs
│   │   ├── retry.py                     # transient-error retry policy
│   │   └── text.py                      # normalization and escaping helpers
│   ├── cli.py                           # command-line entry points
│   ├── config.py                        # environment configuration and validation
│   ├── evaluator.py                     # deterministic checks + LLM judge
│   ├── graph.py                         # Agent Framework workflow topology
│   ├── orchestrator.py                  # clients, workflow execution and errors
│   ├── report.py                        # human-readable CLI rendering
│   └── tracing.py                       # per-query state and trace records
├── tests/
│   ├── fakes.py
│   ├── test_catalog_transform.py
│   ├── test_fallback.py
│   ├── test_injection_defence.py
│   ├── test_logging.py
│   ├── test_routing.py
│   └── test_schemas.py
├── pyproject.toml                        # package metadata and dependencies
└── requirements.txt                     # alternative dependency list
```

## Costs and infrastructure lifecycle

Azure AI Search Basic is billable while provisioned; chat and embedding usage are
also metered. Review the current Azure pricing before creating resources. When
finished, delete the dedicated experiment resource group through the Azure portal
and verify that no resources remain.

Production infrastructure should be managed declaratively with Terraform or
Bicep through a reviewed CI/CD workflow. Imperative provisioning and destructive
teardown scripts are not included in this research prototype.

## Limitations

- gpt-5-family reasoning models fix `temperature`/`top_p`; pinned deployments,
  structured outputs and exact
  retrieval improve stability, but responses are not bit-identical.
- gpt-4o-mini / gpt-4.1-mini were blocked for new deployments ("deprecating state")
  at build time, hence gpt-5-mini; the model is swappable via one env var.
- Semantic ranking uses the service's 1,000-query monthly free allowance by default;
  sustained usage requires the `standard` semantic billing plan.
- The corpus is a public catalog standing in for private enterprise policy; swapping
  the ingestion module is the only change needed for a different corpus.

## Future work

- Add a dedicated conversational route for greetings, follow-up questions and
  limited policy-related chit-chat, while keeping factual policy answers grounded
  in retrieved evidence.
- Build a labelled query-to-control relevance dataset and tune the semantic
  reranker, context-relevance and faithfulness thresholds against precision,
  recall and fallback rates instead of relying on manually selected defaults.
- Introduce Corrective RAG (CRAG): assess retrieval quality, rewrite weak queries,
  retry retrieval and use a controlled secondary source before returning the safe
  fallback.
- Improve retrieval with policy-aware query expansion, control-family filters and
  offline comparison of hybrid, semantic and vector-only search configurations.
- Add multi-turn session context with explicit limits so follow-up questions can
  resolve prior references without allowing conversation history to override
  system instructions or retrieved policy text.
- Use a separate model or human-reviewed benchmark for evaluation to reduce
  self-grading bias, and track quality, latency and cost regressions in CI.
- Add an authenticated API layer, container deployment, managed identity,
  telemetry dashboards, Terraform or Bicep infrastructure, and automated deployment
  checks for production operation.
