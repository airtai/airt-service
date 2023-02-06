# AUTOGENERATED! DO NOT EDIT! File to edit: ../../notebooks/DataBlob_Clickhouse.ipynb.

# %% auto 0
__all__ = ['create_db_uri_for_clickhouse_datablob', 'get_clickhouse_connection', 'get_max_timestamp',
           'partition_index_value_counts_into_chunks', 'clickhouse_pull', 'clickhouse_push', 'get_count',
           'get_count_for_account_ids']

# %% ../../notebooks/DataBlob_Clickhouse.ipynb 3
import json
import re
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import *
from urllib.parse import quote_plus as urlquote
from urllib.parse import unquote_plus as urlunquote

import pandas as pd
from airt.engine.engine import get_default_engine, using_cluster
from airt.helpers import ensure
from airt.logger import get_logger
from airt.remote_path import RemotePath
from fastcore.script import Param, call_parse
from pandas.api.types import is_datetime64_any_dtype
from sqlalchemy import MetaData, Table, and_, column, create_engine, select

# from sqlmodel import create_engine, select, column, Table, MetaData, and_
from sqlalchemy.engine import Connection
from sqlalchemy.orm import sessionmaker
from sqlalchemy.sql.expression import func

import airt_service.sanitizer
from ..aws.utils import create_s3_datablob_path
from ..azure.utils import create_azure_blob_storage_datablob_path
from airt_service.data.utils import (
    calculate_data_object_folder_size_and_path,
    calculate_data_object_pulled_on,
)
from ..db.models import DataBlob, PredictionPush, get_session_with_context
from ..helpers import truncate, validate_user_inputs

# %% ../../notebooks/DataBlob_Clickhouse.ipynb 6
logger = get_logger(__name__)

# %% ../../notebooks/DataBlob_Clickhouse.ipynb 7
def _create_clickhouse_connection_string(
    username: str,
    password: str,
    host: str,
    port: int,
    database: str,
    protocol: str,
) -> str:
    # Double quoting is needed to fix a problem with special character '?' in password
    quoted_password = urlquote(urlquote(password))
    conn_str = (
        f"clickhouse+{protocol}://{username}:{quoted_password}@{host}:{port}/{database}"
    )

    return conn_str

# %% ../../notebooks/DataBlob_Clickhouse.ipynb 9
def create_db_uri_for_clickhouse_datablob(
    username: str,
    password: str,
    host: str,
    port: int,
    table: str,
    database: str,
    protocol: str,
) -> str:
    """Create uri for clickhouse datablob based on connection params

    Args:
        username: Username of clickhouse database
        password: Password of clickhouse database
        host: Host of clickhouse database
        port: Port of clickhouse database
        table: Table of clickhouse database
        database: Database to use
        protocol: Protocol to connect to clickhouse (native/http)

    Returns:
        An uri for the clickhouse datablob
    """
    clickhouse_uri = _create_clickhouse_connection_string(
        username=username,
        password=password,
        host=host,
        port=port,
        database=database,
        protocol=protocol,
    )
    clickhouse_uri = f"{clickhouse_uri}/{table}"
    return clickhouse_uri

# %% ../../notebooks/DataBlob_Clickhouse.ipynb 11
def _get_clickhouse_connection_params_from_db_uri(
    db_uri: str,
) -> Tuple[str, str, str, int, str, str, str, str]:
    """
    Function to get clickhouse connection params from db_uri of the db datablob

    Args:
        db_uri: DB uri of db datablob
    Returns:
        The username, password, host, port, table, database, protocol, database_server of the db datablob as a tuple
    """
    result = re.search("(.*)\+(.*):\/\/(.*):(.*)@(.*):(.*)\/(.*)\/(.*)", db_uri)
    database_server = result.group(1)  # type: ignore
    protocol = result.group(2)  # type: ignore
    username = result.group(3)  # type: ignore
    password = urlunquote(urlunquote(result.group(4)))  # type: ignore
    host = result.group(5)  # type: ignore
    port = int(result.group(6))  # type: ignore
    database = result.group(7)  # type: ignore
    table = result.group(8)  # type: ignore
    return username, password, host, port, table, database, protocol, database_server

# %% ../../notebooks/DataBlob_Clickhouse.ipynb 14
@contextmanager  # type: ignore
def get_clickhouse_connection(  # type: ignore
    *,
    username: str,
    password: str,
    host: str,
    port: int,
    database: str,
    table: str,
    protocol: str,
    #     verbose: bool = False,
) -> Connection:
    if protocol != "native":
        raise ValueError()
    conn_str = _create_clickhouse_connection_string(
        username=username,
        password=password,
        host=host,
        port=port,
        database=database,
        protocol=protocol,
    )

    db_engine = create_engine(conn_str)
    # args, kwargs = db_engine.dialect.create_connect_args(db_engine.url)
    with db_engine.connect() as connection:
        logger.info(f"Connected to database using {db_engine}")
        yield connection

# %% ../../notebooks/DataBlob_Clickhouse.ipynb 16
def get_max_timestamp(
    timestamp_column: str,
    connection: Connection,
    table,
    verbose: bool = False,
) -> int:
    engine = connection.engine

    # create a Session
    Session = sessionmaker(bind=engine)
    session = Session()

    metadata = MetaData(bind=None)
    sql_table = Table(table, metadata, autoload=True, autoload_with=engine)

    query = func.max(sql_table.columns[timestamp_column])
    #     logger.info(f"query='{query}'")

    result = session.query(query).scalar()
    return result

# %% ../../notebooks/DataBlob_Clickhouse.ipynb 18
def _construct_filter_query(filters: Optional[Dict[str, str]] = None) -> str:
    filter_query = ""
    if filters:
        for column, value in filters.items():
            filter_query = filter_query + f" AND {column}={value}"
    return filter_query

# %% ../../notebooks/DataBlob_Clickhouse.ipynb 20
def _get_value_counts_for_index_column(
    index_column: str,
    timestamp_column: str,
    filters: Optional[Dict[str, str]] = None,
    *,
    connection: Connection,
    table: str,
    max_timestamp: int,
) -> pd.DataFrame:
    """Queries the database and returns a number of events for each person_id"""
    query = f"SELECT {index_column}, COUNT(*) AS `count` FROM {table} where {timestamp_column}<={max_timestamp}"
    query = query + _construct_filter_query(filters)
    query = query + f" GROUP BY {index_column} ORDER BY {index_column}"

    logger.info(
        f"Querying database to get unique person_ids and its number of events - {query=}"
    )
    df = pd.read_sql(sql=query, con=connection)
    return df

# %% ../../notebooks/DataBlob_Clickhouse.ipynb 22
def partition_index_value_counts_into_chunks(
    index_column: str,
    index_value_counts: pd.DataFrame,
    db_download_size: int,
) -> pd.DataFrame:
    """Partition index value counts into chunks with size less than db_download_size, unless a single index has more than db_download_size events"""
    logger.info("Partitioning index ids into chunks...")
    partitions: Dict[str, List[int]] = {
        "index_id_start": [],
        "index_id_end": [],
        "count": [],
    }

    for index, row in index_value_counts.iterrows():
        index_id = row[index_column]
        count = row["count"]
        if not partitions["count"]:
            partitions["index_id_start"].append(index_id)
            partitions["count"].append(0)

        if (partitions["count"][-1] + count) <= db_download_size:
            partitions["count"][-1] = partitions["count"][-1] + count
        else:
            partitions["index_id_end"].append(index_id)
            partitions["index_id_start"].append(index_id)
            partitions["count"].append(count)
    partitions["index_id_end"].append(index_id + 1)
    logger.info("Partitioning finished")
    return pd.DataFrame(partitions)

# %% ../../notebooks/DataBlob_Clickhouse.ipynb 24
def _download_from_clickhouse(
    *,
    host: str,
    port: int,
    username: str,
    password: str,
    database: str,
    protocol: str,
    table: str,
    chunksize: Optional[int] = 1_000_000,
    index_column: str,
    timestamp_column: str,
    filters: Optional[Dict[str, str]] = None,
    output_path: Path,
    db_download_size=50_000_000,
):
    """Downloads data from database and stores it as parquet files in output path

    Args:
        host: Host of db
        port: Port of db
        username: Username of db
        password: Password of db
        database: Database to use in db
        database_server: Server/engine of db
        table: Table to use in db
        chunksize: Chunksize to download as
        index_column: Column to use to partition rows and to use as index
        timestamp_column: Timestamp column
        filters: Additional column filters
        output_path: Path to store parquet files
        db_download_size: Number of rows to include in single partition
    """

    with get_clickhouse_connection(  # type: ignore
        username=username,
        password=password,
        host=host,
        port=port,
        database=database,
        table=table,
        protocol=protocol,
    ) as connection:
        max_timestamp = get_max_timestamp(
            timestamp_column=timestamp_column,
            connection=connection,
            table=table,
        )
        index_value_counts = _get_value_counts_for_index_column(
            index_column=index_column,
            timestamp_column=timestamp_column,
            filters=filters,
            connection=connection,
            table=table,
            max_timestamp=max_timestamp,
        )
        partitions = partition_index_value_counts_into_chunks(
            index_column=index_column,
            index_value_counts=index_value_counts,
            db_download_size=db_download_size,
        )
        logger.info(
            f"{partitions.shape[0]} chunk(s) of ~{db_download_size} rows each found"
        )

        with tempfile.TemporaryDirectory() as td:
            d = Path(td)
            i = 0
            for index, chunk in partitions.iterrows():
                index_id_start = chunk["index_id_start"]
                index_id_end = chunk["index_id_end"]

                # User input is validated for SQL code injection
                validate_user_inputs([table, timestamp_column, index_column])

                query = f"SELECT * FROM {table} FINAL WHERE {timestamp_column}<={max_timestamp} AND {index_column}>={index_id_start} AND {index_column}<{index_id_end}"  # nosec B608
                query = query + _construct_filter_query(filters)
                query = query + f" ORDER BY {index_column}, {timestamp_column}"
                logger.info(f"{query=}")

                for df in pd.read_sql(sql=query, con=connection, chunksize=chunksize):
                    fname = d / f"clickhouse_data_{i:09d}.parquet"
                    logger.info(
                        f"Writing data retrieved from the database to temporary file {fname}"
                    )
                    df.to_parquet(fname, engine="pyarrow")  # type: ignore
                    i = i + 1

            engine = get_default_engine()
            logger.info(
                f"Rewriting temporary parquet files from {d / f'clickhouse_data_*.parquet'} to output directory {output_path}"
            )
            ddf = engine.dd.read_parquet(
                d,
                blocksize=None,
            )
            ddf.to_parquet(output_path, engine="pyarrow")

# %% ../../notebooks/DataBlob_Clickhouse.ipynb 26
@call_parse
def clickhouse_pull(
    datablob_id: Param("id of datablob in db", int),  # type: ignore
    index_column: Param("column to use to partition rows and to use as index", str),  # type: ignore
    timestamp_column: Param("timestamp column", str),  # type: ignore
    filters_json: Param(  # type: ignore
        "additional column filters as json string key, value pairs", str
    ) = "{}",
):
    """Pull datablob from a clickhouse database and update progress in the internal database

    Args:
        datablob_id: Id of datablob in db
        index_column: Column to use to partition the rows and to use as the index
        timestamp_column: Timestamp column name
        filters_json: Additional column filters as json string

    Example:
        The following code executes a CLI command:
        ```clickhouse_pull 1 PersonId OccurredTimeTicks {"AccountId":312571}
        ```
    """
    with get_session_with_context() as session:
        datablob = session.exec(
            select(DataBlob).where(DataBlob.id == datablob_id)
        ).one()[0]

        datablob.error = None
        datablob.completed_steps = 0
        datablob.folder_size = None
        datablob.path = None

        (
            username,
            password,
            host,
            port,
            table,
            database,
            protocol,
            database_server,
        ) = _get_clickhouse_connection_params_from_db_uri(datablob.uri)

        try:
            if datablob.cloud_provider == "aws":
                destination_bucket, s3_path = create_s3_datablob_path(
                    user_id=datablob.user.id,
                    datablob_id=datablob.id,
                    region=datablob.region,
                )
                destination_remote_url = f"s3://{destination_bucket.name}/{s3_path}"
            elif datablob.cloud_provider == "azure":
                (
                    destination_container_client,
                    destination_azure_blob_storage_path,
                ) = create_azure_blob_storage_datablob_path(
                    user_id=datablob.user.id,
                    datablob_id=datablob.id,
                    region=datablob.region,
                )
                destination_remote_url = f"{destination_container_client.url}/{destination_azure_blob_storage_path}"
            with RemotePath.from_url(
                remote_url=destination_remote_url,
                pull_on_enter=False,
                push_on_exit=True,
                exist_ok=True,
                parents=True,
            ) as destionation_s3_path:
                with using_cluster("cpu") as engine:
                    filters = json.loads(filters_json)
                    _download_from_clickhouse(
                        host=host,
                        port=port,
                        username=username,
                        password=password,
                        database=database,
                        table=table,
                        protocol=protocol,
                        index_column=index_column,
                        timestamp_column=timestamp_column,
                        filters=filters,
                        output_path=destionation_s3_path.as_path(),
                    )
                calculate_data_object_pulled_on(datablob)

                if len(list(destionation_s3_path.as_path().glob("*"))) == 0:
                    raise ValueError(f"no files to download, table is empty")

            # Calculate folder size in S3
            calculate_data_object_folder_size_and_path(datablob)
        except Exception as e:
            logger.error(f"Error while pulling from clickhouse - {str(e)}")
            datablob.error = truncate(str(e))
        session.add(datablob)
        session.commit()

# %% ../../notebooks/DataBlob_Clickhouse.ipynb 29
def _sql_type(xs: pd.Series) -> str:
    dtype = str(xs.dtype)
    if dtype.startswith("int"):
        dtype = f"Int{dtype[3:]}"
    elif dtype.startswith("float"):
        dtype = f"Float{dtype[5:]}"
    elif is_datetime64_any_dtype(xs):
        dtype = "DateTime64"
    elif dtype == "object":
        dtype = "String"
    elif dtype == "bool":
        dtype = "UInt8"
    else:
        raise ValueError(dtype)
    return dtype


def _sql_types(df: pd.DataFrame) -> str:
    ensure(df.index.name is not None)
    return ", ".join(
        [f"{df.index.name} {_sql_type(df.index.to_series())}"]
        + [f"{c} {_sql_type(df[c])}" for c in df]
    )

# %% ../../notebooks/DataBlob_Clickhouse.ipynb 31
def _insert_table_query(
    df: pd.DataFrame,
    table_name: str,
    *,
    if_not_exists: bool = True,
    engine: str = "ReplacingMergeTree",
) -> str:
    if if_not_exists:
        if_not_exists_str = "IF NOT EXISTS "
    else:
        if_not_exists_str = ""

    return f"CREATE TABLE {if_not_exists_str}{table_name} ({_sql_types(df)}) ENGINE = {engine} ORDER BY {df.index.name};"

# %% ../../notebooks/DataBlob_Clickhouse.ipynb 33
def _insert_table(
    df: pd.DataFrame,
    table_name: str,
    *,
    if_not_exists: bool = True,
    engine: str = "ReplacingMergeTree",
    username: str,
    password: str,
    host: str,
    port: int,
    database: str,
    table: str,
    protocol: str,
):
    with get_clickhouse_connection(  # type: ignore
        username=username,
        password=password,
        host=host,
        port=port,
        database=database,
        table=table,
        protocol=protocol,
    ) as connection:
        if not type(connection) == Connection:
            raise ValueError(f"{type(connection)=} != Connection")

        query = _insert_table_query(
            df, table_name, if_not_exists=if_not_exists, engine=engine
        )
        logger.info(f"Inserting table with query={query}")

        return connection.execute(query)

# %% ../../notebooks/DataBlob_Clickhouse.ipynb 34
def _drop_table(
    table_name: str,
    *,
    if_exists: bool = True,
    username: str,
    password: str,
    host: str,
    port: int,
    database: str,
    table: str,
    protocol: str,
):
    with get_clickhouse_connection(  # type: ignore
        username=username,
        password=password,
        host=host,
        port=port,
        database=database,
        table=table,
        protocol=protocol,
    ) as connection:
        if not type(connection) == Connection:
            raise ValueError(f"{type(connection)=} != Connection")

        if if_exists:
            if_exists_str = "IF EXISTS "
        else:
            if_exists_str = ""

        # User input is validated for SQL code injection
        validate_user_inputs([table_name])

        # nosemgrep: python.sqlalchemy.security.sqlalchemy-execute-raw-query.sqlalchemy-execute-raw-query
        query = f"DROP TABLE {if_exists_str}{table_name};"
        logger.info(f"Dropping table with query={query}")

        # nosemgrep: python.lang.security.audit.formatted-sql-query.formatted-sql-query
        return connection.execute(query)

# %% ../../notebooks/DataBlob_Clickhouse.ipynb 37
def _insert_data(
    df: pd.DataFrame,
    table_name: str,
    *,
    if_exists: str = "append",
    username: str,
    password: str,
    host: str,
    port: int,
    database: str,
    table: str,
    protocol: str,
):
    _insert_table(
        df,
        table_name,
        username=username,
        password=password,
        host=host,
        port=port,
        database=database,
        table=table,
        protocol=protocol,
    )
    with get_clickhouse_connection(  # type: ignore
        username=username,
        password=password,
        host=host,
        port=port,
        database=database,
        table=table,
        protocol=protocol,
    ) as connection:
        if not type(connection) == Connection:
            raise ValueError(f"{type(connection)=} != Connection")

        logger.info(f"Inserting data to table '{table_name}'")
        df.to_sql(table_name, connection, if_exists="append")

# %% ../../notebooks/DataBlob_Clickhouse.ipynb 39
@call_parse
def clickhouse_push(prediction_push_id: int):  # type: ignore
    """Push the data to a clickhouse database

    Args:
        prediction_push_id: Id of prediction_push

    Example:
        The following code executes a CLI command:
        ```clickhouse_push 1
        ```
    """
    with get_session_with_context() as session:
        prediction_push = session.exec(
            select(PredictionPush).where(PredictionPush.id == prediction_push_id)
        ).one()[0]

        prediction_push.error = None
        prediction_push.completed_steps = 0

        (
            username,
            password,
            host,
            port,
            table,
            database,
            protocol,
            database_server,
        ) = _get_clickhouse_connection_params_from_db_uri(db_uri=prediction_push.uri)

        try:
            with RemotePath.from_url(
                remote_url=prediction_push.prediction.path,
                pull_on_enter=True,
                push_on_exit=False,
                exist_ok=True,
                parents=False,
            ) as s3_path:
                df = pd.read_parquet(s3_path.as_path())
                _insert_table(
                    df,
                    table,
                    username=username,
                    password=password,
                    host=host,
                    port=port,
                    database=database,
                    table=table,
                    protocol=protocol,
                )
            prediction_push.completed_steps = 1
        except Exception as e:
            prediction_push.error = truncate(str(e))

        session.add(prediction_push)
        session.commit()

# %% ../../notebooks/DataBlob_Clickhouse.ipynb 42
def get_count(
    account_id: int,
    username: str,
    password: str,
    host: str,
    port: int,
    database: str,
    table: str,
    protocol: str,
) -> int:
    """
    Function to get count of all rows from given table

    Args:
        account_id: AccountId for which to get count
        username: Username of clickhouse database
        password: Password of clickhouse database
        host: Host of clickhouse database
        port: Port of clickhouse database
        table: Table of clickhouse database
        database: Database to use
        protocol: Protocol to connect to clickhouse (native/http)

    Returns:
        Count of all rows for given table
    """
    with get_clickhouse_connection(  # type: ignore
        username=username,
        password=password,
        host=host,
        port=port,
        database=database,
        table=table,
        protocol=protocol,
    ) as connection:
        if not type(connection) == Connection:
            raise ValueError(f"{type(connection)=} != Connection")

        # nosemgrep: python.sqlalchemy.security.sqlalchemy-execute-raw-query.sqlalchemy-execute-raw-query
        query = f"SELECT count() FROM {database}.{table} where AccountId={account_id}"  # nosec B608
        logger.info(f"Getting count with query={query}")

        # nosemgrep: python.lang.security.audit.formatted-sql-query.formatted-sql-query
        result = connection.execute(query)
        return result.fetchall()[0][0]

# %% ../../notebooks/DataBlob_Clickhouse.ipynb 44
def get_count_for_account_ids(
    account_ids: List[Union[int, str]],
    username: str,
    password: str,
    host: str,
    port: int,
    database: str,
    table: str,
    protocol: str,
) -> pd.DataFrame:
    """
    Function to get count for the given account ids from given table

    Args:
        account_ids: List of account ids
        username: Username of clickhouse database
        password: Password of clickhouse database
        host: Host of clickhouse database
        port: Port of clickhouse database
        table: Table of clickhouse database
        database: Database to use
        protocol: Protocol to connect to clickhouse (native/http)

    Returns:
        A pandas dataframe which contains all account ids and their counts
    """
    with get_clickhouse_connection(  # type: ignore
        username=username,
        password=password,
        host=host,
        port=port,
        database=database,
        table=table,
        protocol=protocol,
    ) as connection:
        if not type(connection) == Connection:
            raise ValueError(f"{type(connection)=} != Connection")

        account_ids_query = ", ".join([str(a_id) for a_id in account_ids])

        # nosemgrep: python.sqlalchemy.security.sqlalchemy-execute-raw-query.sqlalchemy-execute-raw-query
        query = f"SELECT AccountId, count() AS curr_count, now() AS curr_check_on FROM {database}.{table} WHERE AccountId IN ({account_ids_query}) GROUP BY AccountId ORDER BY AccountId ASC"  # nosec B608
        logger.info(f"Getting count with query={query}")

        df = pd.read_sql(sql=query, con=connection)
    return df.set_index("AccountId")
