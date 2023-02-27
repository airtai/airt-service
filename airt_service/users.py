# AUTOGENERATED! DO NOT EDIT! File to edit: ../notebooks/Users.ipynb.

# %% auto 0
__all__ = ['user_router', 'ensure_super_user', 'GenerateMFARresponse', 'generate_mfa_url', 'ActivateMFARequest', 'activate_mfa',
           'get_user_to_disable_mfa', 'send_sms_otp', 'require_otp_or_totp_if_mfa_enabled', 'disable_mfa',
           'create_user', 'UserUpdateRequest', 'update_user', 'disable_user', 'enable_user', 'get_all_users',
           'get_user_details', 'EnableSSORequest', 'enable_sso', 'disable_sso', 'create_trial_user', 'sso_signup',
           'RegisterPhoneNumberRequest', 'register_phone_number', 'validate_phone_number', 'ResetPasswordRequest',
           'require_otp_or_totp', 'reset_password', 'UserCleanupRequest', 'cleanup']

# %% ../notebooks/Users.ipynb 3
import functools
import re
import uuid
from typing import *
import secrets
import random
import string

from airt.logger import get_logger
from airt.patching import patch
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, EmailStr, validator
from sqlalchemy.exc import IntegrityError, NoResultFound
from sqlmodel import Session, select

import airt_service
import airt_service.sanitizer
from .auth import get_current_active_user, get_user, get_valid_user
from .cleanup import cleanup_user
from .confluent import create_topics_for_user
from airt_service.db.models import (
    SMS,
    SSO,
    SMSProtocol,
    SSOBase,
    SSOProvider,
    SSORead,
    User,
    UserCreate,
    UserRead,
    get_session,
    get_session_with_context,
)
from .errors import ERRORS, HTTPError
from .helpers import commit_or_rollback, get_attr_by_name, get_password_hash
from airt_service.sms_utils import (
    get_app_and_message_id,
    get_application_and_message_config,
    send_sms,
    validate_otp,
    verify_pin,
)
from airt_service.totp import (
    generate_mfa_provisioning_url,
    generate_mfa_secret,
    require_otp_if_mfa_enabled,
    validate_totp,
)
from .sso import initiate_sso_flow

# %% ../notebooks/Users.ipynb 5
logger = get_logger(__name__)

# %% ../notebooks/Users.ipynb 8
SEND_SMS_OTP_MSG = "If you have already registered and verified your phone number, you will receive the OTP by SMS. If you did not receive the OTP, please contact your administrator."
PASSWORD_RESET_MSG = "Password reset successful"  # nosec B105

# %% ../notebooks/Users.ipynb 9
# Default router for users
user_router = APIRouter(
    prefix="/user",
    tags=["user"],
    #     dependencies=[Depends(get_current_active_user)],
    responses={
        404: {"description": "Not found"},
        500: {
            "model": HTTPError,
            "description": ERRORS["INTERNAL_SERVER_ERROR"],
        },
    },
)

# %% ../notebooks/Users.ipynb 10
def ensure_super_user(func: Callable[..., Any]) -> Callable[..., Any]:
    """Decorator to ensure the user who executes the operation is a super user"""

    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        if not kwargs["user"].super_user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=ERRORS["NOT_ENOUGH_PERMISSION"],
            )
        return func(*args, **kwargs)

    return wrapper

# %% ../notebooks/Users.ipynb 12
class GenerateMFARresponse(BaseModel):
    """A base class for creating mfa url

    Args:
        mfa_url: The provisioning url generated from the secret
    """

    mfa_url: str

# %% ../notebooks/Users.ipynb 13
@user_router.get("/mfa/generate", response_model=GenerateMFARresponse)
@require_otp_if_mfa_enabled
def generate_mfa_url(
    otp: Optional[str] = None,
    user: User = Depends(get_current_active_user),
    session: Session = Depends(get_session),
) -> GenerateMFARresponse:
    """Generate MFA url"""
    user = session.merge(user)

    mfa_secret = generate_mfa_secret()
    mfa_url = generate_mfa_provisioning_url(
        mfa_secret=mfa_secret, user_email=user.email
    )

    with commit_or_rollback(session):
        user.mfa_secret = mfa_secret
        session.add(user)

    return GenerateMFARresponse(mfa_url=mfa_url)

# %% ../notebooks/Users.ipynb 15
class ActivateMFARequest(BaseModel):
    """A base class for activating mfa

    Args:
        user_otp: OTP passed by the user
    """

    user_otp: str

# %% ../notebooks/Users.ipynb 16
@user_router.post("/mfa/activate", response_model=UserRead)
def activate_mfa(
    activate_mfa_request: ActivateMFARequest,
    user: User = Depends(get_current_active_user),
    session: Session = Depends(get_session),
) -> User:
    """Activate MFA"""
    user = session.merge(user)
    user_otp = activate_mfa_request.user_otp

    if not user.mfa_secret:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ERRORS["GENERATE_MFA_URL_NOT_GENERATED"],
        )

    validate_totp(user.mfa_secret, user_otp)

    with commit_or_rollback(session):
        user.is_mfa_active = True
        session.add(user)

    return user

# %% ../notebooks/Users.ipynb 18
def get_user_to_disable_mfa(user: User, session: Session, user_uuid: str) -> User:
    """Get user object to disable MFA

    Only a super user can disable MFA for other users in the server

    Args:
        user: User object
        session: Sqlmodel session
        user_uuid: User uuid to disable MFA

    Returns:
        User object to disable MFA
    """
    _user = get_valid_user(user, session, user_uuid)

    if not _user.is_mfa_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ERRORS["MFA_ALREADY_DISABLED"],
        )

    return _user

# %% ../notebooks/Users.ipynb 21
def create_sms_protocol(xs: Dict[str, str], sms: SMS, session: Session) -> None:
    """Create a new record in the sms protocol table

    Args:
        xs: The response from infobip's send sms API
        sms: Instance of the SMS db model
        session: Session object
    """

    with commit_or_rollback(session):
        sms_protocol = SMSProtocol(
            pin_id=xs["pinId"],
            number_lookup_status=xs["ncStatus"],
            sent_sms_status=xs["smsStatus"],
            phone_number=xs["to"],
        )
        sms_protocol.sms = sms
        session.add(sms_protocol)

# %% ../notebooks/Users.ipynb 23
def _get_allowed_message_template_names() -> List[str]:
    """Get valid message templates for sending SMS

    The **register_phone_number** template will be removed from the allowed list because
    while registering the phone number the users should use the /register_phone_number
    route for sending the SMS and use /validate_phone_number route to validate.

    Returns:
        The list of valid message template names
    """
    message_template_names = list(
        get_application_and_message_config()["message_config"].keys()
    )
    message_template_names.remove("register_phone_number")

    return message_template_names

# %% ../notebooks/Users.ipynb 25
def _send_sms_otp_to_user(
    user: User,
    message_template_name: str,
    session: Session,
    phone_number: Optional[str] = None,
) -> User:
    """Send the OTP via SMS to the user for the given message template

    Args:
        user: User object for whom the SMS needs to be sent
        message_template_name: Message template name to include in the SMS
        phone_number: The phone number of the user to send SMS. If this setting is passed, then the
            SMS will be sent to this phone number in place of the one stored in the database. This will
            allow the user if they wish to register a new phone number or change an existing one.
        session: Session object

    Returns:
        The user object if the SMS is sent successfully

    Raises:
        HTTPException: If the Infobip server is not reachable or not able to send SMS
        HTTPException: If the user requests for more sms's to the same number than the allocated limit. Currently
            the limit is set to 30 messages per day to one phone number.
    """
    user = session.merge(user)

    application_id, message_id = get_app_and_message_id(
        message_template_name=message_template_name
    )

    sms = session.exec(
        select(SMS)
        .where(SMS.user == user)
        .where(SMS.application_id == application_id)
        .where(SMS.message_id == message_id)
    ).one_or_none()

    if sms is None:
        with commit_or_rollback(session):
            sms = SMS(application_id=application_id, message_id=message_id)
            sms.user = user
            session.add(sms)

    phone_number = phone_number if phone_number is not None else user.phone_number

    sms_send_status = airt_service.sms_utils.send_sms(
        sms.application_id, sms.message_id, phone_number
    )

    if "requestError" in sms_send_status:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"{sms_send_status['requestError']['serviceException']['text']}",
        )

    if sms_send_status["smsStatus"] == "MESSAGE_NOT_SENT":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ERRORS["MESSAGE_NOT_SENT"],
        )

    sms_protocol = session.exec(
        select(SMSProtocol).where(SMSProtocol.sms_id == sms.id)
    ).one_or_none()

    if sms_protocol is None:
        create_sms_protocol(sms_send_status, sms, session)
    else:
        with commit_or_rollback(session):
            session.delete(sms_protocol)

        create_sms_protocol(sms_send_status, sms, session)

    return user

# %% ../notebooks/Users.ipynb 26
@user_router.get("/send_sms_otp")
def send_sms_otp(
    username: str,
    message_template_name: str,
    session: Session = Depends(get_session),
) -> str:
    """Send the OTP via SMS to the user"""

    user = get_user(username)

    if user is not None:
        if (user.phone_number is not None) and (user.is_phone_number_verified):
            allowed_message_template_names = _get_allowed_message_template_names()
            if message_template_name in allowed_message_template_names:
                user = _send_sms_otp_to_user(
                    user=user,
                    message_template_name=message_template_name,
                    session=session,
                )

    return SEND_SMS_OTP_MSG

# %% ../notebooks/Users.ipynb 31
def require_otp_or_totp_if_mfa_enabled(
    message_template_name: str,
) -> Callable[..., Any]:
    """A decorator function to validate the totp/otp for MFA enabled user

    If the totp/otp validation fails, the user will not be granted access to the decorated route

    Args:
        message_template_name: Name of the message template that was used to send the SMS
    """

    def outer_wrapper(func: Callable[..., Any]) -> Callable[..., Any]:
        @functools.wraps(func)
        def inner_wrapper(*args: Any, **kwargs: Any) -> Any:
            user = kwargs["user"]
            session = kwargs["session"]
            otp_or_totp = get_attr_by_name(kwargs, "otp")

            if not user.is_mfa_active and otp_or_totp is not None:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=ERRORS["MFA_NOT_ACTIVATED_BUT_PASSES_OTP"],
                )

            if user.is_mfa_active:
                if otp_or_totp is not None:
                    try:
                        validate_totp(user.mfa_secret, otp_or_totp)
                    except HTTPException as e:
                        try:
                            validate_otp(
                                user=user,
                                otp=otp_or_totp,
                                message_template_name=message_template_name,
                                session=session,
                            )
                        except HTTPException as e:
                            raise HTTPException(
                                status_code=status.HTTP_400_BAD_REQUEST,
                                detail=ERRORS["INVALID_OTP"],
                            )
                else:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=ERRORS["OTP_REQUIRED"],
                    )

            # Do something before
            return func(*args, **kwargs)
            # Do something after

        return inner_wrapper

    return outer_wrapper

# %% ../notebooks/Users.ipynb 33
@user_router.delete(
    "/mfa/{user_uuid_or_name}/disable",
    response_model=UserRead,
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
@require_otp_or_totp_if_mfa_enabled(message_template_name="disable_mfa")
def disable_mfa(
    user_uuid_or_name: str,
    otp: Optional[str] = None,
    user: User = Depends(get_current_active_user),
    session: Session = Depends(get_session),
) -> User:
    """Disable MFA"""

    user = session.merge(user)
    user_to_disable_mfa = get_user_to_disable_mfa(user, session, user_uuid_or_name)

    with commit_or_rollback(session):
        user_to_disable_mfa.is_mfa_active = False
        user_to_disable_mfa.mfa_secret = None
        session.add(user_to_disable_mfa)

    return user_to_disable_mfa

# %% ../notebooks/Users.ipynb 41
@patch(cls_method=True)  # type: ignore
def _create(cls: User, user_to_create: UserCreate, session: Session) -> User:
    """Method to create new user

    Args:
        user_to_create: UserCreate object
        session: DB session object

    Returns:
        A newly created user object

    Raises:
        HTTPException: if username or email already exists in database
    """
    user_to_create.password = get_password_hash(user_to_create.password)
    new_user = User(**user_to_create.dict())

    try:
        session.add(new_user)
        session.commit()
    except IntegrityError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ERRORS["USERNAME_OR_EMAIL_ALREADY_EXISTS"],
        )
    create_topics_for_user(username=new_user.username)
    return new_user

# %% ../notebooks/Users.ipynb 42
@user_router.post(
    "/",
    response_model=UserRead,
    responses={
        400: {
            "model": HTTPError,
            "description": ERRORS["USERNAME_OR_EMAIL_ALREADY_EXISTS"],
        },
        401: {"model": HTTPError, "description": ERRORS["NOT_ENOUGH_PERMISSION"]},
    },
)
@require_otp_if_mfa_enabled
@ensure_super_user
def create_user(
    user_to_create: UserCreate,
    user: User = Depends(get_current_active_user),
    session: Session = Depends(get_session),
) -> User:
    """
    Create new user
    """
    user = session.merge(user)

    return User._create(user_to_create, session)  # type: ignore

# %% ../notebooks/Users.ipynb 47
@patch(cls_method=True)  # type: ignore
def get(cls: User, uuid: str, session: Session) -> User:
    """Function to get user object based on given user id

    Args:
        uuid: User uuid
        session: Sqlmodel session

    Returns:
        A user object for given uuid

    Raises:
        HTTPException: if uuid does not exists in database
    """
    try:
        user = session.exec(select(User).where(User.uuid == uuid)).one()
    except NoResultFound:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ERRORS["INCORRECT_USER_UUID"],
        )

    return user

# %% ../notebooks/Users.ipynb 48
class UserUpdateRequest(BaseModel):
    """Request object to update user

    Args:
        username: Updated username
        first_name: Updated first name
        last_name: Updated last name
        email: Updated email
        otp: Dynamically generated six-digit verification code from the authenticator app
    """

    username: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    email: Optional[str] = None
    otp: Optional[str] = None

# %% ../notebooks/Users.ipynb 49
@patch(cls_method=True)  # type: ignore
def check_username_exists(cls: User, username: str, session: Session) -> None:
    """Check given username already exists in database or not

    Args:
        username: Username to check
        session: Sqlmodel session

    Raises:
        HTTPException: if username exists
    """
    try:
        session.exec(select(User).where(User.username == username)).one()
    except NoResultFound:
        return

    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=ERRORS["USERNAME_ALREADY_EXISTS"],
    )

# %% ../notebooks/Users.ipynb 50
def check_valid_email(email: str) -> str:
    """Check the given email is valid or not

    Args:
        email: Email to check

    Returns:
        The email, if its valid

    Raises:
        HTTPException: if email is an invalid one
    """
    email_regex = re.compile(r"[^@]+@[^@]+\.[^@]+")
    if not email_regex.match(email):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ERRORS["INVALID_EMAIL"],
        )
    return email

# %% ../notebooks/Users.ipynb 53
@patch(cls_method=True)  # type: ignore
def check_email_exists(cls: User, email: str, session: Session) -> None:
    """Check given email already exists in database or not

    Args:
        email: Email to check
        session: Sqlmodel session

    Raises:
        HTTPException: if email is an invalid one or if email exists
    """

    email = check_valid_email(email)

    try:
        session.exec(select(User).where(User.email == email)).one()
    except NoResultFound:
        return

    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=ERRORS["EMAIL_ALREADY_EXISTS"],
    )

# %% ../notebooks/Users.ipynb 54
@patch  # type: ignore
def _update(self: User, to_update: UserUpdateRequest, session: Session) -> User:
    if to_update.username:
        User.check_username_exists(to_update.username, session)
        self.username = to_update.username

    if to_update.email:
        User.check_email_exists(to_update.email, session)
        self.email = to_update.email  # type: ignore

    if to_update.first_name:
        self.first_name = to_update.first_name
    if to_update.last_name:
        self.last_name = to_update.last_name

    with commit_or_rollback(session):
        session.add(self)

    return self

# %% ../notebooks/Users.ipynb 55
@user_router.post(
    "/{user_uuid_or_name}/update",
    response_model=UserRead,
    responses={
        400: {
            "model": HTTPError,
            "description": ERRORS["USERNAME_OR_EMAIL_ALREADY_EXISTS"],
        },
        401: {
            "model": HTTPError,
            "description": ERRORS["NOT_ENOUGH_PERMISSION"],
        },
    },
)
@require_otp_if_mfa_enabled
def update_user(
    to_update: UserUpdateRequest,
    user_uuid_or_name: str,
    user: User = Depends(get_current_active_user),
    session: Session = Depends(get_session),
) -> User:
    """Update user"""
    user = session.merge(user)

    user_to_update = get_valid_user(user, session, user_uuid_or_name)
    return user_to_update._update(to_update, session)  # type: ignore

# %% ../notebooks/Users.ipynb 60
@patch  # type: ignore
def disable(self: User, session: Session) -> User:
    """Disable user

    Args:
        session: Sqlmodel session

    Returns:
        The disabled user object

    Raises:
        HTTPException: if user is already disabled
    """
    if self.disabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ERRORS["USER_ALREADY_DISABLED"],
        )

    with commit_or_rollback(session):
        self.disabled = True
        session.add(self)

        for apikey in self.apikeys:
            apikey.disabled = True
            session.add(apikey)
    return self

# %% ../notebooks/Users.ipynb 61
@user_router.delete(
    "/{user_uuid_or_name}",
    response_model=UserRead,
    responses={
        400: {"model": HTTPError, "description": ERRORS["INCORRECT_USER_UUID"]},
        401: {
            "model": HTTPError,
            "description": ERRORS["NOT_ENOUGH_PERMISSION"],
        },
    },
)
@require_otp_if_mfa_enabled
@ensure_super_user
def disable_user(
    user_uuid_or_name: str,
    otp: Optional[str] = None,
    user: User = Depends(get_current_active_user),
    session: Session = Depends(get_session),
) -> User:
    """Disable user"""
    user = session.merge(user)

    user_to_disable = get_valid_user(user, session, user_uuid_or_name)

    return user_to_disable.disable(session)

# %% ../notebooks/Users.ipynb 65
@patch  # type: ignore
def enable(self: User, session: Session) -> User:
    """Enable user

    Args:
        session: Sqlmodel session

    Returns:
        The enabled user object
    """
    if not self.disabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ERRORS["USER_ALREADY_ENABLED"],
        )
    with commit_or_rollback(session):
        self.disabled = False
        session.add(self)
    return self

# %% ../notebooks/Users.ipynb 66
@user_router.get(
    "/{user_uuid_or_name}/enable",
    response_model=UserRead,
    responses={
        400: {"model": HTTPError, "description": ERRORS["INCORRECT_USER_UUID"]},
        401: {
            "model": HTTPError,
            "description": ERRORS["NOT_ENOUGH_PERMISSION"],
        },
    },
)
@require_otp_if_mfa_enabled
@ensure_super_user
def enable_user(
    user_uuid_or_name: str,
    otp: Optional[str] = None,
    user: User = Depends(get_current_active_user),
    session: Session = Depends(get_session),
) -> User:
    """Enable user"""
    user = session.merge(user)
    user_to_enable = get_valid_user(user, session, user_uuid_or_name)

    return user_to_enable.enable(session)

# %% ../notebooks/Users.ipynb 70
@patch(cls_method=True)  # type: ignore
def get_all(
    cls: User,
    disabled: bool,
    offset: int,
    limit: int,
    session: Session,
) -> List[User]:
    """Function to get all users

    Args:
        disabled: Whether to get only disabled users
        offset: Offset results by given integer
        limit: Limit results by given integer
        session: Sqlmodel session

    Returns:
        a list of user objects
    """
    statement = select(User)
    statement = statement.where(User.disabled == disabled)

    return session.exec(statement.offset(offset).limit(limit)).all()

# %% ../notebooks/Users.ipynb 71
@user_router.get(
    "/",
    response_model=List[UserRead],
    responses={
        401: {
            "model": HTTPError,
            "description": ERRORS["NOT_ENOUGH_PERMISSION"],
        },
    },
)
@ensure_super_user
def get_all_users(
    disabled: bool = False,
    offset: int = 0,
    limit: int = Query(default=100, lte=100),
    user: User = Depends(get_current_active_user),
    session: Session = Depends(get_session),
) -> List[User]:
    """Get all users"""
    user = session.merge(user)

    return User.get_all(disabled=disabled, offset=offset, limit=limit, session=session)

# %% ../notebooks/Users.ipynb 74
@user_router.get("/details", response_model=UserRead)
def get_user_details(
    user_uuid_or_name: Optional[str] = None,
    user: User = Depends(get_current_active_user),
    session: Session = Depends(get_session),
) -> User:
    """Get user details"""
    user = session.merge(user)

    _user = (
        get_valid_user(user, session, user_uuid_or_name)
        if user_uuid_or_name is not None
        else user
    )

    return User.get(_user.uuid, session)  # type: ignore

# %% ../notebooks/Users.ipynb 77
@patch  # type: ignore
def enable(self: SSO, session: Session, sso_email: EmailStr) -> SSO:
    """Enable SSO for a particular service

    Args:
        session: Sqlmodel session
        sso_email: Email address to enable SSO for this provider

    Returns:
        The enabled SSO object
    """
    with commit_or_rollback(session):
        self.disabled = False
        self.sso_email = sso_email
        session.add(self)

    return self

# %% ../notebooks/Users.ipynb 78
def check_valid_sso_provider(sso_provider: str) -> str:
    """Validate if the given sso_provider

    Args:
        sso_provider: SSO provider name

    Returns:
        The sso_provider if it is valid

    Raises:
        HTTPException: If the sso_provider didn't match the allowed values
    """
    valid_sso_providers = [e.value for e in SSOProvider]
    if sso_provider not in valid_sso_providers:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f'{ERRORS["INVALID_SSO_PROVIDER"]}: {valid_sso_providers}',
        )
    return sso_provider

# %% ../notebooks/Users.ipynb 80
class EnableSSORequest(SSOBase):
    """A base class for enabling sso for the account

    Args:
        otp: OTP passed by the user
    """

    otp: Optional[str] = None

    @validator("sso_provider", pre=True)
    @classmethod
    def validate_sso_provider(cls, sso_provider: str) -> str:
        return check_valid_sso_provider(sso_provider)

    @validator("sso_email", pre=True)
    @classmethod
    def validate_email(cls, sso_email: str) -> str:
        if sso_email is not None:
            sso_email = check_valid_email(sso_email)
        return sso_email

# %% ../notebooks/Users.ipynb 81
@user_router.post("/sso/enable", response_model=SSORead)
@require_otp_if_mfa_enabled
def enable_sso(
    enable_sso_request: EnableSSORequest,
    user: User = Depends(get_current_active_user),
    session: Session = Depends(get_session),
) -> SSO:
    """Enable SSO for the user"""
    user = session.merge(user)

    sso_email = enable_sso_request.sso_email
    sso_provider = enable_sso_request.sso_provider

    sso = session.exec(
        select(SSO).where(SSO.user == user).where(SSO.sso_provider == sso_provider)
    ).one_or_none()

    if sso is not None:
        return sso.enable(session, sso_email)  # type: ignore

    if sso_email is None:
        sso_email = user.email

    with commit_or_rollback(session):
        _sso = SSO(sso_provider=sso_provider, sso_email=sso_email)
        _sso.user = user
        session.add(_sso)

    return _sso

# %% ../notebooks/Users.ipynb 86
@patch  # type: ignore
def disable(self: SSO, session: Session):
    """Disable SSO for a particular service

    Args:
        session: Sqlmodel session

    Returns:
        The disabled SSO object

    Raises:
        HTTPException: if SSO is already disabled
    """
    if self.disabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ERRORS["SSO_ALREADY_DISABLED"],
        )

    with commit_or_rollback(session):
        self.disabled = True
        session.add(self)

    return self

# %% ../notebooks/Users.ipynb 87
@user_router.delete(
    "/sso/{user_uuid_or_name}/disable/{sso_provider}",
    response_model=SSORead,
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
@require_otp_if_mfa_enabled
def disable_sso(
    user_uuid_or_name: str,
    sso_provider: str,
    otp: Optional[str] = None,
    user: User = Depends(get_current_active_user),
    session: Session = Depends(get_session),
) -> SSO:
    """Disable SSO"""

    user = session.merge(user)

    sso_provider = check_valid_sso_provider(sso_provider)

    user_to_disable_sso = get_valid_user(user, session, user_uuid_or_name)

    try:
        sso_provider_to_disable = session.exec(
            select(SSO)
            .where(SSO.user == user_to_disable_sso)
            .where(SSO.sso_provider == sso_provider)
        ).one()

    except NoResultFound:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ERRORS["SSO_NOT_ENABLED_FOR_SERVICE"],
        )

    return sso_provider_to_disable.disable(session)  # type: ignore

# %% ../notebooks/Users.ipynb 91
def create_trial_user(subscription_type: str, session: Session) -> User:
    """Create a trial user for the given subscription_type"""

    username = "".join(
        random.choice(string.ascii_lowercase) for _ in range(10)  # nosec B311
    )

    user_to_create = UserCreate(
        username=f"{subscription_type}_{username}",
        first_name=f"{subscription_type}_first_name",
        last_name=f"{subscription_type}_last_name",
        email=f"{subscription_type}_{username}@email.com",
        password=f"{subscription_type}_{username}",
        subscription_type=subscription_type,
    )
    return User._create(user_to_create, session)  # type: ignore

# %% ../notebooks/Users.ipynb 93
@user_router.get("/sso_signup")
def sso_signup(subscription_type: str, sso_provider: str) -> str:
    """Method to create new user with SSO"""
    with get_session_with_context() as session:
        # 1. Create Trial user
        trial_user = create_trial_user(
            subscription_type=subscription_type, session=session
        )
        # 2. Enable SSO for the Trial user
        enable_sso_request = EnableSSORequest(
            sso_provider=sso_provider, sso_email=trial_user.email
        )
        sso = enable_sso.__wrapped__(  # type: ignore
            enable_sso_request=enable_sso_request, user=trial_user, session=session
        )
        # 3. get authorization URL
        return initiate_sso_flow(
            username=trial_user.username,
            sso_provider=sso_provider,
            nonce=secrets.token_hex(),
            sso=sso,
        ).authorization_url

# %% ../notebooks/Users.ipynb 95
class RegisterPhoneNumberRequest(BaseModel):
    """A base class for registering a new phone number

    Args:
        phone_number: User's new phone number to add in the db
        otp: Dynamically generated six-digit verification code from the authenticator app
    """

    phone_number: Optional[str] = None
    otp: Optional[str] = None

# %% ../notebooks/Users.ipynb 96
@user_router.post(
    "/register_phone_number",
    response_model=UserRead,
    responses={
        400: {"model": HTTPError, "description": ERRORS["NO_PHONE_NUMBER_TO_REGISTER"]},
    },
)
@require_otp_if_mfa_enabled
def register_phone_number(
    register_phone_number_request: RegisterPhoneNumberRequest,
    user: User = Depends(get_current_active_user),
    session: Session = Depends(get_session),
) -> User:
    """Register a new phone number for the user"""
    user = session.merge(user)

    phone_number = register_phone_number_request.phone_number

    if phone_number is None:
        if user.phone_number is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=ERRORS["NO_PHONE_NUMBER_TO_REGISTER"],
            )
        phone_number = user.phone_number

    else:
        with commit_or_rollback(session):
            user.is_phone_number_verified = False
            user.phone_number = phone_number
            session.add(user)

    user = _send_sms_otp_to_user(
        user=user,
        message_template_name="register_phone_number",
        session=session,
        phone_number=phone_number,
    )

    return user

# %% ../notebooks/Users.ipynb 101
@user_router.get(
    "/validate_phone_number",
    response_model=UserRead,
    responses={
        400: {"model": HTTPError, "description": ERRORS["PHONE_NUMBER_NOT_REGISTERED"]},
    },
)
def validate_phone_number(
    otp: str,
    user: User = Depends(get_current_active_user),
    session: Session = Depends(get_session),
) -> User:
    """Validate user's phone number"""
    user = session.merge(user)

    if user.phone_number is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ERRORS["PHONE_NUMBER_NOT_REGISTERED"],
        )

    validate_otp(
        user=user,
        otp=otp,
        message_template_name="register_phone_number",
        session=session,
    )

    with commit_or_rollback(session):
        user.is_phone_number_verified = True
        session.add(user)

    return user

# %% ../notebooks/Users.ipynb 105
class ResetPasswordRequest(BaseModel):
    """Request object to reset user's password

    Args:
        username: Username to reset the password
        new_password: New password to set for the user's account
        otp: Dynamically generated six-digit verification code from the authenticator app or the OTP received via SMS
    """

    username: str
    new_password: str
    otp: str

# %% ../notebooks/Users.ipynb 106
def require_otp_or_totp(message_template_name: str) -> Callable[..., Any]:
    """A decorator function to validate the totp/otp

    If the totp/otp validation fails, the user will not be granted access to the decorated route

    Args:
        message_template_name: Name of the message template that was used to send the SMS
    """

    def outer_wrapper(func: Callable[..., Any]) -> Callable[..., Any]:
        @functools.wraps(func)
        def inner_wrapper(*args: Any, **kwargs: Any) -> Any:
            username = get_attr_by_name(kwargs, "username")
            otp_or_totp = get_attr_by_name(kwargs, "otp")
            session = kwargs["session"]

            user = get_user(username)  # type: ignore
            if user is None:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail=ERRORS["INCORRECT_USERNAME_OR_OTP"],
                )

            if user.is_mfa_active:
                try:
                    validate_totp(user.mfa_secret, otp_or_totp)  # type: ignore
                    return func(*args, **kwargs)
                except HTTPException as e:
                    pass
            try:
                validate_otp(
                    user=user,
                    otp=otp_or_totp,  # type: ignore
                    message_template_name=message_template_name,
                    session=session,
                )
            except HTTPException as e:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail=ERRORS["INCORRECT_USERNAME_OR_OTP"],
                )

            # Do something before
            return func(*args, **kwargs)
            # Do something after

        return inner_wrapper

    return outer_wrapper

# %% ../notebooks/Users.ipynb 110
@user_router.post(
    "/reset_password",
    responses={
        401: {"model": HTTPError, "description": ERRORS["INCORRECT_USERNAME_OR_OTP"]},
    },
)
@require_otp_or_totp(message_template_name="reset_password")
def reset_password(
    reset_password_request: ResetPasswordRequest,
    session: Session = Depends(get_session),
) -> str:
    """Reset passowrd for the user"""
    username = reset_password_request.username
    new_password = reset_password_request.new_password

    user = get_user(username)
    user = session.merge(user)

    with commit_or_rollback(session):
        user.password = get_password_hash(new_password)  # type: ignore
        session.add(user)

    return PASSWORD_RESET_MSG

# %% ../notebooks/Users.ipynb 123
class UserCleanupRequest(BaseModel):
    """Request object to cleanup user

    Args:
        username: username
        otp: Dynamically generated six-digit verification code from the authenticator app
    """

    username: str
    otp: Optional[str] = None

# %% ../notebooks/Users.ipynb 124
@user_router.post(
    "/cleanup",
    response_model=UserRead,
    responses={
        400: {"model": HTTPError, "description": ERRORS["CANT_CLEANUP_SELF"]},
        401: {"model": HTTPError, "description": ERRORS["NOT_ENOUGH_PERMISSION"]},
    },
)
@require_otp_if_mfa_enabled
@ensure_super_user
def cleanup(
    user_to_cleanup: UserCleanupRequest,
    user: User = Depends(get_current_active_user),
    session: Session = Depends(get_session),
) -> User:
    """
    Cleanup user
    """
    user = session.merge(user)

    if user.username == user_to_cleanup.username:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ERRORS["CANT_CLEANUP_SELF"],
        )

    try:
        user_to_cleanup_obj = session.exec(
            select(User).where(User.username == user_to_cleanup.username)
        ).one()
    except NoResultFound:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ERRORS["INCORRECT_USERNAME"],
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

    cleanup_user(user_to_cleanup_obj, session)

    return user
