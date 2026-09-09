# ClawHub Publishing

This repository is prepared for ClawHub publishing as a text-based OpenClaw skill bundle.

## Included In ClawHub

The ClawHub bundle is intended to include text-based skill material only:

- `SKILL.md`, `README.md`, `QUALITY.md`, and this file
- `agents/openai.yaml`
- `pyproject.toml`
- `.github/workflows/quality.yml`
- `scripts/*.py` and `tests/*.py`
- `references/` catalogs and format notes
- `templates/` JSON manifests, pricing sheet, account and report-config examples
- `examples/` text inputs and README placeholders
- `assets/diagrams/*.mmd`
- `assets/examples/example.md` (the rendered study in Markdown)

## Excluded From ClawHub

`.clawhubignore` excludes binary and generated assets from the publish candidate, including PDFs, PNG previews, DOCX files, fonts, logos, `preview/`, `output/`, caches, virtual environments, local env files, temporary files, and generated `scans/`, `compiled/` and `reports/` working directories.

Those files remain part of the GitHub repository for brand presentation, examples, local demos, and generated artifact previews. They are not part of the ClawHub text bundle.

## License And Brand Boundary

ClawHub publishes skills under MIT-0. The text/code bundle can be used under ClawHub's publishing terms, but CompleteTech LLC names, logos, seals, and other brand assets remain reserved. Publishing this text bundle does not grant a trademark or brand-asset license and does not relicense excluded binary brand assets.

## Runtime Dependencies

Runtime requirements are declared in `SKILL.md` under `metadata.openclaw`.

- The pipeline itself needs only `python3` (standard library).
- `pyyaml` is declared so the included quality validator can parse YAML metadata.
- `ruff` is a development-time dependency for the validator, not a runtime requirement.

## Data Boundary

The skill reads agent transcripts and credential files on the user's own machines to identify accounts. It decodes identity claims only and never copies, prints, or transmits tokens. Publishing the skill bundle never includes any scanned data; `scans/`, `compiled/` and `reports/` are excluded.

## Security Audit Response

ClawHub's audit of 1.5.0 reported shell command injection through the report output directory (`os.system` sort), through unquoted SSH manifest fields, and through the scheduler's free-form extra arguments, plus unescaped branding in generated HTML and external Google Fonts requests. 1.5.1 replaces the shell sort with a Python merge sort, validates and quotes every remote command word, removes free-form scheduler arguments, escapes and validates branding, inlines all resources with a Content-Security-Policy, warns on group- or world-writable configuration, and adds `tests/test_security.py` to the quality gate.

## Local Readiness Check

Run before publishing:

```bash
python3 scripts/validate_quality.py
```

The validator checks lint, Python compilation, structured-file parsing, Mermaid rendering, smoke tests, the parser fixture suite, and ClawHub bundle readiness. It does not publish to ClawHub.

## Publishing

Do not publish automatically. Use the ClawHub CLI only after explicit approval and an authenticated owner context, for example:

```bash
clawhub skill publish . --owner <owner> --version <semver>
```
