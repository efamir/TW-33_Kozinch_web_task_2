from typing import Optional

from pika.adapters.blocking_connection import BlockingChannel
from pymongo import MongoClient
import electricall_bills as eb
from electrical_bills_updates_validator import validate_and_execute_update

import pika
import json


__client = MongoClient("localhost", 27017)
__db = __client["electrical_bills"]
__bm = eb.ElectricalBills(__db)
channel: Optional[BlockingChannel] = None

def callback(ch, method, _, body):
    update: dict = json.loads(body)
    e_response = validate_and_execute_update(__bm, update)

    try:
        if "routing_key" in update:
            channel.basic_publish(
                exchange="electrical_bills",
                routing_key=update.get("routing_key"),
                body=json.dumps({"response": e_response if not e_response else str(e_response)}).encode()
            )
    except Exception as e:
        print(e)

    ch.basic_ack(delivery_tag=method.delivery_tag)


def main():
    global channel
    connection = pika.BlockingConnection(pika.ConnectionParameters('localhost'))
    channel = connection.channel()

    queue_consume = channel.queue_declare('electrical_bills_updates')
    queue_name = queue_consume.method.queue

    channel.exchange_declare(exchange="electrical_bills", exchange_type="direct")

    channel.queue_bind(
        exchange="electrical_bills",
        queue=queue_name,
        routing_key="electrical.bills.updates"
    )

    channel.basic_consume(on_message_callback=callback, queue=queue_name)
    channel.start_consuming()


if __name__ == "__main__":
    main()
