# AUTOGENERATED! DO NOT EDIT! File to edit: ../../notebooks/Azure_Batch_Job_Context.ipynb.

# %% auto 0
__all__ = ["AzureBatchJobContext"]

# %% ../../notebooks/Azure_Batch_Job_Context.ipynb 3
from typing import *
from os import environ

import azure.batch.models as batchmodels
from airt.logger import get_logger

import airt_service
from .base import BatchJobContext
from ..azure.utils import get_batch_account_pool_job_names
from ..azure.batch_utils import azure_batch_create_job

# %% ../../notebooks/Azure_Batch_Job_Context.ipynb 5
logger = get_logger(__name__)

# %% ../../notebooks/Azure_Batch_Job_Context.ipynb 7
class AzureBatchJobContext(BatchJobContext):
    """A class for creating AzureBatchJobContext"""

    def __init__(self, task: str, **kwargs):
        """Azure Batch Job Context

        Do not use __init__, please use factory method `create` to initiate object
        """
        BatchJobContext.__init__(self, task=task)
        self.region = kwargs["region"]

    def create_job(self, command: str, environment_vars: Dict[str, str]):
        """Create a new job

        Args:
            command: Command to execute in job
            environment_vars: Environment vars to set in the container
        """
        logger.info(
            f"{self.__class__.__name__}.create_job({self=}, {command=}, {environment_vars=})"
        )
        # ToDo: We have batch accounts available only in northeurope for now
        region = "northeurope"
        (
            batch_account_name,
            batch_pool_name,
            batch_job_name,
        ) = airt_service.azure.utils.get_batch_account_pool_job_names(self.task, region)

        tag = "dev"
        if environ["DOMAIN"] == "api.airt.ai":
            tag = "latest"

        container_settings = batchmodels.TaskContainerSettings(
            image_name=f"registry.gitlab.com/airt.ai/airt-service:{tag}"
        )

        airt_service.azure.batch_utils.azure_batch_create_job(
            command=command,
            batch_job_name=batch_job_name,
            batch_pool_name=batch_pool_name,
            batch_account_name=batch_account_name,
            region=region,
            container_settings=container_settings,
            environment_vars=environment_vars,
        )


AzureBatchJobContext.add_factory()
