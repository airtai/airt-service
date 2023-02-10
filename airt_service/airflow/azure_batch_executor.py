# AUTOGENERATED! DO NOT EDIT! File to edit: ../../notebooks/AirflowAzureBatchExecutor.ipynb.

# %% auto 0
__all__ = ['DEFAULT_EXEC_ENVIRONMENT', 'AirflowAzureBatchExecutor', 'test_azure_batch_executor']

# %% ../../notebooks/AirflowAzureBatchExecutor.ipynb 2
import os
import shlex
import tempfile
from pathlib import Path
from typing import *

import yaml
from airt.executor.subcommand import ClassCLICommand, CLICommandBase
from airt.helpers import slugify
from airt.logger import get_logger
from airt.patching import patch
from azure.batch.batch_auth import SharedKeyCredentials
from fastcore.script import Param, call_parse

from .base_executor import BaseAirflowExecutor, dag_template
from .utils import trigger_dag, wait_for_run_to_complete
from airt_service.azure.batch_utils import (
    AUTO_SCALE_FORMULA,
    BatchJob,
    BatchPool,
    get_random_string,
)
from airt_service.azure.utils import (
    get_azure_batch_environment_component_names,
    get_batch_account_pool_job_names,
)
from ..batch_job import get_environment_vars_for_batch_job
from ..helpers import generate_random_string
from ..sanitizer import sanitized_print

# %% ../../notebooks/AirflowAzureBatchExecutor.ipynb 5
logger = get_logger(__name__)

# %% ../../notebooks/AirflowAzureBatchExecutor.ipynb 8
def setup_test_paths(td: str) -> Tuple[str, str]:
    d = Path(td)
    paths = [d / sd for sd in ["data", "model"]]
    sanitized_print(f"{paths=}")

    # create tmp dirs for data and model
    for p in paths:
        p.mkdir(parents=True, exist_ok=True)

    # RemotePaths: data_path is "read-only", while model_path can be used for both reading and writing between calls
    return tuple(f"local:{p}" for p in paths)  # type: ignore

# %% ../../notebooks/AirflowAzureBatchExecutor.ipynb 10
DEFAULT_EXEC_ENVIRONMENT = "preprocessing"

# %% ../../notebooks/AirflowAzureBatchExecutor.ipynb 11
class AirflowAzureBatchExecutor(BaseAirflowExecutor):
    def __init__(
        self,
        steps: List[CLICommandBase],
        region: str,
        exec_environments: Optional[List[Optional[str]]] = None,
        batch_environment_path: Optional[Union[str, Path]] = None,
    ):
        """Constructs a new AirflowAzureBatchExecutor instance

        Args:
            steps: List of instances of either ClassCLICommand or SimpleCLICommand
            region: Region to execute
            exec_environments: List of execution environments to execute steps
            batch_environment_path: Path for yaml file in which azure batch environment names are stored
        """
        self.region = region
        self.batch_environment_path = batch_environment_path

        if exec_environments is None:
            exec_environments = [DEFAULT_EXEC_ENVIRONMENT] * len(steps)

        if len(exec_environments) != len(steps):
            raise ValueError(
                f"len(exec_environments)={len(exec_environments)} != len(steps){len(steps)}"
            )

        existing_exec_environments = list(
            get_azure_batch_environment_component_names(
                self.region, self.batch_environment_path
            ).keys()
        )

        self.exec_environments = []
        for exec_env in exec_environments:
            if exec_env is None:
                self.exec_environments.append(DEFAULT_EXEC_ENVIRONMENT)
                continue
            if exec_env not in existing_exec_environments:
                raise ValueError(
                    f"Invalid value {exec_env} given for exec environment; Allowed values are {existing_exec_environments}"
                )
            self.exec_environments.append(exec_env)

        self.exec_environments = [
            exec_env if exec_env is not None else DEFAULT_EXEC_ENVIRONMENT
            for exec_env in exec_environments
        ]

        super(AirflowAzureBatchExecutor, self).__init__(steps)

    def execute(
        self,
        *,
        description: str,
        tags: Union[str, List[str]],
        on_step_start: Optional[CLICommandBase] = None,
        on_step_end: Optional[CLICommandBase] = None,
        **kwargs: Any,
    ) -> Tuple[Path, str]:
        """Create DAG and execute steps in airflow

        Args:
            description: description of DAG
            tags: tags for DAG
            on_step_start: CLI to call before executing step/task in DAG
            on_step_end: CLI to call after executing step/task in DAG
            kwargs: keyword arguments needed for steps/tasks
        Returns:
            A tuple which contains dag file path and run id
        """
        raise NotImplementedError("Need to implement")

# %% ../../notebooks/AirflowAzureBatchExecutor.ipynb 15
@patch
def _create_step_template(
    self: AirflowAzureBatchExecutor,
    step: CLICommandBase,
    exec_environment: str,
    **kwargs: Any,
) -> str:
    """
    Create template for step

    Args:
        step: step to create template
        kwargs: keyword arguments for step
    Returns:
        Template for step
    """
    cli_command = step.to_cli(**kwargs)
    task_id = slugify(cli_command)

    azure_batch_environment_vars = ""
    for name, value in get_environment_vars_for_batch_job().items():
        azure_batch_environment_vars = (
            azure_batch_environment_vars + f" --env {name}='{value}'"
        )

    (
        batch_account_name,
        batch_pool_name,
        batch_job_name,
    ) = get_batch_account_pool_job_names(
        task=exec_environment,
        region=self.region,
        batch_environment_path=self.batch_environment_path,
    )

    if exec_environment in ["training", "predictions"]:
        batch_pool_vm_size = "standard_nc6s_v3"
    elif exec_environment in ["csv_processing", "preprocessing"]:
        batch_pool_vm_size = "standard_d2s_v3"

    batch_task_id = f"batch-task-{get_random_string()}"
    azure_batch_conn_id = f'azure_batch_conn_id="custom_azure_batch_default"'
    task_params = f"""task_id="{task_id}", batch_pool_id="{batch_pool_name}", batch_pool_vm_size="{batch_pool_vm_size}", batch_job_id="{batch_job_name}", batch_task_command_line="{cli_command}", batch_task_id="{batch_task_id}", {azure_batch_conn_id}"""

    vm_details = f"""vm_publisher="microsoft-azure-batch", vm_offer="ubuntu-server-container", vm_sku="20-04-lts", vm_version="latest", vm_node_agent_sku_id="batch.node.ubuntu 20.04" """

    auto_scale_params = (
        f'enable_auto_scale=True, auto_scale_formula="""{AUTO_SCALE_FORMULA}"""'
    )

    tag = "dev"
    if os.environ["DOMAIN"] == "api.airt.ai":
        tag = "latest"
    batch_task_container_settings = f"""batch_task_container_settings=batchmodels.TaskContainerSettings(image_name="ghcr.io/airtai/airt-service:{tag}", container_run_options="{azure_batch_environment_vars}")"""

    task = f"""AzureBatchOperator({task_params}, {vm_details}, {auto_scale_params}, {batch_task_container_settings})"""
    return task

# %% ../../notebooks/AirflowAzureBatchExecutor.ipynb 17
@patch
def _create_dag_template(
    self: AirflowAzureBatchExecutor,
    on_step_start: Optional[CLICommandBase] = None,
    on_step_end: Optional[CLICommandBase] = None,
    **kwargs: Any,
) -> str:
    """
    Create DAG template with steps as tasks

    Args:
        on_step_start: CLI to call before executing step/task in DAG
        on_step_end: CLI to call after executing step/task in DAG
        kwargs: keyword arguments to pass to steps' CLI
    Returns:
        Generated DAG with steps as tasks
    """
    curr_dag_template = dag_template

    downstream_tasks = ""
    newline = "\n"
    tab = " " * 4

    existing_tasks = 0
    for i, step in enumerate(self.steps):
        if on_step_start is not None:
            curr_dag_template += f"""{newline}{tab}t{existing_tasks+1} = {self._create_step_template(on_step_start, self.exec_environments[i], step_count=i+1, **kwargs)}"""  # type: ignore
            existing_tasks += 1

        curr_dag_template += f"""{newline}{tab}t{existing_tasks+1} = {self._create_step_template(step, self.exec_environments[i], **kwargs)}"""  # type: ignore
        existing_tasks += 1

        if on_step_end is not None:
            curr_dag_template += f"""{newline}{tab}t{existing_tasks+1} = {self._create_step_template(on_step_end, self.exec_environments[i], step_count=i+1, **kwargs)}"""  # type: ignore
            existing_tasks += 1

    downstream_tasks = f"{newline}{tab}" + " >> ".join(
        [f"t{i}" for i in range(1, existing_tasks + 1)]
    )
    curr_dag_template += downstream_tasks

    return curr_dag_template

# %% ../../notebooks/AirflowAzureBatchExecutor.ipynb 21
@patch
def execute(
    self: AirflowAzureBatchExecutor,
    *,
    description: str,
    tags: Union[str, List[str]],
    on_step_start: Optional[CLICommandBase] = None,
    on_step_end: Optional[CLICommandBase] = None,
    **kwargs: Any,
) -> Tuple[Path, str]:
    """Create DAG and execute steps in airflow

    Args:
        description: description of DAG
        tags: tags for DAG
        on_step_start: CLI to call before executing step/task in DAG
        on_step_end: CLI to call after executing step/task in DAG
        kwargs: keyword arguments needed for steps/tasks
    Returns:
        A tuple which contains dag file path and run id
    """
    schedule_interval = None
    dag_id, dag_file_path = self._create_dag(
        schedule_interval=schedule_interval,
        description=description,
        tags=tags,
        on_step_start=on_step_start,
        on_step_end=on_step_end,
        **kwargs,
    )

    run_id = trigger_dag(dag_id=dag_id, conf={})
    return dag_file_path, run_id

# %% ../../notebooks/AirflowAzureBatchExecutor.ipynb 23
def _test_azure_batch_executor(region: str = "northeurope") -> None:
    with tempfile.TemporaryDirectory() as d:
        data_path_url, model_path_url = setup_test_paths(d)

        steps = [
            ClassCLICommand(
                executor_name="test-executor", class_name="MyTestExecutor", f_name="f"
            )
        ]
        exec_environments = ["training"]

        td = Path(d)
        created_azure_env_path = td / "azure_batch_environment.yml"

        shared_key_credentials = SharedKeyCredentials(
            "testbatchnortheurope", os.environ["SHARED_KEY_CREDENTIALS"]
        )

        batch_account_name = "testbatchnortheurope"
        region = "northeurope"

        batch_pool = BatchPool.from_name(
            name="test-cpu-pool",
            batch_account_name=batch_account_name,
            region=region,
            shared_key_credentials=shared_key_credentials,
        )
        batch_job = BatchJob.from_name(name="test-cpu-job", batch_pool=batch_pool)

        sanitized_print(f"{batch_pool.name=}")
        sanitized_print(f"{batch_job.name=}")
        region = "northeurope"
        test_batch_environment_names = {
            region: {
                task: {
                    "batch_job_name": batch_job.name,
                    "batch_pool_name": batch_pool.name,
                    "batch_account_name": batch_account_name,
                }
                for task in [
                    "csv_processing",
                    "predictions",
                    "preprocessing",
                    "training",
                ]
            }
        }
        sanitized_print(f"{test_batch_environment_names=}")
        with open(created_azure_env_path, "w") as f:
            yaml.dump(test_batch_environment_names, f, default_flow_style=False)

        abe = AirflowAzureBatchExecutor(
            steps=steps,
            region=region,
            exec_environments=exec_environments,  # type: ignore
            batch_environment_path=created_azure_env_path,
        )
        dag_file_path, run_id = abe.execute(
            data_path_url=data_path_url,
            model_path_url=model_path_url,
            description="test description",
            tags="test_tag",
        )

        sanitized_print(f"{dag_file_path=}")
        sanitized_print(f"{run_id=}")

        dag_id = str(dag_file_path).split("/")[-1].split(".py")[0]
        state = wait_for_run_to_complete(dag_id=dag_id, run_id=run_id, timeout=3600)
        sanitized_print(f"{state=}")
        dag_file_path.unlink()

# %% ../../notebooks/AirflowAzureBatchExecutor.ipynb 24
@call_parse
def test_azure_batch_executor(region: Param("region", str) = "northeurope"):  # type: ignore
    """
    Create throw away environment for azure batch and execute airflow batch executor
    """
    _test_azure_batch_executor(region=region)
