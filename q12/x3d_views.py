"""Q12 run 2: what x3d_mcp says about each X3D file (the X3D side of the join).

    python -I x3d_views.py X3D_MCP_DIR OUT.json DIR [DIR ...] [--max-mb 3] [--jobs 2]

For every *.x3d under the DIRs (node_modules skipped, files over --max-mb skipped and listed): parse, X3D 4.0 schema
error count, and the semantic diagnostics with the file's own folder (so the file checks, such as texture-too-large,
see its textures). Same reading as tests/usd_q12/join.py in x3d_mcp #33: error and warning codes, info codes apart.
"""
import hashlib
import json
import sys
from multiprocessing import Pool
from pathlib import Path

A = sys.argv[1:]
opt = {k: A[A.index(k) + 1] for k in ("--max-mb", "--jobs") if k in A}
pos = [a for i, a in enumerate(A) if not a.startswith("--") and (i == 0 or A[i - 1] not in opt)]
MCP, OUT, DIRS = Path(pos[0]).resolve(), Path(pos[1]), [Path(d).resolve() for d in pos[2:]]
MAX = float(opt.get("--max-mb", 3)) * 1e6
sys.path.insert(0, str(MCP / "src"))


def view(path):
    from lxml import etree
    from validation import semantic
    from validation.validate import validate_xml
    p = Path(path)
    b = p.read_bytes()
    row = {"sha256": hashlib.sha256(b).hexdigest(), "bytes": len(b)}
    try:
        text = b.decode("utf-8")
        etree.fromstring(b)
    except Exception as e:
        return path, dict(row, parse_ok=False, xsd=0, codes=[], info=[], why=str(e)[:120])
    try:
        xsd = len(validate_xml(text).get("errors") or [])
    except Exception as e:
        xsd, row["xsd_crash"] = -1, str(e)[:120]
    try:
        ds = semantic.semantic_diagnostics_with_files(text, str(p.parent))
    except Exception as e:
        return path, dict(row, parse_ok=True, xsd=xsd, codes=[], info=[], crash=str(e)[:160])
    return path, dict(row, parse_ok=True, xsd=xsd,
                      codes=sorted({d.check for d in ds if d.level in ("error", "warning")}),
                      info=sorted({d.check for d in ds if d.level == "info"}))


if __name__ == "__main__":
    files, big = [], []
    for d in DIRS:
        for p in sorted(d.rglob("*.x3d")):
            if "node_modules" in p.parts or not p.is_file():
                continue
            (big if p.stat().st_size > MAX else files).append(str(p))
    with Pool(int(opt.get("--jobs", 2))) as pool:
        rows = dict(pool.imap_unordered(view, files, chunksize=4))
    root = Path(DIRS[0]).parent
    rel = lambda s: str(Path(s).relative_to(root)) if Path(s).is_relative_to(root) else s
    OUT.write_text(json.dumps({"root": str(root), "max_mb": MAX / 1e6, "skipped_big": [rel(b) for b in big],
                               "files": {rel(k): rows[k] for k in sorted(rows)}}, indent=0))
    print(len(rows), "files viewed;", len(big), "over the size cap;",
          sum(1 for r in rows.values() if r.get("codes") or r.get("info")), "with a finding")
