## What this changes

<!-- One paragraph. What is different after this pull request? -->

## Why

<!-- The problem it solves. Link the issue if there is one: Fixes #123 -->

## How

<!-- The approach. Anything a reviewer would be surprised by belongs here. -->

## Checklist

- [ ] `cd backend && .venv/bin/python -m pytest -q` passes
- [ ] `yarn typecheck` and `yarn build` pass
- [ ] The change adds a **migration** if it changes the schema
  (the migrations are the schema, not the models)
- [ ] Every new user-facing string is in `en.json`, `fr.json` and `zh.json`
- [ ] Any new data source is documented in `docs/DATA_SOURCES.md`, with its
      licence and its attribution obligation
- [ ] No secret, key or credential is included — not even a "temporary" one
- [ ] The commit messages follow `type(scope): summary`

## Notes for the reviewer

<!-- Anything you want to draw attention to, or a place you are unsure about. -->
