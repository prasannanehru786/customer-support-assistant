from __future__ import annotations

import os

import streamlit as st

from backend.support_app.security.auth import (
    AuthUser,
    app_auth_enabled,
    authenticate_google_code,
    create_first_admin_user,
    enabled_auth_methods,
    first_admin_setup_allowed,
    google_auth_configured,
    google_login_url,
    password_auth_configured,
    verify_password_login,
)


def query_param(name: str) -> str | None:
    value = st.query_params.get(name)
    if isinstance(value, list):
        return value[0] if value else None
    return value


def authenticate_google_callback() -> tuple[AuthUser | None, str | None]:
    code = query_param("code")
    state = query_param("state")
    user, error = authenticate_google_code(code, state)
    if code or state:
        st.query_params.clear()
    return user, error


def set_authenticated_user(user: AuthUser) -> None:
    st.session_state["auth_user"] = {
        "email": user.email,
        "name": user.name,
        "auth_method": user.auth_method,
    }


def current_auth_user() -> AuthUser | None:
    raw_user = st.session_state.get("auth_user")
    if not isinstance(raw_user, dict):
        return None
    email = str(raw_user.get("email", ""))
    if not email:
        return None
    return AuthUser(
        email=email,
        name=str(raw_user.get("name", "")),
        auth_method=str(raw_user.get("auth_method", "password")),
    )


def render_password_login() -> None:
    if not password_auth_configured():
        if first_admin_setup_allowed():
            render_first_admin_setup()
            return
        st.warning("Password auth needs an admin user, APP_AUTH_PASSWORD_HASH, or APP_AUTH_PASSWORD.")
        return

    with st.form("password_login_form"):
        username = st.text_input("Username", value=os.getenv("APP_AUTH_USERNAME", "admin"))
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Sign in", type="primary", use_container_width=True)

    if submitted:
        if verify_password_login(username, password):
            set_authenticated_user(AuthUser(email=username.strip(), name=username.strip(), auth_method="password"))
            st.rerun()
        st.error("Invalid username or password.")


def render_first_admin_setup() -> None:
    st.warning("No admin user exists yet. Create the first admin account before using the app.")
    with st.form("first_admin_setup_form"):
        username = st.text_input("Create username", value=os.getenv("APP_AUTH_USERNAME", "admin"))
        password = st.text_input("Create password", type="password")
        confirm_password = st.text_input("Confirm password", type="password")
        submitted = st.form_submit_button("Create admin account", type="primary", use_container_width=True)

    if submitted:
        created, message = create_first_admin_user(username, password, confirm_password)
        if created:
            st.success(message)
            st.rerun()
        else:
            st.error(message)


def render_google_login() -> None:
    if not google_auth_configured():
        st.warning("Google login needs GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, and GOOGLE_OAUTH_REDIRECT_URI.")
        return

    user, error = authenticate_google_callback()
    if user:
        set_authenticated_user(user)
        st.rerun()
    if error:
        st.error(error)

    st.link_button("Continue with Google", google_login_url(), type="primary", use_container_width=True)


def require_authentication() -> bool:
    if not app_auth_enabled():
        return True

    if current_auth_user():
        return True

    methods = enabled_auth_methods()
    st.markdown(
        '<div class="app-eyebrow">Secure access</div>'
        "<h1>Customer Support Assistant</h1>"
        '<div class="app-kicker">Sign in before using the support workspace.</div>',
        unsafe_allow_html=True,
    )

    if not methods:
        st.error("App authentication is enabled, but APP_AUTH_METHODS is empty.")
        return False

    if methods == {"password"}:
        render_password_login()
        return False

    if methods == {"google"}:
        render_google_login()
        return False

    password_tab, google_tab = st.tabs(["Password", "Google"])
    with password_tab:
        render_password_login()
    with google_tab:
        render_google_login()
    return False


def render_auth_sidebar() -> None:
    user = current_auth_user()
    if not app_auth_enabled() or user is None:
        return

    st.markdown("### Access")
    st.caption(f"Signed in as `{user.email}` via `{user.auth_method}`")
    if st.button("Sign out", use_container_width=True):
        st.session_state.pop("auth_user", None)
        st.rerun()
