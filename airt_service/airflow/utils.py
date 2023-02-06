# AUTOGENERATED! DO NOT EDIT! File to edit: ../../notebooks/Airflow_Utils.ipynb.

# %% auto 0
__all__ = ['list_dags', 'list_dag_runs', 'create_dag', 'create_testing_dag_ctx', 'run_subprocess_with_retry', 'unpause_dag',
           'trigger_dag', 'wait_for_run_to_complete']

# %% ../../notebooks/Airflow_Utils.ipynb 2
import json
import os
import shlex
import subprocess  # nosec B404
import tempfile
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from time import sleep
from typing import *

import pandas as pd
from ..sanitizer import sanitized_print

# %% ../../notebooks/Airflow_Utils.ipynb 11
def list_dags(
    *,
    airflow_command: str = f"{os.environ['HOME']}/airflow_venv/bin/airflow",
):
    command = f"{airflow_command} dags list -o json"
    # nosemgrep: python.lang.security.audit.dangerous-subprocess-use.dangerous-subprocess-use
    p = subprocess.run(  # nosec B603
        shlex.split(command), shell=False, capture_output=True, text=True, check=True
    )
    try:
        return json.loads(p.stdout)
    except Exception as e:
        sanitized_print(f"{p.stdout=}")
        raise e

# %% ../../notebooks/Airflow_Utils.ipynb 15
def list_dag_runs(
    dag_id: str,
    *,
    airflow_command: str = f"{os.environ['HOME']}/airflow_venv/bin/airflow",
):
    command = f"{airflow_command} dags list-runs -d {dag_id} -o json"

    # nosemgrep: python.lang.security.audit.dangerous-subprocess-use.dangerous-subprocess-use
    p = subprocess.run(  # nosec B603
        shlex.split(command),
        shell=False,
        capture_output=True,
        text=True,
        check=True,
    )

    return json.loads(p.stdout)

# %% ../../notebooks/Airflow_Utils.ipynb 17
def create_dag(
    dag_id: str,
    dag_definition_template: str,
    *,
    root_path: Path = Path(f"{os.environ['HOME']}/airflow/dags"),
    **kwargs,
):
    root_path.mkdir(exist_ok=True, parents=True)
    tmp_file_path = root_path / f'{dag_id.replace(":", "_")}.py'
    with open(tmp_file_path, "w") as temp_file:
        temp_file.write(dag_definition_template.format(dag_name=dag_id, **kwargs))

    while True:
        df: pd.DataFrame = pd.DataFrame.from_dict(list_dags())
        if (dag_id == df["dag_id"]).sum():  # type: ignore
            break
        sanitized_print(".", end="")
        sleep(1)
    return tmp_file_path


@contextmanager
def create_testing_dag_ctx(
    dag_definition_template: str,
    *,
    root_path: Path = Path(f"{os.environ['HOME']}/airflow/dags"),
    **kwargs,
):
    tmp_file_path = None
    try:
        dag_id = f"test-{datetime.now().isoformat()}".replace(":", "_")

        tmp_file_path = create_dag(
            dag_id=dag_id,
            dag_definition_template=dag_definition_template,
            root_path=root_path,
            **kwargs,
        )
        yield dag_id
    finally:
        if tmp_file_path and tmp_file_path.exists():
            tmp_file_path.unlink()

# %% ../../notebooks/Airflow_Utils.ipynb 20
def run_subprocess_with_retry(
    command: str, *, no_retries: int = 12, sleep_for: int = 5
):
    for i in range(no_retries):
        # nosemgrep: python.lang.security.audit.dangerous-subprocess-use.dangerous-subprocess-use
        p = subprocess.run(  # nosec B603
            shlex.split(command),
            shell=False,
            capture_output=True,
            text=True,
            check=False,
        )
        if p.returncode == 0:
            return p
        sleep(sleep_for)
    raise TimeoutError(p)

# %% ../../notebooks/Airflow_Utils.ipynb 21
def unpause_dag(
    dag_id: str,
    *,
    airflow_command: str = f"{os.environ['HOME']}/airflow_venv/bin/airflow",
    no_retries: int = 12,
):
    unpause_command = f"{airflow_command} dags unpause {dag_id}"
    p = run_subprocess_with_retry(unpause_command, no_retries=no_retries)

# %% ../../notebooks/Airflow_Utils.ipynb 23
def trigger_dag(
    dag_id: str,
    conf: Dict[str, Any],
    *,
    airflow_command: str = f"{os.environ['HOME']}/airflow_venv/bin/airflow",
    no_retries: int = 12,
    unpause_if_needed: bool = True,
):
    if unpause_if_needed:
        unpause_dag(
            dag_id=dag_id, airflow_command=airflow_command, no_retries=no_retries
        )

    run_id = f"airt-service__{datetime.now().isoformat()}"
    command = f"{airflow_command} dags trigger {dag_id} --conf {shlex.quote(json.dumps(conf))} --run-id {run_id}"
    p = run_subprocess_with_retry(command, no_retries=no_retries)
    sanitized_print(p)

    runs = list_dag_runs(dag_id=dag_id)
    sanitized_print(runs)

    return run_id

# %% ../../notebooks/Airflow_Utils.ipynb 25
def wait_for_run_to_complete(dag_id: str, run_id: str, timeout: int = 60) -> str:
    t0 = datetime.now()
    while (datetime.now() - t0) < timedelta(seconds=timeout):
        runs = pd.DataFrame(list_dag_runs(dag_id=dag_id))
        state = runs.loc[runs["run_id"] == run_id, "state"].iloc[0]
        if state in ["success", "failed"]:
            return state
        sleep(5)
    raise TimeoutError()
