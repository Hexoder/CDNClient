import asyncio
import json
import logging

import aio_pika

from cdn.client import CDNClient
from cdn.common.events import Events
from cdn.conf import RABBITMQ_CONFIG, QUEUE_NAME, EXCHANGE_NAME
from cdn.utils import remove_usages

client = CDNClient()

logger = logging.getLogger(__name__)


class RabbitConsumer:
    ROUTING_KEYS = [
        Events.FILE_DELETED,
    ]

    async def connect(self):

        self.connection = await aio_pika.connect_robust(
            host=RABBITMQ_CONFIG["HOST"],
            port=RABBITMQ_CONFIG["PORT"],
            login=RABBITMQ_CONFIG["USER"],
            password=RABBITMQ_CONFIG["PASSWORD"],
        )

        self.channel = await self.connection.channel()

        await self.channel.set_qos(prefetch_count=10)

        self.exchange = await self.channel.declare_exchange(
            EXCHANGE_NAME,
            aio_pika.ExchangeType.TOPIC,
            durable=True,
        )

        self.queue = await self.channel.declare_queue(
            QUEUE_NAME,
            durable=True,
        )

        for routing_key in self.ROUTING_KEYS:
            await self.queue.bind(self.exchange, routing_key)

    async def start(self):

        await self.connect()

        logger.info("RabbitMQ consumer started")

        await self.queue.consume(self.on_message)

        await asyncio.Future()

    async def on_message(self, message: aio_pika.IncomingMessage):

        async with message.process():
            event = json.loads(message.body)

            logger.info(event)

            await self.dispatch(event)

    async def dispatch(self, event):

        name = event["event"]

        if name == Events.FILE_DELETED:
            await self.file_deleted(event)

    async def file_deleted(self, event):

        file_id = event["file_id"]
        result = client.check_file_status(file_id)
        usages = result.get('usages', [])
        await remove_usages(usages)

        logger.info("Removed references to file %s", file_id)
