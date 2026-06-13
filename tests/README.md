# Tests

## Layout (conventional — mirrors the source tree)

```
tests/
  conftest.py          # shared fixtures (DB session, TestClient, FX-* test data)
  api/                 # mirrors api/v1/endpoints/   (router tests)
  services/            # mirrors services/           (service-layer tests)
  utils/               # mirrors utils/              (pure-function tests)
```

Test files are named `test_<module>.py`, mirroring the module under test
(e.g. `utils/video_validation_helpers.py` → `tests/utils/test_video_validation_helpers.py`).

## Unit vs integration — use markers, not folders

Every test is tagged so it can be selected regardless of where it lives:

```bash
pytest -m unit                # fast, no I/O
pytest -m integration         # needs the test DB
pytest -m video_submission    # one feature, across all layers
pytest -m "unit and video_submission"
```

Markers are declared in `pyproject.toml` (`--strict-markers` is on, so unknown
markers fail fast). Add `pytestmark = [pytest.mark.unit, pytest.mark.video_submission]`
at the top of a module to tag every test in it.

## Running

```bash
pytest                        # everything
pytest tests/utils            # one layer
pytest -m unit                # just the fast tests
```

## Database for integration tests

Several models use PostgreSQL `JSONB` columns (`Caption.tokens`,
`Vocabulary.meanings`, `ContextualExplanation.examples`), which **SQLite cannot
create** — so integration tests need a real Postgres test database.

Set `TEST_DATABASE_URL` (default:
`postgresql+psycopg://postgres:postgres@localhost:5432/immersio_test`). If the DB
is unreachable, the `db_session` / `client` fixtures **skip** rather than fail, so
the unit suite still runs anywhere.

Quick local DB:

```bash
docker compose up -d            # starts Postgres on :5432
createdb -h localhost -U postgres immersio_test   # or let create_all build it in the main db
```

## Conventions

- Test data and mock returns live in `conftest.py` as `fx_*` fixtures, mirroring
  **Appendix A of `docs/test_plan.md`**. Reuse them; don't inline large dicts.
- Import application code with **absolute imports** (`from services.... import ...`)
  so files can be relocated without edits.
- Case IDs in docstrings (EVI-01, SVP-11, …) map to `docs/test_plan.md`.
