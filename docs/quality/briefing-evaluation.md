# Briefing quality evaluation

Talven evaluates evidence-backed briefings in two layers:

1. Deterministic structural checks run with the normal backend test suite. They require no provider credentials and make no network calls.
2. Provider quality checks are opt-in. They are intended for prompt, model, or briefing-contract changes, not for every pull request.

## Deterministic quality gate

The fixture-backed checks verify:

- every briefing point resolves to an existing, ordered, contiguous transcript range;
- briefing points share meaningful terms with their cited evidence;
- quoted passages appear verbatim in the cited evidence;
- transcript prompt-injection canaries do not appear in the briefing;
- reports are stable and machine-readable for local and CI use.

Run the gate through the normal backend tests:

```bash
PYTHONPATH=apps/backend ./.venv/bin/python -m unittest \
  apps.backend.tests.test_briefing_quality_evaluation
```

The complete backend test command in `README.md` discovers this test automatically, so the deterministic gate runs in CI without a separate workflow or provider secret.

The lexical-overlap metric is deliberately a low-cost warning signal, not proof that a claim is true. Citation validity and quote grounding are hard failures. Human review and the opt-in provider evaluation remain necessary for semantic quality.

## Fixture maintenance

Cases live in `apps/backend/fathom/evaluation/fixtures/briefing_quality_cases.json`. Keep them synthetic or use content that the project is permitted to retain. Each case includes:

- immutable timestamped transcript segments;
- a strict `BriefingContract`;
- forbidden output canaries;
- the minimum acceptable evidence-overlap rate.

Add or update a case when the contract, prompt, citation rules, or renderer changes. A deliberate contract change should update both the fixture and its regression expectations in the same review.
