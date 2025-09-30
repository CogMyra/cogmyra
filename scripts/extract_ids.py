import csv, json, re, pathlib, sys
FN = "CMG_PromptCategoryFramework_v1.0_2025-08-05.csv"
INDEX = pathlib.Path("docs/knowledge/index.json")

def collect_rows():
    data = json.loads(INDEX.read_text())
    recs = [r for r in data.get("records",[]) if r.get("file")==FN]
    recs.sort(key=lambda r: r.get("chunkIndex", 1<<30))
    rows, buf, got_header = [], None, False
    for r in recs:
        for line in (r.get("text") or "").splitlines():
            if line.startswith("#,"): got_header=True; continue
            if not got_header: continue
            if re.match(r"^[0-9]+,", line):
                if buf is not None: rows.append(buf)
                buf = line
            else:
                if buf is not None: buf += line
    if buf is not None: rows.append(buf)
    return rows

def write_id_category(out_path, lo, hi):
    best = {}  # id -> (name, line_len)
    for raw in collect_rows():
        row = next(csv.reader([raw]))
        if not row or not row[0].isdigit(): continue
        i = int(row[0])
        if not (lo <= i <= hi): continue
        name = row[1]
        L = len(raw)
        if i not in best or L > best[i][1]:
            best[i] = (name, L)
    out = pathlib.Path(out_path); out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w") as f:
        for i in range(lo, hi+1):
            if i in best:
                f.write(f"{i},{best[i][0]}\n")
    return out

if __name__ == "__main__":
    # usage: python3 scripts/extract_ids.py OUT LO HI
    _, out_path, lo, hi = sys.argv
    p = write_id_category(out_path, int(lo), int(hi))
    print(p)
