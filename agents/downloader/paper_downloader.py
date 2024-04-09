import asyncio
from nats.aio.client import Client as NATS
from nats.aio.errors import ErrTimeout
import requests
import asyncpg 
import os 
global db_connection
global js
global nc


db_connection = None
js = None
nc = None

CONTENT_DATABASE_URL = os.getenv("CONTENT_DATABASE")
async def get_db_connection():
    return await asyncpg.connect(CONTENT_DATABASE_URL)

async def run_nats_consumer():
    ## Initialize the database connection and NATS Jetstream connection once only 
    global db_connection
    global js
    global nc
    
    if db_connection is None:
        db_connection = await get_db_connection()
    
    if js is None:
        # Initialize the NATS client
        nc = NATS()

        await nc.connect(servers=["nats://localhost:4222"])

        # Connect to Jetstream
        js = nc.jetstream()

    # Process messages
    async def message_handler(msg):
        subject = msg.subject
        data = msg.data.decode()
        print(f"Received a message on '{subject}': {data}")

        # Download the paper using requests
        response = requests.get(data)
        
        paper_path = f"./papers/{data.split('/')[-1]}"
        
        ## Save the paper to a file
        with open(paper_path, "wb") as f:
            f.write(response.content)
            await db_connection.execute("INSERT INTO papers (title, url, file_path) VALUES ($1, $2, $3)", data.split('/')[-1], data, paper_path)
            
            ## Publish on the subject PAPERS_DOWNLOADED
            await js.publish("PAPERS.DOWNLOADED", f"{paper_path}".encode())
            print(f"Published a message on 'PAPERS.DOWNLOADED': {paper_path}")
            
        
        await msg.ack()

    # Subscribe to the subject with the consumer
    await js.subscribe("PAPERS.NEW", "downloader", cb=message_handler)

    print("NATS Jetstream consumer is running, waiting for messages...")

if __name__ == '__main__':
    loop = asyncio.get_event_loop()
    loop.run_until_complete(run_nats_consumer())
    loop.run_forever()
