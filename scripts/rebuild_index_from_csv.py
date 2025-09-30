#!/usr/bin/env python3
import csv, json, pathlib

CSV_IN = "docs/knowledge/src/CMG_PromptCategoryFramework_v1.0_2025-08-05.csv"
INDEX = "docs/knowledge/index.json"
FILE_KEY = "CMG_PromptCategoryFramework_v1.0_2025-08-05.csv"

p = pathlib.Path(INDEX)
if p.exists():
    data = json.loads(p.read_text(encoding="utf-8"))
else:
    data = {"records": []}

# Drop old records for this file
data["records"] = [r for r in data.get("records", []) if r.get("file") != FILE_KEY]

records = []
with open(CSV_IN, newline="", encoding="utf-8-sig") as f:
    r = csv.DictReader(f)
    for row in r:
        raw_id = (row.get("#") or "").strip()
        cat = (row.get("Category Name") or "").strip()
        try:
            i = int(raw_id)
        except:
            continue
        records.append({
            "file": FILE_KEY,
            "chunkIndex": i - 1,  # 0-based
            "id": i,
            "title": cat,
            "text": f"{i},{cat}"
        })

records.sort(key=lambda r: r["chunkIndex"])
data["records"].extend(records)

p.parent.mkdir(parents=True, exist_ok=True)
p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

print(f"Wrote {len(records)} records for {FILE_KEY}")
