"""Extract only basketball-train sequences from SportsMOT train.tar."""
import tarfile
from pathlib import Path

TAR = Path("datasets/_dl_sportsmot/dataset/train.tar")
OUT = Path("datasets/sportsmot_basketball_train")
SPLITS = Path("datasets/_dl_sportsmot/splits/splits_txt")

bb = set(SPLITS.joinpath("basketball.txt").read_text().split())
tr = set(SPLITS.joinpath("train.txt").read_text().split())
keep = bb & tr
print(f"keeping {len(keep)} basketball-train seqs")

OUT.mkdir(parents=True, exist_ok=True)
n_files = 0
with tarfile.open(TAR) as t:
    for m in t:
        # paths look like "train/v_-6Os86HzwCs_c001/img1/000001.jpg" or "./train/..."
        p = m.name.lstrip("./")
        parts = p.split("/")
        if len(parts) < 2: continue
        if parts[0] != "train": continue
        seq = parts[1]
        if seq not in keep: continue
        # rebase to OUT/<seq>/...
        rel = "/".join(parts[1:])
        target = OUT / rel
        if m.isdir():
            target.mkdir(parents=True, exist_ok=True)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            with t.extractfile(m) as src, open(target, "wb") as dst:
                dst.write(src.read())
            n_files += 1
            if n_files % 500 == 0:
                print(f"  {n_files} files extracted")
print(f"done. {n_files} files extracted to {OUT}")
