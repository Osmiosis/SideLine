"""Day 28 PART C: tag-per-clip identity tool for BASKETBALL (output #2).

Identical to the Day-27 football tagger -- only the default paths change (basketball C-feed +
SportsMOT frames). Identical house kits (DPS: Rose=red, Lily=yellow, no numbers) make AUTO
player-identity impossible (Day-26 ReID: AssA +0.004), so identity = HUMAN tag-per-clip: each
short clip is one continuously-visible person -> unambiguous even in identical kits.

The basketball manifest holds BOTH involvement clips (Part B) and presence clips (Part C
fallback) -- the user tags them the same way (bulk-name per track; presence clips are named
just like involvement clips, so a presence-only player still lands in a named reel).

Tkinter + PIL (installed OpenCV is headless). Clips grouped by source track id for bulk-naming;
re-tag any ID-switch. Roster via --roster (one name per line) or typed in-app.
Keys: number=pick roster name | type+Enter=new name | b=apply to whole track | s=skip | u=undo | q=save+quit.

Inputs:
  outputs/player_highlights_bb/<seq>/clips_manifest.json   involvement + presence clips
  datasets/sportsmot_basketball/<seq>/img1/*.jpg           key-frame preview (C-feed seqs)
Output:
  outputs/player_highlights_bb/<seq>/clip_tags.json        { "<clip_basename>": "<name>"|"__skip__" }

Usage:
  .venv\\Scripts\\python scripts\\tag_clips_bb.py v_00HRwkvvjtQ_c001 --roster roster_bb.txt
"""
import argparse, json, sys
from pathlib import Path
import numpy as np
import cv2

sys.path.insert(0, str(Path(__file__).parent))
from follow_cam import _crop


def key_frame(seq, rec, source, follow_dir):
    mid = (rec["start_frame"] + rec["end_frame"]) // 2
    img = cv2.imread(str(Path(source, seq, "img1", f"{mid:06d}.jpg")))
    if img is None:
        return None
    d = json.loads(Path(follow_dir, seq, "follow_cam.json").read_text())
    C = {e["frame"]: (e["cx"], e["cy"]) for e in d["variants"]["C"]}
    cx, cy = C.get(mid, (img.shape[1] / 2, img.shape[0] / 2))
    return cv2.resize(_crop(img, cx, cy, d["crop_w"], d["crop_h"]), (640, 360))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("seq")
    ap.add_argument("--roster", default=None, help="text file, one player name per line")
    ap.add_argument("--clips-dir", default="outputs/player_highlights_bb")
    ap.add_argument("--source", default="datasets/sportsmot_basketball")
    ap.add_argument("--follow-dir", default="outputs/follow_cam_bb")
    args = ap.parse_args()

    seq = args.seq
    man = json.loads(Path(args.clips_dir, seq, "clips_manifest.json").read_text())
    clips = sorted(man["clips"], key=lambda r: (r["track_id"], r.get("kind", "z"), r["moment_idx"]))
    if not clips:
        print("no clips in manifest"); return
    roster = [l.strip() for l in Path(args.roster).read_text().splitlines() if l.strip()] \
        if args.roster else []

    tags_path = Path(args.clips_dir, seq, "clip_tags.json")
    tags = json.loads(tags_path.read_text()) if tags_path.exists() else {}

    import tkinter as tk
    from PIL import Image, ImageTk
    state = {"i": 0, "history": [], "roster": list(roster)}

    root = tk.Tk()
    root.title(f"tag clips - {seq}")
    status = tk.Label(root, font=("Consolas", 12), fg="#0a0", anchor="w", justify="left")
    status.pack(fill="x", padx=6, pady=4)
    tk.Label(root, font=("Consolas", 10), justify="left",
             text="number=pick roster name | type+Enter=new name | b=apply name to whole track "
                  "| s=skip | u=undo | q=save+quit").pack(fill="x", padx=6)
    roster_lbl = tk.Label(root, font=("Consolas", 10), fg="#06c", anchor="w", justify="left")
    roster_lbl.pack(fill="x", padx=6)
    panel = tk.Label(root); panel.pack(padx=6, pady=6)
    entry = tk.Entry(root, font=("Consolas", 13)); entry.pack(fill="x", padx=6, pady=4)

    def save():
        tags_path.write_text(json.dumps(tags, indent=2))

    def basename(rec):
        return Path(rec["clip"]).name

    def roster_text():
        return "roster: " + "  ".join(f"[{i+1}]{n}" for i, n in enumerate(state["roster"][:9])) \
            if state["roster"] else "roster: (none yet - type a name + Enter)"

    def show():
        i = state["i"]
        while i < len(clips) and basename(clips[i]) in tags:
            i += 1
        state["i"] = i
        if i >= len(clips):
            status.config(text=f"ALL DONE  tagged={len(tags)}/{len(clips)}  -- press q to quit")
            panel.config(image=""); return
        rec = clips[i]
        img = key_frame(seq, rec, args.source, args.follow_dir)
        if img is None:
            img = np.full((360, 640, 3), 40, np.uint8)
            cv2.putText(img, "frames absent - metadata only", (40, 180),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (200, 200, 200), 1, cv2.LINE_AA)
        photo = ImageTk.PhotoImage(Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB)))
        panel.config(image=photo); panel.image = photo
        prev = tags.get(f"__track_last__{rec['track_id']}", "")
        kind = rec.get("kind", "involvement")
        status.config(text=f"#{i+1}/{len(clips)}  track {rec['track_id']} [{kind}] "
                           f"({rec['involve_start_sec']:.1f}s str={rec['strength']})   "
                           f"tagged={len(tags)}  | last-for-track: {prev}")
        roster_lbl.config(text=roster_text())

    def commit(name, whole_track=False):
        i = state["i"]; rec = clips[i]
        if name and name not in state["roster"] and name != "__skip__":
            state["roster"].append(name)
        if whole_track:
            tid = rec["track_id"]
            for r in clips:
                if r["track_id"] == tid and basename(r) not in tags:
                    tags[basename(r)] = name
        else:
            tags[basename(rec)] = name
        tags[f"__track_last__{rec['track_id']}"] = name
        state["history"].append(basename(rec)); save()
        entry.delete(0, "end"); show()

    def on_enter(_=None):
        name = entry.get().strip()
        if name:
            commit(name)

    def on_key(e):
        k = (e.char or "")
        if k.isdigit() and k != "0":
            idx = int(k) - 1
            if idx < len(state["roster"]):
                commit(state["roster"][idx])
        elif k == "b":
            name = entry.get().strip() or tags.get(
                f"__track_last__{clips[state['i']]['track_id']}", "")
            if name:
                commit(name, whole_track=True)
        elif k == "s":
            commit("__skip__")
        elif k == "u":
            if state["history"]:
                last = state["history"].pop(); tags.pop(last, None); save()
                for j, r in enumerate(clips):
                    if basename(r) == last:
                        state["i"] = j; break
                show()
        elif k == "q" or e.keysym == "Escape":
            save(); root.destroy()

    entry.bind("<Return>", on_enter)
    root.bind("<Key>", on_key)
    root.protocol("WM_DELETE_WINDOW", lambda: (save(), root.destroy()))
    show()
    root.mainloop()
    save()
    real = {k: v for k, v in tags.items() if not k.startswith("__")}
    print(f"saved {len(real)} clip tags -> {tags_path}")


if __name__ == "__main__":
    main()
