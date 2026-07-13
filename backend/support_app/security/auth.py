from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import time
from dataclasses import dataclass
from typing import Any

from backend.support_app.config import AUTH_USERS_PATH, ensure_runtime_dirs


@dataclass
class AuthUser:
    email: str
    name: str = ""
    auth_method: str = "password"


def app_auth_enabled() -> bool:
    return os.getenv("ENABLE_APP_AUTH", "false").lower() == "true"


def enabled_auth_methods() -> set[str]:
    raw_methods = os.getenv("APP_AUTH_METHODS", "password")
    return {method.strip().lower() for method in raw_methods.split(",") if method.strip()}


def auth_session_secret() -> str:
    return (
        os.getenv("APP_AUTH_SESSION_SECRET")
        or os.getenv("APP_AUTH_PASSWORD_HASH")
        or os.getenv("APP_AUTH_PASSWORD")
        or os.getenv("GOOGLE_CLIENT_SECRET")
        or "development-only-auth-secret"
    )


def b64encode_json(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def b64decode_json(value: str) -> dict[str, Any]:
    padded = value + ("=" * (-len(value) % 4))
    decoded = base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8")
    payload = json.loads(decoded)
    return payload if isinstance(payload, dict) else {}


def sign_value(value: str) -> str:
    digest = hmac.new(auth_session_secret().encode("utf-8"), value.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{value}.{digest}"


def verify_signed_value(signed_value: str) -> str | None:
    try:
        value, digest = signed_value.rsplit(".", 1)
    except ValueError:
        return None
    expected_digest = hmac.new(
        auth_session_secret().encode("utf-8"),
        value.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(digest, expected_digest):
        return None
    return value


def create_oauth_state() -> str:
    return sign_value(b64encode_json({"nonce": secrets.token_urlsafe(16), "ts": int(time.time())}))


def verify_oauth_state(state: str, max_age_seconds: int = 600) -> bool:
    raw_state = verify_signed_value(state)
    if raw_state is None:
        return False
    try:
        payload = b64decode_json(raw_state)
        timestamp = int(payload.get("ts", 0))
    except (ValueError, TypeError, json.JSONDecodeError):
        return False
    return timestamp > 0 and int(time.time()) - timestamp <= max_age_seconds


def hash_password(password: str, salt: str | None = None, iterations: int = 260_000) -> str:
    active_salt = salt or secrets.token_urlsafe(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), active_salt.encode("utf-8"), iterations)
    encoded_digest = base64.urlsafe_b64encode(digest).decode("ascii")
    return f"pbkdf2_sha256${iterations}${active_salt}${encoded_digest}"


def verify_password_hash(password: str, stored_hash: str) -> bool:
    if not stored_hash:
        return False

    if stored_hash.startswith("pbkdf2_sha256$"):
        try:
            _algorithm, iterations, salt, expected_digest = stored_hash.split("$", 3)
            calculated = hash_password(password, salt=salt, iterations=int(iterations)).rsplit("$", 1)[-1]
            return hmac.compare_digest(calculated, expected_digest)
        except (TypeError, ValueError):
            return False

    normalized_hash = stored_hash.removeprefix("sha256:")
    calculated_sha256 = hashlib.sha256(password.encode("utf-8")).hexdigest()
    return hmac.compare_digest(calculated_sha256, normalized_hash)


def normalize_username(username: str) -> str:
    return username.strip().lower()


def valid_username(username: str) -> bool:
    normalized = normalize_username(username)
    return bool(re.fullmatch(r"[A-Za-z0-9_.@-]{3,80}", normalized))


def min_password_length() -> int:
    try:
        return int(os.getenv("APP_AUTH_MIN_PASSWORD_LENGTH", "8"))
    except ValueError:
        return 8


def load_local_users() -> dict[str, Any]:
    if not AUTH_USERS_PATH.exists():
        return {"users": {}}
    try:
        payload = json.loads(AUTH_USERS_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"users": {}}
    if not isinstance(payload, dict):
        return {"users": {}}
    users = payload.get("users")
    return {"users": users if isinstance(users, dict) else {}}


def save_local_users(payload: dict[str, Any]) -> None:
    ensure_runtime_dirs()
    AUTH_USERS_PATH.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def local_user_count() -> int:
    return len(load_local_users().get("users", {}))


def local_user_record(username: str) -> dict[str, Any] | None:
    users = load_local_users().get("users", {})
    record = users.get(normalize_username(username))
    return record if isinstance(record, dict) else None


def create_first_admin_user(username: str, password: str, confirm_password: str) -> tuple[bool, str]:
    normalized = normalize_username(username)
    if local_user_count() > 0 or os.getenv("APP_AUTH_PASSWORD_HASH") or os.getenv("APP_AUTH_PASSWORD"):
        return False, "An admin user is already configured."
    if os.getenv("APP_AUTH_ALLOW_SIGNUP", "true").lower() != "true":
        return False, "First admin setup is disabled."
    if not valid_username(username):
        return False, "Username must be 3-80 characters and use only letters, numbers, dot, underscore, hyphen, or @."
    if len(password) < min_password_length():
        return False, f"Password must be at least {min_password_length()} characters."
    if password != confirm_password:
        return False, "Passwords do not match."

    save_local_users(
        {
            "users": {
                normalized: {
                    "username": normalized,
                    "password_hash": hash_password(password),
                    "role": "admin",
                    "created_at": int(time.time()),
                }
            }
        }
    )
    return True, "Admin user created. Sign in with the new credentials."


def first_admin_setup_allowed() -> bool:
    return (
        os.getenv("APP_AUTH_ALLOW_SIGNUP", "true").lower() == "true"
        and not os.getenv("APP_AUTH_PASSWORD_HASH")
        and not os.getenv("APP_AUTH_PASSWORD")
        and local_user_count() == 0
    )


def password_auth_configured() -> bool:
    return bool(os.getenv("APP_AUTH_PASSWORD_HASH") or os.getenv("APP_AUTH_PASSWORD") or local_user_count() > 0)


def verify_password_login(username: str, password: str) -> bool:
    expected_username = os.getenv("APP_AUTH_USERNAME", "admin")
    stored_hash = os.getenv("APP_AUTH_PASSWORD_HASH", "").strip()
    if stored_hash and hmac.compare_digest(username.strip(), expected_username):
        return verify_password_hash(password, stored_hash)

    fallback_password = os.getenv("APP_AUTH_PASSWORD", "")
    if fallback_password and hmac.compare_digest(username.strip(), expected_username):
        return hmac.compare_digest(password, fallback_password)

    record = local_user_record(username)
    if not record:
        return False
    return verify_password_hash(password, str(record.get("password_hash", "")))


def google_auth_configured() -> bool:
    return bool(
        os.getenv("GOOGLE_CLIENT_ID", "").strip()
        and os.getenv("GOOGLE_CLIENT_SECRET", "").strip()
        and os.getenv("GOOGLE_OAUTH_REDIRECT_URI", "").strip()
    )


def allowed_google_emails() -> set[str]:
    raw_emails = os.getenv("APP_AUTH_ALLOWED_EMAILS", "")
    return {email.strip().lower() for email in raw_emails.split(",") if email.strip()}


def google_oauth_flow() -> Any:
    from google_auth_oauthlib.flow import Flow

    redirect_uri = os.getenv("GOOGLE_OAUTH_REDIRECT_URI", "").strip()
    return Flow.from_client_config(
        {
            "web": {
                "client_id": os.getenv("GOOGLE_CLIENT_ID", "").strip(),
                "client_secret": os.getenv("GOOGLE_CLIENT_SECRET", "").strip(),
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": [redirect_uri],
            }
        },
        scopes=["openid", "email", "profile"],
        redirect_uri=redirect_uri,
    )


def google_login_url() -> str:
    flow = google_oauth_flow()
    auth_url, _state = flow.authorization_url(
        state=create_oauth_state(),
        prompt="select_account",
        include_granted_scopes="true",
    )
    return auth_url


def authenticate_google_code(code: str | None, state: str | None) -> tuple[AuthUser | None, str | None]:
    if not code and not state:
        return None, None

    if not state or not verify_oauth_state(state):
        return None, "Google sign-in state is invalid or expired. Please try again."
    if not code:
        return None, "Google sign-in code is missing. Please try again."

    try:
        from google.auth.transport import requests
        from google.oauth2 import id_token

        flow = google_oauth_flow()
        flow.fetch_token(code=code)
        id_info = id_token.verify_oauth2_token(
            flow.credentials.id_token,
            requests.Request(),
            os.getenv("GOOGLE_CLIENT_ID", "").strip(),
        )
    except Exception as exc:
        return None, f"Google sign-in failed: {exc}"

    email = str(id_info.get("email", "")).lower()
    email_verified = bool(id_info.get("email_verified"))
    allowed_emails = allowed_google_emails()
    if not email or not email_verified:
        return None, "Google account email is missing or not verified."
    if allowed_emails and email not in allowed_emails:
        return None, "This Google account is not allowed to access the app."

    return AuthUser(email=email, name=str(id_info.get("name", "")), auth_method="google"), None
