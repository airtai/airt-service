# AUTOGENERATED! DO NOT EDIT! File to edit: ../../notebooks/Data_Utils.ipynb.

# %% auto 0
__all__ = ['create_db_uri_for_s3_datablob', 'get_s3_connection_params_from_db_uri',
           'create_db_uri_for_azure_blob_storage_datablob', 'get_azure_blob_storage_connection_params_from_db_uri',
           'create_db_uri_for_db_datablob', 'get_db_connection_params_from_db_uri', 'create_db_uri_for_local_datablob',
           'calculate_azure_data_object_folder_size_and_path', 'calculate_s3_data_object_folder_size_and_path',
           'calculate_data_object_folder_size_and_path', 'calculate_data_object_pulled_on',
           'delete_data_object_files_in_cloud']

# %% ../../notebooks/Data_Utils.ipynb 3
import re
from datetime import datetime
from typing import *
from urllib.parse import unquote_plus as urlunquote

import dask.dataframe as dd
from airt.logger import get_logger
from mypy_boto3_s3.service_resource import Bucket

import airt_service.sanitizer
from airt_service.aws.utils import (
    create_s3_datablob_path,
    create_s3_datasource_path,
    get_s3_bucket_and_path_from_uri,
    get_s3_bucket_name_and_folder_from_uri,
)
from airt_service.azure.utils import (
    create_azure_blob_storage_datablob_path,
    create_azure_blob_storage_datasource_path,
    get_azure_blob_storage_container,
)
from ..constants import METADATA_FOLDER_PATH
from airt_service.db.models import (
    DataBlob,
    DataSource,
    Model,
    Prediction,
    create_connection_string,
)

# %% ../../notebooks/Data_Utils.ipynb 6
logger = get_logger(__name__)

# %% ../../notebooks/Data_Utils.ipynb 7
def create_db_uri_for_s3_datablob(uri: str, access_key: str, secret_key: str) -> str:
    """Create db_uri for s3 datablob based on s3 connection params

    Args:
        uri: URI of s3 datablob
        access_key: Access key of s3 datablob
        secret_key: Secret key of s3 datablob

    Returns:
        The uri for the s3 datablob
    """
    return f"s3://{access_key}:{secret_key}@{uri.replace('s3://', '')}"

# %% ../../notebooks/Data_Utils.ipynb 9
def get_s3_connection_params_from_db_uri(db_uri: str) -> Tuple[str, str, str]:
    """Get S3 connection params from db_uri of the s3 datablob

    Args:
        db_uri: DB uri of s3 datablob

    Returns:
        The uri, access key and secret key of the s3 datablob as a tuple
    """
    result = re.search("s3:\/\/(.*):(.*)@(.*)", db_uri)
    access_key = result.group(1)  # type: ignore
    secret_key = result.group(2)  # type: ignore
    uri = f"s3://{result.group(3)}"  # type: ignore
    return uri, access_key, secret_key

# %% ../../notebooks/Data_Utils.ipynb 11
def create_db_uri_for_azure_blob_storage_datablob(uri: str, credential: str) -> str:
    """Create db_uri for azure datablob based on azure blob storage connection params

    Args:
        uri: URI of azure blob storage datablob
        credential: Credential of azure blob storage datablob

    Returns:
        The uri for the azure blob storage datablob
    """
    return f"https://{credential}@{uri.replace('https://', '')}"

# %% ../../notebooks/Data_Utils.ipynb 13
def get_azure_blob_storage_connection_params_from_db_uri(
    db_uri: str,
) -> Tuple[str, str]:
    """Get azure blob storage connection params from db_uri of the azure blob storage datablob

    Args:
        db_uri: DB uri of azure blob storage datablob

    Returns:
        The uri and credential of the azure blob storage datablob as a tuple
    """
    result = re.search("https:\/\/(.*)@(.*)", db_uri)
    credential = result.group(1)  # type: ignore
    uri = f"https://{result.group(2)}"  # type: ignore
    return uri, credential

# %% ../../notebooks/Data_Utils.ipynb 15
def create_db_uri_for_db_datablob(
    username: str,
    password: str,
    host: str,
    port: int,
    table: str,
    database: str,
    database_server: str,
) -> str:
    """Create db_uri for the datablob based on connection params

    Args:
        username: Username of db datablob
        password: Password of db datablob
        host: Host of db datablob
        port: Port of db datablob
        table: Table of db datablob
        database: Database to use
        database_server: Server/engine of db datablob
    Returns:
        The db_uri for the db datasource
    """
    db_uri = create_connection_string(
        username=username,
        password=password,
        host=host,
        port=port,
        database=database,
        database_server=database_server,
    )
    db_uri = f"{db_uri}/{table}"
    return db_uri

# %% ../../notebooks/Data_Utils.ipynb 17
def get_db_connection_params_from_db_uri(
    db_uri: str,
) -> Tuple[str, str, str, int, str, str, str]:
    """Get db connection params from db_uri

    Args:
        db_uri: DB uri of db datablob
    Returns:
        The username, password, host, port, table, database, database_server of the datablob as a tuple
    """
    result = re.search("(.*):\/\/(.*):(.*)@(.*):(.*)\/(.*)\/(.*)", db_uri)
    database_server = result.group(1)  # type: ignore
    username = result.group(2)  # type: ignore
    password = urlunquote(result.group(3))  # type: ignore
    host = result.group(4)  # type: ignore
    port = int(result.group(5))  # type: ignore
    database = result.group(6)  # type: ignore
    table = result.group(7)  # type: ignore
    return username, password, host, port, table, database, database_server

# %% ../../notebooks/Data_Utils.ipynb 19
def create_db_uri_for_local_datablob(bucket: Bucket, s3_path: str) -> str:
    """Create db_uri for csv datablob

    Args:
        bucket: S3 bucket object
        s3_path: S3 path in which uploaded csv is stored

    Returns:
        The db uri for the csv datablob
    """
    return f"s3://{bucket.name}/{s3_path}"

# %% ../../notebooks/Data_Utils.ipynb 21
def calculate_azure_data_object_folder_size_and_path(
    data_object: Union[DataBlob, DataSource]
):
    """Calculate datasource/datablob folder size based on azure blob storage object size and its path

    Args:
        data_object: DataBlob or DataSource object
    """
    if isinstance(data_object, DataBlob):
        (
            container_client,
            azure_blob_storage_path,
        ) = create_azure_blob_storage_datablob_path(
            user_id=data_object.user.id, datablob_id=data_object.id, region=data_object.region  # type: ignore
        )
    elif isinstance(data_object, DataSource):
        (
            container_client,
            azure_blob_storage_path,
        ) = create_azure_blob_storage_datasource_path(
            user_id=data_object.user.id, datasource_id=data_object.id, region=data_object.region  # type: ignore
        )
    destination_container_objects = list(
        container_client.list_blobs(name_starts_with=azure_blob_storage_path + "/")
    )
    data_object.completed_steps = 1
    data_object.folder_size = sum(
        obj["size"]
        for obj in destination_container_objects
        if METADATA_FOLDER_PATH not in obj["name"]
    )
    data_object.path = f"{container_client.url}/{azure_blob_storage_path}"  # type: ignore

# %% ../../notebooks/Data_Utils.ipynb 23
def calculate_s3_data_object_folder_size_and_path(
    data_object: Union[DataBlob, DataSource]
):
    """Calculate datasource/datablob folder size based on s3 object size and its s3 path

    Args:
        data_object: DataBlob or DataSource object
    """
    if isinstance(data_object, DataBlob):
        destination_bucket, s3_path = create_s3_datablob_path(
            user_id=data_object.user.id, datablob_id=data_object.id, region=data_object.region  # type: ignore
        )
    elif isinstance(data_object, DataSource):
        destination_bucket, s3_path = create_s3_datasource_path(
            user_id=data_object.user.id, datasource_id=data_object.id, region=data_object.region  # type: ignore
        )
    destination_bucket_objects = list(
        destination_bucket.objects.filter(Prefix=s3_path + "/")
    )
    data_object.completed_steps = 1
    data_object.folder_size = sum(
        obj.size
        for obj in destination_bucket_objects
        if METADATA_FOLDER_PATH not in obj.key
    )
    data_object.path = f"s3://{destination_bucket.name}/{s3_path}"  # type: ignore

# %% ../../notebooks/Data_Utils.ipynb 25
def calculate_data_object_folder_size_and_path(
    data_object: Union[DataBlob, DataSource]
):
    """Calculate datasource/datablob folder size for both aws and azure data objects

    Args:
        data_object: DataBlob or DataSource object
    """
    if data_object.cloud_provider == "aws":
        calculate_s3_data_object_folder_size_and_path(data_object=data_object)
    elif data_object.cloud_provider == "azure":
        calculate_azure_data_object_folder_size_and_path(data_object=data_object)

# %% ../../notebooks/Data_Utils.ipynb 27
def calculate_data_object_pulled_on(data_object: Union[DataBlob, DataSource]):
    """Calculate datasource/datablob's pulled_on datetime

    Args:
        data_object: DataBlob or DataSource object
    """
    data_object.pulled_on = datetime.utcnow()

# %% ../../notebooks/Data_Utils.ipynb 29
def delete_data_object_files_in_cloud(
    data_object: Union[DataBlob, DataSource, Model, Prediction]
):
    """
    Delete files for data object stored in cloud - aws or azure

    Args:
        data_object: object of type DataBlob, DataSource, Model, Prediction
    """

    if (
        data_object.completed_steps != data_object.total_steps
        or data_object.disabled == True
    ):
        return

    if data_object.cloud_provider == "aws":
        bucket, s3_path = get_s3_bucket_and_path_from_uri(data_object.path)  # type: ignore
        bucket.objects.filter(Prefix=s3_path + "/").delete()
    elif data_object.cloud_provider == "azure":
        container_client, _ = get_azure_blob_storage_container(
            region=data_object.region
        )
        blob_folder = "/".join(
            get_s3_bucket_name_and_folder_from_uri(data_object.path)[1].split("/")[1:]
        )
        for blob in container_client.list_blobs(name_starts_with=blob_folder + "/"):
            container_client.delete_blob(blob)
