# AUTOGENERATED! DO NOT EDIT! File to edit: ../notebooks/Confluent.ipynb.

# %% auto 0
__all__ = ['kafka_server_url', 'kafka_server_port', 'aio_kafka_config', 'confluent_kafka_config', 'get_topic_names_to_create',
           'create_topics_for_user', 'delete_topics_for_user']

# %% ../notebooks/Confluent.ipynb 2
from os import environ
from pathlib import Path
from typing import *

from confluent_kafka.admin import AdminClient, NewTopic

from airt.logger import get_logger

# %% ../notebooks/Confluent.ipynb 5
logger = get_logger(__name__)

# %% ../notebooks/Confluent.ipynb 7
kafka_server_url = environ["KAFKA_HOSTNAME"]
kafka_server_port = environ["KAFKA_PORT"]

aio_kafka_config = {
    "bootstrap_servers": f"{kafka_server_url}:{kafka_server_port}",
    "group_id": f"{kafka_server_url}:{kafka_server_port}_group",
    "auto_offset_reset": "earliest",
}
if "KAFKA_API_KEY" in environ:
    aio_kafka_config = {
        **aio_kafka_config,
        **{
            "security_protocol": "SASL_SSL",
            "sasl_mechanisms": "PLAIN",
            "sasl_username": environ["KAFKA_API_KEY"],
            "sasl_password": environ["KAFKA_API_SECRET"],
        },
    }

# %% ../notebooks/Confluent.ipynb 9
confluent_kafka_config = {
    key.replace("_", "."): value for key, value in aio_kafka_config.items()
}

# %% ../notebooks/Confluent.ipynb 11
def get_topic_names_to_create(username: str) -> List[str]:
    """
    Get a list of topic names to create for given username

    Args:
        username: username of user for whom the list of topic names is required
    Returns:
        A list of topic names unique to the username
    """
    return [f"airt_service_{username}_training_data"]

# %% ../notebooks/Confluent.ipynb 13
def create_topics_for_user(username: str):
    """
    Create necessary topics for given user

    Args:
        username: username of user for whom the topics needs to be created
    """

    topic_names_to_create = get_topic_names_to_create(username)
    admin_client = AdminClient(confluent_kafka_config)

    num_partitions = 6
    replication_factor = 2 if "KAFKA_API_KEY" in environ else 1

    existing_topics = admin_client.list_topics().topics

    topics_to_create = [
        NewTopic(topic_name, num_partitions, replication_factor)
        for topic_name in topic_names_to_create
        if topic_name not in existing_topics
    ]
    if not topics_to_create:
        return

    futures = admin_client.create_topics(topics_to_create)

    for topic, future in futures.items():
        try:
            future.result()
            logger.info(f"Topic {topic} created")
        except Exception as e:
            logger.error(f"Topic {topic} creation failed")
            raise e

# %% ../notebooks/Confluent.ipynb 15
def delete_topics_for_user(username: str):
    """
    Delete necessary topics for given user

    Args:
        username: username of user for whom the topics needs to be deleted
    """

    topic_names_to_delete = get_topic_names_to_create(username)
    admin_client = AdminClient(confluent_kafka_config)

    existing_topics = admin_client.list_topics().topics

    topics_to_delete = [
        topic_name
        for topic_name in topic_names_to_delete
        if topic_name in existing_topics
    ]
    if not topics_to_delete:
        return

    futures = admin_client.delete_topics(topics_to_delete)

    for topic, future in futures.items():
        try:
            future.result()
            logger.info(f"Topic {topic} deleted")
        except Exception as e:
            logger.error(f"Topic {topic} deletion failed")
            raise e
