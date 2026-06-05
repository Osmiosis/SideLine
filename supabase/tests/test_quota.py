import requests

from conftest import FUNCTIONS_URL, user_headers
from test_decide import make_admin


def test_quota_admin_only(two_users):
    r = requests.get(f"{FUNCTIONS_URL}/quota",
                     headers=user_headers(two_users["a_tok"]))
    assert r.status_code == 403, r.text


def test_quota_returns_drive_numbers(two_users):
    make_admin(two_users["a_id"])
    r = requests.get(f"{FUNCTIONS_URL}/quota",
                     headers=user_headers(two_users["a_tok"]))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["free_bytes"] > 0
    assert body["limit_bytes"] >= body["usage_bytes"]
