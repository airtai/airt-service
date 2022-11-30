# AUTOGENERATED! DO NOT EDIT! File to edit: ../../notebooks/AirflowExecutor.ipynb.

# %% auto 0
__all__ = ["AirflowExecutor"]

# %% ../../notebooks/AirflowExecutor.ipynb 2
from os import environ
from typing import *

import airt_service.sanitizer
from airt.executor.subcommand import CLICommandBase
from airt.logger import get_logger
from .base_executor import BaseAirflowExecutor
from .bash_executor import AirflowBashExecutor
from .aws_batch_executor import AirflowAWSBatchExecutor
from .azure_batch_executor import AirflowAzureBatchExecutor

# %% ../../notebooks/AirflowExecutor.ipynb 4
logger = get_logger(__name__)

# %% ../../notebooks/AirflowExecutor.ipynb 7
class AirflowExecutor:
    @classmethod
    def create_executor(
        cls, steps: List[CLICommandBase], cloud_provider: str, **kwargs
    ) -> BaseAirflowExecutor:
        """
        Initialize and return airflow bash or batch executor based on env variable

        Args:
            steps: list of instances of either ClassCLICommand or SimpleCLICommand
            cloud_provider: cloud provider to executor batch job
            kwargs: additional keyword arguments to pass to init
        Returns:
            An instance of AirflowBashExecutor or AirflowAWSBatchExecutor
        """

        job_executor = environ.get("JOB_EXECUTOR", None)

        if job_executor == "aws":
            if cloud_provider == "azure":
                executor = AirflowAzureBatchExecutor(steps=steps, **kwargs)
            else:
                executor = AirflowAWSBatchExecutor(steps=steps, **kwargs)
        else:
            executor = AirflowBashExecutor(steps=steps)

        return executor
