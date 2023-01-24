# AUTOGENERATED! DO NOT EDIT! File to edit: ../notebooks/Training_Status_Process.ipynb.

# %% auto 0
__all__ = ['get_recent_event_for_user', 'get_count_from_training_data_ch_table', 'get_user', 'process_row', 'process_dataframes',
           'process_training_status']

# %% ../notebooks/Training_Status_Process.ipynb 2
import random
from datetime import datetime, timedelta
from os import environ
from time import sleep
from typing import *

import asyncio
import numpy as np
import pandas as pd
from asyncer import asyncify
from fastapi import FastAPI
from fast_kafka_api.application import FastKafkaAPI
from sqlalchemy.exc import NoResultFound
from sqlalchemy import create_engine as sqlalchemy_create_engine
from sqlmodel import Session, select, func

import airt_service
from .users import User
from .data.clickhouse import get_count_for_account_ids
from airt_service.db.models import (
    create_connection_string,
    get_db_params_from_env_vars,
    get_engine,
    get_session_with_context,
    User,
    TrainingStreamStatus,
)
from airt.logger import get_logger
from airt.patching import patch

# %% ../notebooks/Training_Status_Process.ipynb 5
logger = get_logger(__name__)

# %% ../notebooks/Training_Status_Process.ipynb 6
@patch(cls_method=True)
def _create(
    cls: TrainingStreamStatus,
    *,
    account_id: int,
    event: str,
    count: int,
    total: int,
    user: User,
    session: Session
) -> TrainingStreamStatus:
    """
    Method to create event

    Args:
        account_id: account id
        event: one of start, upload, end
        count: current count of rows in clickhouse db
        total: total no. of rows sent by user
        user: user object
        session: session object

    Returns:
        created object of type TrainingStreamStatus
    """
    training_event = TrainingStreamStatus(
        account_id=account_id, event=event, count=count, total=total, user=user
    )
    session.add(training_event)
    session.commit()
    return training_event

# %% ../notebooks/Training_Status_Process.ipynb 9
def get_recent_event_for_user(username: str, session: Session) -> pd.DataFrame:
    """
    Get recent event for user

    Args:
        username: username of user to get recent events
        session: session object

    Returns:
        A list of recent events for given user
    """
    user = session.exec(select(User).where(User.username == username)).one()

    conn_str = create_connection_string(**get_db_params_from_env_vars())  # type: ignore
    sqlalchemy_engine = sqlalchemy_create_engine(conn_str)

    # Get all rows from table
    df = pd.read_sql_table(table_name="trainingstreamstatus", con=sqlalchemy_engine)

    sqlalchemy_engine.dispose()

    # Filter events for given user and group by account_id
    events_for_user = (
        df.loc[df["user_id"] == user.id]
        .sort_values(["created", "id"], ascending=[False, False])
        .groupby("account_id")
        .first()
    )
    events_for_user.index.names = ["AccountId"]
    events_for_user.rename(columns={"count": "prev_count"}, inplace=True)

    # Leave 'end' events
    return events_for_user.loc[events_for_user["event"] != "end"].sort_values(
        ["AccountId"], ascending=[True]
    )

# %% ../notebooks/Training_Status_Process.ipynb 11
def get_count_from_training_data_ch_table(
    account_ids: List[Union[int, str]]
) -> pd.DataFrame:
    """
    Get count of all rows for given account ids from clickhouse table

    Args:
        account_ids: List of account_ids to get count

    Returns:
        Count for the given account id
    """
    return airt_service.data.clickhouse.get_count_for_account_ids(
        account_ids=account_ids,
        username=environ["KAFKA_CH_USERNAME"],
        password=environ["KAFKA_CH_PASSWORD"],
        host=environ["KAFKA_CH_HOST"],
        port=int(environ["KAFKA_CH_PORT"]),
        database=environ["KAFKA_CH_DATABASE"],
        table=environ["KAFKA_CH_TABLE"],
        protocol=environ["KAFKA_CH_PROTOCOL"],
    )

# %% ../notebooks/Training_Status_Process.ipynb 13
def get_user(username: str, session: Session) -> Optional[User]:
    """Get the user object for the given username

    Args:
        username: Username as a string

    Returns:
        The user object if username is valid else None
    """

    return session.exec(select(User).where(User.username == username)).one()

# %% ../notebooks/Training_Status_Process.ipynb 15
async def process_row(
    row: pd.Series,
    user: User,
    session: Session,
    fast_kafka_api_app: FastKafkaAPI,
):
    """
    Process a single row, update mysql db and send status message to kafka

    Args:
        row: pandas row
        user: user object
        session: session object
    """
    if not row["action"]:
        return

    async_training_stream_status_create = asyncify(TrainingStreamStatus._create)

    account_id = row.name

    upload_event = await async_training_stream_status_create(  # type: ignore
        account_id=account_id,
        event=row["action"],
        count=row["curr_count"],
        total=row["total"],
        user=user,
        session=session,
    )
    await fast_kafka_api_app.to_infobip_training_data_status(
        account_id=account_id,
        no_of_records=row["curr_count"],
        total_no_of_records=row["total"],
    )

# %% ../notebooks/Training_Status_Process.ipynb 17
async def process_dataframes(
    recent_events_df: pd.DataFrame,
    ch_df: pd.DataFrame,
    *,
    user: User,
    session: Session,
    end_timedelta: int = 30,
    fast_kafka_api_app: FastKafkaAPI,
):
    """
    Process mysql, clickhouse dataframes and take action if needed

    Args:
        recent_events_df: recent events as pandas dataframe from mysql db
        ch_df: count from clickhouse table as dataframe
        user: user object
        session: session object
        end_timedelta: timedelta in seconds to use to determine whether upload is over or not
    """
    df = pd.merge(recent_events_df, ch_df, on="AccountId")
    xs = np.where(  # type: ignore
        df["curr_check_on"] - df["created"] > pd.Timedelta(seconds=end_timedelta),
        "end",
        None,
    )
    df["action"] = np.where(
        df["curr_count"] != df["prev_count"],
        "upload",
        xs,
    )

    for account_id, row in df.iterrows():

        await process_row(
            row, user=user, session=session, fast_kafka_api_app=fast_kafka_api_app
        )

# %% ../notebooks/Training_Status_Process.ipynb 20
async def process_training_status(username: str, fast_kafka_api_app: FastKafkaAPI):
    """
    An infinite loop to keep track of training_data uploads from user

    Args:
        username: username of user to track training data uploads
    """
    async_get_user = asyncify(get_user)
    async_get_recent_event_for_user = asyncify(get_recent_event_for_user)
    async_get_count_from_training_data_ch_table = asyncify(
        get_count_from_training_data_ch_table
    )

    while True:
        #         logger.info(f"Starting the process loop")
        try:
            engine = get_engine(**get_db_params_from_env_vars())  # type: ignore
            session = Session(engine)

            user = await async_get_user(username, session)
            recent_events_df = await async_get_recent_event_for_user(username, session)
            if not recent_events_df.empty:
                ch_df = await async_get_count_from_training_data_ch_table(
                    account_ids=recent_events_df.index.tolist()
                )
                await process_dataframes(
                    recent_events_df=recent_events_df,
                    ch_df=ch_df,
                    user=user,  # type: ignore
                    session=session,
                    fast_kafka_api_app=fast_kafka_api_app,
                )

            session.close()
            engine.dispose()
        except Exception as e:
            logger.info(f"Error in process_training_status - {e}")

        await asyncio.sleep(random.randint(5, 20))  # nosec B311
