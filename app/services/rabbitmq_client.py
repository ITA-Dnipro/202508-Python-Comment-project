import pika
import json
import os

def publish_notification_event(payload: dict):
    host = os.getenv("RABBITMQ_HOST", "rabbitmq")
    user = os.getenv("RABBITMQ_USER", "guest")
    pwd = os.getenv("RABBITMQ_PASS", "guest")
    exchange = os.getenv("RABBITMQ_EXCHANGE", "notifications.exchange")

    credentials = pika.PlainCredentials(user, pwd)
    connection = pika.BlockingConnection(
        pika.ConnectionParameters(
            host=host,
            credentials=credentials
        )
    )
    channel = connection.channel()

    # Durable exchange
    channel.exchange_declare(exchange=exchange, exchange_type="topic", durable=True)

    # Publish persistent message
    channel.basic_publish(
        exchange=exchange,
        routing_key=payload["event_type"],
        body=json.dumps(payload),
        properties=pika.BasicProperties(delivery_mode=2)  # persistent
    )

    connection.close()
