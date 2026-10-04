# Quality Checks

Run the production-readiness checks from this repository root:

```bash
python3 scripts/validate_quality.py
```

The validator compiles Python files, runs Ruff, parses YAML/JSON files, renders Mermaid sources when Mermaid tooling is available, runs the pipeline `--help` smoke check, runs the parser fixture suite (`tests/make_fixtures.py`, `ALL OK`), the store and onboarding suite (`tests/test_store.py`, `STORE OK`), the security regression suite (`tests/test_security.py`, `SECURITY OK`: shell syntax in paths, manifest fields, the scheduler wrapper and branding stays literal; generated pages are self-contained with a CSP), checks that the committed example pages reference nothing on the network, and checks ClawHub bundle readiness.

GitHub Actions runs the same validator on push and pull request.

The gate also runs synthetic pricing and scoped-report tests. These cover local-midnight and daylight-saving boundaries, timestamp cutoffs, cached-token arithmetic and context pricing, report-only price overrides, read-only store access, private artifacts and HTML escaping. They do not scan personal agent logs or certify provider billing totals.
