# AUTOGENERATED! DO NOT EDIT! File to edit: ../notebooks/BatchJob.ipynb.

# %% auto 0
__all__ = ["get_environment_vars_for_batch_job", "create_batch_job"]

# %% ../notebooks/BatchJob.ipynb 2
from .batch_job_components.base import BatchJobContext

from .batch_job_components.aws import AwsBatchJobContext
from .batch_job_components.azure import AzureBatchJobContext
from .batch_job_components.fastapi import FastAPIBatchJobContext
from .batch_job_components.none import NoneBatchJobContext

# %% ../notebooks/BatchJob.ipynb 4
from os import environ

from fastapi import BackgroundTasks

from airt.logger import get_logger

# %% ../notebooks/BatchJob.ipynb 6
logger = get_logger(__name__)

# %% ../notebooks/BatchJob.ipynb 7
def get_environment_vars_for_batch_job() -> dict:
    """Get the necessary environment variables for creating a batch job

    Returns:
        The environment variables as a dict
    """
    return {
        var: environ[var]
        for var in [
            "AWS_ACCESS_KEY_ID",
            "AWS_SECRET_ACCESS_KEY",
            "AWS_DEFAULT_REGION",
            "AZURE_SUBSCRIPTION_ID",
            "AZURE_TENANT_ID",
            "AZURE_CLIENT_ID",
            "AZURE_CLIENT_SECRET",
            "AZURE_STORAGE_ACCOUNT_PREFIX",
            "AZURE_RESOURCE_GROUP",
            #             "AIRT_SERVICE_SUPER_USER_PASSWORD",
            #             "AIRT_TOKEN_SECRET_KEY",
            "STORAGE_BUCKET_PREFIX",
            "DB_USERNAME",
            "DB_PASSWORD",
            "DB_HOST",
            "DB_PORT",
            "DB_DATABASE",
            "DB_DATABASE_SERVER",
        ]
    }


# %% ../notebooks/BatchJob.ipynb 9
def create_batch_job(
    command: str,
    task: str,
    cloud_provider: str,
    region: str,
    background_tasks: BackgroundTasks,
):
    """Create a new batch job

    Args:
        command: The CLI command as a string
        task: Task name as a string
        cloud_provider: Cloud provider in which to execute batch job
        region: Region to execute
        background_tasks: An instance of BackgroundTasks
    """
    logger.info(f"create_batch_job(): {command=}, {task=}")
    with BatchJobContext.create(
        task,
        cloud_provider=cloud_provider,
        region=region,
        background_tasks=background_tasks,
    ) as batch_ctx:
        logger.info(f"{batch_ctx=}")
        batch_ctx.create_job(
            command=command, environment_vars=get_environment_vars_for_batch_job()
        )


# %% ../notebooks/BatchJob.ipynb 13
def update_all():
    global __all__
    __all__ = [
        "BatchJobContext",
        "AwsBatchJobContext",
        "AzureBatchJobContext",
        "FastAPIBatchJobContext",
        "NoneBatchJobContext",
        "get_environment_vars_for_batch_job",
        "create_batch_job",
    ]


update_all()
