# Quality Checks

Run the production-readiness checks from this repository root:

```bash
python3 scripts/validate_quality.py
```

The validator compiles Python files, runs Ruff, parses YAML/JSON files, renders Mermaid sources when Mermaid tooling is available, runs the pipeline `--help` smoke check, runs the parser fixture suite (`tests/make_fixtures.py`, which must print `ALL OK`), and checks ClawHub bundle readiness.

GitHub Actions runs the same validator on push and pull request.
