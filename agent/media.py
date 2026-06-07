"""Video probing — same cv2 approach as backend/main.py:_probe_duration_sec."""
import cv2


def probe_duration_sec(path: str) -> float | None:
    """Real duration in seconds, or None when the file isn't a readable video."""
    cap = cv2.VideoCapture(path)
    try:
        if not cap.isOpened():
            return None
        fps = cap.get(cv2.CAP_PROP_FPS)
        frames = cap.get(cv2.CAP_PROP_FRAME_COUNT)
        if fps <= 0 or frames <= 0:
            return None
        return frames / fps
    finally:
        cap.release()
