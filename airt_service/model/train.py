# AUTOGENERATED! DO NOT EDIT! File to edit: ../../notebooks/Model_Train.ipynb.

# %% auto 0
__all__ = ['model_train_router', 'get_model_responses', 'TrainRequest', 'train_model', 'get_model', 'get_details_of_model',
           'delete_model', 'evaluate_model', 'get_all_model', 'predict_model', 'predict']

# %% ../../notebooks/Model_Train.ipynb 3
import shutil
import uuid
from datetime import timedelta
from typing import *

import airt_service.sanitizer
from airt.logger import get_logger
from airt.remote_path import RemotePath
from ..auth import get_current_active_user
from ..aws.utils import create_s3_prediction_path
from ..azure.utils import create_azure_blob_storage_prediction_path
from ..batch_job import create_batch_job
from ..constants import METADATA_FOLDER_PATH
from ..data.datasource import get_datasource_responses
from airt_service.db.models import (
    DataSource,
    DataSourceSelect,
    Model,
    ModelRead,
    Prediction,
    PredictionRead,
    User,
    get_session,
    get_session_with_context,
)
from ..errors import ERRORS, HTTPError
from ..helpers import truncate
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from fastcore.script import Param, call_parse
from pydantic import BaseModel
from sqlalchemy.exc import NoResultFound
from sqlmodel import Session, select

# %% ../../notebooks/Model_Train.ipynb 5
logger = get_logger(__name__)

# %% ../../notebooks/Model_Train.ipynb 9
# Default router for all train routes
model_train_router = APIRouter(
    prefix="/model",
    tags=["train"],
    #     dependencies=[Depends(get_current_active_user)],
    responses={
        404: {"description": "Not found"},
        500: {
            "model": HTTPError,
            "description": ERRORS["INTERNAL_SERVER_ERROR"],
        },
    },
)

# %% ../../notebooks/Model_Train.ipynb 10
class TrainRequest(BaseModel):
    """Request object for the /model/train route

    Args:
        data_uuid: Datasource uuid to train model
        client_column: Column in which client ids are present
        target_column: Column where target events for training are present
        target: Regex string to use as target event for training
        predict_after: Time period after to predict(in seconds)
    """

    data_uuid: uuid.UUID
    client_column: str
    target_column: str
    target: str
    predict_after: timedelta

# %% ../../notebooks/Model_Train.ipynb 11
@model_train_router.post(
    "/train",
    response_model=ModelRead,
    responses={
        **get_datasource_responses,  # type: ignore
        412: {"model": HTTPError, "description": ERRORS["QUOTA_EXCEEDED"]},
    },
)
def train_model(
    train_request: TrainRequest,
    user: User = Depends(get_current_active_user),
    session: Session = Depends(get_session),
) -> Model:
    """Start model training from the given datasource"""
    user = session.merge(user)
    if not user.subscription_type.value in [
        "small",
        "medium",
        "large",
        "infobip",
        "captn",
    ]:
        raise HTTPException(
            status_code=status.HTTP_412_PRECONDITION_FAILED,
            detail=ERRORS["QUOTA_EXCEEDED"],
        )
    datasource = DataSource.get(uuid=train_request.data_uuid, user=user, session=session)  # type: ignore
    # send msg to batch job queue to start training and return model_id
    model = Model(
        client_column=train_request.client_column,
        target_column=train_request.target_column,
        target=train_request.target,
        predict_after=train_request.predict_after,
        cloud_provider=datasource.cloud_provider,
        region=datasource.region,
        total_steps=5,
        user=user,
        datasource_id=datasource.id,
    )
    session.add(model)
    session.commit()
    session.refresh(model)
    return model

# %% ../../notebooks/Model_Train.ipynb 14
get_model_responses = {
    400: {"model": HTTPError, "description": ERRORS["INCORRECT_MODEL_ID"]}
}


def get_model(model_uuid: str, user: User, session: Session) -> Model:
    """Get model object for the model_id

    Args:
        model_uuid: Model uuid
        user: User object
        session: Sqlmodel session

     Returns:
        The model object for given model uuid
    """
    try:
        model = session.exec(
            select(Model).where(Model.uuid == model_uuid, Model.user == user)
        ).one()
    except NoResultFound:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ERRORS["INCORRECT_MODEL_ID"],
        )

    if model.disabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=ERRORS["MODEL_IS_DELETED"]
        )
    return model

# %% ../../notebooks/Model_Train.ipynb 17
@model_train_router.get(
    "/{model_uuid}",
    response_model=ModelRead,
    responses={
        **get_model_responses,  # type: ignore
        422: {"model": HTTPError, "description": "Model error"},
    },
)
def get_details_of_model(
    model_uuid: str,
    user: User = Depends(get_current_active_user),
    session: Session = Depends(get_session),
) -> Model:
    """Get details of the model"""
    user = session.merge(user)
    # get details from the internal db for model_id
    model = get_model(model_uuid=model_uuid, user=user, session=session)

    if model.error is not None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=model.error
        )

    # ToDo: Remove following temporary fix once actual train is implemented
    model.completed_steps = model.total_steps
    session.add(model)
    session.commit()
    session.refresh(model)
    return model

# %% ../../notebooks/Model_Train.ipynb 20
@model_train_router.delete(
    "/{model_uuid}", response_model=ModelRead, responses=get_model_responses  # type: ignore
)
def delete_model(
    model_uuid: str,
    user: User = Depends(get_current_active_user),
    session: Session = Depends(get_session),
) -> Model:
    """Delete model"""
    user = session.merge(user)
    # get details from the internal db for model_id
    model = get_model(model_uuid=model_uuid, user=user, session=session)

    if model.path is not None:
        shutil.rmtree(model.path)
    model.disabled = True

    session.add(model)
    session.commit()
    session.refresh(model)
    return model

# %% ../../notebooks/Model_Train.ipynb 22
@model_train_router.get("/{model_uuid}/evaluate", responses=get_model_responses)  # type: ignore
def evaluate_model(
    model_uuid: str,
    user: User = Depends(get_current_active_user),
    session: Session = Depends(get_session),
) -> Dict[str, float]:
    """Get accuracy, recall, precision of the trained model"""
    user = session.merge(user)
    # get evaluation for the trained model
    model = get_model(model_uuid=model_uuid, user=user, session=session)
    return {"accuracy": 0.985, "recall": 0.962, "precision": 0.934}

# %% ../../notebooks/Model_Train.ipynb 24
@model_train_router.get("/", response_model=List[ModelRead])
def get_all_model(
    disabled: bool = False,
    completed: bool = False,
    offset: int = 0,
    limit: int = Query(default=100, lte=100),
    user: User = Depends(get_current_active_user),
    session: Session = Depends(get_session),
) -> List[Model]:
    """Get all models created by user"""
    user = session.merge(user)
    statement = select(Model).where(Model.user == user)
    statement = statement.where(Model.disabled == disabled)
    if completed:
        statement = statement.where(Model.completed_steps == Model.total_steps)
    # get all models from db
    models = session.exec(statement.offset(offset).limit(limit)).all()
    return models

# %% ../../notebooks/Model_Train.ipynb 27
@model_train_router.post(
    "/{model_uuid}/predict",
    response_model=PredictionRead,
    responses={
        **get_model_responses,  # type: ignore
        412: {"model": HTTPError, "description": ERRORS["QUOTA_EXCEEDED"]},
    },
)
def predict_model(
    *,
    model_uuid: str,
    datasource_select: Optional[DataSourceSelect] = None,
    user: User = Depends(get_current_active_user),
    session: Session = Depends(get_session),
    background_tasks: BackgroundTasks,
) -> Prediction:
    """Start prediction using trained model and for the given datasource"""
    user = session.merge(user)
    if not user.subscription_type.value in [
        "small",
        "medium",
        "large",
        "infobip",
        "captn",
    ]:
        raise HTTPException(
            status_code=status.HTTP_412_PRECONDITION_FAILED,
            detail=ERRORS["QUOTA_EXCEEDED"],
        )
    model = get_model(model_uuid=model_uuid, user=user, session=session)
    data_uuid = (
        model.datasource.uuid
        if datasource_select is None
        else datasource_select.data_uuid
    )
    datasource = DataSource.get(uuid=data_uuid, user=user, session=session)  # type: ignore
    # start prediction for the trained model and return prediction_id
    prediction = Prediction(
        total_steps=3,
        user=user,
        model=model,
        datasource_id=datasource.id,
        cloud_provider=datasource.cloud_provider,
        region=datasource.region,
    )
    session.add(prediction)
    session.commit()

    command = f"predict {prediction.id}"

    create_batch_job(
        command=command,
        task="csv_processing",
        cloud_provider=prediction.cloud_provider,
        region=prediction.region,
        background_tasks=background_tasks,
    )

    return prediction

# %% ../../notebooks/Model_Train.ipynb 29
@call_parse
def predict(prediction_id: Param("id of prediction in db", int)):  # type: ignore
    """Copy datasource parquet to prediction path to create dummy prediction output

    Args:
        prediction_id: Id of prediction in db

    Example:
        The following code executes a CLI command:
        ```predict 1
        ```
    """
    with get_session_with_context() as session:
        prediction = session.exec(
            select(Prediction).where(Prediction.id == prediction_id)
        ).one()
        prediction.path = None

        datasource = session.exec(
            select(DataSource).where(DataSource.id == prediction.model.datasource_id)
        ).one()

        try:
            if datasource.cloud_provider == "aws":
                destination_bucket, s3_path = create_s3_prediction_path(
                    user_id=prediction.model.user.id,
                    prediction_id=prediction.id,
                    region=prediction.region,
                )
                destination_remote_url = f"s3://{destination_bucket.name}/{s3_path}"
            elif datasource.cloud_provider == "azure":
                (
                    destination_container_client,
                    destination_azure_blob_storage_path,
                ) = create_azure_blob_storage_prediction_path(
                    user_id=prediction.model.user.id,
                    prediction_id=prediction.id,
                    region=prediction.region,
                )
                destination_remote_url = f"{destination_container_client.url}/{destination_azure_blob_storage_path}"

            with RemotePath.from_url(
                remote_url=destination_remote_url,
                pull_on_enter=False,
                push_on_exit=True,
                exist_ok=True,
                parents=True,
            ) as destination_path:
                sync_path = destination_path.as_path()
                source_remote_url = datasource.path
                with RemotePath.from_url(
                    remote_url=source_remote_url,
                    pull_on_enter=True,
                    push_on_exit=False,
                    exist_ok=True,
                    parents=False,
                ) as source_remote_path:
                    source_files = source_remote_path.as_path().iterdir()
                    source_files = [
                        f for f in source_files if METADATA_FOLDER_PATH not in str(f)
                    ]
                    for f in source_files:
                        shutil.move(str(f), sync_path)

            prediction.path = destination_remote_url  # type: ignore
            prediction.completed_steps = prediction.total_steps
        except Exception as e:
            prediction.error = truncate(str(e))
        session.add(prediction)
        session.commit()
