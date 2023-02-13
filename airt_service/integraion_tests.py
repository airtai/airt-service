# AUTOGENERATED! DO NOT EDIT! File to edit: ../notebooks/Integration_Test.ipynb.

# %% auto 0
__all__ = ['integration_scenario_docs', 'test_auth', 'test_create_user', 'test_apikey', 'check_steps_completed',
           'test_csv_local_datablob_and_datasource', 'test_azure_datablob', 'test_model', 'test_prediction',
           'test_generate_mfa_url', 'get_valid_otp', 'test_activate_mfa', 'reset_test_user_password',
           'test_disable_mfa', 'test_auth_with_otp', 'delete_test_user', 'integration_tests', 'run_integration_tests']

# %% ../notebooks/Integration_Test.ipynb 3
import json
import os
import random
import string
import time
from datetime import datetime, timedelta
from typing import *

import httpx
import pandas as pd
import pyotp
from airt.remote_path import RemotePath
from azure.identity import DefaultAzureCredential
from azure.mgmt.storage import StorageManagementClient
from fastcore.script import Param, call_parse
from sqlmodel import select

from .aws.utils import upload_to_s3_with_retry
from .sanitizer import sanitized_print

# %% ../notebooks/Integration_Test.ipynb 5
def integration_scenario_docs(base_url: str = "http://127.0.0.1:6006") -> None:
    """Test fastapi docs

    Args:
        base_url: Base url
    """
    sanitized_print("getting /docs")
    r = httpx.get(f"{base_url}/docs")
    assert not r.is_error, r  # nosec B101

    sanitized_print("getting /redocs")
    r = httpx.get(f"{base_url}/redoc")
    assert not r.is_error, r  # nosec B101

# %% ../notebooks/Integration_Test.ipynb 6
def test_auth(base_url: str, username: str, password: str) -> str:
    """Get jwt token for given credentials

    Args:
        base_url: Base url
        username: Username
        password: Password
    Returns:
        The jwt token for the given username and password
    """
    # Authenticate
    sanitized_print("authenticating and getting token")
    r = httpx.post(
        f"{base_url}/token",
        data=dict(username=username, password=password),
        timeout=30,
    )
    assert not r.is_error, r.text  # nosec B101
    token = r.json()["access_token"]
    return token

# %% ../notebooks/Integration_Test.ipynb 7
def test_create_user(base_url: str) -> Tuple[Dict[str, Any], str]:
    """Create a new user for testing

    Args:
        base_url: Base url
    Returns:
        The user dictionary and its password as a tuple
    """
    # Get token for super user
    token = os.environ["AIRT_SERVICE_TOKEN"]
    headers = {"Authorization": f"Bearer {token}"}

    sanitized_print("creating user")
    username = "".join(  # nosec
        random.choice(string.ascii_lowercase) for _ in range(10)
    )
    password = "".join(  # nosec
        random.choice(string.ascii_lowercase) for _ in range(10)
    )
    r = httpx.post(
        f"{base_url}/user/",
        json=dict(
            username=username,
            first_name="integration",
            last_name="user",
            email=f"{username}@email.com",
            subscription_type="small",
            super_user=False,
            password=password,
            otp=None,
        ),
        headers=headers,
        timeout=30,
    )
    assert not r.is_error, r.text  # nosec B101
    user = r.json()
    return user, password

# %% ../notebooks/Integration_Test.ipynb 8
def test_apikey(
    base_url: str, headers: Dict[str, str], otp: Optional[str] = None
) -> str:
    """Create apikey for testing

    Args:
        base_url: Base url
        headers: Headers dict with authorization header
        otp: Dynamically generated six-digit verification code from the authenticator app
    Returns:
        The apikey jwt token
    """
    sanitized_print("creating apikey")
    r = httpx.post(
        f"{base_url}/apikey",
        json=dict(
            expiry=(datetime.utcnow() + timedelta(minutes=60)).isoformat(), otp=otp
        ),
        headers=headers,
    )
    assert not r.is_error, r.text  # nosec B101
    apikey = r.json()["access_token"]
    return apikey

# %% ../notebooks/Integration_Test.ipynb 9
def check_steps_completed(url: str, headers: Dict[str, str]) -> Dict[str, Any]:
    """Check whether completed steps equals to total steps

    Args:
        url: Url to call
        headers: Headers dict with authorization header
    Returns:
        The dictionary returned by url
    """
    sanitized_print("start waiting for steps to complete")
    while True:
        r = httpx.get(url, headers=headers)
        assert not r.is_error, f"{r.text=} {r.status_code=}"  # nosec B101
        obj = r.json()
        if obj["completed_steps"] == obj["total_steps"]:
            break
        time.sleep(5)
    sanitized_print("stop waiting for steps to complete")
    return obj

# %% ../notebooks/Integration_Test.ipynb 10
def test_csv_local_datablob_and_datasource(
    base_url: str, headers: Dict[str, str]
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Create datablob from local, upload csv files and create datasource from it

    Args:
        base_url: Base url
        headers: Headers dict with authorization header
    Returns:
        Datablob and datasource dictionaries as a tuple
    """
    # Create csv datablob
    sanitized_print("creating datablob")
    r = httpx.post(
        f"{base_url}/datablob/from_local/start",
        json=dict(path="tmp/test-folder/"),
        headers=headers,
    )
    assert not r.is_error, r.text  # nosec B101
    datablob_uuid = r.json()["uuid"]
    presigned = r.json()["presigned"]

    sanitized_print("downloading csv file")
    with RemotePath.from_url(
        remote_url=f"s3://test-airt-service/account_312571_events",
        pull_on_enter=True,
        push_on_exit=False,
        exist_ok=True,
        parents=False,
        access_key=os.environ["AWS_ACCESS_KEY_ID"],
        secret_key=os.environ["AWS_SECRET_ACCESS_KEY"],
    ) as test_s3_path:
        df = pd.read_parquet(test_s3_path.as_path())
        df.to_csv(test_s3_path.as_path() / "file.csv", index=False)

        sanitized_print("uploading csv file using presigned url")
        upload_to_s3_with_retry(
            test_s3_path.as_path() / "file.csv", presigned["url"], presigned["fields"]
        )

    # Create datasource from csv datablob
    sanitized_print("creating datasource")
    r = httpx.post(
        f"{base_url}/datablob/{datablob_uuid}/to_datasource",
        json=dict(
            file_type="csv",
            deduplicate_data=True,
            index_column="PersonId",
            sort_by="OccurredTime",
            blocksize="256MB",
            kwargs_json=dict(
                usecols=[0, 1, 2, 3, 4],
                parse_dates=["OccurredTime"],
            ),
        ),
        headers=headers,
    )
    assert not r.is_error, r.text  # nosec B101
    datasource = r.json()

    # Wait for pull to complete
    datasource = check_steps_completed(
        url=f"{base_url}/datasource/{datasource['uuid']}", headers=headers
    )
    sanitized_print("pull completed for datasource")

    # Get datablob object to return
    datablob = check_steps_completed(
        url=f"{base_url}/datablob/{datablob_uuid}", headers=headers
    )

    # Display head and dtypes
    r = httpx.get(f"{base_url}/datasource/{datasource['uuid']}/head", headers=headers)
    sanitized_print("head of datasource")
    sanitized_print(r.json())
    r = httpx.get(f"{base_url}/datasource/{datasource['uuid']}/dtypes", headers=headers)
    sanitized_print("dtypes of datasource")
    sanitized_print(r.json())

    return datablob, datasource

# %% ../notebooks/Integration_Test.ipynb 11
def test_azure_datablob(base_url: str, headers: Dict[str, str]) -> Dict[str, Any]:
    """Create datablob using from_azure route

    Args:
        base_url: Base url
        headers: Headers dict with authorization header
    Returns:
        A azure datablob
    """
    storage_client = StorageManagementClient(
        DefaultAzureCredential(), os.environ["AZURE_SUBSCRIPTION_ID"]
    )
    keys = storage_client.storage_accounts.list_keys(
        "test-airt-service", "testairtservice"
    )
    credential = keys.keys[0].value

    # Create azure datablob
    sanitized_print("creating azure datablob")
    r = httpx.post(
        f"{base_url}/datablob/from_azure_blob_storage",
        json=dict(
            uri="https://testairtservice.blob.core.windows.net/test-container/account_312571_events",
            credential=credential,
            cloud_provider="azure",
            region="westeurope",
        ),
        headers=headers,
    )
    assert not r.is_error, r.text  # nosec B101
    datablob = r.json()

    # Wait for pull to complete
    datablob = check_steps_completed(
        url=f"{base_url}/datablob/{datablob['uuid']}", headers=headers
    )
    sanitized_print("pull completed for azure datablob")

    return datablob

# %% ../notebooks/Integration_Test.ipynb 12
def test_model(
    base_url: str, headers: Dict[str, str], datasource: Dict[str, Any]
) -> Dict[str, Any]:
    """Train model and evaluate it for testing

    Args:
        base_url: Base url
        headers: Headers dict with authorization header
        datasource: Datasource dictionary
    Returns:
        The model dictionary
    """
    # Train model
    sanitized_print("training model")
    r = httpx.post(
        f"{base_url}/model/train",
        json=dict(
            data_uuid=datasource["uuid"],
            client_column="AccountId",
            target_column="DefinitionId",
            target="load*",
            predict_after=20 * 24 * 60 * 60,
        ),
        headers=headers,
    )
    assert not r.is_error, r.text  # nosec B101
    model = r.json()

    # Wait for model training to complete
    model = check_steps_completed(
        url=f"{base_url}/model/{model['uuid']}", headers=headers
    )
    sanitized_print("model training completed")

    # Evaluate model
    r = httpx.get(f"{base_url}/model/{model['uuid']}/evaluate", headers=headers)
    assert not r.is_error  # nosec B101
    sanitized_print("model evaluation")
    sanitized_print(r.json())

    return model

# %% ../notebooks/Integration_Test.ipynb 13
def test_prediction(
    base_url: str, headers: Dict[str, str], model: Dict[str, Any]
) -> Dict[str, Any]:
    """Run prediction and evaluate prediction for testing

    Args:
        base_url: Base url
        headers: Headers dict with authorization header
        model: Model dictionary
    Returns:
        The prediction dictionary
    """
    # Run prediction for the model
    sanitized_print("running prediction")
    r = httpx.post(
        f"{base_url}/model/{model['uuid']}/predict",
        headers=headers,
    )
    assert not r.is_error, r.text  # nosec B101
    prediction = r.json()

    # Wait for prediction to complete
    prediction = check_steps_completed(
        url=f"{base_url}/prediction/{prediction['uuid']}", headers=headers
    )
    sanitized_print("prediction completed")

    # Get prediction as pandas
    r = httpx.get(f"{base_url}/prediction/{prediction['uuid']}/pandas", headers=headers)
    assert not r.is_error  # nosec B101
    sanitized_print("prediction as pandas")
    sanitized_print(r.json())

    return prediction

# %% ../notebooks/Integration_Test.ipynb 14
def test_generate_mfa_url(base_url: str, headers: Dict[str, str]) -> Dict[str, Any]:
    """Generate mfa provisioning uri

    Args:
        base_url: Base url
        headers: Headers dict with authorization header

    Returns:
        The provisioning uri generated from the secret
    """

    r = httpx.get(f"{base_url}/user/mfa/generate", headers=headers)
    assert not r.is_error, f"{r.text=} {r.status_code=}"  # nosec B101
    sanitized_print("Generating mfa url")
    return r.json()

# %% ../notebooks/Integration_Test.ipynb 15
def get_valid_otp(mfa_url: str) -> str:
    """Get valid otp for the mfa_url

    Args:
        mfa_url: mfa provisioning url

    Returns:
        The valid otp for the url
    """
    return pyotp.TOTP(pyotp.parse_uri(mfa_url).secret).now()

# %% ../notebooks/Integration_Test.ipynb 16
def test_activate_mfa(
    base_url: str, mfa_url: str, headers: Dict[str, str]
) -> Dict[str, Any]:
    """Activate mfa

    Args:
        base_url: Base url
        mfa_url: mfa provisioning url
        headers: Headers dict with authorization header

    Returns:
        The provisioning uri generated from the secret
    """
    r = httpx.post(
        f"{base_url}/user/mfa/activate",
        json=dict(user_otp=get_valid_otp(mfa_url)),
        headers=headers,
    )
    assert not r.is_error, f"{r.text=} {r.status_code=}"  # nosec B101
    sanitized_print("Activate mfa")
    return r.json()

# %% ../notebooks/Integration_Test.ipynb 17
def reset_test_user_password(
    base_url: str, headers: Dict[str, str], username: str, password: str, otp: str
) -> None:
    """Reset the test user password"""
    sanitized_print(f"Resetting password for: {username}")
    r = httpx.post(
        f"{base_url}/user/reset_password",
        json=dict(username=username, new_password=password, otp=otp),
    )
    assert not r.is_error, r.text  # nosec B101
    sanitized_print(r.text)

# %% ../notebooks/Integration_Test.ipynb 18
def test_disable_mfa(
    base_url: str, headers: Dict[str, str], username: str, otp: Optional[str] = None
) -> None:
    """Disable MFA for the user"""
    current_active_user = httpx.get(
        f"{base_url}/user/details?user_id_or_name=None", headers=headers
    )
    current_active_user_uuid = current_active_user.json()["uuid"]
    r = httpx.delete(
        f"{base_url}/user/mfa/{current_active_user_uuid}/disable?otp={otp}",
        headers=headers,
    )
    assert not r.is_error, r.text  # nosec B101
    sanitized_print(r.text)
    assert username in r.text  # nosec B101
    sanitized_print("Deactivate mfa")

# %% ../notebooks/Integration_Test.ipynb 19
def test_auth_with_otp(
    base_url: str, username: str, password: str, mfa_url: str, retry_limit: int = 3
) -> str:
    """Get jwt token for given credentials and otp

    Args:
        base_url: Base url
        username: Username
        password: Password
        mfa_url: MFA URL
        retry_limit: Retry limit if there is an error with otp auth
    Returns:
        The jwt token for the given username and password
    """
    # Authenticate
    sanitized_print("authenticating with otp and getting token")
    for i in range(retry_limit):
        otp = get_valid_otp(mfa_url)
        r = httpx.post(
            f"{base_url}/token",
            data=dict(
                username=username,
                password=json.dumps(
                    {
                        "password": password,
                        "user_otp": otp,
                    }
                ),
            ),
        )

        if not r.is_error:
            break

    assert not r.is_error, r.text  # nosec B101
    token = r.json()["access_token"]
    return token

# %% ../notebooks/Integration_Test.ipynb 20
def delete_test_user(base_url: str, test_username: str) -> None:
    """Delete the test user created for testing

    Args:
        base_url: Base url
        test_username: Username to delete
    """
    # Get token for super user
    token = os.environ["AIRT_SERVICE_TOKEN"]
    headers = {"Authorization": f"Bearer {token}"}

    sanitized_print("deleting test user")
    r = httpx.post(
        f"{base_url}/user/cleanup",
        json=dict(
            username=test_username,
        ),
        headers=headers,
        timeout=None,
    )
    assert not r.is_error, r.text  # nosec B101

# %% ../notebooks/Integration_Test.ipynb 21
def integration_tests(base_url: str = "http://127.0.0.1:6006") -> None:
    """Integration tests

    Args:
        base_url: Base url
    """
    sanitized_print("starting integration tests")
    integration_scenario_docs(base_url)

    user, password = test_create_user(base_url)

    token = test_auth(
        base_url,
        username=user["username"],
        password=password,
    )
    headers = {"Authorization": f"Bearer {token}"}

    # enable mfa for the user
    mfa_url = test_generate_mfa_url(base_url, headers)
    # activate mfa
    test_activate_mfa(base_url, mfa_url["mfa_url"], headers)

    # Get token by passing password and otp as json encoded dict
    token = test_auth_with_otp(
        base_url,
        username=user["username"],
        password=password,
        mfa_url=mfa_url["mfa_url"],
        retry_limit=3,
    )

    headers = {"Authorization": f"Bearer {token}"}

    apikey = test_apikey(base_url, headers, otp=get_valid_otp(mfa_url["mfa_url"]))
    headers = {"Authorization": f"Bearer {apikey}"}

    datablob, datasource = test_csv_local_datablob_and_datasource(base_url, headers)

    azure_datablob = test_azure_datablob(base_url, headers)

    model = test_model(base_url, headers, datasource)

    prediction = test_prediction(base_url, headers, model)

    new_password = "new_password"  # nosec B105
    reset_test_user_password(
        base_url=base_url,
        headers=headers,
        username=user["username"],
        password=new_password,
        otp=get_valid_otp(mfa_url["mfa_url"]),
    )

    # Get token by using the new password
    token = test_auth_with_otp(
        base_url,
        username=user["username"],
        password=new_password,
        mfa_url=mfa_url["mfa_url"],
        retry_limit=3,
    )

    headers = {"Authorization": f"Bearer {token}"}

    test_disable_mfa(
        base_url, headers, user["username"], otp=get_valid_otp(mfa_url["mfa_url"])
    )

    delete_test_user(base_url, test_username=user["username"])

    sanitized_print("ok")

# %% ../notebooks/Integration_Test.ipynb 23
@call_parse  # type: ignore
def run_integration_tests(
    host: Param("hostname", str),  # type: ignore
    port: Param("port", int),  # type: ignore
    protocol: Param("http or https", str) = "https",  # type: ignore
) -> None:
    """Run integration tests against given host and port

    Args:
        host: Hostname of the webserver to run tests against
        port: Port of the webserver
        protocol: Protocol to use for testing
    """
    base_url = f"{protocol}://{host}:{port}"
    integration_tests(base_url=base_url)
