"""Day 29 helper: download Alfheim single-camera clips for one half, with resume.

Alfheim ships each half as ~900 sequential 3-second raw-H264 clips named
  NNNN_YYYY-MM-DD HH:MM:SS.ns.h264
Windows filenames cannot contain ':' so we save each clip under its zero-padded INDEX
(NNNN.h264) preserving chronological order, and emit files.txt for `ffmpeg -f concat`.

NOT committed (license + size): saved under datasets/alfheim/ which is gitignored.

Usage:
  .venv\\Scripts\\python scripts\\dl_alfheim.py --half "First Half" --cam 1 --out datasets/alfheim/2013-11-03/fh_cam1
"""
import argparse, urllib.request, ssl, re, http.client, os, time
from urllib.parse import quote, unquote

CTX = ssl.create_default_context(); CTX.check_hostname = False; CTX.verify_mode = ssl.CERT_NONE
MATCH = "2013-11-03"


def get(url, retries=4):
    for a in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            r = urllib.request.urlopen(req, context=CTX, timeout=120)
            try:
                return r.read()
            except http.client.IncompleteRead as e:
                return e.partial
        except Exception as ex:
            if a == retries - 1:
                raise
            time.sleep(2 * (a + 1))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--half", default="First Half")
    ap.add_argument("--cam", default="1")
    ap.add_argument("--out", default="datasets/alfheim/2013-11-03/fh_cam1")
    args = ap.parse_args()

    base = f"https://datasets.simula.no/downloads/alfheim/{MATCH}/{quote(args.half)}/{args.cam}/"
    # the directory listing is chunked and a single fetch often truncates -> union several fetches
    names = set()
    for attempt in range(6):
        html = get(base).decode("utf-8", "replace")
        new = set(unquote(l.split("/")[-1])
                  for l in re.findall(r'href=["\']([^"\']+)["\']', html)
                  if re.search(r"\.h264$", l, re.I))
        before = len(names); names |= new
        print(f"[dl] listing attempt {attempt+1}: +{len(names)-before} -> {len(names)} total", flush=True)
        if attempt >= 2 and len(names) == before:
            break
    names = sorted(names)
    recs = []
    for fn in names:
        m = re.match(r"(\d+)_", fn)
        if m:
            recs.append((int(m.group(1)), fn))
    recs.sort()
    os.makedirs(args.out, exist_ok=True)
    print(f"[dl] {len(recs)} clips  {base}", flush=True)

    files_txt = []
    done = skipped = 0
    t0 = time.time()
    for i, (idx, fn) in enumerate(recs):
        local = os.path.join(args.out, f"{idx:04d}.h264")
        files_txt.append(f"file '{idx:04d}.h264'")
        if os.path.exists(local) and os.path.getsize(local) > 0:
            skipped += 1
            continue
        data = get(base + quote(fn))
        with open(local, "wb") as f:
            f.write(data)
        done += 1
        if done % 50 == 0:
            el = time.time() - t0
            print(f"[dl] {i+1}/{len(recs)}  (new {done}, skip {skipped})  {el:.0f}s", flush=True)
    with open(os.path.join(args.out, "files.txt"), "w") as f:
        f.write("\n".join(files_txt) + "\n")
    print(f"[dl] DONE  new={done} skipped={skipped} total={len(recs)}  "
          f"files.txt written  ({time.time()-t0:.0f}s)", flush=True)


if __name__ == "__main__":
    main()
