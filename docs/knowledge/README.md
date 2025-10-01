# Knowledge Base Updates

**Owner:** @MichaelFAngotti
**Cadence:** Weekly on **Mondays, 9:00 AM PT** (or ad-hoc with PR + review)

## Update Process
1. Edit CSVs in `docs/knowledge/src/` following `docs/knowledge/SCHEMA.md`.
2. Run:
```
pre-commit run --all-files
make rebuild-index
make check-index
```
3. Open PR with summary of changes and rationale.
4. Upon merge, CI will run `verify-ids`.
