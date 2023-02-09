# AUTOGENERATED! DO NOT EDIT! File to edit: ../notebooks/Background_Task.ipynb.

# %% auto 0
__all__ = ['execute_cli']

# %% ../notebooks/Background_Task.ipynb 3
import os
import yaml
from pathlib import Path
from time import sleep
from typing import *

import shlex
import subprocess  # nosec B404
from subprocess import Popen  # nosec B404

import asyncio


import airt_service
import airt_service.sanitizer
from airt.logger import get_logger

# %% ../notebooks/Background_Task.ipynb 5
logger = get_logger(__name__)

# %% ../notebooks/Background_Task.ipynb 7
async def execute_cli(
    command: str,
    timeout: int = 0,
    sleep_step: int = 1,
    on_timeout: Optional[Callable[[], None]] = None,
    on_success: Optional[Callable[[], None]] = None,
    on_error: Optional[Callable[[], None]] = None,
) -> None:
    """Execute CLI command

    Args:
        command: CLI command to be started in another process
        timeout: The maximum time allowed in seconds for the command to complete. If greater than 0,
                then the command will be killed after the timeout
        sleep_step: The time interval in seconds to check the completion status of the command
        on_timeout: Callback to be called in case the command gets killed due to a timeout
        on_success: Callback to be called if the command execution is successful, i.e., return code is 0
        on_error: Callback to be called if the command execution failed, i.e., return code is not 0

    Example:
        The following code executes a CLI command:
        ```python
        @app.post("/call_cli/{command}",  status_code=201)
        async def call_cli(command: str, background_tasks: BackgroundTasks, response: Response):
            background_tasks.add_task(
                execute_cli,
                command,
                timeout=3,
                on_timeout=lambda: logger.warning(f"Callback: background task timeouted for command: {command}")
            )
            response.code = 201
            return {"message": f"call_cli() returning after backgound task started for command: {command}"}
        ```
    """
    logger.info(f"Background task starting for command: '{command}'")
    cmd = shlex.split(command)
    logger.info(f"Background task command broken into: {cmd}")

    try:
        curr_env = os.environ.copy()
        if "HOME" in curr_env:
            curr_env["PATH"] = f"{curr_env['HOME']}/.local/bin:" + curr_env["PATH"]
        # start process
        # nosemgrep: python.lang.security.audit.dangerous-subprocess-use.dangerous-subprocess-use
        proc = Popen(  # nosec B603
            cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=curr_env
        )
    except Exception as e:
        logger.info(
            f"Background task thrown exception for command: '{command}' with exception {str(e)}"
        )
        raise e
    logger.info(f"Background task started for command: '{command}'")

    i = 0
    while proc.poll() is None:
        if 0 < timeout <= i:
            logger.info(
                f"Background task timeouted after {i:,d} seconds for command: '{command}'"
            )
            logger.info(f"Killing background task command: '{command}'")
            proc.kill()
            while proc.poll() is None:
                logger.info(
                    f"Waiting for the background task to be killed for command: '{command}'"
                )
                await asyncio.sleep(sleep_step)
            logger.info(f"Background task killed for command: '{command}'")
            if on_timeout is not None:
                on_timeout()
            break

        logger.debug(
            f"Background task running for {i:,d} seconds for command: '{command}'"
        )
        await asyncio.sleep(sleep_step)
        i = i + sleep_step

    logger.info(f"Command finished with return code {proc.returncode}")
    if proc.returncode == 0:
        if on_success is not None:
            on_success()
    else:
        if on_error is not None:
            on_error()

    if proc.stdout is not None:
        logger.info(
            f"Background task stdout for command: '{command}':\n{proc.stdout.read()}"
        )
    if proc.stderr is not None:
        logger.info(
            f"Background task stderr for command: '{command}':\n{proc.stderr.read()}"
        )

    logger.info(
        f"Background task finished for command: '{command}' with return code {proc.returncode}"
    )
