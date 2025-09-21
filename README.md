# CogMyra

## Install

```bash
python -m pip install cogmyra
# or a specific version:
python -m pip install cogmyra==0.3.4
```

## Quick start

```bash
cogmyra greet World
# Hello, World!
```

## Exporting Admin Logs
- One-off: `COGMYRA_ADMIN_KEY=... ./scripts/export_logs.sh` (creates `~/Downloads/logs-YYYYmmdd-HHMMSS.csv`)
- Scheduled (macOS): LaunchAgent `com.cogmyra.export-logs` runs daily at 17:30. Logs at `/tmp/com.cogmyra.export-logs.{out,err}`.

