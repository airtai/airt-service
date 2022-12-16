# AUTOGENERATED! DO NOT EDIT! File to edit: ../notebooks/API_Web_Service.ipynb.

# %% auto 0
__all__ = ['description', 'create_ws_server']

# %% ../notebooks/API_Web_Service.ipynb 2
from pathlib import Path
from typing import *

# %% ../notebooks/API_Web_Service.ipynb 3
import yaml
from os import environ

from fastapi import FastAPI, Request
from fastapi.openapi.docs import get_swagger_ui_html, get_redoc_html
from fastapi.openapi.utils import get_openapi
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

import airt_service
from .sanitizer import sanitized_print
from .auth import auth_router
from .data.datablob import datablob_router
from .data.datasource import datasource_router
from .model.train import model_train_router
from .model.prediction import model_prediction_router
from .users import user_router

# %% ../notebooks/API_Web_Service.ipynb 5
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

# %% ../notebooks/API_Web_Service.ipynb 6
def create_ws_server(assets_path: Path = Path("./assets")) -> FastAPI:
    """Create a FastAPI based web service

    Args:
        assets_path: Path to assets (should include favicon.ico)

    Returns:
        A FastAPI server
    """
    global description
    title = "airt service"
    version = airt_service.__version__
    openapi_url = "/openapi.json"
    favicon_url = "/assets/images/favicon.ico"
    assets_path = assets_path.resolve()
    favicon_path = assets_path / "images/favicon.ico"

    app = FastAPI(
        title=title,
        description=description,
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

    return app
