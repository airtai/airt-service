# AUTOGENERATED! DO NOT EDIT! File to edit: ../../notebooks/AWS_Utils.ipynb.

# %% auto 0
__all__ = ['get_available_aws_regions', 'verify_aws_region', 'get_s3_storage_bucket', 'create_s3_datablob_path',
           'create_s3_datasource_path', 'create_s3_prediction_path', 'get_batch_environment_arns',
           'get_queue_definition_arns', 'upload_to_s3_with_retry', 'get_s3_bucket_and_path_from_uri']

# %% ../../notebooks/AWS_Utils.ipynb 3
import os
import yaml
from pathlib import Path
from typing import *

import boto3
import requests
from botocore.client import Config
from fastapi import status, HTTPException
from mypy_boto3_s3.service_resource import Bucket

from ..sanitizer import sanitized_print
from airt.helpers import get_s3_bucket_name_and_folder_from_uri
from airt.logger import get_logger

# %% ../../notebooks/AWS_Utils.ipynb 6
logger = get_logger(__name__)

# %% ../../notebooks/AWS_Utils.ipynb 7
def get_available_aws_regions() -> List[str]:
    """Get supported regions

    Returns:
        List of supported regions
    """

    # boto3.session.Session().get_available_regions('s3') is the api to get available regions of an aws service
    # batch supports one less region than s3 so hardcoding the following list of regions
    return [
        #         "af-south-1", # Africa capetown
        #         "ap-east-1", # Asia Pasific HongKong
        "ap-northeast-1",
        "ap-northeast-2",
        #         "ap-northeast-3", # Problem with creating gpu instances for training during build_wheel stage
        "ap-south-1",
        "ap-southeast-1",
        "ap-southeast-2",
        "ca-central-1",
        "eu-central-1",
        "eu-north-1",
        #         "eu-south-1", # Europe Milan
        "eu-west-1",
        "eu-west-2",
        "eu-west-3",
        #         "me-south-1", # Middle East Bahrain
        "sa-east-1",
        "us-east-1",
        "us-east-2",
        "us-west-1",
        "us-west-2",
    ]

# %% ../../notebooks/AWS_Utils.ipynb 9
def verify_aws_region(region: str):
    """
    Verify region is in available regions else raise an error

    Args:
        region: region name
    Raises:
        HTTPException: If region is not a valid region
    """
    available_regions = get_available_aws_regions()
    if region not in available_regions:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown region - {region}; Available regions are {', '.join(available_regions)}",
        )

# %% ../../notebooks/AWS_Utils.ipynb 11
def get_s3_storage_bucket(region: str = "eu-west-1") -> Tuple[Bucket, str]:
    """Get the root s3 bucket to store datasources, models, predictions

    Args:
        region: region name
    Returns:
        The root storage s3 bucket
    Raises:
        HTTPException: If region is not a valid region
    """
    verify_aws_region(region)

    storage_bucket = f"s3://{os.environ['STORAGE_BUCKET_PREFIX']}-{region}"
    bucket_name, base_path = get_s3_bucket_name_and_folder_from_uri(storage_bucket)

    s3 = boto3.resource("s3", config=Config(signature_version="s3v4"))
    bucket = s3.Bucket(bucket_name)

    if not bucket.creation_date:
        s3_client = boto3.client(
            "s3", region_name=region, config=Config(signature_version="s3v4")
        )
        #         region = s3_client.meta.region_name
        try:
            s3_client.create_bucket(
                Bucket=bucket_name,
                CreateBucketConfiguration={"LocationConstraint": region},
            )
        except s3_client.exceptions.BucketAlreadyOwnedByYou as e:
            logger.info("Bucket already created")
        bucket = s3.Bucket(bucket_name)
    return bucket, base_path

# %% ../../notebooks/AWS_Utils.ipynb 15
def create_s3_datablob_path(
    user_id: int, datablob_id: int, region: str
) -> Tuple[Bucket, str]:
    """Create an S3 path to store the datablobs

    Args:
        user_id: User id
        datablob_id: Datablob id

    Returns:
        The root storage bucket object and the s3 path as a tuple
    """
    bucket, base_path = get_s3_storage_bucket(region=region)
    s3_path = f"{user_id}/datablob/{datablob_id}"
    s3_path = f"{base_path}/{s3_path}" if base_path else s3_path

    return bucket, s3_path

# %% ../../notebooks/AWS_Utils.ipynb 17
def create_s3_datasource_path(
    user_id: int, datasource_id: int, region: str
) -> Tuple[Bucket, str]:
    """Create an S3 path to store the datasources

    Args:
        user_id: User id
        datasource_id: Datasource id to store

    Returns:
        The root storage bucket object and the s3 path as a tuple
    """
    bucket, base_path = get_s3_storage_bucket(region=region)
    s3_path = f"{user_id}/datasource/{datasource_id}"
    s3_path = f"{base_path}/{s3_path}" if base_path else s3_path

    return bucket, s3_path

# %% ../../notebooks/AWS_Utils.ipynb 19
def create_s3_prediction_path(
    user_id: int, prediction_id: int, region: str
) -> Tuple[Bucket, str]:
    """Create an S3 path to store the prediction results

    Args:
        user_id: User id
        prediction_id: Prediction id

    Returns:
        The root storage bucket object and the s3 path as a tuple
    """
    bucket, base_path = get_s3_storage_bucket(region=region)
    s3_path = f"{user_id}/prediction/{prediction_id}"
    s3_path = f"{base_path}/{s3_path}" if base_path else s3_path

    return bucket, s3_path

# %% ../../notebooks/AWS_Utils.ipynb 21
def get_batch_environment_arns(
    region: str, batch_environment_arn_path: Optional[Union[str, Path]] = None
) -> Dict[str, Dict[str, str]]:
    """Read the batch environment arn yaml file and return as a dict

    Args:
        region: Region to get batch environment arns
        batch_environment_arn_path: Path to the arn file. If not set, then the batch_environment
            will be loaded from the current working directory

    Returns:
        The created batch environment arns as a dict
    """
    if batch_environment_arn_path is None:
        batch_environment_arn_path = Path("./batch_environment.yml")
    with open(batch_environment_arn_path) as f:
        batch_environment_arns = yaml.safe_load(f)

    return batch_environment_arns[region]

# %% ../../notebooks/AWS_Utils.ipynb 23
def get_queue_definition_arns(
    task: str,
    region: str,
    batch_environment_arn_path: Optional[Union[str, Path]] = None,
) -> Tuple[str, str]:
    """Get the job queue arn and the job definition arn for the given task

    Args:
        task: Task name
        region: Region to get queue definition arns
        batch_environment_arn_path: Path to the arn file. If not set, then the batch_environment
            will be loaded from the current working directory
    """
    batch_environment_arns = get_batch_environment_arns(
        region=region, batch_environment_arn_path=batch_environment_arn_path
    )
    job_queue_arn = batch_environment_arns[task]["job_queue_arn"]
    job_definition_arn = batch_environment_arns[task]["job_definition_arn"]
    return job_queue_arn, job_definition_arn

# %% ../../notebooks/AWS_Utils.ipynb 26
def upload_to_s3_with_retry(
    file_to_upload: str,
    presigned_url: str,
    presigned_fields: Dict[str, Any],
    max_retry: int = 3,
    curr_iteration: int = 1,
):
    """
    Helper function to upload local files to s3 using presigned url; Used only in tests

    Args:
        file_to_upload: path of file to upload
        presigned_url: presigned url to upload to
        presigned_fields: presigned fields provided by boto3
        max_retry: maximum retry count
        curr_iteration: current iteration count for internal use
    """
    try:
        with open(file_to_upload, "rb") as f:
            files = {"file": (str(file_to_upload), f)}
            response = requests.post(presigned_url, data=presigned_fields, files=files)
            assert response.status_code == 204, response.text  # nosec B101
    except requests.exceptions.ConnectionError as e:
        sanitized_print("Retrying upload")
        if curr_iteration == max_retry:
            sanitized_print("Retry failed")
            raise e
        upload_to_s3_with_retry(
            file_to_upload,
            presigned_url,
            presigned_fields,
            max_retry,
            curr_iteration + 1,
        )

# %% ../../notebooks/AWS_Utils.ipynb 28
def get_s3_bucket_and_path_from_uri(uri: Union[str, Path]) -> Tuple[Bucket, str]:
    """Get bucket object and s3 path from s3 uri

    Args:
        uri: full s3 uri

    Returns:
        The bucket object and the s3 path as a tuple
    """
    s3 = boto3.resource("s3", config=Config(signature_version="s3v4"))
    bucket_name, s3_path = get_s3_bucket_name_and_folder_from_uri(str(uri))
    bucket = s3.Bucket(bucket_name)
    return bucket, s3_path
