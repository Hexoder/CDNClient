import asyncio

from django.core.management.base import BaseCommand

from cdn.common.rabbitmq import RabbitConsumer


class Command(BaseCommand):

    def handle(self, *args, **kwargs):
        asyncio.run(RabbitConsumer().start())