from backend import landmarks


def test_football_has_four_corners_in_metres():
    t = landmarks.template("football")
    assert set(t) == {"far-left corner", "far-right corner",
                      "near-right corner", "near-left corner"}
    # FIFA pitch 105 x 68 m, centre origin -> corners at (+/-52.5, +/-34)
    xs = sorted({abs(x) for x, y in t.values()})
    ys = sorted({abs(y) for x, y in t.values()})
    assert xs == [52.5] and ys == [34.0]


def test_basketball_has_four_corners():
    t = landmarks.template("basketball")
    assert set(t) == {"far-left corner", "far-right corner",
                      "near-right corner", "near-left corner"}


def test_world_points_orders_to_labels():
    labels = ["far-left corner", "near-left corner"]
    pts = landmarks.world_points("football", labels)
    assert pts == [list(landmarks.template("football")[l]) for l in labels]
