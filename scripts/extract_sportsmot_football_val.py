"""Extract 5 football-val sequences from SportsMOT val.tar (one per game)."""
import tarfile
from pathlib import Path

TAR = Path("datasets/_dl_sportsmot/val.tar")
OUT = Path("datasets/sportsmot_football")
KEEP = {
    "v_2QhNRucNC7E_c017",
    "v_G-vNjfx1GGc_c004",
    "v_ITo3sCnpw_k_c007",
    "v_dw7LOz17Omg_c053",
    "v_i2_L4qquVg0_c006",
}

OUT.mkdir(parents=True, exist_ok=True)
n = 0
with tarfile.open(TAR) as t:
    for m in t:
        p = m.name.lstrip("./")
        parts = p.split("/")
        if len(parts) < 2 or parts[0] != "val": continue
        seq = parts[1]
        if seq not in KEEP: continue
        rel = "/".join(parts[1:])
        target = OUT / rel
        if m.isdir():
            target.mkdir(parents=True, exist_ok=True)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            with t.extractfile(m) as src, open(target, "wb") as dst:
                dst.write(src.read())
            n += 1
            if n % 500 == 0:
                print(f"  {n} files extracted")
print(f"done. {n} files extracted to {OUT}")
