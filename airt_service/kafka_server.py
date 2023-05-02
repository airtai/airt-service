# AUTOGENERATED! DO NOT EDIT! File to edit: ../notebooks/Kafka_Service.ipynb.

# %% auto 0
__all__ = ['get_count_from_training_data_ch_table', 'json_datetime_sec_encoder', 'ModelType', 'ModelTrainingRequest', 'EventData',
           'RealtimeData', 'TrainingDataStatus', 'TrainingModelStart', 'Tracker', 'add_process_start_training_data',
           'TrainingModelStatus', 'ModelMetrics', 'add_process_training_model_start', 'Prediction', 'add_predictions',
           'create_fastkafka_application']

# %% ../notebooks/Kafka_Service.ipynb 1
import asyncio
from datetime import datetime, timedelta
from enum import Enum
from os import environ
from typing import *

import numpy as np
import pandas as pd
from airt.logger import get_logger
from fastkafka import FastKafka
from pydantic import BaseModel, EmailStr, Field, HttpUrl, NonNegativeInt, validator

import airt_service
from .confluent import aio_kafka_config
from airt_service.data.clickhouse import (
    get_all_person_ids_for_account_ids,
    get_count_for_account_ids,
)

# %% ../notebooks/Kafka_Service.ipynb 3
logger = get_logger(__name__)

# %% ../notebooks/Kafka_Service.ipynb 5
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
    return get_count_for_account_ids(
        account_ids=account_ids,
        username=environ["KAFKA_CH_USERNAME"],
        password=environ["KAFKA_CH_PASSWORD"],
        host=environ["KAFKA_CH_HOST"],
        port=int(environ["KAFKA_CH_PORT"]),
        database=environ["KAFKA_CH_DATABASE"],
        table=environ["KAFKA_CH_TABLE"],
        protocol=environ["KAFKA_CH_PROTOCOL"],
    )

# %% ../notebooks/Kafka_Service.ipynb 14
def json_datetime_sec_encoder(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%S")

# %% ../notebooks/Kafka_Service.ipynb 16
class ModelType(str, Enum):
    churn = "churn"
    propensity_to_buy = "propensity_to_buy"


class ModelTrainingRequest(BaseModel):
    AccountId: NonNegativeInt = Field(
        ..., example=202020, description="ID of an account"
    )
    ApplicationId: Optional[str] = Field(
        default=None,
        example="TestApplicationId",
        description="Id of the application in case there is more than one for the AccountId",
    )
    ModelId: Optional[str] = Field(
        default=None,
        example="ChurnModelForDrivers",
        description="User supplied ID of the model trained",
    )
    model_type: ModelType = Field(
        ..., description="Model type, only 'churn' is supported right now"
    )
    total_no_of_records: NonNegativeInt = Field(
        ...,
        example=1_000_000,
        description="approximate total number of records (rows) to be ingested",
    )

# %% ../notebooks/Kafka_Service.ipynb 18
class EventData(BaseModel):
    """
    A sequence of events for a fixed account_id
    """

    AccountId: NonNegativeInt = Field(
        ..., example=202020, description="ID of an account"
    )
    ApplicationId: Optional[str] = Field(
        default=None,
        example="TestApplicationId",
        description="Id of the application in case there is more than one for the AccountId",
    )
    ModelId: Optional[str] = Field(
        default=None,
        example="ChurnModelForDrivers",
        description="User supplied ID of the model trained",
    )

    DefinitionId: str = Field(
        ...,
        example="appLaunch",
        description="name of the event",
        min_length=1,
    )
    OccurredTime: datetime = Field(
        ...,
        example="2021-03-28T00:34:08",
        description="local time of the event",
    )
    OccurredTimeTicks: NonNegativeInt = Field(
        ...,
        example=1616891648496,
        description="local time of the event as the number of ticks",
    )
    PersonId: NonNegativeInt = Field(
        ..., example=12345678, description="ID of a person"
    )


class RealtimeData(EventData):
    pass

# %% ../notebooks/Kafka_Service.ipynb 20
class TrainingDataStatus(BaseModel):
    AccountId: NonNegativeInt = Field(
        ..., example=202020, description="ID of an account"
    )
    ApplicationId: Optional[str] = Field(
        default=None,
        example="TestApplicationId",
        description="Id of the application in case there is more than one for the AccountId",
    )
    ModelId: Optional[str] = Field(
        default=None,
        example="ChurnModelForDrivers",
        description="User supplied ID of the model trained",
    )

    no_of_records: NonNegativeInt = Field(
        ...,
        example=12_345,
        description="number of records (rows) ingested",
    )
    total_no_of_records: NonNegativeInt = Field(
        ...,
        example=1_000_000,
        description="total number of records (rows) to be ingested",
    )

# %% ../notebooks/Kafka_Service.ipynb 22
class TrainingModelStart(BaseModel):
    AccountId: NonNegativeInt = Field(
        ..., example=202020, description="ID of an account"
    )
    ApplicationId: Optional[str] = Field(
        default=None,
        example="TestApplicationId",
        description="Id of the application in case there is more than one for the AccountId",
    )
    ModelId: Optional[str] = Field(
        default=None,
        example="ChurnModelForDrivers",
        description="User supplied ID of the model trained",
    )
    model_type: ModelType = Field(
        ..., description="Model type, only 'churn' is supported right now"
    )
    no_of_records: NonNegativeInt = Field(
        ...,
        example=1_000_000,
        description="number of records (rows) in the DB used for training",
    )

# %% ../notebooks/Kafka_Service.ipynb 24
class Tracker:
    def __init__(self, *, limit: int, timeout: int):
        self._limit = limit
        self._timeout = timeout
        self._count: Optional[int] = None
        self._last_updated: Optional[datetime] = None

    def update(self, count: int) -> bool:
        if self._count != count:
            self._count = count
            self._last_updated = datetime.now()
            return True
        else:
            return False

    def finished(self) -> bool:
        if self._count is not None:
            return (self._count >= self._limit) or (
                datetime.now() - self._last_updated  # type: ignore
            ) > timedelta(seconds=self._timeout)
        else:
            return False

# %% ../notebooks/Kafka_Service.ipynb 27
def add_process_start_training_data(
    app: FastKafka,
    *,
    username: str = "infobip",
    stop_on_no_change_interval: int = 60,
    sleep_interval: int = 5,
) -> None:
    #     app.produces(
    #         topic=f"{username}_training_data_status",
    #         msg_type=TrainingDataStatus,
    #         encoding="avro",
    #     )

    @app.produces(topic=f"{username}_training_data_status")  # type: ignore
    async def to_training_data_status(
        training_data_status: TrainingDataStatus,
    ) -> TrainingDataStatus:
        print(f"to_training_data_status({training_data_status})")
        return training_data_status

    @app.produces(topic=f"{username}_training_model_start")  # type: ignore
    async def to_training_model_start(
        training_model_start: TrainingModelStart,
    ) -> TrainingModelStart:
        print(f"to_training_model_start({training_model_start})")
        return training_model_start

    app.to_training_data_status = to_training_data_status
    app.to_training_model_start = to_training_model_start

    @app.consumes(topic=f"{username}_start_training_data")  # type: ignore
    async def on_start_training_data(msg: ModelTrainingRequest, app=app) -> None:
        print(f"on_start_training_data({msg}) starting...")

        account_ids = [msg.AccountId]
        total_no_of_records = msg.total_no_of_records

        tracker = Tracker(limit=total_no_of_records, timeout=stop_on_no_change_interval)

        while not tracker.finished():
            df = get_count_from_training_data_ch_table(
                account_ids=account_ids  # type: ignore
            )
            if df.shape[0] == 1:
                curr_count, _ = df.iloc[0, :]

                print(f"{curr_count=}")

                if tracker.update(curr_count):
                    training_data_status = TrainingDataStatus(
                        no_of_records=curr_count, **msg.dict()
                    )
                    await app.to_training_data_status(training_data_status)
            else:
                logger.info(
                    f"on_start_training_data(): no data yet received in clickhouse for {msg=}."
                )

            await asyncio.sleep(sleep_interval)

        # trigger model training start
        training_model_start = TrainingModelStart(
            no_of_records=curr_count, **msg.dict()
        )
        await app.to_training_model_start(training_model_start)

        print(f"on_start_training_data({msg}) finished.")

# %% ../notebooks/Kafka_Service.ipynb 29
class TrainingModelStatus(BaseModel):
    AccountId: NonNegativeInt = Field(
        ..., example=202020, description="ID of an account"
    )
    ApplicationId: Optional[str] = Field(
        default=None,
        example="TestApplicationId",
        description="Id of the application in case there is more than one for the AccountId",
    )
    ModelId: Optional[str] = Field(
        default=None,
        example="ChurnModelForDrivers",
        description="User supplied ID of the model trained",
    )

    current_step: NonNegativeInt = Field(
        ...,
        example=0,
        description="number of records (rows) ingested",
    )
    current_step_percentage: float = Field(
        ...,
        example=0.21,
        description="the percentage of the current step completed",
    )
    total_no_of_steps: NonNegativeInt = Field(
        ...,
        example=20,
        description="total number of steps for training the model",
    )

# %% ../notebooks/Kafka_Service.ipynb 31
class ModelMetrics(BaseModel):
    """The standard metrics for classification models.

    The most important metrics is AUC for unbalanced classes such as churn. Metrics such as
    accuracy are not very useful since they are easily maximized by outputting the most common
    class all the time.
    """

    AccountId: NonNegativeInt = Field(
        ..., example=202020, description="ID of an account"
    )
    ApplicationId: Optional[str] = Field(
        default=None,
        example="TestApplicationId",
        description="Id of the application in case there is more than one for the AccountId",
    )
    ModelId: Optional[str] = Field(
        default=None,
        example="ChurnModelForDrivers",
        description="User supplied ID of the model trained",
    )

    timestamp: datetime = Field(
        ...,
        example="2021-03-28T00:34:08",
        description="UTC time when the model was trained",
    )
    model_type: ModelType = Field(
        ...,
        example="churn",
        description="Name of the model used (churn, propensity to buy)",
    )

    auc: float = Field(
        ..., example=0.91, description="Area under ROC curve", ge=0.0, le=1.0
    )
    f1: float = Field(..., example=0.89, description="F-1 score", ge=0.0, le=1.0)
    precission: float = Field(
        ..., example=0.84, description="precission", ge=0.0, le=1.0
    )
    recall: float = Field(..., example=0.82, description="recall", ge=0.0, le=1.0)
    accuracy: float = Field(..., example=0.82, description="accuracy", ge=0.0, le=1.0)

    class Config:
        json_encoders = {
            datetime: json_datetime_sec_encoder,
        }

# %% ../notebooks/Kafka_Service.ipynb 34
def add_process_training_model_start(
    app: FastKafka,
    *,
    username: str = "infobip",
    total_no_of_steps: int = 10,
    substep_interval: Union[int, float] = 2,
) -> None:
    @app.produces(topic=f"{username}_training_model_status")  # type: ignore
    async def to_training_model_status(
        training_model_status: TrainingModelStatus,
    ) -> TrainingModelStatus:
        print(f"to_training_model_status({training_model_status})")
        return training_model_status

    @app.produces(topic=f"{username}_model_metrics")  # type: ignore
    async def to_model_metrics(
        model_metrics: ModelMetrics,
    ) -> ModelMetrics:
        print(f"to_model_metrics({model_metrics})")
        return model_metrics

    app.to_training_model_status = to_training_model_status
    app.to_model_metrics = to_model_metrics

    @app.consumes(topic=f"{username}_training_model_start")  # type: ignore
    async def on_training_model_start(msg: TrainingModelStart) -> None:
        print(f"on_training_model_start({msg}) starting...")

        AccountId = msg.AccountId
        ApplicationId = msg.ApplicationId
        ModelId = msg.ModelId
        model_type = msg.model_type

        for current_step in range(total_no_of_steps):
            for current_step_percentage in [0.0, 0.2, 0.5, 0.75, 1.0]:
                training_model_status = TrainingModelStatus(
                    AccountId=AccountId,
                    ApplicationId=ApplicationId,
                    ModelId=ModelId,
                    current_step=current_step,
                    current_step_percentage=current_step_percentage,
                    total_no_of_steps=total_no_of_steps,
                )
                await app.to_training_model_status(training_model_status)

                await asyncio.sleep(substep_interval)

        model_metrics = ModelMetrics(
            AccountId=AccountId,
            ApplicationId=ApplicationId,
            ModelId=ModelId,
            model_type=model_type,
            timestamp=datetime.now(),
            auc=0.951,
            recall=0.944,
            precission=0.983,
            accuracy=0.992,
            f1=f"{2*0.944*0.983/(0.944+0.983):0.3f}",
        )
        await app.to_model_metrics(model_metrics)

        print(f"on_training_model_start({msg}) finished.")

# %% ../notebooks/Kafka_Service.ipynb 36
class Prediction(BaseModel):
    AccountId: NonNegativeInt = Field(
        ..., example=202020, description="ID of an account"
    )
    ApplicationId: Optional[str] = Field(
        default=None,
        example="TestApplicationId",
        description="Id of the application in case there is more than one for the AccountId",
    )
    ModelId: Optional[str] = Field(
        default=None,
        example="ChurnModelForDrivers",
        description="User supplied ID of the model trained",
    )

    PersonId: NonNegativeInt = Field(
        ..., example=12345678, description="ID of a person"
    )
    prediction_time: datetime = Field(
        ...,
        example="2021-03-28T00:34:08",
        description="UTC time of prediction",
    )
    model_type: ModelType = Field(
        ...,
        example="churn",
        description="Name of the model used (churn, propensity to buy)",
    )
    score: float = Field(
        ...,
        example=0.4321,
        description="Prediction score (e.g. the probability of churn in the next 28 days)",
        ge=0.0,
        le=1.0,
    )

    class Config:
        json_encoders = {
            datetime: json_datetime_sec_encoder,
        }

# %% ../notebooks/Kafka_Service.ipynb 38
def add_predictions(
    app: FastKafka,
    *,
    username: str = "infobip",
) -> None:
    @app.produces(topic=f"{username}_prediction")  # type: ignore
    async def to_prediction(
        prediction: Prediction,
    ) -> Prediction:
        return prediction

    app.to_prediction = to_prediction

    @app.consumes(topic=f"{username}_model_metrics")  # type: ignore
    async def on_model_metrics(msg: ModelMetrics) -> None:
        print(f"on_model_metrics({msg}) starting...")

        AccountId = msg.AccountId
        ApplicationId = msg.ApplicationId
        ModelId = msg.ModelId
        model_type = msg.model_type
        prediction_time = datetime.now()

        person_ids = get_all_person_ids_for_account_ids([AccountId])["PersonId"]

        rng = np.random.default_rng(42)

        print(
            f"Sending predictions for ({AccountId=}, {ApplicationId=}, {ModelId}) started."
        )
        t0 = datetime.now()
        for PersonId in person_ids:
            prediction = Prediction(
                AccountId=AccountId,
                ApplicationId=ApplicationId,
                ModelId=ModelId,
                model_type=model_type,
                prediction_time=prediction_time,
                PersonId=PersonId,
                score=rng.uniform(),
            )
            await to_prediction(prediction)
        print(
            f"Sending predictions for ({AccountId=}, {ApplicationId=}, {ModelId}) finished in {datetime.now()-t0}."
        )

        print(f"on_model_metrics({msg}) finished.")

# %% ../notebooks/Kafka_Service.ipynb 40
def _construct_kafka_brokers() -> Dict[str, Dict[str, Any]]:
    url, port = aio_kafka_config["bootstrap_servers"].split(":")

    kafka_brokers = {
        "staging": {
            "url": "pkc-1wvvj.westeurope.azure.confluent.cloud",
            "description": "Staging Kafka broker",
            "port": 9092,
            "protocol": "kafka-secure",
            "security": {"type": "plain"},
        },
        "production": {
            "url": "pkc-1wvvj.westeurope.azure.confluent.cloud",
            "description": "Production Kafka broker",
            "port": 9092,
            "protocol": "kafka-secure",
            "security": {"type": "plain"},
        },
    }

    if (url != kafka_brokers["staging"]["url"]) and (
        url != kafka_brokers["production"]["url"]
    ):
        kafka_brokers["dev"] = {
            "url": url,
            "description": "Development Kafka broker",
            "port": port,
        }

    return kafka_brokers

# %% ../notebooks/Kafka_Service.ipynb 42
def create_fastkafka_application(
    start_process_for_username: Optional[str] = "infobip",
) -> FastKafka:
    """Create a FastKafka service

    Args:
        start_process_for_username: prefix for topics used

    Returns:
        A FastKafka application
    """

    kafka_brokers = _construct_kafka_brokers()

    exclude_keys = ["bootstrap_servers"]
    kafka_config = {
        k: aio_kafka_config[k]
        for k in set(list(aio_kafka_config.keys())) - set(exclude_keys)
    }

    # global description
    version = airt_service.__version__
    contact = dict(name="airt.ai", url="https://airt.ai", email="info@airt.ai")

    app = FastKafka(
        title="airt service kafka api",
        description="kafka api for airt service",
        kafka_brokers=kafka_brokers,
        version=version,
        contact=contact,
        #         auto_offset_reset="earliest",
        **kafka_config,
    )

    add_process_start_training_data(app)
    add_process_training_model_start(app)
    add_predictions(app)

    return app
