# AUTOGENERATED! DO NOT EDIT! File to edit: ../notebooks/Auth.ipynb.

# %% auto 0
__all__ = [
    "ALGORITHM",
    "ACCESS_TOKEN_EXPIRE_MINUTES",
    "oauth2_scheme",
    "auth_router",
    "get_user",
    "get_password_and_otp_from_json",
    "authenticate_user",
    "create_access_token",
    "Token",
    "login_for_access_token",
    "SSOInitiateRequest",
    "login_for_sso_access_token",
    "sso_google_callback",
    "finish_sso_flow",
    "get_current_active_user",
    "create_apikey",
    "get_details_of_apikey",
    "get_valid_user",
    "delete_apikey",
    "get_all_apikey",
]

# %% ../notebooks/Auth.ipynb 3
import json
import uuid
from datetime import datetime, timedelta
from os import environ
import secrets
from typing import *
from urllib.parse import urlparse, parse_qs


# from fastcore.foundation import patch
from fastapi import APIRouter, Request
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi import Depends, HTTPException, status, Query
from pydantic import BaseModel
from jose import JWTError, jwt
from sqlalchemy.exc import NoResultFound, MultipleResultsFound
from sqlmodel import Session, select

from airt.logger import get_logger
from airt.patching import patch

from .db.models import get_session, get_session_with_context
from .db.models import APIKeyCreate, APIKey, APIKeyRead, User, UserRead, SSO
from .errors import HTTPError, ERRORS
from .helpers import commit_or_rollback, verify_password
from .totp import validate_otp, require_otp_if_mfa_enabled
from .sso import SSOAuthURL, get_valid_sso_providers, initiate_sso_flow
from .sso import get_sso_if_enabled_for_user, validate_sso_response
from .sso import get_sso_protocol_and_email, SESSION_TIME_LIMIT

# %% ../notebooks/Auth.ipynb 5
logger = get_logger(__name__)

# %% ../notebooks/Auth.ipynb 8
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 180 * 24 * 60  # Expire after 180 days

# %% ../notebooks/Auth.ipynb 9
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

# %% ../notebooks/Auth.ipynb 10
def get_user(username: str) -> Optional[User]:
    """Get the user object for the given username

    Args:
        username: Username as a string

    Returns:
        The user object if username is valid else None
    """
    with get_session_with_context() as session:
        try:
            user = session.exec(select(User).where(User.username == username)).one()
        except NoResultFound:
            user = None
    return user


# %% ../notebooks/Auth.ipynb 12
def get_password_and_otp_from_json(password: str) -> Tuple[str, str]:
    """Get password and otp

    Args:
        password: password from form_data

    Returns:
        The password and otp as Tuple
    """
    try:
        password_dict = json.loads(password)
        password = password_dict["password"]
        user_otp = password_dict["user_otp"]

    except json.decoder.JSONDecodeError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=ERRORS["OTP_REQUIRED"]
        )

    return password, user_otp


# %% ../notebooks/Auth.ipynb 14
def authenticate_user(username: str, password: str) -> Optional[User]:
    """Validate if the password matches the user's previously stored password.

    In case of MFA activated user, the passed OTP is also gets validated against the current time OTP.

    Args:
        username: Username of the user
        password: Password to validate

    Returns:
        The user object if the credentials matches else None

    Raises:
        HTTPException: If the OTP is invalid for the mfa activated user.
    """
    user = get_user(username)
    if user is None:
        return None

    if user.is_mfa_active:
        password, user_otp = get_password_and_otp_from_json(password)

    if not verify_password(password, user.password):
        return None

    if user.is_mfa_active:
        validate_otp(user.mfa_secret, user_otp)  # type: ignore

    return user


# %% ../notebooks/Auth.ipynb 16
def create_access_token(data: dict, expire: Optional[datetime] = None) -> str:
    """Create new jwt access token

    Args:
        data: Data to encode in jwt access token
        expire: Expiry datetime of jwt access token

    Returns:
        The encoded jwt access token
    """
    to_encode = data.copy()
    if expire:
        to_encode.update({"exp": expire})

    encoded_jwt = jwt.encode(
        to_encode,
        # nosemgrep: python.jwt.security.jwt-hardcode.jwt-python-hardcoded-secret
        environ["AIRT_TOKEN_SECRET_KEY"],
        algorithm=ALGORITHM,
    )
    return encoded_jwt


# %% ../notebooks/Auth.ipynb 19
auth_router = APIRouter(
    responses={
        500: {
            "model": HTTPError,
            "description": ERRORS["INTERNAL_SERVER_ERROR"],
        }
    }
)

# %% ../notebooks/Auth.ipynb 20
class Token(BaseModel):
    """A base class for creating and managing Access token

    Args:
        access_token: Access token
        token_type: Type of the token (bearer token is the only one currently supported)
    """

    access_token: str
    token_type: str


# %% ../notebooks/Auth.ipynb 21
def generate_token(username: str) -> Token:
    """Generate access token

    Args:
        username: Username as a string

    Returns:
        The generated access token
    """
    access_token_expires = datetime.utcnow() + timedelta(
        minutes=ACCESS_TOKEN_EXPIRE_MINUTES
    )
    access_token = create_access_token(
        data={"sub": username}, expire=access_token_expires  # type: ignore
    )

    # Sast recongnizes "bearer" string as hardcoded password but it is not. So using nosec B106.
    return Token(access_token=access_token, token_type="bearer")  # nosec B106


# %% ../notebooks/Auth.ipynb 23
@auth_router.post(
    "/token",
    response_model=Token,
    responses={
        400: {
            "model": HTTPError,
            "description": ERRORS["INCORRECT_USERNAME_OR_PASSWORD"],
        }
    },
)
def login_for_access_token(
    form_data: OAuth2PasswordRequestForm = Depends(),
) -> Token:
    """Authenticate with credentials"""

    user = authenticate_user(form_data.username, form_data.password)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ERRORS["INCORRECT_USERNAME_OR_PASSWORD"],
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = generate_token(user.username)
    return token


# %% ../notebooks/Auth.ipynb 31
class SSOInitiateRequest(BaseModel):
    """A base class for initiating SSO for the provider

    Args:
        username: Username as a string
        password: password as a string
        sso_provider: The name of the sso provider
    """

    username: str
    password: str
    sso_provider: str


# %% ../notebooks/Auth.ipynb 32
@auth_router.post(
    "/sso/initiate",
    response_model=SSOAuthURL,
    responses={
        400: {
            "model": HTTPError,
            "description": ERRORS["INCORRECT_USERNAME_OR_PASSWORD"],
        }
    },
)
def login_for_sso_access_token(
    sso_initiate_request: SSOInitiateRequest,
) -> SSOAuthURL:
    """Initiate the SSO authentication"""
    user = authenticate_user(
        sso_initiate_request.username, sso_initiate_request.password
    )
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ERRORS["INCORRECT_USERNAME_OR_PASSWORD"],
        )

    sso_provider = sso_initiate_request.sso_provider
    valid_sso_providers = get_valid_sso_providers()
    if sso_provider not in valid_sso_providers:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f'{ERRORS["INVALID_SSO_PROVIDER"]}: {valid_sso_providers}',
        )

    sso = get_sso_if_enabled_for_user(user.username, sso_provider)
    if sso is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ERRORS["SSO_NOT_ENABLED_FOR_SERVICE"],
        )
    return initiate_sso_flow(
        username=user.username,
        sso_provider=sso_initiate_request.sso_provider,
        nonce=secrets.token_hex(),
        sso=sso,
    )


# %% ../notebooks/Auth.ipynb 41
@auth_router.get("/sso/callback")
def sso_google_callback(request: Request) -> str:
    """SSO callback route"""

    sso_provider = "google" if "googleapis" in str(request.url) else "github"
    return validate_sso_response(request=request, sso_provider=sso_provider)


# %% ../notebooks/Auth.ipynb 42
@auth_router.get(
    "/sso/token",
    responses={
        400: {
            "model": HTTPError,
            "description": ERRORS["INCORRECT_USER_USERNAME"],
        }
    },
)
def finish_sso_flow(authorization_url: str) -> Token:
    """Finish SSO flow"""
    sso_provider = "google" if "accounts.google.com" in authorization_url else "github"

    state = parse_qs(urlparse(authorization_url).query)["state"][0]
    nonce, username = state.split("_", 1)

    sso_protocol, _ = get_sso_protocol_and_email(username, nonce, sso_provider)

    # https://stackoverflow.com/questions/3297048/403-forbidden-vs-401-unauthorized-http-responses
    if (datetime.utcnow() - sso_protocol.created_at) > timedelta(
        minutes=SESSION_TIME_LIMIT
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=ERRORS["SSO_SESSION_EXPIRED"],
        )
    if not sso_protocol.is_sso_successful:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=ERRORS["SSO_NOT_YET_FINISHED"],
        )
    else:
        token = generate_token(username)
        return token


# %% ../notebooks/Auth.ipynb 47
get_apikey_responses = {
    400: {"model": HTTPError, "description": ERRORS["APIKEY_REVOKED"]},
    401: {"model": HTTPError, "description": ERRORS["INCORRECT_APIKEY"]},
}


@patch(cls_method=True)
def get(cls: APIKey, key_uuid_or_name: str, user: User, session: Session) -> APIKey:
    """Function to get APIKey object

    Args:
        key_uuid_or_name: UUID/Name of the APIKey object
        user: User object
        session: Sqlmodel session

    Returns:
        The APIKey object

    Raises:
        HTTPException: if the key UUID/name is invalid or not enough authorization to access apikey object
    """

    try:
        key_uuid_or_name = uuid.UUID(key_uuid_or_name)  # type: ignore
        statement = select(APIKey).where(
            APIKey.uuid == key_uuid_or_name, APIKey.user == user
        )
    except ValueError:
        statement = select(APIKey).where(
            APIKey.name == key_uuid_or_name, APIKey.user == user
        )

    try:
        apikey = session.exec(statement).one()

    except MultipleResultsFound:
        try:
            # ignoring revoked keys from the results
            apikey = session.exec(statement.where(APIKey.disabled == False)).one()
        except NoResultFound:
            # if all the keys matching the name are disabled
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail=ERRORS["APIKEY_REVOKED"]
            )

    except NoResultFound:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=ERRORS["INCORRECT_APIKEY"],
        )

    if apikey.disabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=ERRORS["APIKEY_REVOKED"]
        )
    return apikey


# %% ../notebooks/Auth.ipynb 51
def get_current_active_user(token: str = Depends(oauth2_scheme)) -> User:
    """Get active user details

    Args:
        token: OAuth token

    Returns:
        The active user details

    Raises:
        HTTPException: if the user is inactive or the token is invalid
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=ERRORS["INVALID_CREDENTIALS"],
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(
            token,
            # nosemgrep: python.jwt.security.jwt-hardcode.jwt-python-hardcoded-secret
            environ["AIRT_TOKEN_SECRET_KEY"],
            algorithms=[ALGORITHM],
        )
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
    user = get_user(username=username)
    if user is None:
        raise credentials_exception
    if user.disabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=ERRORS["INACTIVE_USER"]
        )
    with get_session_with_context() as session:
        user = session.merge(user)
        if "key_uuid" in payload:
            apikey = APIKey.get(key_uuid_or_name=payload["key_uuid"], user=user, session=session)  # type: ignore
    return user  # type: ignore


# %% ../notebooks/Auth.ipynb 53
@patch(cls_method=True)
def _create(
    cls: APIKey, apikey_to_create: APIKeyCreate, user: User, session: Session
) -> APIKey:
    """Create APIKey

    Args:
        apikey_to_create: APIKeyCreate object
        user: User object
        session: Sqlmodel session
    Returns:
        The created APIKey object
    """
    with commit_or_rollback(session):
        apikey = APIKey(**apikey_to_create.dict())
        apikey.user = user
        session.add(apikey)
    return apikey


# %% ../notebooks/Auth.ipynb 54
@auth_router.post("/apikey", response_model=Token)
@require_otp_if_mfa_enabled
def create_apikey(
    apikey_to_create: APIKeyCreate,
    user: User = Depends(get_current_active_user),
    session: Session = Depends(get_session),
) -> Token:
    """Create apikey"""
    user = session.merge(user)

    key_exists = session.exec(
        select(APIKey)
        .where(APIKey.user == user)
        .where(APIKey.name == apikey_to_create.name)
        .where(APIKey.disabled == False)
    ).first()

    if key_exists is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ERRORS["APIKEY_NAME_ALREADY_EXISTS"],
        )

    try:
        apikey = APIKey._create(apikey_to_create, user, session)  # type: ignore
        access_token = create_access_token(
            data={"sub": user.username, "key_uuid": str(apikey.uuid)}, expire=apikey.expiry  # type: ignore
        )
    except Exception as e:
        logger.exception(e)
        error_message = (
            e._message() if callable(getattr(e, "_message", None)) else str(e)  # type: ignore
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_message,
        )

    # Sast recongnizes "bearer" string as hardcoded password but it is not. So using nosec B106.
    return Token(access_token=access_token, token_type="bearer")  # nosec B106


# %% ../notebooks/Auth.ipynb 61
@auth_router.get(
    "/apikey/{key_uuid_or_name}", response_model=APIKeyRead, responses=get_apikey_responses  # type: ignore
)
def get_details_of_apikey(
    key_uuid_or_name: str,
    user: User = Depends(get_current_active_user),
    session: Session = Depends(get_session),
) -> APIKey:
    """Get details of the apikey"""
    user = session.merge(user)
    # get details from the internal db for apikey_id
    return APIKey.get(key_uuid_or_name=key_uuid_or_name, user=user, session=session)  # type: ignore


# %% ../notebooks/Auth.ipynb 64
def get_valid_user(user: User, session: Session, user_uuid_or_name: str) -> User:
    """Get valid user object to perform the operation

    Args:
        user: User object
        session: Sqlmodel session
        user_uuid_or_name: Account user_uuid/username to perform the operation

    Returns:
        User object

    Raises:
        HTTPException: If the user_uuid/username is invalid or the user have insufficient permission to modify other user's data
    """
    try:
        user_uuid_or_name = uuid.UUID(user_uuid_or_name)  # type: ignore
        attribute_to_check = "uuid"
    except ValueError:
        attribute_to_check = "username"

    if getattr(user, attribute_to_check) != user_uuid_or_name and not user.super_user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=ERRORS["NOT_ENOUGH_PERMISSION_TO_ACCESS_OTHERS_DATA"],
        )

    try:
        _user = session.exec(
            select(User).where(getattr(User, attribute_to_check) == user_uuid_or_name)
        ).one()

    except NoResultFound:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ERRORS[f"INCORRECT_USER_{attribute_to_check.upper()}"],
        )

    return _user


# %% ../notebooks/Auth.ipynb 66
@patch
def disable(self: APIKey, session: Session) -> APIKey:
    """Disable an APIKey

    Args:
        session: Sqlmodel session

    Returns:
        The disabled APIKey object
    """
    with commit_or_rollback(session):
        self.disabled = True
        session.add(self)
    return self


# %% ../notebooks/Auth.ipynb 67
@auth_router.delete(
    "/{user_uuid_or_name}/apikey/{key_uuid_or_name}", response_model=APIKeyRead, responses=get_apikey_responses  # type: ignore
)
@require_otp_if_mfa_enabled
def delete_apikey(
    user_uuid_or_name: str,
    key_uuid_or_name: str,
    otp: Optional[str] = None,
    user: User = Depends(get_current_active_user),
    session: Session = Depends(get_session),
) -> APIKey:
    """Revoke apikey"""
    user = session.merge(user)
    # get details from the internal db for apikey_id
    apikey = APIKey.get(key_uuid_or_name=key_uuid_or_name, user=get_valid_user(user, session, user_uuid_or_name), session=session)  # type: ignore

    return apikey.disable(session)  # type: ignore


# %% ../notebooks/Auth.ipynb 74
@patch(cls_method=True)
def get_all(
    cls: APIKey,
    user: User,
    include_disabled: bool,
    offset: int,
    limit: int,
    session: Session,
) -> List[APIKey]:
    """Get all apikeys

    Args:
        user: User object
        include_disabled: Whether to include disabled apikeys
        offset: offset Results by given integer
        limit: limit Results by given integer
        session: Sqlmodel session

    Returns:
        A list of apikey objects
    """
    statement = select(APIKey).where(APIKey.user == user)
    if not include_disabled:
        statement = statement.where(APIKey.disabled == False)
    return session.exec(statement.offset(offset).limit(limit)).all()


# %% ../notebooks/Auth.ipynb 75
@auth_router.get(
    "/{user_uuid_or_name}/apikey",
    response_model=List[APIKeyRead],
    responses={
        400: {
            "model": HTTPError,
            "description": ERRORS["INCORRECT_USER_UUID"],
        },
        401: {
            "model": HTTPError,
            "description": ERRORS["NOT_ENOUGH_PERMISSION_TO_ACCESS_OTHERS_DATA"],
        },
    },
)
def get_all_apikey(
    user_uuid_or_name: str,
    include_disabled: bool = False,
    offset: int = 0,
    limit: int = Query(default=100, lte=100),
    user: User = Depends(get_current_active_user),
    session: Session = Depends(get_session),
) -> List[APIKey]:
    """Get all apikeys created by user"""
    user = session.merge(user)
    return APIKey.get_all(  # type: ignore
        user=get_valid_user(user, session, user_uuid_or_name),
        include_disabled=include_disabled,
        offset=offset,
        limit=limit,
        session=session,
    )
