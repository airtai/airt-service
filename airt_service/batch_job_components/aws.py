# AUTOGENERATED! DO NOT EDIT! File to edit: ../../notebooks/AWS_Batch_Job_Context.ipynb.

# %% auto 0
__all__ = ["AwsBatchJobContext"]

# %% ../../notebooks/AWS_Batch_Job_Context.ipynb 3
from typing import *

from airt.logger import get_logger

import airt_service
import airt_service.sanitizer
from .base import BatchJobContext
from ..aws.utils import get_queue_definition_arns
from ..aws.batch_utils import aws_batch_create_job

# %% ../../notebooks/AWS_Batch_Job_Context.ipynb 5
logger = get_logger(__name__)

# %% ../../notebooks/AWS_Batch_Job_Context.ipynb 7
class AwsBatchJobContext(BatchJobContext):
    """A class for creating AwsBatchJobContext"""

    def __init__(self, task: str, **kwargs):
        """AWS Batch Job Context

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
        (
            job_queue_arn,
            job_definition_arn,
        ) = airt_service.aws.utils.get_queue_definition_arns(self.task, self.region)

        airt_service.aws.batch_utils.aws_batch_create_job(
            job_queue_arn=job_queue_arn,
            job_definition_arn=job_definition_arn,
            region=self.region,
            command=command,
            environment_vars=environment_vars,
        )


AwsBatchJobContext.add_factory()
