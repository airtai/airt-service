# AUTOGENERATED! DO NOT EDIT! File to edit: ../../notebooks/Model_Prediction.ipynb.

# %% auto 0
__all__ = ['model_prediction_router', 'get_details_of_prediction', 'delete_prediction', 'prediction_pandas',
           'prediction_to_local_route', 'prediction_to_s3_route', 'prediction_to_azure_blob_storage_route',
           'prediction_to_mysql_route', 'prediction_to_clickhouse_route', 'get_details_of_prediction_push',
           'get_all_prediction']

# %% ../../notebooks/Model_Prediction.ipynb 3
import boto3
import pandas as pd

from botocore.client import Config
from fastapi import APIRouter, Depends, HTTPException, status, Query, BackgroundTasks
from pathlib import Path
from sqlalchemy.exc import NoResultFound
from sqlmodel import Session, select
from typing import *

import airt_service.sanitizer
from airt.logger import get_logger
from airt.patching import patch

from ..auth import get_current_active_user
from ..aws.utils import get_s3_bucket_and_path_from_uri
from ..batch_job import create_batch_job
from ..data.clickhouse import create_db_uri_for_clickhouse_datablob
from airt_service.data.datablob import (
    AzureBlobStorageRequest,
    ClickHouseRequest,
    DBRequest,
    S3Request,
)
from airt_service.data.utils import (
    create_db_uri_for_azure_blob_storage_datablob,
    create_db_uri_for_db_datablob,
    create_db_uri_for_s3_datablob,
    delete_data_object_files_in_cloud,
)
from airt_service.db.models import (
    get_session,
    User,
    Model,
    Prediction,
    PredictionRead,
    PredictionPush,
    PredictionPushRead,
)
from ..errors import HTTPError, ERRORS
from ..helpers import commit_or_rollback

# %% ../../notebooks/Model_Prediction.ipynb 5
logger = get_logger(__name__)

# %% ../../notebooks/Model_Prediction.ipynb 9
# Default router for all train routes
model_prediction_router = APIRouter(
    prefix="/prediction",
    tags=["prediction"],
    #     dependencies=[Depends(get_current_active_user)],
    responses={
        404: {"description": "Not found"},
        500: {
            "model": HTTPError,
            "description": ERRORS["INTERNAL_SERVER_ERROR"],
        },
    },
)

# %% ../../notebooks/Model_Prediction.ipynb 10
get_prediction_responses = {
    400: {"model": HTTPError, "description": ERRORS["INCORRECT_PREDICTION_ID"]}
}


@patch(cls_method=True)
def get(cls: Prediction, uuid: str, user: User, session: Session) -> Prediction:
    """Get prediction object for given prediction uuid

    Args:
        uuid: UUID of prediction
        user: User object
        session: Sqlmodel session
    Returns:
        The prediction object for given prediction uuid
    """
    try:
        prediction = session.exec(
            select(Prediction)
            .where(Prediction.uuid == uuid)
            .join(Model)
            .where(Model.user == user)
        ).one()
    except NoResultFound:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ERRORS["INCORRECT_PREDICTION_ID"],
        )

    if prediction.disabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ERRORS["PREDICTION_IS_DELETED"],
        )
    return prediction

# %% ../../notebooks/Model_Prediction.ipynb 13
@model_prediction_router.get(
    "/{prediction_uuid}",
    response_model=PredictionRead,
    responses={
        **get_prediction_responses,  # type: ignore
        422: {"model": HTTPError, "description": "Prediction error"},
    },
)
def get_details_of_prediction(
    prediction_uuid: str,
    user: User = Depends(get_current_active_user),
    session: Session = Depends(get_session),
) -> Prediction:
    """Get details of the prediction"""
    user = session.merge(user)
    # get details from the internal db for prediction_id
    prediction = Prediction.get(uuid=prediction_uuid, user=user, session=session)  # type: ignore

    if prediction.error is not None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=prediction.error
        )

    session.add(prediction)
    session.commit()
    session.refresh(prediction)

    return prediction

# %% ../../notebooks/Model_Prediction.ipynb 16
@model_prediction_router.delete(
    "/{prediction_uuid}",
    response_model=PredictionRead,
    responses=get_prediction_responses,  # type: ignore
)
def delete_prediction(
    prediction_uuid: str,
    user: User = Depends(get_current_active_user),
    session: Session = Depends(get_session),
) -> Prediction:
    """Delete prediction"""
    user = session.merge(user)
    # get details from the internal db for prediction_id
    prediction = Prediction.get(uuid=prediction_uuid, user=user, session=session)  # type: ignore

    delete_data_object_files_in_cloud(data_object=prediction)
    prediction.disabled = True

    session.add(prediction)
    session.commit()
    session.refresh(prediction)

    return prediction

# %% ../../notebooks/Model_Prediction.ipynb 18
@model_prediction_router.get(
    "/{prediction_uuid}/pandas", responses=get_prediction_responses  # type: ignore
)
def prediction_pandas(
    prediction_uuid: str,
    user: User = Depends(get_current_active_user),
    session: Session = Depends(get_session),
) -> Dict[str, List[Any]]:
    """Get prediction result as dictionary"""
    user = session.merge(user)
    prediction = Prediction.get(uuid=prediction_uuid, user=user, session=session)  # type: ignore
    # return prediction pandas as list

    df = pd.DataFrame(
        {
            "user_id": [
                520088904,
                530496790,
                561587266,
                518085591,
                558856683,
                520772685,
                514028527,
                518574284,
                532364121,
                532647354,
            ],
            "Score": [
                0.979853,
                0.979157,
                0.979055,
                0.978915,
                0.977960,
                0.004043,
                0.003890,
                0.001346,
                0.001341,
                0.001139,
            ],
        }
    )
    return df.to_dict("list")

# %% ../../notebooks/Model_Prediction.ipynb 20
@patch
def to_local(
    self: Prediction,
    session: Session,
) -> Dict[str, str]:
    """Download prediction results to local

    Args:
        session: Session object

    Returns:
        The Download url of the prediction as a dict
    """
    bucket, s3_path = get_s3_bucket_and_path_from_uri(self.path)  # type: ignore

    client = boto3.client(
        "s3",
        region_name=self.region,
        config=Config(signature_version="s3v4"),
        endpoint_url=f"https://s3.{self.region}.amazonaws.com",
    )

    return {
        Path(s3_file.key).name: client.generate_presigned_url(
            "get_object",
            Params={
                "Bucket": str(bucket.name).strip(),
                "Key": str(s3_file.key).strip(),
            },
            ExpiresIn=60 * 60 * 24,
        )
        for s3_file in bucket.objects.filter(Prefix=s3_path + "/")
        if Path(s3_file.key).name != str(self.id)
    }

# %% ../../notebooks/Model_Prediction.ipynb 21
@model_prediction_router.get(
    "/{prediction_uuid}/to_local",
    responses=get_prediction_responses,  # type: ignore
)
def prediction_to_local_route(
    prediction_uuid: str,
    *,
    user: User = Depends(get_current_active_user),
    session: Session = Depends(get_session),
) -> Dict[str, str]:
    """Get dict of filename, presigned url to download prediction parquet files"""
    user = session.merge(user)
    prediction = Prediction.get(uuid=prediction_uuid, user=user, session=session)  # type: ignore

    return prediction.to_local(session)  # type: ignore

# %% ../../notebooks/Model_Prediction.ipynb 23
@patch
def to_s3(
    self: Prediction,
    s3_request: S3Request,
    session: Session,
    background_tasks: BackgroundTasks,
) -> PredictionPush:
    """Push prediction results to S3

    Args:
        s3_request: S3Request object
        session: session

    Returns:
        An object of PredictionPush
    """
    uri = create_db_uri_for_s3_datablob(
        uri=s3_request.uri,
        access_key=s3_request.access_key,
        secret_key=s3_request.secret_key,
    )

    try:
        with commit_or_rollback(session):
            prediction_push = PredictionPush(
                total_steps=1,
                prediction_id=self.id,
                uri=uri,
            )
            session.add(prediction_push)
    except Exception as e:
        logger.exception(e)
        error_message = (
            e._message() if callable(getattr(e, "_message", None)) else str(e)  # type: ignore
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_message,
        )

    command = f"s3_push {prediction_push.id}"

    create_batch_job(
        command=command,
        task="csv_processing",
        cloud_provider=self.cloud_provider,
        region=self.region,
        background_tasks=background_tasks,
    )

    return prediction_push

# %% ../../notebooks/Model_Prediction.ipynb 24
@model_prediction_router.post(
    "/{prediction_uuid}/to_s3",
    response_model=PredictionPushRead,
    responses=get_prediction_responses,  # type: ignore
)
def prediction_to_s3_route(
    prediction_uuid: str,
    *,
    s3_request: S3Request,
    user: User = Depends(get_current_active_user),
    session: Session = Depends(get_session),
    background_tasks: BackgroundTasks,
) -> PredictionPush:
    """Push prediction results to s3"""
    user = session.merge(user)
    prediction = Prediction.get(uuid=prediction_uuid, user=user, session=session)  # type: ignore

    return prediction.to_s3(s3_request, session, background_tasks)  # type: ignore

# %% ../../notebooks/Model_Prediction.ipynb 26
@patch
def to_azure_blob_storage(
    self: Prediction,
    azure_blob_storage_request: AzureBlobStorageRequest,
    session: Session,
    background_tasks: BackgroundTasks,
) -> PredictionPush:
    """Push prediction reslults to azure blob storage

    Args:
        azure_blob_storage_request: AzureBlobStorageRequest object
        session: session

    Returns:
        An object of PredictionPush
    """
    uri = create_db_uri_for_azure_blob_storage_datablob(
        uri=azure_blob_storage_request.uri,
        credential=azure_blob_storage_request.credential,
    )

    try:
        with commit_or_rollback(session):
            prediction_push = PredictionPush(
                total_steps=1,
                prediction_id=self.id,
                uri=uri,
            )
            session.add(prediction_push)
    except Exception as e:
        logger.exception(e)
        error_message = (
            e._message() if callable(getattr(e, "_message", None)) else str(e)  # type: ignore
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_message,
        )

    command = f"azure_blob_storage_push {prediction_push.id}"

    create_batch_job(
        command=command,
        task="csv_processing",
        cloud_provider=self.cloud_provider,
        region=self.region,
        background_tasks=background_tasks,
    )

    return prediction_push

# %% ../../notebooks/Model_Prediction.ipynb 27
@model_prediction_router.post(
    "/{prediction_uuid}/to_azure_blob_storage",
    response_model=PredictionPushRead,
    responses=get_prediction_responses,  # type: ignore
)
def prediction_to_azure_blob_storage_route(
    prediction_uuid: str,
    *,
    azure_blob_storage_request: AzureBlobStorageRequest,
    user: User = Depends(get_current_active_user),
    session: Session = Depends(get_session),
    background_tasks: BackgroundTasks,
) -> PredictionPush:
    """Push prediction results to s3"""
    user = session.merge(user)
    prediction = Prediction.get(uuid=prediction_uuid, user=user, session=session)  # type: ignore

    return prediction.to_azure_blob_storage(azure_blob_storage_request, session, background_tasks)  # type: ignore

# %% ../../notebooks/Model_Prediction.ipynb 29
@patch
def to_rdbms(
    self: Prediction,
    db_request: DBRequest,
    database_server: str,
    session: Session,
    background_tasks: BackgroundTasks,
) -> PredictionPush:
    """Push prediction resluts to a relational database

    Args:
        db_request: DBRequest object
        database_server: Database server to push the results
        session: Session object

    Returns:
        An object of PredictionPush
    """
    if database_server not in ["mysql", "postgresql"]:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail=f"{ERRORS['PUSH_NOT_AVAILABLE']} for database server {database_server}",
        )

    uri = create_db_uri_for_db_datablob(
        username=db_request.username,
        password=db_request.password,
        host=db_request.host,
        port=db_request.port,
        table=db_request.table,
        database=db_request.database,
        database_server=database_server,
    )

    try:
        with commit_or_rollback(session):
            prediction_push = PredictionPush(
                total_steps=1,
                prediction_id=self.id,
                uri=uri,
            )
            session.add(prediction_push)
    except Exception as e:
        logger.exception(e)
        error_message = (
            e._message() if callable(getattr(e, "_message", None)) else str(e)  # type: ignore
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_message,
        )

    command = f"db_push {prediction_push.id}"

    create_batch_job(
        command=command,
        task="csv_processing",
        cloud_provider=self.cloud_provider,
        region=self.region,
        background_tasks=background_tasks,
    )

    return prediction_push

# %% ../../notebooks/Model_Prediction.ipynb 30
@model_prediction_router.post(
    "/{prediction_uuid}/to_mysql",
    response_model=PredictionPushRead,
    responses=get_prediction_responses,  # type: ignore
)
def prediction_to_mysql_route(
    prediction_uuid: str,
    *,
    db_request: DBRequest,
    user: User = Depends(get_current_active_user),
    session: Session = Depends(get_session),
    background_tasks: BackgroundTasks,
) -> PredictionPush:
    """Push prediction results to mysql database"""
    user = session.merge(user)
    prediction = Prediction.get(uuid=prediction_uuid, user=user, session=session)  # type: ignore

    return prediction.to_rdbms(  # type: ignore
        db_request=db_request,
        database_server="mysql",
        session=session,
        background_tasks=background_tasks,
    )

# %% ../../notebooks/Model_Prediction.ipynb 32
@patch
def to_clickhouse(
    self: Prediction,
    clickhouse_request: ClickHouseRequest,
    session: Session,
    background_tasks: BackgroundTasks,
) -> PredictionPush:
    """Push prediction results to a clickhouse database

    Args:
        clickhouse_request: ClickHouseRequest object
        session: Session object
        background_tasks: BackgroundTasks object

    Returns:
        An object of PredictionPush
    """

    uri = create_db_uri_for_clickhouse_datablob(
        username=clickhouse_request.username,
        password=clickhouse_request.password,
        host=clickhouse_request.host,
        port=clickhouse_request.port,
        table=clickhouse_request.table,
        database=clickhouse_request.database,
        protocol=clickhouse_request.protocol,
    )

    try:
        with commit_or_rollback(session):
            prediction_push = PredictionPush(
                total_steps=1,
                prediction_id=self.id,
                uri=uri,
            )
            session.add(prediction_push)
    except Exception as e:
        logger.exception(e)
        error_message = (
            e._message() if callable(getattr(e, "_message", None)) else str(e)  # type: ignore
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_message,
        )

    command = f"clickhouse_push {prediction_push.id}"

    create_batch_job(
        command=command,
        task="csv_processing",
        cloud_provider=self.cloud_provider,
        region=self.region,
        background_tasks=background_tasks,
    )

    return prediction_push

# %% ../../notebooks/Model_Prediction.ipynb 33
@model_prediction_router.post(
    "/{prediction_uuid}/to_clickhouse",
    response_model=PredictionPushRead,
    responses=get_prediction_responses,  # type: ignore
)
def prediction_to_clickhouse_route(
    prediction_uuid: str,
    *,
    clickhouse_request: ClickHouseRequest,
    user: User = Depends(get_current_active_user),
    session: Session = Depends(get_session),
    background_tasks: BackgroundTasks,
) -> PredictionPush:
    """Push prediction results to clickhouse database"""
    user = session.merge(user)
    prediction = Prediction.get(uuid=prediction_uuid, user=user, session=session)  # type: ignore

    return prediction.to_clickhouse(  # type: ignore
        clickhouse_request=clickhouse_request,
        session=session,
        background_tasks=background_tasks,
    )

# %% ../../notebooks/Model_Prediction.ipynb 35
@model_prediction_router.get(
    "/push/{prediction_push_uuid}",
    response_model=PredictionPushRead,
    responses={
        400: {
            "model": HTTPError,
            "description": ERRORS["INCORRECT_PREDICTION_PUSH_ID"],
        },
        422: {"model": HTTPError, "description": "Prediction push error"},
    },
)
def get_details_of_prediction_push(
    prediction_push_uuid: str,
    user: User = Depends(get_current_active_user),
    session: Session = Depends(get_session),
) -> PredictionPush:
    """Push prediction results to the given datasource"""
    user = session.merge(user)

    try:
        prediction_push = session.exec(
            select(PredictionPush)
            .where(PredictionPush.uuid == prediction_push_uuid)
            .join(Prediction)
            .join(Model)
            .where(Model.user == user)
        ).one()
    except NoResultFound:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ERRORS["INCORRECT_PREDICTION_PUSH_ID"],
        )

    if prediction_push.error is not None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=prediction_push.error,
        )

    session.add(prediction_push)
    session.commit()
    session.refresh(prediction_push)

    return prediction_push

# %% ../../notebooks/Model_Prediction.ipynb 37
@model_prediction_router.get("/", response_model=List[PredictionRead])
def get_all_prediction(
    disabled: bool = False,
    completed: bool = False,
    offset: int = 0,
    limit: int = Query(default=100, lte=100),
    user: User = Depends(get_current_active_user),
    session: Session = Depends(get_session),
) -> List[Prediction]:
    """Get all predictions created by user"""
    user = session.merge(user)
    statement = select(Prediction)
    statement = statement.where(Prediction.disabled == disabled)
    if completed:
        statement = statement.where(
            Prediction.completed_steps == Prediction.total_steps
        )
    # get all predictions from db
    predictions = session.exec(
        statement.join(Model).where(Model.user == user).offset(offset).limit(limit)
    ).all()
    return predictions
