# Knowledge CSV Schema & Format (v1)

- **Encoding**: UTF-8, **EOL**: LF, **delimiter**: comma, **quoting**: RFC 4180 (quote fields containing commas/newlines)
- **Required columns (minimum)**:
  - `id` (stable string identifier)
  - `chunkIndex` (0..N-1 contiguous integers, no gaps)
  - `title` (human-readable label)
  - `body` (text content)
  - `updated_at` (ISO 8601)
- **Uniqueness**: (`id`, `chunkIndex`) pair must be unique
- **Ordering**: Rows should be in ascending `chunkIndex`
- **No PII** in CSV content
- **Checks before PR**:
  1) `pre-commit run --all-files`
  2) `make rebuild-index`
  3) `make check-index` (expect 26 records; 0..25)

> Note: If the set of CSVs changes (add/remove), update any scripts and the expected counts accordingly.
