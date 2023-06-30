# AUTOGENERATED! DO NOT EDIT! File to edit: ../notebooks/Kafka_Service.ipynb.

# %% auto 0
__all__ = ['heading', 'json_datetime_sec_encoder', 'LogMessage', 'add_logging', 'ModelType', 'ModelTrainingRequest', 'EventData',
           'RealtimeData', 'TrainingDataStatus', 'TrainingModelStart', 'get_key', 'Tracker',
           'add_process_start_training_data', 'TrainingModelStatus', 'ModelMetrics', 'add_process_training_model_start',
           'Prediction', 'add_predictions', 'create_fastkafka_application']

# %% ../notebooks/Kafka_Service.ipynb 1
import asyncio
import logging
from datetime import datetime, timedelta
from enum import Enum
from os import environ
from typing import *

import numpy as np
import pandas as pd
from airt.logger import get_logger, supress_timestamps
from fastkafka import FastKafka, KafkaEvent
from pydantic import (
    BaseModel,
    EmailStr,
    Field,
    HttpUrl,
    NonNegativeInt,
    root_validator,
    validator,
)

import airt_service
from .confluent import aio_kafka_config
from airt_service.data.clickhouse import (
    get_all_person_ids_for_account_id,
    get_count_for_account_id,
)

# %% ../notebooks/Kafka_Service.ipynb 3
supress_timestamps(False)
logger = get_logger(__name__)

# %% ../notebooks/Kafka_Service.ipynb 5
def heading(title: Optional[str] = None, width: int = 160) -> None:
    print()
    print("*" * width)
    print("*" * 3 + " " * (width - 6) + "*" * 3)
    if title:
        l = int((width - 6 - len(title)) / 2)
        print("*" * 3 + " " * l + title + " " * l + "*" * 3)
        print("*" * 3 + " " * (width - 6) + "*" * 3)

# %% ../notebooks/Kafka_Service.ipynb 12
def json_datetime_sec_encoder(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%S")

# %% ../notebooks/Kafka_Service.ipynb 14
class LogMessage(BaseModel):
    """
    Info, error and warning messages
    """

    level: NonNegativeInt = Field(10, example=10, description="level of the message")
    timestamp: datetime = Field(None, description="timestamp")
    message: str = Field(..., example="something went wrong", description="message")

    original_message: Optional[BaseModel] = Field(...)

    @root_validator
    def number_validator(cls, values: Dict[str, Any]) -> Dict[str, Any]:
        if values["timestamp"] is None:
            values["timestamp"] = datetime.now()

        return values

    class Config:
        json_encoders = {
            datetime: json_datetime_sec_encoder,
        }
        validate_assignment = True

# %% ../notebooks/Kafka_Service.ipynb 17
def add_logging(
    app: FastKafka,
    *,
    username: str = "infobip",
) -> None:
    @app.produces(topic=f"{username}_logger")  # type: ignore
    async def to_logger(
        msg: LogMessage,
        key: Optional[Union[bytes, str]] = None,
        #     ) -> KafkaEvent[LogMessage]:
        #         print(f"to_logger({msg})")
        #         k = key.encode("utf-8") if isinstance(key, str) else key
        #         return KafkaEvent(message=msg, key=k)
    ) -> LogMessage:
        print(f"to_logger({msg})")
        k = key.encode("utf-8") if isinstance(key, str) else key
        return msg

    async def log(
        org_msg: BaseModel,
        msg: LogMessage,
        key: Optional[Union[bytes, str]] = None,
        *,
        level: int,
        app: FastKafka = app,
    ) -> None:
        log_msg = LogMessage(message=msg, level=10, key=key, original_message=org_msg)
        await app.to_logger(log_msg)
        logger.info(f"{msg} while processing {org_msg}.")

    async def info(
        org_msg: BaseModel,
        msg: LogMessage,
        key: Optional[Union[bytes, str]] = None,
        *,
        app: FastKafka = app,
    ) -> None:
        await app.log(org_msg, msg=msg, key=key, level=10)

    async def warning(
        org_msg: BaseModel,
        msg: LogMessage,
        key: Optional[Union[bytes, str]] = None,
        *,
        app: FastKafka = app,
    ) -> None:
        await app.log(org_msg, msg=msg, key=key, level=20)

    async def error(
        org_msg: BaseModel,
        msg: LogMessage,
        key: Optional[Union[bytes, str]] = None,
        *,
        app: FastKafka = app,
    ) -> None:
        await app.log(org_msg, msg=msg, key=key, level=30)

    #     app.to_logger = to_logger
    app.log = log
    app.info = info
    app.warning = warning
    app.error = error

# %% ../notebooks/Kafka_Service.ipynb 19
class ModelType(str, Enum):
    churn = "churn"
    propensity_to_buy = "propensity_to_buy"


class ModelTrainingRequest(BaseModel):
    AccountId: NonNegativeInt = Field(
        ..., example=202020, description="ID of an account"
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

# %% ../notebooks/Kafka_Service.ipynb 21
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

# %% ../notebooks/Kafka_Service.ipynb 23
class TrainingDataStatus(BaseModel):
    AccountId: NonNegativeInt = Field(
        ..., example=202020, description="ID of an account"
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

# %% ../notebooks/Kafka_Service.ipynb 25
class TrainingModelStart(BaseModel):
    AccountId: NonNegativeInt = Field(
        ..., example=202020, description="ID of an account"
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

# %% ../notebooks/Kafka_Service.ipynb 27
def get_key(msg: BaseModel, attrs: Optional[List[str]] = None) -> bytes:
    if attrs is None:
        attrs = ["AccountId", "ModelId"]

    sx = [
        f"{attr}='{getattr(msg, attr)}'" if hasattr(msg, attr) else "" for attr in attrs
    ]

    return ", ".join(sx).encode("utf-8")

# %% ../notebooks/Kafka_Service.ipynb 30
class Tracker:
    def __init__(self, *, limit: int, timeout: int, abort_after: int):
        self._limit = limit
        self._timeout = timeout
        self._abort_after = abort_after
        self._count: Optional[int] = None
        self._last_updated: Optional[datetime] = None
        self._sterted_at: datetime = datetime.now()

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
            return self.aborted()

    def aborted(self) -> bool:
        return self._count is None and (datetime.now() - self._sterted_at) > timedelta(
            seconds=self._abort_after
        )

# %% ../notebooks/Kafka_Service.ipynb 34
def add_process_start_training_data(
    app: FastKafka,
    *,
    username: str = "infobip",
    stop_on_no_change_interval: int = 60,
    abort_on_no_change_interval: int = 120,
    sleep_interval: int = 5,
) -> None:
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

    #     app.to_training_data_status = to_training_data_status
    #     app.to_training_model_start = to_training_model_start

    @app.consumes(topic=f"{username}_start_training_data")  # type: ignore
    async def on_start_training_data(
        msg: ModelTrainingRequest, app: FastKafka = app
    ) -> None:
        await app.info(msg, f"on_start_training_data() starting...")

        account_id = msg.AccountId
        model_id = msg.ModelId
        total_no_of_records = msg.total_no_of_records

        tracker = Tracker(
            limit=total_no_of_records,
            timeout=stop_on_no_change_interval,
            abort_after=abort_on_no_change_interval,
        )

        while not tracker.finished():
            curr_count, timestamp = get_count_for_account_id(
                account_id=account_id,
                model_id=model_id,
            )
            if curr_count is not None:
                if tracker.update(curr_count):
                    training_data_status = TrainingDataStatus(
                        no_of_records=curr_count, **msg.dict()
                    )
                    await app.to_training_data_status(training_data_status)
            else:
                await app.warning(
                    msg,
                    f"on_start_training_data(): no data yet received in the database.",
                )

            await asyncio.sleep(sleep_interval)

        if tracker.aborted():
            await app.error(msg, f"on_start_training_data(): data retrieval aborted!")
        else:
            # trigger model training start
            training_model_start = TrainingModelStart(
                no_of_records=curr_count, **msg.dict()
            )
            await app.to_training_model_start(training_model_start)

            await app.info(msg, f"on_start_training_data(): finished")

# %% ../notebooks/Kafka_Service.ipynb 36
class TrainingModelStatus(BaseModel):
    AccountId: NonNegativeInt = Field(
        ..., example=202020, description="ID of an account"
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

# %% ../notebooks/Kafka_Service.ipynb 38
class ModelMetrics(BaseModel):
    """The standard metrics for classification models.

    The most important metrics is AUC for unbalanced classes such as churn. Metrics such as
    accuracy are not very useful since they are easily maximized by outputting the most common
    class all the time.
    """

    AccountId: NonNegativeInt = Field(
        ..., example=202020, description="ID of an account"
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

# %% ../notebooks/Kafka_Service.ipynb 40
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

    #     app.to_training_model_status = to_training_model_status
    #     app.to_model_metrics = to_model_metrics

    @app.consumes(topic=f"{username}_training_model_start")  # type: ignore
    async def on_training_model_start(
        msg: TrainingModelStart, app: FastKafka = app
    ) -> None:
        await app.info(msg, f"on_training_model_start() starting")

        AccountId = msg.AccountId
        ModelId = msg.ModelId
        model_type = msg.model_type

        for current_step in range(total_no_of_steps):
            for current_step_percentage in [0.0, 0.2, 0.5, 0.75, 1.0]:
                training_model_status = TrainingModelStatus(
                    AccountId=AccountId,
                    ModelId=ModelId,
                    current_step=current_step,
                    current_step_percentage=current_step_percentage,
                    total_no_of_steps=total_no_of_steps,
                )
                await app.to_training_model_status(training_model_status)

                await asyncio.sleep(substep_interval)

        model_metrics = ModelMetrics(
            AccountId=AccountId,
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

        await app.info(msg, f"on_training_model_start() finished")

# %% ../notebooks/Kafka_Service.ipynb 42
class Prediction(BaseModel):
    AccountId: NonNegativeInt = Field(
        ..., example=202020, description="ID of an account"
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

# %% ../notebooks/Kafka_Service.ipynb 44
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
    async def on_model_metrics(msg: ModelMetrics, app: FastKafka = app) -> None:
        await app.info(msg, "on_model_metrics() starting")

        AccountId = msg.AccountId
        ModelId = msg.ModelId
        model_type = msg.model_type
        prediction_time = datetime.now()

        person_ids = get_all_person_ids_for_account_id(
            account_id=AccountId, model_id=ModelId
        )

        rng = np.random.default_rng(42)

        await app.info(msg, f"Sending predictions for {len(person_ids):,d} PersonIds")
        t0 = datetime.now()
        for PersonId in person_ids:
            prediction = Prediction(
                AccountId=AccountId,
                ModelId=ModelId,
                model_type=model_type,
                prediction_time=prediction_time,
                PersonId=PersonId,
                score=rng.uniform(),
            )
            await to_prediction(prediction)
        await app.info(
            msg,
            f"Sending predictions for {len(person_ids):,d} PersonIds finished in {datetime.now()-t0}.",
        )

        await app.info(msg, "on_model_metrics() finished")

# %% ../notebooks/Kafka_Service.ipynb 46
def _construct_kafka_brokers() -> Dict[str, Dict[str, Any]]:
    url = aio_kafka_config["bootstrap_servers"].split(":")[0]
    port = aio_kafka_config["bootstrap_servers"].split(":")[-1]

    kafka_brokers = {
        "staging": {
            "url": "kafka.staging.airt.ai",
            "description": "Staging Kafka broker",
            "port": 9092,
            "protocol": "kafka-secure",
            "security": {"type": "scramSha256"},
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
        kafka_brokers["localhost"] = {
            "url": url,
            "description": "Development Kafka broker",
            "port": port,
        }

    return kafka_brokers

# %% ../notebooks/Kafka_Service.ipynb 48
def create_fastkafka_application(
    start_process_for_username: Optional[str] = "infobip",
    *,
    use_logging: bool = True,
    # temporarely removed from the processor => we'll do training and predictions locally
    use_process_start_training_data: bool = True,
    use_process_training_model_start: bool = False,
    use_predictions: bool = False,
    **kwargs: Any,
) -> FastKafka:
    """Create a FastKafka service

    Arg
        start_process_for_username: prefix for topics used

    Returns:
        A FastKafka application
    """

    kafka_brokers = _construct_kafka_brokers()

    # TODO: why is this here?
    exclude_keys = ["bootstrap_servers"]
    kafka_config = {
        k: aio_kafka_config[k]
        for k in set(list(aio_kafka_config.keys())) - set(exclude_keys)
    }
    for k, v in kwargs.items():
        kafka_config[k] = v

    logger.info(f"create_fastkafka_application(): {kafka_config=}")

    # global description
    version = airt_service.__version__
    contact = dict(name="airt.ai", url="https://airt.ai", email="info@airt.ai")

    app = FastKafka(
        title="airt service kafka api",
        description="kafka api for airt service",
        kafka_brokers=kafka_brokers,
        version=version,
        contact=contact,
        enable_idempotence=True,
        request_timeout_ms=120_000,
        max_batch_size=120_000,
        connections_max_idle_ms=10_000,
        #         auto_offset_reset="earliest",
        **kafka_config,
    )

    if use_logging:
        add_logging(app)

    if use_process_start_training_data:
        add_process_start_training_data(app)
    if use_process_training_model_start:
        add_process_training_model_start(app)
    if use_predictions:
        add_predictions(app)

    return app
