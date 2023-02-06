# AUTOGENERATED! DO NOT EDIT! File to edit: ../../notebooks/Azure_Utils.ipynb.

# %% auto 0
__all__ = ['get_available_azure_regions', 'verify_azure_region', 'create_azure_resource_group_storage_account_and_container',
           'get_azure_blob_storage_container', 'create_azure_blob_storage_datablob_path',
           'create_azure_blob_storage_datasource_path', 'create_azure_blob_storage_prediction_path',
           'get_azure_batch_environment_component_names', 'get_batch_account_pool_job_names']

# %% ../../notebooks/Azure_Utils.ipynb 3
import logging
import os
from pathlib import Path
from typing import *

import yaml
from airt.helpers import get_s3_bucket_name_and_folder_from_uri
from airt.logger import get_logger
from azure.identity import DefaultAzureCredential
from azure.mgmt.resource import ResourceManagementClient
from azure.mgmt.storage import StorageManagementClient
from azure.storage.blob import BlobServiceClient
from azure.storage.blob._container_client import ContainerClient
from fastapi import HTTPException, status

import airt_service.sanitizer

# %% ../../notebooks/Azure_Utils.ipynb 6
logger = get_logger(__name__)

# %% ../../notebooks/Azure_Utils.ipynb 7
# This is needed to disable excessive logging from azure-storage-blob library

(logging.getLogger("azure.core.pipeline.policies.http_logging_policy")).setLevel(
    logging.WARNING
)

# %% ../../notebooks/Azure_Utils.ipynb 8
def get_available_azure_regions() -> List[str]:
    """Get supported azure regions

    Returns:
        List of supported azure regions
    """

    # Hardcoded list from https://stackoverflow.com/a/61263190/3664629
    # ToDo: retrieve programmatically and replace
    return [
        "australiacentral",
        "australiacentral2",
        "australiaeast",
        "australiasoutheast",
        "brazilsouth",
        "canadacentral",
        "canadaeast",
        "centralindia",
        "centralus",
        "eastasia",
        "eastus",
        "eastus2",
        "francecentral",
        "francesouth",
        "germanynorth",
        "germanywestcentral",
        "japaneast",
        "japanwest",
        "koreacentral",
        "koreasouth",
        "northcentralus",
        "northeurope",
        "norwayeast",
        "norwaywest",
        "southafricanorth",
        "southafricawest",
        "southcentralus",
        "southeastasia",
        "southindia",
        "switzerlandnorth",
        "switzerlandwest",
        "uaecentral",
        "uaenorth",
        "uksouth",
        "ukwest",
        "westcentralus",
        "westeurope",
        "westindia",
        "westus",
        "westus2",
    ]

# %% ../../notebooks/Azure_Utils.ipynb 10
def verify_azure_region(region: str):
    """
    Verify given region is in available azure regions else raise an error

    Args:
        region: region name
    Raises:
        HTTPException: If region is not a valid region
    """
    available_regions = get_available_azure_regions()
    if region not in available_regions:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown region - {region}; Available regions are {', '.join(available_regions)}",
        )

# %% ../../notebooks/Azure_Utils.ipynb 12
def create_azure_resource_group_storage_account_and_container(
    resource_group_region: str = "westeurope",
    *,
    storage_account_region: str,
) -> str:
    """
    Create azure resource group and storage account

    Args:
        resource_group_region: region of resource group
        storage_account_region: region of storage account
    Returns:
        Created storage account's name
    """
    credential = DefaultAzureCredential()
    subscription_id = os.environ["AZURE_SUBSCRIPTION_ID"]

    resource_group = os.environ["AZURE_RESOURCE_GROUP"]
    resource_client = ResourceManagementClient(credential, subscription_id)
    rg_result = resource_client.resource_groups.create_or_update(
        resource_group, {"location": resource_group_region}
    )

    storage_client = StorageManagementClient(credential, subscription_id)
    storage_account_name = (
        f"{os.environ['AZURE_STORAGE_ACCOUNT_PREFIX']}{storage_account_region}"[-24:]
    )
    availability_result = storage_client.storage_accounts.check_name_availability(
        {"name": storage_account_name}
    )

    if availability_result.name_available:
        poller = storage_client.storage_accounts.begin_create(
            resource_group,
            storage_account_name,
            {
                "location": storage_account_region,
                "kind": "StorageV2",
                "sku": {"name": "Standard_LRS"},
            },
        )

        # Long-running operations return a poller object; calling poller.result()
        # waits for completion.
        account_result = poller.result()

    # Container name is same as storage account name
    container = storage_client.blob_containers.create(
        resource_group, storage_account_name, storage_account_name, {}
    )
    return storage_account_name

# %% ../../notebooks/Azure_Utils.ipynb 14
def get_azure_blob_storage_container(
    region: str = "westeurope",
) -> Tuple[ContainerClient, str]:
    """Get the root azure blob storage container to store datasources, models, predictions

    Args:
        region: region name
    Returns:
        The root storage azure blob storage container
    Raises:
        HTTPException: If region is not a valid region
    """
    verify_azure_region(region)

    storage_account_name = create_azure_resource_group_storage_account_and_container(
        storage_account_region=region,
    )

    storage_container_path = (
        f"https://{storage_account_name}.blob.core.windows.net/{storage_account_name}"
    )

    storage_account, base_path = get_s3_bucket_name_and_folder_from_uri(
        storage_container_path
    )
    container_name = base_path.split("/")[0]
    base_path = "/".join(base_path.split("/")[1:])

    blob_service_client = BlobServiceClient(
        account_url=f"https://{storage_account}",
        credential=DefaultAzureCredential(),
    )
    container_client = blob_service_client.get_container_client(
        container=container_name
    )

    return container_client, base_path

# %% ../../notebooks/Azure_Utils.ipynb 17
def create_azure_blob_storage_datablob_path(
    user_id: int, datablob_id: int, region: str
) -> Tuple[ContainerClient, str]:
    """Create an S3 path to store the datablobs

    Args:
        user_id: User id
        datablob_id: Datablob id

    Returns:
        The root storage bucket object and the s3 path as a tuple
    """
    container_client, base_path = get_azure_blob_storage_container(region=region)
    azure_blob_storage_path = f"{user_id}/datablob/{datablob_id}"
    azure_blob_storage_path = (
        f"{base_path}/{azure_blob_storage_path}"
        if base_path
        else azure_blob_storage_path
    )

    return container_client, azure_blob_storage_path

# %% ../../notebooks/Azure_Utils.ipynb 19
def create_azure_blob_storage_datasource_path(
    user_id: int, datasource_id: int, region: str
) -> Tuple[ContainerClient, str]:
    """Create an azure blob storage path to store the datasources

    Args:
        user_id: User id
        datasource_id: Datasource id to store

    Returns:
        The root container client object and the azure blob storage path as a tuple
    """
    container_client, base_path = get_azure_blob_storage_container(region=region)
    azure_blob_storage_path = f"{user_id}/datasource/{datasource_id}"
    azure_blob_storage_path = (
        f"{base_path}/{azure_blob_storage_path}"
        if base_path
        else azure_blob_storage_path
    )

    return container_client, azure_blob_storage_path

# %% ../../notebooks/Azure_Utils.ipynb 21
def create_azure_blob_storage_prediction_path(
    user_id: int, prediction_id: int, region: str
) -> Tuple[ContainerClient, str]:
    """Create an S3 path to store the prediction results

    Args:
        user_id: User id
        prediction_id: Prediction id

    Returns:
        The root storage bucket object and the s3 path as a tuple
    """
    container_client, base_path = get_azure_blob_storage_container(region=region)
    azure_blob_storage_path = f"{user_id}/prediction/{prediction_id}"
    azure_blob_storage_path = (
        f"{base_path}/{azure_blob_storage_path}"
        if base_path
        else azure_blob_storage_path
    )

    return container_client, azure_blob_storage_path

# %% ../../notebooks/Azure_Utils.ipynb 23
def get_azure_batch_environment_component_names(
    region: str, batch_environment_path: Optional[Union[str, Path]] = None
) -> Dict[str, Dict[str, str]]:
    """Read the batch environment yaml file and return as a dict

    Args:
        region: Region to get batch environment names
        batch_environment_path: Path to the yaml file with azure batch environment names. If not set, then the batch_environment
            will be loaded from the current working directory

    Returns:
        The created batch environment names as a dict
    """
    if batch_environment_path is None:
        batch_environment_path = Path("./azure_batch_environment.yml")
    with open(batch_environment_path) as f:
        batch_environment_names = yaml.safe_load(f)

    # ToDo: For now we have azure batch environment only for northeurope region. Fix this once we have more regions
    return batch_environment_names["northeurope"]

# %% ../../notebooks/Azure_Utils.ipynb 25
def get_batch_account_pool_job_names(
    task: str,
    region: str,
    batch_environment_path: Optional[Union[str, Path]] = None,
) -> Tuple[str, str, str]:
    """Get the job queue arn and the job definition arn for the given task

    Args:
        task: Task name
        region: Region to get component names
        batch_environment_path: Path to the yaml file with azure batch environment names. If not set, then the batch_environment
            will be loaded from the current working directory
    Returns:
        A tuple which consists of batch account name, batch pool name, batch job name for the given task and region
    """
    batch_environment_component_names = get_azure_batch_environment_component_names(
        region=region, batch_environment_path=batch_environment_path
    )
    batch_account_name = batch_environment_component_names[task]["batch_account_name"]
    batch_pool_name = batch_environment_component_names[task]["batch_pool_name"]
    batch_job_name = batch_environment_component_names[task]["batch_job_name"]

    return batch_account_name, batch_pool_name, batch_job_name
