# AUTOGENERATED! DO NOT EDIT! File to edit: ../notebooks/TOTP.ipynb.

# %% auto 0
__all__ = ['generate_mfa_secret', 'generate_mfa_provisioning_url', 'validate_totp', 'require_otp_if_mfa_enabled']

# %% ../notebooks/TOTP.ipynb 3
import functools
from typing import *

import pyotp
from airt.logger import get_logger
from fastapi import HTTPException, status

import airt_service.sanitizer
from .constants import MFA_ISSUER_NAME
from .errors import ERRORS
from .helpers import get_attr_by_name

# %% ../notebooks/TOTP.ipynb 5
logger = get_logger(__name__)

# %% ../notebooks/TOTP.ipynb 6
def generate_mfa_secret() -> str:
    """Generate a 16 character base32 secret, compatible with Google Authenticator.

    Returns:
        The 16 character base32 secret string.
    """
    # Create a new secret for each user and store it in the database
    base32secret = pyotp.random_base32()
    return base32secret

# %% ../notebooks/TOTP.ipynb 8
def generate_mfa_provisioning_url(mfa_secret: str, user_email: str) -> str:
    """Generate mfa provisioning uri

    Args:
        mfa_secret: The 16 character base32 secret string
        user_email: The user email to generate the provisioning url for

    Returns:
        The provisioning uri generated from the secret
    """
    uri = pyotp.totp.TOTP(mfa_secret).provisioning_uri(
        name=user_email, issuer_name=MFA_ISSUER_NAME
    )
    return uri

# %% ../notebooks/TOTP.ipynb 13
def validate_totp(mfa_secret: str, user_otp: str) -> None:
    """Validate the OTP passed in against the current time OTP

    Args:
        mfa_secret: The 16 character base32 secret string assigned to the user
        user_otp: The OTP to validate against the current time OTP

    Raises:
        HTTPError: If the user OTP does not match the current time OTP
    """
    totp = pyotp.TOTP(mfa_secret)

    if not totp.verify(otp=user_otp):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ERRORS["INVALID_OTP"],
        )

# %% ../notebooks/TOTP.ipynb 15
def require_otp_if_mfa_enabled(func: Callable[..., Any]) -> Callable[..., Any]:
    """A decorator function to validate the otp for MFA enabled user

    If the otp validation fails, the user will not be granted access to the decorated routes
    """

    @functools.wraps(func)
    def wrapper(*args, **kwargs):  # type: ignore
        user = kwargs["user"]
        session = kwargs["session"]
        otp = get_attr_by_name(kwargs, "otp")

        if not user.is_mfa_active and otp is not None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=ERRORS["MFA_NOT_ACTIVATED_BUT_PASSES_OTP"],
            )

        if user.is_mfa_active:
            if otp is not None:
                validate_totp(user.mfa_secret, otp)
            else:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=ERRORS["OTP_REQUIRED"],
                )

        # Do something before
        return func(*args, **kwargs)
        # Do something after

    return wrapper
