# AUTOGENERATED! DO NOT EDIT! File to edit: ../../notebooks/AirflowAWSBatchExecutor.ipynb.

# %% auto 0
__all__ = [
    "DEFAULT_EXEC_ENVIRONMENT",
    "AirflowAWSBatchExecutor",
    "test_aws_batch_executor",
]

# %% ../../notebooks/AirflowAWSBatchExecutor.ipynb 2
import tempfile
import shlex
import yaml
from pathlib import Path
from typing import *

from fastcore.script import call_parse, Param

from ..sanitizer import sanitized_print
from airt.executor.subcommand import CLICommandBase, ClassCLICommand
from airt.helpers import slugify
from airt.logger import get_logger
from airt.patching import patch
from .base_executor import BaseAirflowExecutor, dag_template
from .utils import trigger_dag, wait_for_run_to_complete
from airt_service.aws.batch_utils import (
    _create_default_batch_environment_config,
    create_testing_batch_environment_ctx,
)
from ..aws.utils import get_batch_environment_arns, get_queue_definition_arns
from ..batch_job import get_environment_vars_for_batch_job
from ..helpers import generate_random_string

# %% ../../notebooks/AirflowAWSBatchExecutor.ipynb 5
logger = get_logger(__name__)

# %% ../../notebooks/AirflowAWSBatchExecutor.ipynb 8
def setup_test_paths(td: str) -> Tuple[str, str]:
    d = Path(td)
    paths = [d / sd for sd in ["data", "model"]]
    sanitized_print(f"{paths=}")

    # create tmp dirs for data and model
    for p in paths:
        p.mkdir(parents=True, exist_ok=True)

    # RemotePaths: data_path is "read-only", while model_path can be used for both reading and writing between calls
    return tuple(f"local:{p}" for p in paths)  # type: ignore


# %% ../../notebooks/AirflowAWSBatchExecutor.ipynb 10
DEFAULT_EXEC_ENVIRONMENT = "preprocessing"

# %% ../../notebooks/AirflowAWSBatchExecutor.ipynb 11
class AirflowAWSBatchExecutor(BaseAirflowExecutor):
    def __init__(
        self,
        steps: List[CLICommandBase],
        region: str,
        exec_environments: Optional[List[Optional[str]]] = None,
        batch_environment_arn_path: Optional[Union[str, Path]] = None,
    ):
        """Constructs a new AirflowAWSBatchExecutor instance

        Args:
            steps: List of instances of either ClassCLICommand or SimpleCLICommand
            region: Region to execute
            exec_environments: List of execution environments to execute steps
        """
        self.region = region
        self.batch_environment_arn_path = batch_environment_arn_path

        if exec_environments is None:
            exec_environments = [DEFAULT_EXEC_ENVIRONMENT] * len(steps)

        if len(exec_environments) != len(steps):
            raise ValueError(
                f"len(exec_environments)={len(exec_environments)} != len(steps){len(steps)}"
            )

        existing_exec_environments = list(
            get_batch_environment_arns(
                self.region, self.batch_environment_arn_path
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

        super(AirflowAWSBatchExecutor, self).__init__(steps)

    def execute(
        self,
        *,
        description: str,
        tags: Union[str, List[str]],
        on_step_start: Optional[CLICommandBase] = None,
        on_step_end: Optional[CLICommandBase] = None,
        **kwargs,
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


# %% ../../notebooks/AirflowAWSBatchExecutor.ipynb 15
@patch
def _create_step_template(
    self: AirflowAWSBatchExecutor, step: CLICommandBase, exec_environment: str, **kwargs
):
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

    batch_environment_vars = [
        dict(name=name, value=value)
        for name, value in get_environment_vars_for_batch_job().items()
    ]
    overrides = (
        dict(
            command=shlex.split(cli_command),
            environment=batch_environment_vars,
        )
        .__repr__()
        .replace("{", "{{")
        .replace("}", "}}")
    )

    job_queue_arn, job_definition_arn = get_queue_definition_arns(
        task=exec_environment,
        region=self.region,
        batch_environment_arn_path=self.batch_environment_arn_path,
    )

    task = f"""BatchOperator(task_id='{task_id}', job_definition="{job_definition_arn}", job_queue="{job_queue_arn}", job_name="{task_id}", overrides={overrides})"""

    return task


# %% ../../notebooks/AirflowAWSBatchExecutor.ipynb 17
@patch
def _create_dag_template(
    self: AirflowAWSBatchExecutor,
    on_step_start: Optional[CLICommandBase] = None,
    on_step_end: Optional[CLICommandBase] = None,
    **kwargs,
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


# %% ../../notebooks/AirflowAWSBatchExecutor.ipynb 21
@patch
def execute(
    self: AirflowAWSBatchExecutor,
    *,
    description: str,
    tags: Union[str, List[str]],
    on_step_start: Optional[CLICommandBase] = None,
    on_step_end: Optional[CLICommandBase] = None,
    **kwargs,
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


# %% ../../notebooks/AirflowAWSBatchExecutor.ipynb 23
def _test_aws_batch_executor(region: str = "eu-west-1"):  # type: ignore
    with tempfile.TemporaryDirectory() as d:
        data_path_url, model_path_url = setup_test_paths(d)

        steps = [
            ClassCLICommand(
                executor_name="test-executor", class_name="MyTestExecutor", f_name="f"
            )
        ]
        exec_environments = ["training"]

        td = Path(d)
        env_config_path = td / "env_config.yaml"
        created_env_info_path = td / "output_file.yaml"

        prefix = f"airflow_batch_execute_testing_{generate_random_string()}"
        regions = [region]
        _create_default_batch_environment_config(
            prefix=prefix,
            output_path=env_config_path,
            regions=regions,
        )

        with open(env_config_path) as f:
            env_config = yaml.safe_load(f)
        logger.info(f"{env_config=}")
        with create_testing_batch_environment_ctx(
            input_yaml_path=env_config_path, output_yaml_path=created_env_info_path  # type: ignore
        ):
            abe = AirflowAWSBatchExecutor(
                steps=steps,
                region=region,
                exec_environments=exec_environments,  # type: ignore
                batch_environment_arn_path=created_env_info_path,
            )

            dag_file_path, run_id = abe.execute(
                description="test description",
                tags="test_tag",
                data_path_url=data_path_url,
                model_path_url=model_path_url,
            )
            logger.info(f"{dag_file_path=}")
            logger.info(f"{run_id=}")

            dag_id = str(dag_file_path).split("/")[-1].split(".py")[0]
            state = wait_for_run_to_complete(dag_id=dag_id, run_id=run_id, timeout=1200)
            logger.info(f"{state=}")
            dag_file_path.unlink()


# %% ../../notebooks/AirflowAWSBatchExecutor.ipynb 24
@call_parse
def test_aws_batch_executor(region: Param("region", str) = "eu-west-1"):  # type: ignore
    """
    Create throw away environment for aws batch and execute airflow batch executor
    """
    _test_aws_batch_executor(region=region)
