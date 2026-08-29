import json
import logging
from confluent_kafka import Consumer, KafkaError
from typing import Dict, Any, Generator

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class KafkaEventStreamer:
    def __init__(self, topic: str, group_id: str = "ner_logistics_orchestrator"):
        self.topic = topic
        self.consumer = Consumer({
            'bootstrap.servers': 'localhost:9092',  # Replace with your Kafka broker
            'group.id': group_id,
            'auto.offset.reset': 'latest',          # Start reading new messages
            'enable.auto.commit': False             # Manual commit to ensure processing
        })
        self.consumer.subscribe([topic])

    def consume_events(self) -> Generator[Dict[str, Any], None, None]:
        """
        Generator that yields parsed event dictionaries from Kafka.
        Events can be: ML hazard predictions, GPS pings, or field reports.
        """
        try:
            while True:
                msg = self.consumer.poll(timeout=1.0)
                
                if msg is None:
                    continue
                if msg.error():
                    if msg.error().code() == KafkaError._PARTITION_EOF:
                        continue
                    else:
                        logging.error(f"Kafka error: {msg.error()}")
                        break
                
                try:
                    # Parse the JSON payload from the message
                    event_data = json.loads(msg.value().decode('utf-8'))
                    logging.info(f"Received event on {self.topic}: {event_data.get('event_type', 'Unknown')}")
                    
                    yield event_data
                    
                    # Manually commit offset after successful processing
                    self.consumer.commit(asynchronous=False)
                    
                except json.JSONDecodeError:
                    logging.error(f"Failed to decode JSON from message: {msg.value()}")
                except Exception as e:
                    logging.error(f"Error processing message: {e}")
                    
        except KeyboardInterrupt:
            logging.info("Stopping consumer...")
        finally:
            self.consumer.close()

# Example usage hook for the orchestrator
def consume_ml_events():
    streamer = KafkaEventStreamer(topic="ml-disaster-events")
    for event in streamer.consume_events():
        # Yield to the event loop in orchestrator.py
        yield event