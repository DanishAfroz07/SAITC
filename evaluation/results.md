# Evaluation results

Not yet populated. This environment doesn't have Ollama installed, so no
model was actually run here - `results.json` is genuinely empty rather than
containing fabricated answers.

To populate this file for real:

```bash
python -m app.main ingest
python -m evaluation.run_eval
```

That overwrites this file and `results.json` with the model's actual answers
to all 15 questions (the 12 required by the assignment plus 3 added ones),
their outcome classification (sufficient / insufficient / conflicting /
ambiguous), and their citations.

## How I'd measure this more rigorously at scale

- **Retrieval quality**: build a small gold set mapping each question to the
  document IDs (and ideally section headings) that should be retrieved, then
  track recall@k and MRR against it. The 15 questions here already imply
  such a set (e.g. Q3 -> {HR-POL-002, HR-PRO-011}, Q12 -> {FIN-POL-003,
  FIN-POL-007}); it would just need to be written down explicitly and
  checked automatically on every run rather than read off the model's
  citations by eye.
- **Answer quality / hallucination detection at scale**: an LLM-as-judge pass
  that is given the question, the retrieved context, and the answer, and
  scores whether every claim in the answer is entailed by the context
  (a lightweight NLI-style check). Flag any claim not traceable to a cited
  chunk. This is what would catch hallucination on the long tail of
  questions no one hand-reviews.
- **Regression / A-B comparison between versions**: freeze the 15-question
  set (or a larger one) as a fixture, run it against both versions, and diff
  the outcome classification and citations per question rather than the raw
  text (raw text will legitimately vary between runs even at low
  temperature; outcome + citations are the stable signal). A version that
  flips Q4/Q5 from CONFLICTING to SUFFICIENT, or Q9/Q10 from refused to
  answered, is a regression regardless of how fluent the new prose reads.
- **Guardrail-specific regression tests**: keep the three known injection
  payloads and the extraction/bypass attempts as a permanent fixture (see
  `tests/test_guardrails.py` and `tests/test_classifier.py`) so a future
  prompt or model change that silently reopens one of them fails CI, not a
  demo.
