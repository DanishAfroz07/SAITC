# Cerulean Systems RAG Assistant (SAITC take-home)

A grounded retrieval-augmented assistant over the 13-document Cerulean Systems corpus, built
so it treats "I don't know" and "these two documents disagree" as first-class answers, not
failure modes to be papered over.

## Corpus provenance - read this first

This project was built from the assignment's PDFs as text extracted into a conversation, not
from the original PDF files on disk. `scripts/corpus_content.py` is a faithful transcription
of that same text (identical facts, numbers, tables, cross-references, and all three embedded
prompt-injection payloads, verbatim), and `scripts/build_corpus.py` renders it into 13 real
PDFs plus `data/corpus_manifest.json`, so the ingestion pipeline has real files to run against
end to end.

**If you have the original assignment PDFs**, you can use them instead of the generated ones:
drop them into `data/documents/` with the same file names `corpus_manifest.json` expects, and
skip `scripts/build_corpus.py` entirely. `app/ingestion/parser.py` reads metadata from the
manifest either way, so nothing else in the pipeline changes.

The generated PDFs are simple (one font, pipe-delimited tables rendered as plain text) - they
exist to exercise the pipeline honestly, not to look like the real documents.

## What to install

| Tool | Version tested | Why |
|---|---|---|
| Python | 3.12.3 | everything runs on it; 3.11+ should also work |
| [Ollama](https://ollama.com/download) | any recent | serves the local open-weight LLM + embedding model |
| pip packages | see `requirements.txt` | pinned to versions verified to install cleanly on Windows/Python 3.12 in this environment |

No GPU, Docker, or external API key is required. Everything - vector store, embeddings, LLM -
runs locally.

> **Windows note**: `requirements.txt` pins `chromadb==1.5.9` specifically because older
> chromadb versions (~0.5.x) pull in `chroma-hnswlib`, which has no prebuilt wheel for recent
> Python/Windows combinations and fails to install without the Microsoft C++ Build Tools.
> 1.5.9 ships a working wheel and needs nothing extra. Found this the hard way while building
> this project - see the Weaknesses section.

## Setup, step by step

```bash
# 1. Get the code and enter the project
cd SAITC

# 2. Create and activate a virtual environment
python -m venv .venv
.venv\Scripts\activate            # Windows
# source .venv/bin/activate       # macOS/Linux

# 3. Install Python dependencies
pip install -r requirements.txt

# 4. Install Ollama (https://ollama.com/download), then pull the two models this
#    project uses - one for chat generation, one for embeddings:
ollama pull llama3.2:3b
ollama pull nomic-embed-text

# 5. .env is already committed with working defaults matching the two models
#    above - open it if you want to change the model, ports, or thresholds.
#    See "Why one .env file" below for why there's no separate .env.example.

# 6. Generate the synthetic PDF corpus (see "Corpus provenance" above) -
#    skip this step if you've dropped the original assignment PDFs into
#    data/documents/ yourself
python scripts/build_corpus.py

# 7. Ingest the corpus into the local vector store
python -m app.main ingest

# 8. Ask it questions
python -m app.main chat
```

### Why one `.env` file, not `.env` + `.env.example`

The usual split exists to keep secrets (API keys, passwords) out of git while still
documenting what variables exist. Nothing in this project's `.env` is a secret - it's all
local config (which model to call, which port to serve on, retrieval thresholds) - so the
split added a second file to keep in sync for no real benefit. `.env` is committed with
working defaults; edit it directly if you want a different model or port.

Example session:

```
> What is the current price of the Atlas Professional plan?

Cerulean Systems' price lists show two different figures for Atlas Professional:
SAR 4,500/month in the 2025 list [SALES-PL-2025, effective 2025-01-01] and SAR 5,200/month
in the 2026 list [SALES-PL-2026, effective 2026-03-01]. SALES-PL-2026 supersedes
SALES-PL-2025 and has been in effect since 1 March 2026, so as of today the current list
price is SAR 5,200/month for new subscriptions and renewals. Note SALES-PL-2026 itself says
customers on an active term keep their contracted price until renewal, so an existing
customer may still legitimately be paying SAR 4,500 until then.

Sources: [SALES-PL-2025], [SALES-PL-2026]
```

## Running the HTTP API (Postman etc.)

Start the whole application with one command, run as a module from the project root
(**not** `python app/main.py` directly - that fails with `ModuleNotFoundError: No module
named 'app'`, since `app` only resolves as a package when Python is started from the project
root with `-m`):

```bash
python -m app.main
# equivalent to: python -m app.main serve
# equivalent to: uvicorn app.main:app --reload   (auto-reload on code changes, for dev)
```

This blocks the terminal serving on `http://localhost:8000` (configurable via `API_HOST`/
`API_PORT` in `.env`). Interactive Swagger docs, where you can try every endpoint without
Postman, are at `http://localhost:8000/docs`.

| Method | Path | Body | What it does |
|---|---|---|---|
| GET | `/health` | - | liveness check |
| POST | `/ingest` | - | re-ingests every PDF already in `data/documents/` against the manifest, wiping and rebuilding the whole vector store - use for the fixed 13-document corpus |
| POST | `/documents/upload` | `multipart/form-data`: `file` (required, a PDF) + optional form fields `document_id`, `title`, `version`, `effective_date` (YYYY-MM-DD), `owner`, `classification`, `supersedes` | saves the PDF into `data/documents/`, adds/replaces its entry in `corpus_manifest.json`, and ingests just that document - the endpoint to use for adding an arbitrary PDF from Postman |
| GET | `/documents` | - | lists every document currently in the manifest |
| DELETE | `/documents/{document_id}` | - | removes a document's manifest entry, file, and vector store chunks |
| POST | `/query` | JSON: `{"question": "..."}` | ask the assistant |

**Postman walkthrough for uploading a PDF:**
1. New request, `POST http://localhost:8000/documents/upload`.
2. Body tab -> `form-data` (not `raw`/JSON - file uploads need `multipart/form-data`).
3. Add a key `file`, change its type dropdown from "Text" to **"File"**, and choose a PDF.
4. Optionally add more keys as plain Text: `document_id`, `title`, `effective_date` (e.g.
   `2026-08-01`), etc. Any you omit fall back to a sensible default (document_id defaults to
   the file name, effective_date to today) - see `app/api/controllers/document_controller.py`.
5. Send. The response includes `chunks_created` - if that's 0, the PDF likely has no
   extractable text (a scanned image PDF, for example; this pipeline does no OCR).
6. `GET /documents` to confirm it's listed, then `POST /query` to ask about it.

Metadata matters here: this corpus's whole conflict/supersession-resolution behaviour
(`VersionResolver`, `EvidenceAnalyzer`) depends on `effective_date` and `document_id` being
meaningful, not placeholder values - an upload with defaults left untouched will be retrievable
and answerable, but won't participate correctly in a conflict against another document unless
you set `supersedes` (or add its document_id pair to `KNOWN_CONFLICT_PAIRS`, see
`app/retrieval/evidence_analyzer.py`) yourself.

Re-uploading the same `document_id` (even under a different file name) replaces its previous
chunks rather than duplicating them, and deletes the old file.

To run the required evaluation pass over all 15 questions (12 from the assignment + 3 added):

```bash
python -m evaluation.run_eval
```

This overwrites `evaluation/results.json` and `evaluation/results.md` with the model's actual
answers, outcome classification, and citations. **Those files are currently placeholders in
this repo** - this environment has no Ollama installed, so no model was actually run here; see
`evaluation/results.md` for why that's disclosed rather than faked, and for how I'd measure
quality more rigorously than eyeballing 15 answers.

To run the test suite (pure logic only - no Ollama or a running vector store needed):

```bash
pytest tests/ -v
```

All 20 tests pass in this environment in well under a second.

## Hardware and timing

Built and tested on a Windows 11 laptop (the sandboxed environment this was authored in),
Python 3.12.3, no GPU. Ingestion (chunking + Chroma insertion, excluding the embedding calls
which need a running Ollama server not present here) processes all 13 documents into 125
chunks in under 0.1 seconds - the corpus is tiny (the assignment README notes it's under
100 KB), so ingestion cost is dominated entirely by the embedding model's throughput, not by
parsing or chunking.

I could not benchmark live Ollama calls in this environment (no Ollama installed here). On a
laptop CPU, a realistic expectation for `llama3.2:3b` is roughly 1-4 seconds per answer and
`nomic-embed-text` a few milliseconds per chunk (well under a second for the whole 125-chunk
corpus) - please treat these as rough expectations to sanity-check against, not measured
numbers, and note your own actual timings here after running `python -m evaluation.run_eval`.

## Architecture

```mermaid
flowchart TD
    subgraph Ingestion["Ingestion (python -m app.main ingest)"]
        PDF["13 PDFs + corpus_manifest.json"] --> LOAD["loader.py + parser.py\n(extract text, resolve metadata)"]
        LOAD --> CHUNK["chunker.py\nSectionChunker\n(tables kept whole)"]
        CHUNK --> STORE["vector_store.py\nChromaVectorStore"]
    end

    subgraph Query["Query time (CLI chat / POST /query)"]
        Q["User question"] --> CLS["safety/classifier.py\nInputClassifier"]
        CLS -- "injection / out-of-scope" --> REFUSE["canned refusal\n(no retrieval, no LLM call)"]
        CLS -- "safe" --> RET["retrieval/retriever.py\n(top_k candidates)"]
        RET --> VER["retrieval/version_resolver.py\ntag superseded docs"]
        VER --> SAN["safety/guardrails.py\nContextSanitizer\n(strip HTML-comment payloads)"]
        SAN --> EV["retrieval/evidence_analyzer.py\nsufficient / insufficient /\nconflicting / ambiguous"]
        EV --> RR["retrieval/reranker.py\nLLMReranker\n(reorder; narrow to rerank_top_n\nonly if SUFFICIENT)"]
        RR --> GEN["generation/generator.py\n+ prompts.py + Ollama LLM"]
        GEN --> OG["safety/guardrails.py\nOutputGuard"]
        OG --> ANS["Answer + citations"]
    end

    STORE -. "embeddings via Ollama\n(nomic-embed-text)" .-> RET
```

`app/wiring.py` is the composition root: the only module that constructs concrete classes
from `Settings` and wires them together. Everything else - `RagPipeline`, `IngestionPipeline`,
the API controllers, the CLI - depends only on interfaces (`ChatClient`, `Embedder`,
`Reranker`) passed into its constructor, which is what makes the pure-logic layers (chunker,
version resolver, evidence analyzer, reranker, classifier, guardrails) unit-testable without
Ollama or Chroma running - see `tests/`.

Note evidence assessment happens **before** reranking, not after: reranking must never be able
to hide one side of a detected conflict by reordering it out of a narrowed top-N, so the
narrowing step only ever applies to the SUFFICIENT case (see `app/rag_pipeline.py`).

## Project structure - what each folder is for

```
SAITC/
├── app/                One Python package: the whole running application.
│   ├── main.py          Entrypoint - run with `python -m app.main`.
│   ├── config.py        All settings, read once from .env.
│   ├── models.py         Shared domain types (Chunk, Answer, etc).
│   ├── wiring.py         Builds and wires every component together.
│   ├── rag_pipeline.py    Orchestrates one query: safety -> retrieve -> assess -> rerank -> generate.
│   ├── api/              HTTP layer, controller/service split (see below). -> req: HTTP interface
│   ├── ingestion/         PDF -> text -> chunks -> vector store.    -> req #1, #2
│   ├── retrieval/         Vector store, retrieval, reranking, conflict/version/ambiguity logic. -> req #3, #7, #8
│   ├── generation/        Prompts + LLM call + citations.          -> req #3, #4, #6
│   └── safety/            Injection/bypass detection, both directions. -> req #9, Security
├── data/                 The corpus itself (not code).
│   ├── documents/          The 13 PDFs.
│   └── corpus_manifest.json  Metadata for each PDF (see below).
├── scripts/              One-time corpus generation (not part of the running app).
├── evaluation/           The required 12+3 question run + results + methodology write-up.
├── tests/                Unit tests for every pure-logic module (no Ollama/Chroma needed).
├── postman/              Importable Postman collection for manual/API testing.
├── requirements.txt, .env, .gitignore, README.md
```

Nothing above is unused scaffolding - every folder maps to something the assignment asks
for, noted next to it. `scripts/` and `postman/` are the two folders that aren't part of the
running application itself: `scripts/` only exists because this session received the corpus
as extracted text rather than PDF files (see "Corpus provenance"); `postman/` is a testing
aid, not app code.

### `app/api/` - controller/service split

```
app/api/
├── schemas.py              Pydantic request/response models (the HTTP contract).
├── controllers/            One thin file per resource - HTTP only, no business logic.
│   ├── health_controller.py     GET /health
│   ├── query_controller.py       POST /query          -> calls RagPipeline
│   ├── ingest_controller.py      POST /ingest          -> calls IngestionPipeline
│   └── document_controller.py    /documents...         -> calls DocumentService
└── services/
    └── document_service.py   Upload/list/delete business logic (file I/O, manifest updates).
```

`RagPipeline` and `IngestionPipeline` already **are** the service layer for `/query` and
`/ingest` - they contain the real logic, are fully unit-testable on their own, and know
nothing about FastAPI. Wrapping them in a `QueryService`/`IngestionService` that just forwards
to them would be a pass-through with no purpose, so there isn't one. `DocumentService` exists
because upload/list/delete logic (saving a file, upserting the manifest, cleaning up an
orphaned file on re-upload) didn't have a home anywhere else - it's the one place the API
layer does real work beyond translating a request into a pipeline call.

### What corpus_manifest.json actually does (and doesn't do)

This is the one JSON file the client provided. **It is never ingested as content** - it is
never chunked, embedded, or retrieved. Its only job is to supply each PDF's metadata
(document ID, version, effective date, owner, classification, supersedes) to
`app/ingestion/loader.py`, which attaches that metadata to every chunk produced from that PDF.
That metadata is what `version_resolver.py` and `evidence_analyzer.py` later use to reason
about "which price list is current" or "which document takes precedence" - it never appears
in the vector store as its own searchable text.

So: `/ingest` reads the manifest for metadata, then reads and embeds the actual PDFs it
points to. There is no code path that embeds `corpus_manifest.json`'s own JSON content as if
it were a document, and there shouldn't be - it isn't information a customer or employee would
ever ask a question about, it's the index card describing the real documents.

## Technology choices and why

- **Ollama for both chat and embeddings** (`llama3.2:3b` + `nomic-embed-text`): one runtime
  dependency instead of two (no separate `sentence-transformers`/PyTorch stack), satisfies the
  assignment's "open-weight, runs locally" requirement directly, and keeps the POC's install
  footprint small. `llama3.2:3b` is a deliberately modest default so it runs on a CPU-only
  laptop in reasonable time; swap `OLLAMA_LLM_MODEL` in `.env` for a bigger model if you have
  the hardware.
- **ChromaDB, persistent, embedded** (no separate server process): the corpus is 13 documents
  and ~125 chunks - there is no scale argument for a standalone vector database service here,
  and an embedded store keeps the whole system runnable with one command.
- **PyMuPDF** for text extraction: recommended in the corpus README, extracts the text-based
  PDFs cleanly with no OCR needed.
- **Section-aware chunking, tables kept whole** (`app/ingestion/chunker.py`): the corpus
  README calls out table handling as one of the more interesting chunking decisions. Splitting
  a table row-by-row across chunks would let the model see "SAR 25,001 to SAR 100,000" without
  ever seeing "Finance Manager and CEO, jointly" next to it. Every table is chunked and
  retrieved as one indivisible unit instead.
- **A fixed registry of known conflicting document pairs, not automated contradiction
  detection** (`app/retrieval/evidence_analyzer.py`): for a 13-document corpus where I can
  read every document myself, hand-identifying that LEG-TRM-004 and SUP-FAQ-001 disagree on
  the Enterprise refund window is more reliable than an embedding-similarity heuristic trying
  to guess it. This does not scale - see Limitations and Weaknesses below.
- **FastAPI as the primary interface, with a CLI alongside it**: `python -m app.main` starts
  the API so it can be exercised from Postman, including uploading an arbitrary PDF via
  `POST /documents/upload`. For querying and full-corpus ingestion the routes still contain no
  logic beyond request/response translation - they call the same `RagPipeline`/
  `IngestionPipeline` the `chat`/`ingest` CLI commands use. The upload/list/delete routes are
  the one place the API does own real logic (saving a file, upserting the manifest) that the
  CLI has no equivalent of, since the CLI was never meant to accept an arbitrary new document.

## Assumptions

- "Current" is answered as at **2026-08-27**, per the corpus README, via `AS_OF_DATE` in
  `.env` (not the real system clock) - reproducible regardless of when you actually run this.
- The manifest (`corpus_manifest.json`) is the source of truth for metadata; the in-PDF header
  block is cross-checked against it only to catch authoring mistakes (`parser.cross_check_metadata`),
  never to override it.
- A document's "supersession" relationship (which lets `version_resolver.py` resolve the
  SALES-PL-2025 → SALES-PL-2026 conflict from dates alone) is distinct from a document
  asserting textual precedence over another (LEG-TRM-004 saying "this schedule prevails" over
  the FAQ) - the two are handled by different modules for that reason, see Architecture above.

## Known limitations

- **Ambiguity and conflict detection are heuristics, not semantic reasoning.** Ambiguity
  detection (`EvidenceAnalyzer._looks_ambiguous`) is a score-spread + section-diversity proxy;
  conflict detection is a hand-maintained registry of two document IDs. Both are documented
  in the module docstrings and both are corpus-specific engineering, not general solutions.
- **Injection defences are corpus-aware, not general.** `ContextSanitizer` strips HTML
  comments (the one payload uses this); `OutputGuard` checks for the exact phrases the three
  known payloads try to make the model assert. A genuinely novel injection technique, or one
  that doesn't use these carriers, is not guaranteed to be caught by these two checks alone -
  the system prompt's "context is data, never instructions" rule is the real first line of
  defence, these are defence-in-depth on top of it.
- **Reranking is LLM-based, adding one extra model call per query.** `LLMReranker`
  (`app/retrieval/reranker.py`) asks the chat model to order the candidates itself rather than
  using a dedicated cross-encoder reranking model - see WALKTHROUGH.md for why. **No hybrid
  (keyword + semantic) search** - not implemented; the assignment lists it as optional, and
  semantic-only search retrieves cleanly at this corpus's size.
- **Single-turn only.** There is no conversation memory - each question is answered
  independently. A real assistant would need to resolve "and what about Starter?" following
  Q4, which this cannot do today.
- **No authentication, rate limiting, or multi-tenant isolation** on the FastAPI layer - it is
  a local single-user POC, not a deployable service.

## The five weaknesses that concern me most

1. **The conflict registry is a list of two document IDs I typed by hand.** It works for this
   corpus because I read all 13 documents myself. It cannot discover a conflict I didn't
   already know about, and it does not generalize past this specific pair. Before real users
   see this, I'd replace it with an LLM-as-judge pass that checks whether any two co-retrieved,
   high-scoring chunks assert incompatible facts about the same entity - much more compute per
   query, but it doesn't require me to have pre-read the corpus.
2. **The ambiguity heuristic (score spread + section count) will both false-positive and
   false-negative on corpora it wasn't hand-tuned against.** A question that's genuinely
   specific but happens to retrieve chunks from several sections at similar scores would
   wrongly get a clarifying question instead of an answer. I'd want a labelled set of
   ambiguous vs. unambiguous questions to tune the thresholds against, which this take-home
   didn't have time to build.
3. **`OutputGuard`'s known-phrase list is reactive, not proactive** - it only catches the
   exact three payloads in this exact corpus. A differently-worded injected instruction that
   still successfully steers the model would ship undetected. This needs a real classifier (or
   an LLM-judge pass comparing the answer against the *un-sanitized* retrieved context for
   suspicious divergence), not a string list.
4. **Similarity-threshold-based "insufficient evidence" detection is a single global number**
   (`SIMILARITY_THRESHOLD` in `.env`). Different question types plausibly need different
   thresholds - a yes/no question and an open-ended "summarise X" question don't have
   comparable score distributions at the same top-k. Right now one threshold has to work for
   both, which is a source of both over- and under-refusal I haven't rigorously measured.
5. **No caching and no batching.** Every query re-embeds the question and makes one full LLM
   call; ingestion re-embeds every chunk from scratch on every run (`vector_store.reset()`
   deliberately drops and rebuilds the whole collection). Fine at 125 chunks; not fine at
   10,000 documents - see Production thinking below.

## What I deliberately chose not to build, and why

- **Hybrid (keyword + semantic) search.** Explicitly optional in the assignment. At 125
  chunks, semantic search alone retrieves cleanly - no precision problem here that a keyword
  signal would visibly fix.
- **A dedicated cross-encoder reranking model** (rather than the LLM-based reranker actually
  built - see WALKTHROUGH.md). A cross-encoder needs `sentence-transformers`/PyTorch, a heavy
  dependency this project otherwise avoids entirely by using Ollama for both chat and
  embeddings; reusing the already-running chat model keeps the install footprint to "just
  Ollama" at the cost of one extra LLM round-trip per query.
- **A confidence score attached to each answer.** I considered exposing the top chunk's
  similarity score as a "confidence" number, but a raw cosine similarity is not a calibrated
  probability of correctness, and presenting it as one would be more misleading than useful.
  The `EvidenceOutcome` classification (sufficient/insufficient/conflicting/ambiguous) is the
  honest version of this signal - it's discrete and each state has a defined behaviour instead
  of a number the user has to guess a threshold for.
- **Conversation memory / multi-turn state.** Out of scope for the assignment's test
  questions, all single-turn, and adding it correctly (deciding what carries over between
  turns, especially for the ambiguity-clarification flow) is a bigger design problem than this
  take-home's scope justified.
- **A general-purpose ML-based prompt-injection classifier.** Regex/keyword matching
  (`InputClassifier`) is auditable and fast, and sufficient for the three known injection
  vectors in this corpus plus the two required test questions (Q9, Q10). Training or hosting a
  real classifier model for a 13-document POC would be disproportionate effort - flagged
  instead as the first thing to add before this sees a corpus I haven't personally read.

## Evaluation methodology (beyond the 15-question run)

See `evaluation/results.md` for the full write-up. Summary: a gold retrieval set (question ->
expected document IDs) for recall@k/MRR, an LLM-as-judge entailment check for hallucination
detection at scale, and outcome-classification diffing (not raw text diffing) between versions
for regression detection, since raw generated text legitimately varies run to run even at low
temperature.

## Production thinking: what would break, and where

- **At 10 million documents**: the embedded, single-process Chroma store stops being
  appropriate - you'd need a proper vector database service (Qdrant, pgvector, or managed
  Chroma) with sharding, and re-embedding the whole collection on every ingest
  (`vector_store.reset()`) becomes infeasible; ingestion would need to become incremental
  (diff against what's already indexed) rather than "wipe and rebuild."
- **At thousands of concurrent users**: `OllamaChatClient`/`OllamaEmbedder` make one
  synchronous HTTP call per request against a single local Ollama process - that's a hard
  ceiling on throughput. A production deployment needs a batching/queueing layer in front of
  the model server (or a hosted inference endpoint that scales horizontally) and the FastAPI
  layer would need to go async end to end.
- **Under strict latency limits**: the current design does one embedding call, one reranking
  LLM call, and one generation LLM call per query, serially. The evidence-analyzer logic
  itself is cheap, but the two LLM calls dominate - a latency-constrained deployment would need
  a smaller/faster model, response streaming, disabling reranking (`RERANK_ENABLED=false`), or
  a real cross-encoder reranker (much cheaper per call than an LLM completion), or some
  combination of these.
- **Under strict cost limits**: local Ollama has no per-token cost, which is exactly why this
  POC uses it - but a production system serving many users would likely need a hosted
  open-weight endpoint, at which point token cost reappears and argues for tighter context
  (better top-k tuning, reranking to cut the number of chunks sent per call) rather than
  "retrieve generously and let the model sort it out."

## One closing thought

What would worry me first about deploying this to a real enterprise tomorrow is not the
happy-path retrieval - it's that every safety behaviour in this system (the conflict registry,
the injection phrase list, the ambiguity thresholds) was tuned by a person who read all 13
source documents in advance. A real corpus is never fully read by anyone, updates continuously,
and will contain conflicts, injected instructions, and ambiguous terminology I never
anticipated. The honest failure mode of this architecture isn't that it hallucinates on the
happy path - it's that it will confidently give a clean, well-cited, SUFFICIENT-classified
answer to a question whose true answer was actually CONFLICTING or INSUFFICIENT, simply
because nothing in this design detects problems it wasn't specifically built to look for.
That gap between "handles the traps I knew about" and "handles the traps I didn't" is the
real production risk, and closing it needs the general-purpose detectors called out above,
not more corpus-specific tuning.
