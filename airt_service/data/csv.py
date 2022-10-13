# AUTOGENERATED! DO NOT EDIT! File to edit: ../../notebooks/DataSource_CSV.ipynb.

# %% auto 0
__all__ = ["process_csv"]

# %% ../../notebooks/DataSource_CSV.ipynb 3
import json
from typing import *

from fastcore.script import call_parse, Param
from fastcore.utils import *
from sqlmodel import select

from airt.data.importers import import_csv
from airt.logger import get_logger
from airt.remote_path import RemotePath
from ..aws.utils import create_s3_datasource_path
from ..azure.utils import create_azure_blob_storage_datasource_path
from ..helpers import truncate
from .utils import calculate_azure_data_object_folder_size_and_path
from .utils import calculate_data_object_folder_size_and_path
from .utils import calculate_data_object_pulled_on

from ..db.models import get_session_with_context, DataBlob
from .datasource import DataSource

# %% ../../notebooks/DataSource_CSV.ipynb 6
logger = get_logger(__name__)

# %% ../../notebooks/DataSource_CSV.ipynb 7
@call_parse
def process_csv(
    datablob_id: Param("datablob_id", int),  # type: ignore
    datasource_id: Param("datasource_id", int),  # type: ignore
    *,
    deduplicate_data: Param("deduplicate_data", bool) = False,  # type: ignore
    index_column: Param("index_column", str),  # type: ignore
    sort_by: Param("sort_by", str),  # type: ignore
    blocksize: Param("blocksize", str) = "256MB",  # type: ignore
    kwargs_json: Param("kwargs_json", str) = "{}",  # type: ignore
):
    """Download the user uploaded CSV from S3, run import_csv against it and finally upload the processed parquet files to S3

    Args:
        datablob_id: Datablob id
        datasource_id: Datasource id
        deduplicate_data: If set to True (default value False), then duplicate rows are removed while uploading
        index_column: Name of the column to use as index and partition the data
        sort_by: Name of the column to sort data within the same index value
        blocksize: Size of partition
        kwargs_json: Parameters as json string which are passed to the **dask.dataframe.read_csv()** function,
            typically params for underlining **pd.read_csv()** from Pandas.
    """
    logger.info(
        f"process_csv({datablob_id=}, {datasource_id=}): processing user uploaded csv file for {datablob_id=} and uploading parquet back to S3 for {datasource_id=}"
    )
    with get_session_with_context() as session:
        datablob = session.exec(
            select(DataBlob).where(DataBlob.id == datablob_id)
        ).one()
        datasource = session.exec(
            select(DataSource).where(DataSource.id == datasource_id)
        ).one()

        # Following is needed if datablob was created from user uploaded csv files
        calculate_data_object_folder_size_and_path(datablob)

        datasource.error = None
        datasource.completed_steps = 0
        datasource.folder_size = None
        datasource.no_of_rows = None
        datasource.path = None
        datasource.hash = None

        try:
            source_path = datablob.path
            if datasource.cloud_provider == "aws":
                destination_bucket, s3_path = create_s3_datasource_path(
                    user_id=datasource.user.id,
                    datasource_id=datasource.id,
                    region=datasource.region,
                )
                destination_remote_url = f"s3://{destination_bucket.name}/{s3_path}"
            elif datasource.cloud_provider == "azure":
                (
                    destination_container_client,
                    destination_azure_blob_storage_path,
                ) = create_azure_blob_storage_datasource_path(
                    user_id=datasource.user.id,
                    datasource_id=datasource.id,
                    region=datasource.region,
                )
                destination_remote_url = f"{destination_container_client.url}/{destination_azure_blob_storage_path}"
            logger.info(
                f"process_csv({datablob_id=}, {datasource_id=}): step 1/4: downloading user uploaded file from bucket {source_path}"
            )

            with RemotePath.from_url(
                remote_url=source_path,
                pull_on_enter=True,
                push_on_exit=False,
                exist_ok=True,
                parents=False,
            ) as source_s3_path:
                calculate_data_object_pulled_on(datasource)
                if len(list(source_s3_path.as_path().iterdir())) == 0:
                    raise ValueError("Files not found")
                logger.info(
                    f"process_csv({datablob_id=}, {datasource_id=}): step 2/4: running import_csv()"
                )

                with RemotePath.from_url(
                    remote_url=destination_remote_url,
                    pull_on_enter=False,
                    push_on_exit=True,
                    exist_ok=True,
                    parents=True,
                ) as destination_path:
                    processed_path = destination_path.as_path()
                    kwargs = json.loads(kwargs_json)
                    try:
                        sort_by = json.loads(sort_by)
                    except json.JSONDecodeError:
                        pass
                    import_csv(
                        input_path=source_s3_path.as_path(),
                        output_path=processed_path,
                        index_column=index_column,
                        sort_by=sort_by,
                        blocksize=blocksize,
                        **kwargs,
                    )
                    datasource.calculate_properties(processed_path)

                    if not len(list(processed_path.glob("*.parquet"))) > 0:
                        raise ValueError(
                            f"processing failed; parquet files not available"
                        )

                    logger.info(
                        f"process_csv({datablob_id=}, {datasource_id=}): step 3/4: uploading parquet files back to path {destination_path}"
                    )
            logger.info(
                f"process_csv({datablob_id=}, {datasource_id=}): step 4/4: calculating datasource attributes - folder_size, no_of_rows, head, hash"
            )

            calculate_data_object_folder_size_and_path(datasource)
        except Exception as e:
            logger.error(
                f"process_csv({datablob_id=}, {datasource_id=}): error: {str(e)}"
            )
            datasource.error = truncate(str(e))
        logger.info(f"process_csv({datablob_id=}, {datasource_id=}): completed")
        session.add(datablob)
        session.add(datasource)
        session.commit()
