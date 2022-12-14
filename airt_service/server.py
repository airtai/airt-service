# AUTOGENERATED! DO NOT EDIT! File to edit: ../notebooks/API_Web_Service.ipynb.

# %% auto 0
__all__ = ['description', 'ModelType', 'ModelTrainingRequest', 'EventData', 'RealtimeData', 'TrainingDataStatus',
           'TrainingModelStatus', 'ModelMetrics', 'Prediction', 'create_ws_server']

# %% ../notebooks/API_Web_Service.ipynb 2
from pathlib import Path
from typing import *

# %% ../notebooks/API_Web_Service.ipynb 3
import yaml
from datetime import datetime
from enum import Enum
from os import environ

from aiokafka.helpers import create_ssl_context
from fastapi import Request
from fastapi.openapi.docs import get_swagger_ui_html, get_redoc_html
from fastapi.openapi.utils import get_openapi
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fast_kafka_api.application import FastKafkaAPI
from pydantic import validator, BaseModel, Field, HttpUrl, EmailStr, NonNegativeInt

import airt_service
from .sanitizer import sanitized_print
from .auth import auth_router
from .confluent import aio_kafka_config
from .data.datablob import datablob_router
from .data.datasource import datasource_router
from .model.train import model_train_router
from .model.prediction import model_prediction_router
from .users import user_router
from airt.logger import get_logger

# %% ../notebooks/API_Web_Service.ipynb 5
logger = get_logger(__name__)

# %% ../notebooks/API_Web_Service.ipynb 6
description = """
# airt service to import, train and predict events data

## Python client

To use python library please visit: <a href="https://docs.airt.ai" target="_blank">https://docs.airt.ai</a>

## How to use

To access the airt service, you must create a developer account. Please fill out the signup form below to get one:

[https://bit.ly/3hbXQLY](https://bit.ly/3hbXQLY)

Upon successful verification, you will receive the username and password for the developer account to your email.

### 0. Authenticate

Once you receive the username and password, please authenticate the same by calling the `/token` API. The API 
will return a bearer token if the authentication is successful.

```console
curl -X 'POST' \
  'https://api.airt.ai/token' \
  -H 'accept: application/json' \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  -d 'grant_type=&username=<username>&password=<password>&scope=&client_id=&client_secret='
```

You can either use the above bearer token or create additional apikey's for accessing the rest of the API's. 

To create additional apikey's, please call the `/apikey` API by passing the bearer token along with the 
details of the new apikey in the request. e.g:

```console
curl -X 'POST' \
  'https://api.airt.ai/apikey' \
  -H 'accept: application/json' \
  -H 'Authorization: Bearer <bearer_token>' \
  -H 'Content-Type: application/json' \
  -d '{
  "name": "<apikey_name>",
  "expiry": "<datetime_in_ISO_8601_format>"
}'
```

### 1. Connect data

Establishing the connection with the data source is a two-step process. The first step allows 
you to pull the data into airt servers and the second step allows you to perform necessary data 
pre-processing that are required model training.

Currently, we support importing data from:

- files stored in the AWS S3 bucket,
- databases like MySql, ClickHouse, and 
- local CSV/Parquet files,

We plan to support other databases and storage medium in the future.

To pull the data from a S3 bucket, please call the `/from_s3` API

```console
curl -X 'POST' \
  'https://api.airt.ai/datablob/from_s3' \
  -H 'accept: application/json' \
  -H 'Authorization: Bearer <bearer_token>' \
  -H 'Content-Type: application/json' \
  -d '{
  "uri": "s3://bucket/folder",
  "access_key": "<access_key>",
  "secret_key": "<secret_key>",
  "tag": "<tag_name>"
}'
```

Calling the above API will start importing the data in the background. This may take a while to complete depending on the size of the data.

You can also check the data importing progress by calling the `/datablob/<datablob_id>` API

```console
curl -X 'GET' \
  'https://api.airt.ai/datablob/<datablob_id>' \
  -H 'accept: application/json' \
  -H 'Authorization: Bearer <bearer_token>'
```

Once the data import is completed, you can either call `/from_csv` or `/from_parquet` API for data pre-processing. Below is an 
example to pre-process an imported CSV data.

```
curl -X 'POST' \
'https://api.airt.ai/datablob/<datablob_id>/from_csv' \
-H 'accept: application/json' \
-H 'Authorization: Bearer <bearer_token>' \
-H 'Content-Type: application/json' \
-d '{
  "deduplicate_data": <deduplicate_data>,
  "index_column": "<index_column>",
  "sort_by": "<sort_by>",
  "blocksize": "<block_size>",
  "kwargs": {}
}'
```

### 2. Train

For model training, we assume the input data includes the following:

- a column identifying a client client_column (person, car, business, etc.),
- a column specifying a type of event we will try to predict target_column (buy, checkout, click on form submit, etc.), and
- a timestamp column specifying the time of an occurred event.

The input data can have additional features of any type and will be used to make predictions more accurate. Finally, we need to 
know how much ahead we wish to make predictions. Please use the parameter predict_after to specify the period based on your needs.

In the following example, we will train a model to predict which users will perform a purchase event (*purchase) 3 hours before they acctually do it:

```console
curl -X 'POST' \
  'https://api.airt.ai/model/train' \
  -H 'accept: application/json' \
  -H 'Authorization: Bearer <bearer_token>' \
  -H 'Content-Type: application/json' \
  -d '{
  "data_id": <datasource_id>,
  "client_column": "<client_column>",
  "target_column": "<target_column>",
  "target": "*checkout",
  "predict_after": 10800
}'
```

Calling the above API will start the model training in the background. This may take a while to complete and you can check the 
training progress by calling the `/model/<model_id>` API.

```console
curl -X 'GET' \
  'https://api.airt.ai/model/<model_id>' \
  -H 'accept: application/json' \
  -H 'Authorization: Bearer <bearer_token>'
```

After training is complete, you can check the quality of the model by calling the `/model/<model_id>/evaluate` API. This API 
will return model validation metrics like model accuracy, precision and recall.

```console
curl -X 'GET' \
  'https://api.airt.ai/model/<model_id>/evaluate' \
  -H 'accept: application/json' \
  -H 'Authorization: Bearer <bearer_token>'
```

### 3. Predict

Finally, you can run the predictions by calling the /model/<model_id>/predict API:

```console
curl -X 'POST' \
  'https://api.airt.ai/model/<model_id>/predict' \
  -H 'accept: application/json' \
  -H 'Authorization: Bearer <bearer_token>' \
  -H 'Content-Type: application/json' \
  -d '{
  "data_id": <datasource_id>
}'
```
Calling the above API will start running the model prediction in the background. This may take a while to complete and you can check the training progress by calling the /prediction/<prediction_id> API.

```console
curl -X 'GET' \
  'https://api.airt.ai/prediction/<prediction_id>' \
  -H 'accept: application/json' \
  -H 'Authorization: Bearer <bearer_token>'
```

If the dataset is small, then you can call `/prediction/<prediction_id>/pandas` to get prediction results as a pandas dataframe convertible json format:

```console
curl -X 'GET' \
  'https://api.airt.ai/prediction/<prediction_id>/pandas' \
  -H 'accept: application/json' \
  -H 'Authorization: Bearer <bearer_token>'
```

In many cases, it's much better to push the prediction results to remote destinations. Currently, we support pushing the prediction results to a AWS S3 bucket, MySql database and download to the local machine.

To push the predictions to a S3 bucket, please call the `/prediction/<prediction_id>/to_s3` API

```
curl -X 'POST' \
  'https://api.airt.ai/prediction/<prediction_id>/to_s3' \
  -H 'accept: application/json' \
  -H 'Content-Type: application/json' \
  -d '{
  "uri": "s3://bucket/folder", 
  "access_key": "<access_key>", 
  "secret_key": "<secret_key>",
  }'
```

"""

# %% ../notebooks/API_Web_Service.ipynb 7
class ModelType(str, Enum):
    churn = "churn"
    propensity_to_buy = "propensity_to_buy"


class ModelTrainingRequest(BaseModel):
    AccountId: NonNegativeInt = Field(
        ..., example=202020, description="ID of an account"
    )
    ModelName: ModelType = Field(..., example="churn", description="ID of an account")
    total_no_of_records: NonNegativeInt = Field(
        ...,
        example=1_000_000,
        description="total number of records (rows) to be ingested",
    )


class EventData(BaseModel):
    """
    A sequence of events for a fixed account_id
    """

    AccountId: NonNegativeInt = Field(
        ..., example=202020, description="ID of an account"
    )
    Application: Optional[str] = Field(
        None,
        example="DriverApp",
        description="Name of the application in case there is more than one for the AccountId",
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


class RealtimeData(BaseModel):
    event_data: EventData = Field(
        ...,
        example=dict(
            AccountId=202020,
            Application="DriverApp",
            DefinitionId="appLaunch",
            OccurredTime="2021-03-28T00:34:08",
            OccurredTimeTicks=1616891648496,
            PersonId=12345678,
        ),
        description="realtime event data",
    )
    make_prediction: bool = Field(
        ..., example=True, description="trigger prediction message in prediction topic"
    )


class TrainingDataStatus(BaseModel):
    AccountId: NonNegativeInt = Field(
        ..., example=202020, description="ID of an account"
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


class TrainingModelStatus(BaseModel):
    AccountId: NonNegativeInt = Field(
        ..., example=202020, description="ID of an account"
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
        example=1_000_000,
        description="total number of steps for training the model",
    )


class ModelMetrics(BaseModel):
    """The standard metrics for classification models.

    The most important metrics is AUC for unbalanced classes such as churn. Metrics such as
    accuracy are not very useful since they are easily maximized by outputting the most common
    class all the time.
    """

    AccountId: NonNegativeInt = Field(
        ..., example=202020, description="ID of an account"
    )
    Application: Optional[str] = Field(
        None,
        example="DriverApp",
        description="Name of the application in case there is more than one for the AccountId",
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


class Prediction(BaseModel):
    AccountId: NonNegativeInt = Field(
        ..., example=202020, description="ID of an account"
    )
    Application: Optional[str] = Field(
        None,
        example="DriverApp",
        description="Name of the application in case there is more than one for the AccountId",
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

# %% ../notebooks/API_Web_Service.ipynb 8
_total_no_of_records = 0
_no_of_records_received = 0

# %% ../notebooks/API_Web_Service.ipynb 9
def create_ws_server(assets_path: Path = Path("./assets")) -> FastKafkaAPI:
    """Create a FastKafkaAPI based web service

    Args:
        assets_path: Path to assets (should include favicon.ico)

    Returns:
        A FastKafkaAPI server
    """
    global description
    title = "airt service"
    version = airt_service.__version__
    openapi_url = "/openapi.json"
    favicon_url = "/assets/images/favicon.ico"
    assets_path = assets_path.resolve()
    favicon_path = assets_path / "images/favicon.ico"

    kafka_brokers = {
        "localhost": {
            "url": "kafka",
            "description": "local development kafka",
            "port": 9092,
        },
        "staging": {
            "url": "kafka.staging.airt.ai",
            "description": "staging kafka",
            "port": 9092,
            "protocol": "kafka-secure",
            "security": {"type": "plain"},
        },
        "production": {
            "url": "kafka.airt.ai",
            "description": "production kafka",
            "port": 9092,
            "protocol": "kafka-secure",
            "security": {"type": "plain"},
        },
    }

    logger.info(f"kafka_config={aio_kafka_config}")
    app = FastKafkaAPI(
        title=title,
        description=description,
        kafka_brokers=kafka_brokers,
        kafka_config=aio_kafka_config,
        version=version,
        docs_url=None,
        redoc_url=None,
    )
    app.mount("/assets", StaticFiles(directory=assets_path), name="assets")  # type: ignore

    # attaches /token to routes
    app.include_router(auth_router)

    # attaches /datablob/* to routes
    app.include_router(datablob_router)

    # attaches /datasource/* to routes
    app.include_router(datasource_router)

    # attaches /model/* to routes
    app.include_router(model_train_router)

    # attaches /prediction/* to routes
    app.include_router(model_prediction_router)

    # attaches /user/* to routes
    app.include_router(user_router)

    @app.middleware("http")
    async def add_nosniff_x_content_type_options_header(request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Strict-Transport-Security"] = "max-age=31536000"
        return response

    @app.get("/version")
    def get_versions():
        return {"airt_service": airt_service.__version__}

    #     @app.get("/", include_in_schema=False)
    #     def redirect_root():
    #         return RedirectResponse("/docs")

    @app.get("/docs", include_in_schema=False)
    def overridden_swagger():
        return get_swagger_ui_html(
            openapi_url=openapi_url,
            title=title,
            swagger_favicon_url=favicon_url,
        )

    @app.get("/redoc", include_in_schema=False)
    def overridden_redoc():
        return get_redoc_html(
            openapi_url=openapi_url,
            title=title,
            redoc_favicon_url=favicon_url,
        )

    @app.get("/favicon.ico", include_in_schema=False)
    async def serve_favicon():
        return FileResponse(favicon_path)

    def custom_openapi():
        if app.openapi_schema:
            return app.openapi_schema

        fastapi_schema = get_openapi(
            title=title,
            description=description,
            version=version,
            routes=app.routes,
        )

        # ToDo: Figure out recursive dict merge
        fastapi_schema["servers"] = [
            {
                "url": "http://0.0.0.0:6006"
                if (
                    environ["DOMAIN"] == "localhost"
                    or "airt-service" in environ["DOMAIN"]
                )
                else f"https://{environ['DOMAIN']}",
                "description": "Server",
            },
        ]

        app.openapi_schema = fastapi_schema
        return app.openapi_schema

    app.openapi = custom_openapi  # type: ignore

    aiokafka_kwargs = dict()
    if "KAFKA_API_KEY" in environ:
        aiokafka_kwargs["security_protocol"] = aio_kafka_config["security_protocol"]
        aiokafka_kwargs["sasl_mechanism"] = aio_kafka_config["sasl_mechanisms"]
        aiokafka_kwargs["sasl_plain_username"] = aio_kafka_config["sasl_username"]
        aiokafka_kwargs["sasl_plain_password"] = aio_kafka_config["sasl_password"]
        aiokafka_kwargs["ssl_context"] = create_ssl_context()

    @app.consumes(**aiokafka_kwargs)  # type: ignore
    async def on_infobip_training_data(msg: EventData):
        # ToDo: this is not showing up in logs
        logger.debug(f"msg={msg}")
        global _total_no_of_records
        global _no_of_records_received
        _no_of_records_received = _no_of_records_received + 1

        if _no_of_records_received % 100 == 0:
            training_data_status = TrainingDataStatus(
                AccountId=EventData.AccountId,
                no_of_records=_no_of_records_received,
                total_no_of_records=_total_no_of_records,
            )
            app.produce("infobip_training_data_status", training_data_status)

    @app.consumes(**aiokafka_kwargs)  # type: ignore
    async def on_infobip_realtime_data(msg: RealtimeData):
        pass

    @app.produces(**aiokafka_kwargs)  # type: ignore
    def to_infobip_training_data_status(msg: TrainingDataStatus) -> TrainingDataStatus:
        logger.debug(f"on_infobip_training_data_status(msg={msg})")
        return msg

    @app.produces(**aiokafka_kwargs)  # type: ignore
    def to_infobip_training_model_status(msg: str) -> TrainingModelStatus:
        logger.debug(f"on_infobip_training_model_status(msg={msg})")
        return TrainingModelStatus()

    @app.produces(**aiokafka_kwargs)  # type: ignore
    def to_infobip_model_metrics(msg: ModelMetrics) -> ModelMetrics:
        logger.debug(f"on_infobip_training_model_status(msg={msg})")
        return msg

    @app.produces(**aiokafka_kwargs)  # type: ignore
    def to_infobip_prediction(msg: Prediction) -> Prediction:
        logger.debug(f"on_infobip_realtime_data_status(msg={msg})")
        return msg

    return app
