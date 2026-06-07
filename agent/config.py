"""Agent settings, loaded once from agent/.env. Import `settings` everywhere."""
import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))


@dataclass(frozen=True)
class Settings:
    supabase_url: str = os.environ["SUPABASE_URL"]
    service_key: str = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
    google_client_id: str = os.environ["GOOGLE_CLIENT_ID"]
    google_client_secret: str = os.environ["GOOGLE_CLIENT_SECRET"]
    google_refresh_token: str = os.environ["GOOGLE_REFRESH_TOKEN"]
    backend_url: str = os.environ.get("BACKEND_URL", "http://localhost:8000")
    site_origin: str = os.environ.get("SITE_ORIGIN", "")
    smtp_user: str = os.environ.get("SMTP_USER", "")
    smtp_app_password: str = os.environ.get("SMTP_APP_PASSWORD", "")
    email_from: str = os.environ.get("EMAIL_FROM", "Sideline <no-reply@invalid>")
    poll_seconds: int = int(os.environ.get("AGENT_POLL_SECONDS", "60"))
    headroom_bytes: int = 1024 ** 3          # 1 GB, same as mint-upload
    promote_free_bytes: int = 3 * 1024 ** 3  # promote quota_waiting above 3 GB free
    expiry_days: int = 14                    # spec §0.6


settings = Settings()
