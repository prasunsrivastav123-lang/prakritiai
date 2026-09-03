import json
import logging
import asyncio
import redis.asyncio as redis
from typing import Dict, Any, AsyncGenerator

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class RedisEventStreamer:
    """
    Lightweight Message Queue using Redis Pub/Sub for Hackathon demos.
    Replaces heavy Kafka infrastructure.
    """
    def __init__(self, channel: str = "ml-disaster-events", redis_url: str = "redis://localhost:6379"):
        self.channel_name = channel
        self.redis_url = redis_url
        self.redis_client = None
        self.pubsub = None

    async def connect(self):
        try:
            self.redis_client = redis.from_url(self.redis_url)
            self.pubsub = self.redis_client.pubsub()
            await self.pubsub.subscribe(self.channel_name)
            logging.info(f"Successfully subscribed to Redis channel: {self.channel_name}")
        except Exception as e:
            logging.error(f"Failed to connect to Redis: {e}. Make sure Redis server is running!")

    async def consume_events(self) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Async Generator that yields parsed event dictionaries from Redis Pub/Sub.
        Events can be: ML hazard predictions, GPS pings, or field reports.
        """
        if not self.pubsub:
            await self.connect()

        try:
            while True:
                # Listen for messages asynchronously
                message = await self.pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
                
                if message is not None and message['type'] == 'message':
                    try:
                        # Parse the JSON payload from the message
                        event_data = json.loads(message['data'].decode('utf-8'))
                        logging.info(f"Received event on {self.channel_name}: {event_data.get('event_type', 'Unknown')}")
                        
                        yield event_data
                        
                    except json.JSONDecodeError:
                        logging.error(f"Failed to decode JSON from message: {message['data']}")
                    except Exception as e:
                        logging.error(f"Error processing message: {e}")
                
                # Sleep briefly to prevent tight loop CPU pinning
                await asyncio.sleep(0.1)
                
        except asyncio.CancelledError:
            logging.info("Stopping Redis consumer...")
        finally:
            await self.close()

    async def close(self):
        if self.pubsub:
            await self.pubsub.unsubscribe(self.channel_name)
            await self.pubsub.close()
        if self.redis_client:
            await self.redis_client.close()

# Example usage hook for the orchestrator
async def consume_ml_events():
    streamer = RedisEventStreamer(channel="ml-disaster-events")
    async for event in streamer.consume_events():
        # Yield to the event loop in orchestrator.py
        yield event

# --- Helper function to publish events (e.g. from an AI Prediction Script) ---
async def publish_event(event_data: dict, channel: str = "ml-disaster-events"):
    r = redis.from_url("redis://localhost:6379")
    await r.publish(channel, json.dumps(event_data))
    await r.close()