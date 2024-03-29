# AUTOGENERATED! DO NOT EDIT! File to edit: ../../notebooks/AirflowBashExecutor.ipynb.

# %% auto 0
__all__ = ['AirflowBashExecutor']

# %% ../../notebooks/AirflowBashExecutor.ipynb 2
from pathlib import Path
from typing import *

from airt.executor.subcommand import CLICommandBase
from airt.helpers import slugify
from airt.logger import get_logger
from airt.patching import patch

from .base_executor import BaseAirflowExecutor, dag_template
from .utils import trigger_dag
from ..sanitizer import sanitized_print

# %% ../../notebooks/AirflowBashExecutor.ipynb 5
logger = get_logger(__name__)

# %% ../../notebooks/AirflowBashExecutor.ipynb 9
class AirflowBashExecutor(BaseAirflowExecutor):
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

# %% ../../notebooks/AirflowBashExecutor.ipynb 10
@patch  # type: ignore
def _create_step_template(
    self: AirflowBashExecutor, step: CLICommandBase, **kwargs: Any
) -> str:
    """
    Create template for step

    Args:
        step: step to create template
        kwargs: keyword arguments for step
    Returns:
        Template for step
    """
    triple_quote = "'''"
    formatted_kwargs = self._create_jinja2_template_kwargs(**kwargs)

    cli_command = step.to_cli(**formatted_kwargs)
    task_id = slugify(step.to_cli(**kwargs))

    task = f"""BashOperator(task_id="{task_id}", bash_command={triple_quote}{cli_command}{triple_quote})"""
    return task

# %% ../../notebooks/AirflowBashExecutor.ipynb 13
@patch  # type: ignore
def _create_dag_template(
    self: BaseAirflowExecutor,
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
            curr_dag_template += f"""{newline}{tab}t{existing_tasks+1} = {self._create_step_template(on_step_start, step_count=i+1, **kwargs)}"""
            existing_tasks += 1

        curr_dag_template += f"""{newline}{tab}t{existing_tasks+1} = {self._create_step_template(step, **kwargs)}"""
        existing_tasks += 1

        if on_step_end is not None:
            curr_dag_template += f"""{newline}{tab}t{existing_tasks+1} = {self._create_step_template(on_step_end, step_count=i+1, **kwargs)}"""
            existing_tasks += 1

    downstream_tasks = f"{newline}{tab}" + " >> ".join(
        [f"t{i}" for i in range(1, existing_tasks + 1)]
    )
    curr_dag_template += downstream_tasks

    return curr_dag_template

# %% ../../notebooks/AirflowBashExecutor.ipynb 17
@patch  # type: ignore
def execute(
    self: AirflowBashExecutor,
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

    conf = {key: value for key, value in kwargs.items()}
    run_id = trigger_dag(dag_id=dag_id, conf=conf)
    return dag_file_path, run_id
