# AUTOGENERATED! DO NOT EDIT! File to edit: ../../notebooks/BaseAirflowExecutor.ipynb.

# %% auto 0
__all__ = ["dag_template", "BaseAirflowExecutor"]

# %% ../../notebooks/BaseAirflowExecutor.ipynb 2
from datetime import datetime, timedelta
from pathlib import Path
from typing import *

from airt.executor.subcommand import (
    ModelExecutor,
    CLICommandBase,
)
from airt.helpers import slugify
from airt.logger import get_logger
from airt.patching import patch

from .utils import create_dag

# %% ../../notebooks/BaseAirflowExecutor.ipynb 4
logger = get_logger(__name__)

# %% ../../notebooks/BaseAirflowExecutor.ipynb 8
class BaseAirflowExecutor(ModelExecutor):
    def _create_step_template(self, step: CLICommandBase, **kwargs):
        """Create template for step

        Args:
            step: step to create template
            kwargs: keyword arguments for step
        Returns:
            Template for step
        """
        raise NotImplementedError("Need to implement")

    def _create_dag_template(
        self,
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
        raise NotImplementedError("Need to implement")

    def schedule(
        self,
        *,
        schedule_interval: Optional[Union[str, timedelta]] = None,
        description: str,
        tags: Union[str, List[str]],
        on_step_start: Optional[CLICommandBase] = None,
        on_step_end: Optional[CLICommandBase] = None,
        **kwargs,
    ) -> Path:
        """Create scheduled DAG in airflow

        Args:
            schedule_interval: schedule interval of DAG as string or timedelta object
            description: description of DAG
            tags: tags for DAG
            on_step_start: CLI to call before executing step/task in DAG
            on_step_end: CLI to call after executing step/task in DAG
            kwargs: keyword arguments needed for steps/tasks
        Returns:
            Path in which dag file is stored
        """
        raise NotImplementedError("Need to implement")

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


# %% ../../notebooks/BaseAirflowExecutor.ipynb 9
dag_template = """import datetime
from textwrap import dedent

# The DAG object; we'll need this to instantiate a DAG
from airflow import DAG

# Operators; we need this to operate!
from airflow.providers.amazon.aws.operators.batch import BatchOperator
import azure.batch.models as batchmodels
from airflow.providers.microsoft.azure.operators.batch import AzureBatchOperator
from airflow.operators.bash import BashOperator
from airflow.operators.trigger_dagrun import TriggerDagRunOperator
with DAG(
    '{dag_name}',
    # These args will get passed on to each operator
    # You can override them on a per-task basis during operator initialization
    default_args={{
        'schedule_interval': {schedule_interval},
        'depends_on_past': False,
        'email': ['info@airt.ai'],
        'email_on_failure': False,
        'email_on_retry': False,
        'retries': 1,
        'retry_delay': datetime.timedelta(minutes=5),
        # 'queue': 'queue',
        # 'pool': 'backfill',
        # 'priority_weight': 10,
        # 'end_date': datetime.datetime(2016, 1, 1),
        # 'wait_for_downstream': False,
        # 'sla': datetime.timedelta(hours=2),
        # 'execution_timeout': datetime.timedelta(seconds=300),
        # 'on_failure_callback': some_function,
        # 'on_success_callback': some_other_function,
        # 'on_retry_callback': another_function,
        # 'sla_miss_callback': yet_another_function,
        # 'trigger_rule': 'all_success'
    }},
    description='{description}',
    start_date={start_date},
    catchup=False,
    tags={tags},
    is_paused_upon_creation=False,
) as dag:

    # t1, t2 and t3 are examples of tasks created by instantiating operators
"""

# %% ../../notebooks/BaseAirflowExecutor.ipynb 11
@patch
def _create_dag_id(self: BaseAirflowExecutor, **kwargs) -> str:
    """
    Create dag id by combining steps CLIs and their arguments

    Args:
        kwargs: keyword arguments needed by steps
    Returns:
        Created dag id
    """
    return slugify("_".join([step.to_cli(**kwargs) for step in self.steps]))


# %% ../../notebooks/BaseAirflowExecutor.ipynb 14
@patch
def _create_jinja2_template_kwargs(
    self: BaseAirflowExecutor, **kwargs
) -> Dict[str, Any]:
    """
    Convert kwargs into jinja2 compatible template kwargs

    Args:
        kwargs: keyword arguments to convert
    Returns:
        A dict of jinja2 template formatted kwargs
    """
    formatted_kwargs = {}
    for key, value in kwargs.items():
        formatted_kwargs[key] = (
            "{{{{ dag_run.conf['"
            + key
            + "'] if '"
            + key
            + "' in dag_run.conf else "
            + value.__repr__()
            + " }}}}"
        )
    return formatted_kwargs


# %% ../../notebooks/BaseAirflowExecutor.ipynb 20
@patch
def _create_dag(
    self: BaseAirflowExecutor,
    *,
    schedule_interval: Optional[str] = None,
    description: str,
    tags: Union[str, List[str]],
    on_step_start: Optional[CLICommandBase] = None,
    on_step_end: Optional[CLICommandBase] = None,
    **kwargs,
) -> Tuple[str, Path]:
    """Create DAG in airflow

    Args:
        schedule_interval: schedule interval of DAG as string
        description: description of DAG
        tags: tags for DAG
        on_step_start: CLI to call before executing step/task in DAG
        on_step_end: CLI to call after executing step/task in DAG
        kwargs: keyword arguments needed for steps/tasks
    Returns:
        A tuple of dag id and dag file path
    """
    if isinstance(tags, str):
        tags = [tags]

    curr_dag_template = self._create_dag_template(
        on_step_start=on_step_start, on_step_end=on_step_end, **kwargs
    )
    dag_id = self._create_dag_id(**kwargs)
    dag_file_path = create_dag(
        dag_id=dag_id,
        dag_definition_template=curr_dag_template,
        schedule_interval=schedule_interval,
        start_date=datetime.utcnow().today().__repr__(),
        description=description,
        tags=tags.__repr__(),
    )

    return dag_id, dag_file_path


# %% ../../notebooks/BaseAirflowExecutor.ipynb 22
@patch
def schedule(
    self: BaseAirflowExecutor,
    *,
    schedule_interval: Optional[Union[str, timedelta]] = None,
    description: str,
    tags: Union[str, List[str]],
    on_step_start: Optional[CLICommandBase] = None,
    on_step_end: Optional[CLICommandBase] = None,
    **kwargs,
) -> Path:
    """Create scheduled DAG in airflow

    Args:
        schedule_interval: schedule interval of DAG as string or timedelta object
        description: description of DAG
        tags: tags for DAG
        on_step_start: CLI to call before executing step/task in DAG
        on_step_end: CLI to call after executing step/task in DAG
        kwargs: keyword arguments needed for steps/tasks
    Returns:
        Path in which dag file is stored
    """
    schedule_interval = (
        f"'{schedule_interval}'"
        if isinstance(schedule_interval, str)
        else schedule_interval.__repr__()
    )
    dag_id, dag_file_path = self._create_dag(
        schedule_interval=schedule_interval,
        description=description,
        tags=tags,
        on_step_start=on_step_start,
        on_step_end=on_step_end,
        **kwargs,
    )

    return dag_file_path
