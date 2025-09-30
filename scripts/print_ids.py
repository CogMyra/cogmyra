import sys
from extract_ids import write_id_category  # reuse the logic
from pathlib import Path

if __name__ == "__main__":
    # usage: python3 scripts/print_ids.py LO HI
    lo, hi = map(int, sys.argv[1:3])
    tmp = Path("/tmp/_ids_range.txt")
    write_id_category(tmp, lo, hi)
    sys.stdout.write(tmp.read_text())
