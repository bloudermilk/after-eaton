# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

Read `ARCHITECTURE.md` before making changes — it is the primary internal reference.

## Commands

### Pipeline (Python 3.11+)
```bash
cd pipeline
ruff format src/ && ruff check src/   # format + lint
mypy --strict src/                     # type check
pytest                                 # all tests
pytest tests/path/to/test_foo.py      # single file
```

### Frontend (Node 20+)
```bash
cd web
npm run dev        # dev server
npm run build      # production build → web/dist/
npx prettier --write . && npx eslint .
```

## Key constraints
- Pipeline and frontend are fully decoupled — frontend never imports from `pipeline/`.
- Never publish partial releases; abort on schema drift or empty source results.
- `data-latest` release tag is the stable URL contract for the frontend — do not rename it.
