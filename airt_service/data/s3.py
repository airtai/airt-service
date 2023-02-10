# AUTOGENERATED! DO NOT EDIT! File to edit: ../../notebooks/DataBlob_S3.ipynb.

# %% auto 0
__all__ = ['copy_between_s3', 's3_pull', 's3_push']

# %% ../../notebooks/DataBlob_S3.ipynb 3
import shutil
from datetime import datetime
from typing import *

from airt.helpers import get_s3_bucket_name_and_folder_from_uri
from airt.logger import get_logger
from airt.remote_path import RemotePath
from fastcore.script import call_parse
from fastcore.utils import *
from sqlmodel import select

import airt_service.sanitizer
from ..aws.utils import create_s3_datablob_path
from ..azure.utils import create_azure_blob_storage_datablob_path
from ..constants import METADATA_FOLDER_PATH
from airt_service.data.utils import (
    calculate_data_object_folder_size_and_path,
    calculate_data_object_pulled_on,
    get_s3_connection_params_from_db_uri,
)
from ..db.models import DataBlob, PredictionPush, get_session_with_context
from ..helpers import truncate

# %% ../../notebooks/DataBlob_S3.ipynb 6
logger = get_logger(__name__)

# %% ../../notebooks/DataBlob_S3.ipynb 7
def copy_between_s3(
    source_remote_url: str,
    destination_remote_url: str,
    source_access_key: Optional[str] = None,
    source_secret_key: Optional[str] = None,
    destination_access_key: Optional[str] = None,
    destination_secret_key: Optional[str] = None,
    datablob: Optional[DataBlob] = None,
    skip_metadata_dir: Optional[bool] = False,
) -> None:
    """Copy files from source S3 path and to destination S3 path

    By default, all files are copied to the destination_remote_url. In case
    the **skip_metadata_dir** flag is set to **True**, then the **.metadata_by_airt**
    folder will not be copied to the destination_remote_url.

    Args:
        source_remote_url: S3 uri where files to copy are located
        destination_remote_url: S3 uri to copy files
        source_access_key: Source s3 bucket access key
        source_secret_key: Source s3 bucket secret key
        destination_access_key: Destination s3 bucket access key
        destination_secret_key: Destination s3 bucket secret key
        datablob: Optional datablob object to calculate pulled_on field
        skip_metadata_dir: If set to **True** then the **.metadata_by_airt** folder
            will not be copied to the destination_remote_url.
    """
    with RemotePath.from_url(
        remote_url=destination_remote_url,
        pull_on_enter=False,
        push_on_exit=True,
        exist_ok=True,
        parents=True,
        access_key=destination_access_key,
        secret_key=destination_secret_key,
    ) as destionation_s3_path:
        sync_path = destionation_s3_path.as_path()
        with RemotePath.from_url(
            remote_url=source_remote_url,
            pull_on_enter=True,
            push_on_exit=False,
            exist_ok=True,
            parents=False,
            access_key=source_access_key,
            secret_key=source_secret_key,
        ) as source_s3_path:
            if datablob is not None:
                calculate_data_object_pulled_on(datablob)

            source_files = source_s3_path.as_path().iterdir()

            if skip_metadata_dir:
                source_files = [
                    f for f in source_files if METADATA_FOLDER_PATH not in str(f)
                ]

            for f in source_files:
                shutil.move(str(f), sync_path)

        if len(list(sync_path.glob("*"))) == 0:
            raise ValueError(
                f"URI {source_remote_url} is invalid or no files available"
            )

# %% ../../notebooks/DataBlob_S3.ipynb 10
@call_parse
def s3_pull(datablob_id: int) -> None:
    """Pull the data from s3 and updates progress in db

    Args:
        datablob_id: Id of datablob in db

    Example:
        The following code executes a CLI command:
        ```s3_pull 1
        ```
    """
    with get_session_with_context() as session:
        datablob = session.exec(
            select(DataBlob).where(DataBlob.id == datablob_id)
        ).one()

        datablob.error = None
        datablob.completed_steps = 0
        datablob.folder_size = None
        datablob.path = None

        (
            uri,
            source_access_key,
            source_secret_key,
        ) = get_s3_connection_params_from_db_uri(db_uri=datablob.uri)

        try:
            source_bucket, folder = get_s3_bucket_name_and_folder_from_uri(uri=uri)
            source_remote_url = f"s3://{source_bucket}/{folder}"

            if datablob.cloud_provider == "aws":
                destination_bucket, s3_path = create_s3_datablob_path(
                    user_id=datablob.user.id,
                    datablob_id=datablob.id,
                    region=datablob.region,
                )
                destination_remote_url = f"s3://{destination_bucket.name}/{s3_path}"
            elif datablob.cloud_provider == "azure":
                (
                    destination_container_client,
                    destination_azure_blob_storage_path,
                ) = create_azure_blob_storage_datablob_path(
                    user_id=datablob.user.id,
                    datablob_id=datablob.id,
                    region=datablob.region,
                )
                destination_remote_url = f"{destination_container_client.url}/{destination_azure_blob_storage_path}"

            with RemotePath.from_url(
                remote_url=destination_remote_url,
                pull_on_enter=False,
                push_on_exit=True,
                exist_ok=True,
                parents=True,
            ) as destionation_remote_path:
                sync_path = destionation_remote_path.as_path()
                with RemotePath.from_url(
                    remote_url=source_remote_url,
                    pull_on_enter=True,
                    push_on_exit=False,
                    exist_ok=True,
                    parents=False,
                    access_key=source_access_key,
                    secret_key=source_secret_key,
                ) as source_s3_path:
                    calculate_data_object_pulled_on(datablob)

                    source_files = source_s3_path.as_path().iterdir()
                    for f in source_files:
                        shutil.move(str(f), sync_path)

                if len(list(sync_path.glob("*"))) == 0:
                    raise ValueError(
                        f"URI {source_remote_url} is invalid or no files available"
                    )

            # Calculate folder size in S3/Azure blob storage
            calculate_data_object_folder_size_and_path(datablob)
        except Exception as e:
            datablob.error = truncate(str(e))

        session.add(datablob)
        session.commit()

# %% ../../notebooks/DataBlob_S3.ipynb 14
@call_parse
def s3_push(prediction_push_id: int) -> None:
    """Push the data from s3 and update its progress in db

    Args:
        prediction_push_id: Id of prediction_push

    Example:
        The following code executes a CLI command:
        ```s3_push 1
        ```
    """
    with get_session_with_context() as session:
        prediction_push = session.exec(
            select(PredictionPush).where(PredictionPush.id == prediction_push_id)
        ).one()

        prediction_push.error = None
        prediction_push.completed_steps = 0

        (
            uri,
            destination_access_key,
            destination_secret_key,
        ) = get_s3_connection_params_from_db_uri(db_uri=prediction_push.uri)

        try:
            (
                destination_bucket,
                destination_s3_path,
            ) = get_s3_bucket_name_and_folder_from_uri(uri=uri)
            source_remote_url = prediction_push.prediction.path
            destination_remote_url = f"s3://{destination_bucket}/{destination_s3_path}"

            with RemotePath.from_url(
                remote_url=destination_remote_url,
                pull_on_enter=False,
                push_on_exit=True,
                exist_ok=True,
                parents=True,
                access_key=destination_access_key,
                secret_key=destination_secret_key,
            ) as destionation_s3_path:
                sync_path = destionation_s3_path.as_path()
                with RemotePath.from_url(
                    remote_url=source_remote_url,
                    pull_on_enter=True,
                    push_on_exit=False,
                    exist_ok=True,
                    parents=False,
                ) as source_remote_path:
                    source_files = source_remote_path.as_path().iterdir()
                    for f in source_files:
                        shutil.move(str(f), sync_path)

                if len(list(sync_path.glob("*"))) == 0:
                    raise ValueError(
                        f"URI {source_remote_url} is invalid or no files available"
                    )

            prediction_push.completed_steps = 1
        except Exception as e:
            prediction_push.error = truncate(str(e))

        session.add(prediction_push)
        session.commit()
