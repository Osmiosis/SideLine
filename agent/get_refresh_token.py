"""One-time: mint the operator's Google refresh token (drive.file scope)
and smoke-test it against the Drive API. Prints values to paste into env files.
Run: .venv\\Scripts\\python agent\\get_refresh_token.py
"""
import json
import pathlib

import requests
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/drive.file"]
CLIENT_SECRET = pathlib.Path(__file__).with_name("client_secret.json")


def main() -> None:
    flow = InstalledAppFlow.from_client_secrets_file(str(CLIENT_SECRET), SCOPES)
    # access_type=offline + prompt=consent forces a refresh token to be issued
    creds = flow.run_local_server(port=0, access_type="offline", prompt="consent")

    r = requests.get(
        "https://www.googleapis.com/drive/v3/about?fields=storageQuota,user",
        headers={"Authorization": f"Bearer {creds.token}"}, timeout=30)
    r.raise_for_status()
    about = r.json()
    quota = about["storageQuota"]
    free_gb = (int(quota["limit"]) - int(quota["usage"])) / 1024**3

    client = json.loads(CLIENT_SECRET.read_text())["installed"]
    print(f"\nDrive OK for {about['user']['emailAddress']} — {free_gb:.1f} GB free")
    print("\nPaste into supabase/.env AND supabase/tests/.env:")
    print(f"GOOGLE_CLIENT_ID={client['client_id']}")
    print(f"GOOGLE_CLIENT_SECRET={client['client_secret']}")
    print(f"GOOGLE_REFRESH_TOKEN={creds.refresh_token}")


if __name__ == "__main__":
    main()
