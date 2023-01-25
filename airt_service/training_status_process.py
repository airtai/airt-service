# AUTOGENERATED! DO NOT EDIT! File to edit: ../notebooks/Training_Status_Process.ipynb.

# %% auto 0
__all__ = ['get_recent_event_for_user', 'get_count_from_training_data_ch_table', 'process_recent_event',
           'process_training_status']

# %% ../notebooks/Training_Status_Process.ipynb 2
import random
from datetime import datetime, timedelta
from os import environ
from time import sleep
from typing import *

import asyncio
from asyncer import asyncify
from fastapi import FastAPI
from fast_kafka_api.application import FastKafkaAPI
from sqlalchemy.exc import NoResultFound
from sqlmodel import Session, select, func

import airt_service
from .data.clickhouse import get_count
from .db.models import get_session_with_context, User, TrainingStreamStatus
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

# %% ../notebooks/Training_Status_Process.ipynb 8
def get_recent_event_for_user(
    username: str, session: Session
) -> List[TrainingStreamStatus]:
    """
    Get recent event for user

    Args:
        username: username of user to get recent events
        session: session object

    Returns:
        A list of recent events for given user
    """
    user = session.exec(select(User).where(User.username == username)).one()
    try:
        unique_account_ids = session.exec(
            select(TrainingStreamStatus.account_id)
            .where(TrainingStreamStatus.user == user)
            .distinct()
        )
    except NoResultFound:
        return []

    events = []
    for unique_account_id in unique_account_ids:
        try:
            events.append(
                session.exec(
                    select(TrainingStreamStatus)
                    .where(
                        TrainingStreamStatus.user == user,
                        TrainingStreamStatus.account_id == unique_account_id,
                    )
                    .order_by(TrainingStreamStatus.created.desc())  # type: ignore
                    .order_by(TrainingStreamStatus.id.desc())  # type: ignore
                    .limit(1)
                ).one()
            )
        except NoResultFound:
            pass
    return events

# %% ../notebooks/Training_Status_Process.ipynb 10
def get_count_from_training_data_ch_table(account_id: int) -> int:
    """
    Get count of all rows for given account id from clickhouse table

    Args:
        account_id: account id to use

    Returns:
        Count for the given account id
    """
    return airt_service.data.clickhouse.get_count(
        account_id=account_id,
        username=environ["KAFKA_CH_USERNAME"],
        password=environ["KAFKA_CH_PASSWORD"],
        host=environ["KAFKA_CH_HOST"],
        port=int(environ["KAFKA_CH_PORT"]),
        database=environ["KAFKA_CH_DATABASE"],
        table=environ["KAFKA_CH_TABLE"],
        protocol=environ["KAFKA_CH_PROTOCOL"],
    )

# %% ../notebooks/Training_Status_Process.ipynb 12
async def process_recent_event(
    recent_event: TrainingStreamStatus,
    *,
    session: Session,
    end_timedelta: int = 30,
    fast_kafka_api_app: FastKafkaAPI
):
    """
    Process a single recent event for an username and an AccountId

    Args:
        recent_event: A recent event of type TrainingStreamStatus from database
        session: session object
        end_timedelta: timedelta in seconds to use to determine whether upload is over or not
    """
    prev_count = recent_event.count

    if recent_event.event == "end":
        # Check model training status started and start it if not already
        pass
    elif recent_event.event in ["start", "upload"]:
        curr_count = await asyncify(get_count_from_training_data_ch_table)(
            account_id=recent_event.account_id
        )
        curr_check_on = datetime.utcnow()

        #         logger.info(f"{recent_event=}")
        if (
            curr_count == prev_count
            and curr_check_on - recent_event.created > timedelta(seconds=end_timedelta)
        ):
            to_update_event = "end"
            # Start model training status
        elif curr_count != prev_count:
            to_update_event = "upload"
        else:
            return
        upload_event = await asyncify(TrainingStreamStatus._create)(  # type: ignore
            account_id=recent_event.account_id,
            event=to_update_event,
            count=curr_count,
            total=recent_event.total,
            user=recent_event.user,
            session=session,
        )
        # send status msg to kafka
        #         training_data_status = TrainingDataStatus(
        #             AccountId=recent_event.account_id,
        #             no_of_records=curr_count,
        #             total_no_of_records=recent_event.total,
        #         )
        await fast_kafka_api_app.to_infobip_training_data_status(
            account_id=recent_event.account_id,
            no_of_records=curr_count,
            total_no_of_records=recent_event.total,
        )

# %% ../notebooks/Training_Status_Process.ipynb 14
async def process_training_status(username: str, fast_kafka_api_app: FastKafkaAPI):
    """
    An infinite loop to keep track of training_data uploads from user

    Args:
        username: username of user to track training data uploads
    """
    while True:
        #         logger.info(f"Starting the process loop")
        with get_session_with_context() as session:
            recent_events = await asyncify(get_recent_event_for_user)(username, session)
            for recent_event in recent_events:
                await process_recent_event(
                    recent_event, session=session, fast_kafka_api_app=fast_kafka_api_app
                )
        await asyncio.sleep(random.randint(1, 4))  # nosec B311
