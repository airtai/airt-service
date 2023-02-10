# AUTOGENERATED! DO NOT EDIT! File to edit: ../../notebooks/DataSource_Router.ipynb.

# %% auto 0
__all__ = ['datasource_router', 'get_details_of_datasource', 'delete_datasource', 'datasource_head_route',
           'datasource_dtypes_route', 'get_all_datasources', 'tag_datasource']

# %% ../../notebooks/DataSource_Router.ipynb 3
from pathlib import Path
from typing import *

import dask.dataframe as dd
import pandas as pd
from airt.logger import get_logger
from airt.patching import patch
from airt.remote_path import RemotePath
from checksumdir import dirhash
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.exc import NoResultFound
from sqlmodel import Session, select

import airt_service.sanitizer

# import airt_service
from ..auth import get_current_active_user
from ..constants import DS_HEAD_FILE_NAME, METADATA_FOLDER_PATH
from .utils import delete_data_object_files_in_cloud
from airt_service.db.models import (
    DataBlob,
    DataSource,
    DataSourceRead,
    Tag,
    TagCreate,
    User,
    get_session,
)
from ..errors import ERRORS, HTTPError
from ..helpers import commit_or_rollback, df_to_dict

# %% ../../notebooks/DataSource_Router.ipynb 6
logger = get_logger(__name__)

# %% ../../notebooks/DataSource_Router.ipynb 8
# Default router for all data sources
datasource_router = APIRouter(
    prefix="/datasource",
    tags=["datasource"],
    #     dependencies=[Depends(get_current_active_user)],
    responses={
        404: {"description": "Not found"},
        500: {
            "model": HTTPError,
            "description": ERRORS["INTERNAL_SERVER_ERROR"],
        },
    },
)

# %% ../../notebooks/DataSource_Router.ipynb 9
@patch
def calculate_properties(self: DataSource, cache_path: Path):
    """Calculate properties of datasource like no of rows, dtypes, head, hash from parquet files

    Args:
        cache_path: Cache folder path containing the synced parquet files
    """
    self.hash = dirhash(cache_path, hashfunc="md5")

    ddf = dd.read_parquet(cache_path)
    self.no_of_rows = ddf.shape[0].compute()

    metadata_folder_path = cache_path / METADATA_FOLDER_PATH
    metadata_folder_path.mkdir(exist_ok=True)

    head = ddf.head(10)
    head.to_parquet(metadata_folder_path / DS_HEAD_FILE_NAME)

# %% ../../notebooks/DataSource_Router.ipynb 11
@patch
def remove_tag_from_previous_datasources(
    self: DataSource, tag_name: str, session: Session
):
    """Remove the tag_name associated with other/previous datasources

    Args:
        tag_name: Tag name to remove from other datasources
        session: Sqlmodel session
    """
    tag_to_remove = Tag.get_by_name(name=tag_name, session=session)
    try:
        datasources = session.exec(
            select(DataSource).where(
                DataSource.datablob == self.datablob,
                DataSource.user == self.user,
            )
        ).all()
    except NoResultFound:
        return

    for datasource in datasources:
        if tag_to_remove in datasource.tags:
            datasource.tags.remove(tag_to_remove)
            session.add(datasource)
            session.commit()

# %% ../../notebooks/DataSource_Router.ipynb 13
get_datasource_responses = {
    400: {"model": HTTPError, "description": ERRORS["INCORRECT_DATASOURCE_ID"]},
    422: {"model": HTTPError, "description": "DataSource error"},
}


@patch(cls_method=True)
def get(cls: DataSource, uuid: str, user: User, session: Session) -> DataSource:
    """Get datasource based on uuid

    Args:
        uuid: Datasource uuid
        user: User object
        session: Sqlmodel session

    Returns:
        Datasource object for given datasource uuid

    Raises:
        HTTPException: if datasource id is incorrect or if datasource is deleted
    """
    try:
        datasource = session.exec(
            select(DataSource).where(DataSource.uuid == uuid, DataSource.user == user)
        ).one()
    except NoResultFound:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ERRORS["INCORRECT_DATASOURCE_ID"],
        )

    if datasource.disabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ERRORS["DATASOURCE_IS_DELETED"],
        )

    if datasource.error is not None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=datasource.error
        )

    return datasource

# %% ../../notebooks/DataSource_Router.ipynb 16
@datasource_router.get(
    "/{datasource_uuid}",
    response_model=DataSourceRead,
    responses=get_datasource_responses,  # type: ignore
)
def get_details_of_datasource(
    datasource_uuid: str,
    user: User = Depends(get_current_active_user),
    session: Session = Depends(get_session),
) -> DataSource:
    """Get details of the datasource"""
    user = session.merge(user)
    datasource = DataSource.get(uuid=datasource_uuid, user=user, session=session)  # type: ignore

    return datasource

# %% ../../notebooks/DataSource_Router.ipynb 19
@patch
def delete(self: DataSource, user: User, session: Session):
    """Delete a datasource

    Args:
        user: User object
        session: Sqlmodel session
    """
    delete_data_object_files_in_cloud(data_object=self)
    self.disabled = True

    with commit_or_rollback(session):
        session.add(self)

    return self

# %% ../../notebooks/DataSource_Router.ipynb 20
@datasource_router.delete(
    "/{datasource_uuid}",
    response_model=DataSourceRead,
    responses=get_datasource_responses,  # type: ignore
)
def delete_datasource(
    datasource_uuid: str,
    user: User = Depends(get_current_active_user),
    session: Session = Depends(get_session),
) -> DataSource:
    """Delete datasource"""
    user = session.merge(user)
    datasource = DataSource.get(uuid=datasource_uuid, user=user, session=session)  # type: ignore

    return datasource.delete(user, session)

# %% ../../notebooks/DataSource_Router.ipynb 23
def _get_ds_head_and_dtypes(datasource_s3_path: str) -> Dict[str, Any]:
    """Read the head metadata file and return its contents as a dict

    Args:
        datasource_s3_path: Input datasource S3 path

    Returns:
        The head along with its dtypes as a dict
    """
    s3_metadata_path = f"{datasource_s3_path}/{METADATA_FOLDER_PATH}"

    with RemotePath.from_url(
        remote_url=s3_metadata_path,
        push_on_exit=False,
        exist_ok=True,
        parents=False,
    ) as local_metadata_path:
        processed_local_metadata_path = local_metadata_path.as_path()

        df = pd.read_parquet(processed_local_metadata_path / DS_HEAD_FILE_NAME)
        return df_to_dict(df)

# %% ../../notebooks/DataSource_Router.ipynb 25
@patch
def is_ready(self: DataSource):
    """Check if the datasource's completed steps equal to total steps, else raise HTTPException"""
    if self.completed_steps != self.total_steps:
        raise HTTPException(
            status_code=status.HTTP_412_PRECONDITION_FAILED,
            detail=ERRORS["DATASOURCE_IS_NOT_PULLED"],
        )

# %% ../../notebooks/DataSource_Router.ipynb 26
@datasource_router.get(
    "/{datasource_uuid}/head",
    responses={
        **get_datasource_responses,  # type: ignore
        412: {"model": HTTPError, "description": ERRORS["DATASOURCE_IS_NOT_PULLED"]},
    },
)
def datasource_head_route(
    datasource_uuid: str,
    user: User = Depends(get_current_active_user),
    session: Session = Depends(get_session),
) -> Dict[str, List[Any]]:
    """Get head of the datasource"""
    user = session.merge(user)
    datasource = DataSource.get(uuid=datasource_uuid, user=user, session=session)  # type: ignore
    datasource.is_ready()

    df_dict = _get_ds_head_and_dtypes(datasource_s3_path=datasource.path)
    return df_dict

# %% ../../notebooks/DataSource_Router.ipynb 29
@datasource_router.get(
    "/{datasource_uuid}/dtypes",
    responses={
        **get_datasource_responses,  # type: ignore
        412: {"model": HTTPError, "description": ERRORS["DATASOURCE_IS_NOT_PULLED"]},
    },
)
def datasource_dtypes_route(
    datasource_uuid: str,
    user: User = Depends(get_current_active_user),
    session: Session = Depends(get_session),
) -> Dict[str, str]:
    """Get columns and its dtypes of the datasource"""
    user = session.merge(user)
    # get locally saved parquet file path, read it and return columns and its dtypes
    datasource = DataSource.get(uuid=datasource_uuid, user=user, session=session)  # type: ignore
    datasource.is_ready()

    df_dict = _get_ds_head_and_dtypes(datasource_s3_path=datasource.path)
    return df_dict["dtypes"]

# %% ../../notebooks/DataSource_Router.ipynb 32
@patch(cls_method=True)
def get_all(
    cls: DataSource,
    disabled: bool,
    completed: bool,
    offset: int,
    limit: int,
    user: User,
    session: Session,
) -> List[DataSource]:
    """Get all datasources created by the user

    Args:
        disabled: Whether to get disabled datasources
        completed: Whether to include only datasources which are pulled from its source
        offset: Offset results by given integer
        limit: Limit results by given integer
        user: User object
        session: Sqlmodel session

    Returns:
        A list of datasource objects
    """
    statement = select(DataSource).where(DataSource.user == user)
    statement = statement.where(DataSource.disabled == disabled)
    if completed:
        statement = statement.where(
            DataSource.completed_steps == DataSource.total_steps
        )
    # get all data sources from db
    return session.exec(statement.offset(offset).limit(limit)).all()

# %% ../../notebooks/DataSource_Router.ipynb 33
@datasource_router.get("/", response_model=List[DataSourceRead])
def get_all_datasources(
    disabled: bool = False,
    completed: bool = False,
    offset: int = 0,
    limit: int = Query(default=100, lte=100),
    user: User = Depends(get_current_active_user),
    session: Session = Depends(get_session),
) -> List[DataSource]:
    """Get all datasources created by user"""
    user = session.merge(user)
    return DataSource.get_all(
        disabled=disabled,
        completed=completed,
        offset=offset,
        limit=limit,
        user=user,
        session=session,
    )

# %% ../../notebooks/DataSource_Router.ipynb 36
@patch
def tag(self: DataSource, tag_name: str, session: Session):
    """Tag an existing datasource

    Args:
        tag_name: A string to tag the datasource
        session: Sqlmodel session
    """

    user_tag = Tag.get_by_name(name=tag_name, session=session)

    self.remove_tag_from_previous_datasources(tag_name=user_tag.name, session=session)  # type: ignore
    self.tags.append(user_tag)

    with commit_or_rollback(session):
        session.add(self)

    return self

# %% ../../notebooks/DataSource_Router.ipynb 37
@datasource_router.post("/{datasource_uuid}/tag", response_model=DataSourceRead)
def tag_datasource(
    datasource_uuid: str,
    tag_to_create: TagCreate,
    user: User = Depends(get_current_active_user),
    session: Session = Depends(get_session),
) -> DataSource:
    """Add tag to datasource"""
    user = session.merge(user)
    datasource = DataSource.get(uuid=datasource_uuid, user=user, session=session)  # type: ignore

    return datasource.tag(tag_name=tag_to_create.name, session=session)

# %% ../../notebooks/DataSource_Router.ipynb 39
@patch(cls_method=True)
def _create(
    cls: DataSource,
    *,
    datablob: DataBlob,
    total_steps: int = 1,
    user: User,
    session: Session,
) -> DataSource:
    """Create new datasource based on given params

    Args:
        datablob: Datablob object
        total_steps: Total steps
        user: User object
        session: Sqlmodel session

    Returns:
        The created datasource object
    """
    with commit_or_rollback(session):
        datasource = DataSource(
            datablob=datablob,
            cloud_provider=datablob.cloud_provider,
            region=datablob.region,
            total_steps=total_steps,
            user=user,
        )

    for tag in datablob.tags:
        datasource.tag(tag_name=tag.name, session=session)  # type: ignore

    return datasource
