"""Browser-compatible video finalization.

cv2.VideoWriter(fourcc='mp4v') writes MPEG-4 Part 2 (DivX-style). NO browser can
decode that in an HTML5 <video> element -- the element loads the file but renders
nothing (the player-tagging stage and results page both go blank). Every clip the
pipeline serves to the operator UI must therefore be H.264 (avc1) + yuv420p with a
faststart moov atom. OpenCV's own 'avc1' writer is unreliable on Windows pip builds,
so we keep the cv2 mp4v write and transcode in place with ffmpeg afterwards.
"""
import shutil
import subprocess
from pathlib import Path


def to_browser_h264(path) -> bool:
    """Re-encode `path` in place to H.264/yuv420p (browser-playable). Returns True
    on success. If ffmpeg is missing or fails, the original file is left untouched
    and False is returned (we keep the mp4v render rather than lose it)."""
    path = Path(path)
    if not path.is_file():
        return False
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        return False
    tmp = path.with_suffix(path.suffix + ".h264.mp4")
    try:
        subprocess.run(
            [ffmpeg, "-y", "-loglevel", "error", "-i", str(path),
             "-c:v", "libx264", "-pix_fmt", "yuv420p", "-movflags", "+faststart",
             "-an", str(tmp)],
            check=True, capture_output=True)
    except (subprocess.CalledProcessError, OSError):
        try:
            tmp.unlink()
        except OSError:
            pass
        return False
    tmp.replace(path)
    return True
