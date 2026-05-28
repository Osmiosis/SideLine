"""Download SoccerNet-Tracking test split using NDA password from ~/.soccernet/password.

Outputs to ~/SoccerNet/tracking/ (outside the repo; NDA-safe).
"""
from pathlib import Path
from SoccerNet.Downloader import SoccerNetDownloader

PASS_PATH = Path.home() / ".soccernet" / "password"
assert PASS_PATH.exists(), f"missing {PASS_PATH}"
password = PASS_PATH.read_text().strip()

out_root = Path.home() / "SoccerNet"
out_root.mkdir(parents=True, exist_ok=True)

dl = SoccerNetDownloader(LocalDirectory=str(out_root))
print(f"Trying tracking-2023 test split -> {out_root}/tracking-2023/")
dl.downloadDataTask(task="tracking-2023", split=["test", "test_labels"], password=password, verbose=True)
print("done")
