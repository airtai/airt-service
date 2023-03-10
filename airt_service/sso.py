# AUTOGENERATED! DO NOT EDIT! File to edit: ../notebooks/SSO.ipynb.

# %% auto 0
__all__ = ['get_valid_sso_providers', 'SSOAuthURL', 'initiate_sso_flow', 'get_sso_protocol_and_email',
           'update_user_id_in_sso_table', 'disable_trial_user', 'update_user_info_in_db', 'validate_sso_response']

# %% ../notebooks/SSO.ipynb 2
import os
import secrets
from datetime import datetime, timedelta
from typing import *

import requests
from fastapi import HTTPException, Request, status
from pydantic import BaseModel
from requests_oauthlib import OAuth2Session
from sqlalchemy.exc import NoResultFound
from sqlmodel import select

import airt_service.sanitizer
from airt_service.db.models import (
    SSO,
    SSOProtocol,
    SSOProvider,
    User,
    get_session_with_context,
)
from .errors import ERRORS
from .helpers import commit_or_rollback

# %% ../notebooks/SSO.ipynb 4
# Google APi discovery URL
GOOGLE_DISCOVERY_URL = "https://accounts.google.com/.well-known/openid-configuration"

# constants
SSO_SUCCESS_MSG = "Authentication successful. Please close the browser."
SESSION_TIME_LIMIT = 10  # mins
SSO_CONFIG: Dict[str, Any] = {
    "google": {
        "scope": [
            "https://www.googleapis.com/auth/userinfo.email",
            "https://www.googleapis.com/auth/userinfo.profile",
            "openid",
        ]
    },
    "github": {
        "scope": "user:email",
        "authorization_endpoint": "https://github.com/login/oauth/authorize",
        "token_endpoint": "https://github.com/login/oauth/access_token",
        "userinfo_endpoint": "https://api.github.com/user/emails",
    },
}

# %% ../notebooks/SSO.ipynb 5
def _generate_callback_url() -> str:
    """Generate callback URL for the SSO provider

    This is the URL the user will be redirected to after successful user authentication.

    Returns:
        The generated callback URL
    """
    domain_in_env = os.environ["DOMAIN"]
    domain = (
        "http://127.0.0.1:6006"
        if (domain_in_env == "localhost" or "airt-service" in domain_in_env)
        else f"https://{domain_in_env}"
    )

    callback_url = f"{domain}/sso/callback"

    return callback_url

# %% ../notebooks/SSO.ipynb 9
def _get_google_provider_cfg(api_uri: Optional[str] = None) -> Union[str, dict]:
    """Get google's OpenID Connect configuration

    This configuration includes the URIs of the authorization, token, revocation, userinfo, and public-keys endpoints.

    Args:
        api_uri: API endpoint uri to return from the configuration. If not set then the default value **None**
            will be used to return all the API uri endpoints.

    Returns:
        The google's OpenID Connect endpoint(s)
    """
    try:
        google_provider_cfg = requests.get(GOOGLE_DISCOVERY_URL).json()
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=ERRORS["SERVICE_UNAVAILABLE"],
        )

    return google_provider_cfg[api_uri] if api_uri is not None else google_provider_cfg  # type: ignore

# %% ../notebooks/SSO.ipynb 11
def _get_authorization_url_and_nonce(
    sso_provider: str, username: str, nonce: str
) -> Tuple[str, str]:
    """Get authorization url and nonce

    Args:
        sso_provider: The name of the sso provider
        nonce: cryptographically strong random string
        username: username to append in the redirection url

    Returns:
        The authorization url and the nonce
    """

    callback_url = _generate_callback_url()
    nonce_with_username = f"{nonce}_{username}"

    client = OAuth2Session(
        os.environ[f"{sso_provider.upper()}_CLIENT_ID"],
        scope=SSO_CONFIG[f"{sso_provider}"]["scope"],
        redirect_uri=callback_url,
        state=nonce_with_username,
    )

    authorization_endpoint = (
        _get_google_provider_cfg(api_uri="authorization_endpoint")
        if sso_provider == "google"
        else SSO_CONFIG[f"{sso_provider}"]["authorization_endpoint"]
    )

    authorization_url, nonce_with_username = client.authorization_url(
        authorization_endpoint, prompt="select_account"
    )

    return authorization_url, nonce_with_username

# %% ../notebooks/SSO.ipynb 14
def get_valid_sso_providers() -> List[str]:
    """Get valid SSO proiders

    Returns:
        The list of valid SSO providers
    """
    return [e.value for e in SSOProvider]

# %% ../notebooks/SSO.ipynb 16
def get_sso_if_enabled_for_user(user_id: int, sso_provider: str) -> Optional[SSO]:
    """Check if the given sso provider is enabled for the user

    Args:
        user_id: The user_id for whom the SSO provider status needs be checked
        sso_provider: The name of the SSO provider

    Returns:
        The SSO object if the given sso provider is enabled for the user, else None
    """
    with get_session_with_context() as session:
        try:
            sso = session.exec(
                select(SSO)
                .where(SSO.user_id == user_id)
                .where(SSO.sso_provider == sso_provider)
            ).one()

            if sso.disabled:
                sso = None

        except NoResultFound:
            sso = None

        return sso  # type: ignore

# %% ../notebooks/SSO.ipynb 21
class SSOAuthURL(BaseModel):
    """A base class for creating authorization URL for the provider

    Args:
        authorization_url: The generated authorization URL for the provider
    """

    authorization_url: str

# %% ../notebooks/SSO.ipynb 22
def initiate_sso_flow(
    username: str, sso_provider: str, nonce: str, sso: SSO
) -> SSOAuthURL:
    """Initiate SSO flow and return provider authorization URL

    Args:
        username: Username as a string
        sso_provider: The name of the SSO provider
        nonce: A cryptographically strong random string
        sso: SSO object in session

    Returns:
        The authorization URL for the SSO provider
    """
    # Step 1: Generate authorization_url with username and nonce added to the query params
    authorization_url, nonce_with_username = _get_authorization_url_and_nonce(
        sso_provider, username, nonce
    )

    # Step 2: store the nonce and created_at in the sso_protocol table
    with get_session_with_context() as session:
        sso_protocol = SSOProtocol(**dict(nonce=nonce, created_at=datetime.utcnow()))
        sso_protocol.sso = session.merge(sso)
        session.add(sso_protocol)
        session.commit()

    # Step 3: return the redirect URL to the user
    return SSOAuthURL(authorization_url=authorization_url)

# %% ../notebooks/SSO.ipynb 26
def _get_token_and_user_url(sso_provider: str) -> Tuple[str, str]:
    """Get token and the user info URL endpoints for the given provider

    Args:
        sso_provider: Name of the SSO provider

    Returns:
        The token and the user info URL endpoints for the given provider
    """
    if sso_provider == "google":
        token_endpoint = _get_google_provider_cfg(api_uri="token_endpoint")
        userinfo_endpoint = _get_google_provider_cfg(api_uri="userinfo_endpoint")
    else:
        token_endpoint = SSO_CONFIG[f"{sso_provider}"]["token_endpoint"]
        userinfo_endpoint = SSO_CONFIG[f"{sso_provider}"]["userinfo_endpoint"]

    return token_endpoint, userinfo_endpoint  # type: ignore

# %% ../notebooks/SSO.ipynb 29
def get_user_info_from_provider(
    url: str, nonce_with_username: str, sso_provider: str
) -> Union[Dict[str, Any], List[Dict[str, Any]]]:
    """Get user info from the provider

    This function exchanges the authorization code in the response for an access token
    to access user details from the provider.

    Args:
        url: callback url from google
        nonce_with_username: The nonce created by the client along with the username
        sso_provider: Name of the SSO provider

    Returns:
        The user's information registered with the SSO provider
    """
    redirect_uri = _generate_callback_url()
    client = OAuth2Session(
        os.environ[f"{sso_provider.upper()}_CLIENT_ID"],
        state=nonce_with_username,
        redirect_uri=redirect_uri,
    )

    token_endpoint, userinfo_endpoint = _get_token_and_user_url(sso_provider)
    try:
        token = client.fetch_token(
            token_endpoint,
            client_secret=os.environ[f"{sso_provider.upper()}_CLIENT_SECRET"],
            authorization_response=url,
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ERRORS["SSO_CSRF_WARNING"],
        )

    response: Union[Dict[str, Any], List[Dict[str, Any]]] = client.get(
        userinfo_endpoint
    ).json()
    return response

# %% ../notebooks/SSO.ipynb 31
def get_sso_protocol_and_email(
    username: str, nonce: str, sso_provider: str
) -> Tuple[SSOProtocol, str]:
    """Get SSO protocol and SSO email details

    Args:
        username: username to append in the redirection url
        nonce: cryptographically strong random string
        sso_provider: Name of the SSO provider

    Returns:
        The record from sso protocol table and the email address used to enable the sso provider

    Raises:
        HTTPException: If the username is incorrect
        HTTPException: If the SSO is not yet enabled for the provider
        HTTPException: If the received in the callback didn't match
        HTTPException: If the session is timed out
        HTTPException: If the email address used for SSO authentication didn't match with the one used while enabling the SSO
    """
    # Step 1: Check if username exists
    with get_session_with_context() as session:
        try:
            user = session.exec(select(User).where(User.username == username)).one()
        except NoResultFound:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=ERRORS["INCORRECT_USERNAME"],
            )
    # Step 2: Check if the sso provider is enabled for the user
    sso = get_sso_if_enabled_for_user(user.id, sso_provider)
    if sso is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ERRORS["SSO_NOT_ENABLED_FOR_SERVICE"],
        )

    # Step 3: Check if sso_protocol table has a record
    with get_session_with_context() as session:
        try:
            sso_protocol = session.exec(
                select(SSOProtocol)
                .where(SSOProtocol.sso_id == sso.id)
                .where(SSOProtocol.nonce == nonce)
            ).one()
        except NoResultFound:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=ERRORS["SSO_CSRF_WARNING"],
            )

    # Step 4: Check if the sso_protocol already has errored out
    if sso_protocol.error is not None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=sso_protocol.error,
        )

    return sso_protocol, sso.sso_email

# %% ../notebooks/SSO.ipynb 35
def update_user_id_in_sso_table(
    trial_sso_username: str, user_id_to_update: int
) -> None:
    """Update the user_id in the SSO table

    Args:
        trial_sso_username: Name of the trial SSO user
        user_id_to_update: User id to update in the SSO table

    Raises:
        HTTPException: If the username is incorrect or no records found for the user in the SSO table
    """
    with get_session_with_context() as session:
        try:
            trial_sso_user = session.exec(
                select(User).where(User.username == trial_sso_username)
            ).one()
            sso = session.exec(
                select(SSO).where(SSO.user_id == trial_sso_user.id)
            ).one()

        except NoResultFound:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=ERRORS["SSO_GENERIC_ERROR"],
            )

        sso.user_id = user_id_to_update
        with commit_or_rollback(session):
            session.add(sso)

# %% ../notebooks/SSO.ipynb 38
def disable_trial_user(username: str) -> None:
    """Disable the trial user

    Args:
        username: Username of the user to disable
    """
    with get_session_with_context() as session:
        user = session.exec(select(User).where(User.username == username)).one()
        user.disabled = True
        with commit_or_rollback(session):
            session.add(user)

# %% ../notebooks/SSO.ipynb 40
def update_user_info_in_db(
    sso_signup_trial_username: str,
    user_info_from_provider: Dict[str, str],
) -> None:
    """Update user information retrived from an external SSO provider in the database.

    Args:
        sso_signup_trial_username: The username of the SSO signup trial user.
        user_info_from_provider: User information retrieved from an external SSO provider.
    """
    existing_user = False
    with get_session_with_context() as session:
        try:
            user = session.exec(
                select(User).where(User.email == user_info_from_provider["email"])
            ).one()

            existing_user = True
            update_user_id_in_sso_table(sso_signup_trial_username, user.id)

        except NoResultFound:
            user = session.exec(
                select(User).where(User.username == sso_signup_trial_username)
            ).one()

            random_number = secrets.SystemRandom().randint(0, 1000)
            updated_username = f'{user_info_from_provider["name"].replace(" ", "_").lower()}_{random_number}'

            user.username = updated_username
            user.first_name = user_info_from_provider["given_name"]
            user.last_name = user_info_from_provider["family_name"]
            user.email = user_info_from_provider["email"]

        user.sso_signup_trial_username = sso_signup_trial_username

        with commit_or_rollback(session):
            session.add(user)

        # disable the trial user
        if existing_user:
            disable_trial_user(sso_signup_trial_username)

# %% ../notebooks/SSO.ipynb 43
def validate_sso_response(request: Request, sso_provider: str) -> str:
    """Validate the response from the SSO provider

    This function receives the callback from the SSO provider along with the query parameters
    and validates it. Finally the corresponding SSO authentication status and the
    message is stored in the database

    Args:
        request: The callback request object
        sso_provider: The Name of the SSO provider

    Returns:
        The text message indicating the status of the SSO authentication to display in the browser.
    """
    sso_protocol_error = None
    is_sso_successful = False

    # Step 1: get username and nonce from response's state
    try:
        state = request.query_params["state"]
        nonce, username = state.split("_", 1)
    except KeyError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ERRORS["SSO_CSRF_WARNING"],
        )

    # Step 2: Validate and get record from sso protocol table
    sso_protocol, sso_email = get_sso_protocol_and_email(username, nonce, sso_provider)

    try:
        # Step 3: Check if SESSION_TIME_LIMIT exceeded
        if (datetime.utcnow() - sso_protocol.created_at) > timedelta(
            minutes=SESSION_TIME_LIMIT
        ):
            sso_protocol_error = ERRORS["SSO_SESSION_EXPIRED"]
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=ERRORS["SSO_SESSION_EXPIRED"],
            )

        # Step 4: get email from SSO provider and validate against our records
        user_info_from_provider = get_user_info_from_provider(
            url=str(request.url),
            nonce_with_username=state,
            sso_provider=sso_provider,
        )
        email_from_provider: str = (
            user_info_from_provider["email"]  # type: ignore
            if sso_provider == "google"
            else [email["email"] for email in email_from_provider if email["primary"]][  # type: ignore
                0
            ]
        )
        if email_from_provider != sso_email and "captn_trial" not in username:
            sso_protocol_error = ERRORS["SSO_EMAIL_NOT_SAME"]
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=ERRORS["SSO_EMAIL_NOT_SAME"],
            )
    finally:
        # Step 5: Update error and is_sso_successful in database
        if sso_protocol_error is None:
            is_sso_successful = True

        with get_session_with_context() as session:
            sso_protocol.error = sso_protocol_error
            sso_protocol.is_sso_successful = is_sso_successful
            session.add(sso_protocol)
            session.commit()

    if "captn_trial" in username:
        update_user_info_in_db(username, user_info_from_provider)  # type: ignore

    return SSO_SUCCESS_MSG
