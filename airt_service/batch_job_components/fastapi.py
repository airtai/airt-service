# AUTOGENERATED! DO NOT EDIT! File to edit: ../../notebooks/FastAPI_Batch_Job_Context.ipynb.

# %% auto 0
__all__ = ['FastAPIBatchJobContext']

# %% ../../notebooks/FastAPI_Batch_Job_Context.ipynb 3
from typing import *

import airt_service.sanitizer
from airt.logger import get_logger
from ..background_task import execute_cli
from .base import BatchJobContext

# %% ../../notebooks/FastAPI_Batch_Job_Context.ipynb 5
logger = get_logger(__name__)

# %% ../../notebooks/FastAPI_Batch_Job_Context.ipynb 6
class FastAPIBatchJobContext(BatchJobContext):
    def __init__(self, task: str, **kwargs):
        """FastAPI Batch Job Context

        Do not use __init__, please use factory method `create` to initiate object
        """
        BatchJobContext.__init__(self, task=task)
        self.background_tasks = kwargs["background_tasks"]

    def create_job(self, command: str, environment_vars: Dict[str, str]):
        """Create a new job

        Args:
            command: Command to execute in job
            environment_vars: Environment vars to set in the container
        """
        logger.info(
            f"{self.__class__.__name__}.create_job({self=}, {command=}, {environment_vars=})"
        )
        self.background_tasks.add_task(execute_cli, command=command)


FastAPIBatchJobContext.add_factory()
