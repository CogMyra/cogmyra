#!/usr/bin/env python3
import csv, sys, pathlib

# usage: python3 scripts/extract_ids_from_csv.py <in_csv> <out_file> <lo> <hi>
if len(sys.argv) != 5:
    sys.exit("usage: python3 scripts/extract_ids_from_csv.py <in_csv> <out_file> <lo> <hi>")

_, in_csv, out_path, lo, hi = sys.argv
lo, hi = int(lo), int(hi)

def norm_key(k: str) -> str:
    return (k or "").strip().lower().replace(" ", "").replace("_", "")

rows = []
# utf-8-sig strips BOM if present
with open(in_csv, newline='', encoding='utf-8-sig') as f:
    r = csv.DictReader(f)
    fns = r.fieldnames or []

    # Accept '#' and common ID variants
    id_candidates = []
    for k in fns:
        nk = norm_key(k)
        if k.strip() == "#" or nk in {
            "id","categoryid","cmgid","cmgid","categorynumber","number","num","no","index"
        }:
            id_candidates.append(k)

    # Category column: prefer names that include 'category' (e.g. "Category Name")
    cat_candidates = [k for k in fns if "category" in (k or "").lower()]

    if not id_candidates or not cat_candidates:
        sys.exit(f"Could not locate ID/Category columns in {fns}")

    id_key, cat_key = id_candidates[0], cat_candidates[0]

    for row in r:
        raw_id = (row.get(id_key) or "").strip()
        try:
            i = int(raw_id)
        except Exception:
            continue
        if lo <= i <= hi:
            rows.append((i, (row.get(cat_key) or "").strip()))

rows.sort(key=lambda x: x[0])
pathlib.Path(out_path).parent.mkdir(parents=True, exist_ok=True)
with open(out_path, "w", encoding="utf-8") as out:
    for i, cat in rows:
        out.write(f"{i},{cat}\n")
