# AUTOGENERATED! DO NOT EDIT! File to edit: ../notebooks/SMS_Utils.ipynb.

# %% auto 0
__all__ = ['get_application_and_message_config', 'get_app_and_message_id', 'send_sms', 'verify_pin']

# %% ../notebooks/SMS_Utils.ipynb 3
import json
import os
from time import sleep
from typing import *

import numpy as np
import requests
from airt.logger import get_logger
from fastapi import HTTPException, status
from sqlmodel import Session, select

import airt_service
import airt_service.sanitizer
from .db.models import SMS, SMSProtocol, User
from .errors import ERRORS
from .helpers import commit_or_rollback

# %% ../notebooks/SMS_Utils.ipynb 5
logger = get_logger(__name__)

# %% ../notebooks/SMS_Utils.ipynb 7
def _generate_application_name() -> str:
    """Generate an application template name

    The generated template name will be used to create an application template which is necessary for
    using the infobip 2FA service. These templates will be created only once and will be reused on
    subsequent requests.

    Returns:
        The application template name
    """
    domain = os.environ["DOMAIN"]

    return os.environ["HOSTNAME"] if domain == "localhost" else domain

# %% ../notebooks/SMS_Utils.ipynb 10
def get_application_and_message_config() -> Dict[str, Dict[str, Any]]:
    """Get the application and message template configurations

    Before using the Infobip's 2FA service it is necessary to configure the properties and templates for the use case. Properties,
    such as the number of allowed PIN attempts and PIN time to live etc., are configured by creating an application. Templates,
    such as message text, PIN type, PIN length etc., are configured by creating a Message Template.

    Returns:
        The application and message template configurations
    """
    return {
        "application_config": {
            "name": f"{_generate_application_name()}",
            "configuration": {
                "sendPinPerPhoneNumberLimit": "30/1d",  # Default value in Infobip: "3/1d"
            },
        },
        "message_config": {
            "register_phone_number": {
                "senderId": f"{os.environ['INFOBIP_SENDER_ID']}",
                "pinType": "NUMERIC",
                "messageText": "{{pin}} is your OTP to register the phone number. This OTP is valid for the next 15 mins.",
                "pinLength": 6,
            },
            "reset_password": {
                "senderId": f"{os.environ['INFOBIP_SENDER_ID']}",
                "pinType": "NUMERIC",
                "messageText": "{{pin}} is your OTP to reset the password. This OTP is valid for the next 15 mins.",
                "pinLength": 6,
            },
            "disable_mfa": {
                "senderId": f"{os.environ['INFOBIP_SENDER_ID']}",
                "pinType": "NUMERIC",
                "messageText": "{{pin}} is your OTP to disable the multi-factor authentication (MFA). This OTP is valid for the next 15 mins.",
                "pinLength": 6,
            },
            "get_token": {
                "senderId": f"{os.environ['INFOBIP_SENDER_ID']}",
                "pinType": "NUMERIC",
                "messageText": "{{pin}} is your OTP to get an application token. This OTP is valid for the next 15 mins.",
                "pinLength": 6,
            },
        },
    }

# %% ../notebooks/SMS_Utils.ipynb 12
def _send_get_request_to_infobip(
    relative_url: str,
) -> Union[Dict[str, Any], List[Dict[str, Any]]]:
    """Send a GET request to Infobip

    Args:
        relative_url: The relative url of the infobip endpoint

    Returns:
        A list of JSON objects
    """

    headers = {
        "Authorization": f"App {os.environ['INFOBIP_API_KEY']}",
        "Accept": "application/json",
    }
    url = f"{os.environ['INFOBIP_BASE_URL']}{relative_url}"
    for i in range(3):
        err = None
        try:
            response = requests.get(url, headers=headers)
            if response:
                response_json = response.json()
                break
            else:
                err = response.text
                sleep(np.random.uniform(1, 3))

        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=ERRORS["MESSAGING_SERVICE_UNAVAILABLE"],
            )
    if err:
        logger.exception(f"Unexpected response from infobip", exc_info=err)
        raise HTTPException(status_code=500, detail=f"Unexpected exception: {err}")

    return response_json

# %% ../notebooks/SMS_Utils.ipynb 14
def _get_application_id(application_name: str) -> Optional[str]:
    """Get application template id for the given application name

    Args:
        application_name: Application name for which the application id needs to be retrived

    Returns:
        The application id if the exists, else None
    """
    relative_url = "/2fa/2/applications"
    apps = _send_get_request_to_infobip(relative_url)
    app: List[Dict[str, Any]] = [app for app in apps if app["name"] == application_name]  # type: ignore

    return None if len(app) == 0 else app[0]["applicationId"]

# %% ../notebooks/SMS_Utils.ipynb 16
def _send_post_request_to_infobip(
    relative_url: str, data: Dict[str, Any]
) -> Dict[str, Any]:
    """Send a POST request to Infobip

    Args:
        relative_url: The relative url of the infobip endpoint
        data: Template configuration

    Returns:
        A JSON object of the response
    """

    headers = {
        "Authorization": f"App {os.environ['INFOBIP_API_KEY']}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    url = f"{os.environ['INFOBIP_BASE_URL']}{relative_url}"

    try:
        response = requests.post(url, json=data, headers=headers).json()
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=ERRORS["MESSAGING_SERVICE_UNAVAILABLE"],
        )
    return response

# %% ../notebooks/SMS_Utils.ipynb 17
def _create_all_message_templates(
    application_id: str, message_config: Dict[str, Dict[str, str]]
) -> Dict[str, str]:
    """Create new message templates with the given configurations

    Args:
        application_id: Application id for which the message templates needs to be created
        message_config: Message template configurations like message text, PIN type, PIN length etc.,

    Returns:
        The created message template name and their ids as a key value pair.
    """
    relative_url = f"/2fa/2/applications/{application_id}/messages"
    message_templates_to_ids = {}

    for template_name, config in message_config.items():
        message_templates_to_ids[template_name] = _send_post_request_to_infobip(
            relative_url, config
        )["messageId"]

    return message_templates_to_ids

# %% ../notebooks/SMS_Utils.ipynb 19
def _get_message_id_for_template(
    xs: List[Dict[str, Union[str, int]]], message_template_name: str
) -> Optional[str]:
    """Get the message id for the given template

    Args:
        xs: The list of available message templates in Infobip server
        message_template_name: Message template name for which the id needs to be retrieved

    Returns:
        The message id if the template is already created, else None
    """
    config = get_application_and_message_config()

    message_ids = [
        x["messageId"]
        for x in xs
        if config["message_config"][message_template_name].items() <= x.items()
    ]

    if len(message_ids) == 0:
        return None

    return message_ids[0]  # type: ignore

# %% ../notebooks/SMS_Utils.ipynb 21
def _send_put_request_to_infobip(
    relative_url: str, data: Dict[str, Any]
) -> Dict[str, Any]:
    """Send a PUT request to Infobip

    Args:
        relative_url: The relative url of the infobip endpoint
        data: The updated template configuration

    Returns:
        A JSON object of the response
    """

    headers = {
        "Authorization": f"App {os.environ['INFOBIP_API_KEY']}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    url = f"{os.environ['INFOBIP_BASE_URL']}{relative_url}"

    try:
        response = requests.put(url, json=data, headers=headers).json()
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=ERRORS["MESSAGING_SERVICE_UNAVAILABLE"],
        )
    return response

# %% ../notebooks/SMS_Utils.ipynb 22
def _update_application_config(app_id: str, config: Dict[str, Any]):
    """Update an existing application configuration

    Args:
        app_id: Application ID for which the configurations needs to be updated
        config: New configuration for the application
    """
    relative_url = f"/2fa/2/applications/{app_id}"
    return _send_put_request_to_infobip(relative_url, config)

# %% ../notebooks/SMS_Utils.ipynb 23
def _is_config_changed(
    local_config: Dict[str, Any], server_config: Dict[str, Any]
) -> bool:
    """Verify that the shared key values are different for the given configurations

    Args:
        local_config: The template configuration set in the code
        server_config: The template configuration retrieved from the infobip server

    Returns:
        True, if the configurations didn't match else False
    """

    shared_keys = local_config.keys() & server_config.keys()
    for k in shared_keys:
        if not local_config[k] == server_config[k]:
            return True

    return False

# %% ../notebooks/SMS_Utils.ipynb 27
def get_app_and_message_id(message_template_name: str) -> Tuple[str, str]:
    """Get the application id and the message template id

    A new application and a message template will be created in the Infobip server if the requested
    templates are not created yet. In case, the templates are already created then they will be reused.

    Args:
        message_template_name: Message template name for which the id needs to be retrieved. Currently,
            the API only supports **register_phone_number** and **reset_password** as message template name.

    Returns:
        The application id and the message template id for the given message template
    """
    config = get_application_and_message_config()
    application_id = _get_application_id(config["application_config"]["name"])

    if application_id is not None:
        # check and update application configuration if the local configurations are not matching the server configurations
        relative_url = f"/2fa/2/applications/{application_id}"
        server_app_config = _send_get_request_to_infobip(relative_url)["configuration"]  # type: ignore
        local_app_config = config["application_config"]["configuration"]

        if _is_config_changed(local_app_config, server_app_config):
            application_id = _update_application_config(
                application_id, config["application_config"]
            )["applicationId"]

        # Get id for the given message_template_name
        relative_url = f"/2fa/2/applications/{application_id}/messages"
        messages = _send_get_request_to_infobip(relative_url)
        message_id = _get_message_id_for_template(messages, message_template_name)  # type: ignore

        if message_id is None:
            # Create a new message template for the message_template_name
            relative_url = f"/2fa/2/applications/{application_id}/messages"
            ret_val_message_id = _send_post_request_to_infobip(
                relative_url, config["message_config"][message_template_name]
            )["messageId"]
        else:
            ret_val_message_id = message_id
    else:
        # Create a new application template
        relative_url = "/2fa/2/applications"
        application_id = _send_post_request_to_infobip(
            relative_url, config["application_config"]
        )["applicationId"]

        # Create new message templates
        message_templates_to_ids = _create_all_message_templates(
            application_id, config["message_config"]
        )
        ret_val_message_id = message_templates_to_ids[message_template_name]

    return application_id, ret_val_message_id  # type: ignore

# %% ../notebooks/SMS_Utils.ipynb 29
def send_sms(application_id: str, message_id: str, phone_number: str) -> Dict[str, Any]:
    """Send a OTP code over SMS using infobip services

    Args:
        application_id: The ID of the application that represents the 2FA service,
        message_id: The ID of the message template to send to the recipient.
        phone_number: The phone number of the recipient.

    Returns:
        A JSON object of the response from Infobip
    """
    relative_url = "/2fa/2/pin"
    data = {
        "applicationId": f"{application_id}",
        "messageId": f"{message_id}",
        "to": f"{phone_number}",
    }
    return _send_post_request_to_infobip(relative_url, data)

# %% ../notebooks/SMS_Utils.ipynb 30
def verify_pin(pin_id: str, otp: str) -> Dict[str, Any]:
    """Verify a phone number using infobip services.

    Args:
        pin_id: The ID of the pin that needs to be verified. The Infobip 2FA service will dynamically create a pin while sending the SMS.
            And while verifying the OTP, we need to send the same pin to the Infobip 2FA service to validate on their servers.
        otp: The OTP sent to the user via SMS.

    Returns:
        A JSON object of the response from Infobip
    """
    relative_url = f"/2fa/2/pin/{pin_id}/verify"
    data = {
        "pin": otp,
    }
    return _send_post_request_to_infobip(relative_url, data)

# %% ../notebooks/SMS_Utils.ipynb 31
def validate_otp(
    user: User,
    otp: str,
    message_template_name: str,
    session: Session,
):
    """Validate the SMS OTP

    Args:
        user: User object for whom the SMS OTP needs to be checked
        otp: The SMS OTP to validate
        message_template_name: Message template name to validate the OTP
        session: Session object

    Raises:
        HTTPException: If the Phone number is not registered and not verified
        HTTPException: If the OTP is invalid
    """
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
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ERRORS["PHONE_NUMBER_NOT_REGISTERED"],
        )

    sms_protocol = session.exec(
        select(SMSProtocol).where(SMSProtocol.sms_id == sms.id)
    ).one_or_none()

    if sms_protocol is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ERRORS["PHONE_NUMBER_NOT_REGISTERED"],
        )

    if sms_protocol.pin_attempts_remaining == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ERRORS["NO_MORE_PIN_ATTEMPTS"],
        )

    pin_verification_status = airt_service.sms_utils.verify_pin(
        sms_protocol.pin_id, otp
    )

    if "requestError" in pin_verification_status:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"{pin_verification_status['requestError']['serviceException']['text']}",
        )

    if not pin_verification_status["verified"]:
        with commit_or_rollback(session):
            sms_protocol.pin_verified = pin_verification_status["verified"]  # type: ignore
            sms_protocol.pin_attempts_remaining = pin_verification_status[
                "attemptsRemaining"
            ]  # type: ignore
            session.add(sms_protocol)

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ERRORS[f"{pin_verification_status['pinError']}"],
        )

    with commit_or_rollback(session):
        session.delete(sms_protocol)
