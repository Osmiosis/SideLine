from backend import errors


def test_friendly_message_known_stage():
    assert errors.friendly_message("decoding") == (
        "We couldn't read the video. Please try uploading it again."
    )
    assert errors.friendly_message("analytics") == (
        "Something went wrong while building the analytics. Please try again."
    )


def test_friendly_message_unknown_stage_has_generic_fallback():
    msg = errors.friendly_message("some_future_stage")
    assert "went wrong" in msg.lower()


def test_log_stage_failure_writes_file(tmp_path):
    log_path = errors.log_stage_failure(
        tmp_path, stage="tracking", detail="Traceback: boom"
    )
    assert log_path.exists()
    assert "boom" in log_path.read_text(encoding="utf-8")
    assert log_path.name == "tracking.log"
