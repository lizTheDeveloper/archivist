import asyncio
from nats.aio.client import Client as NATS
from nats.aio.errors import ErrTimeout
import requests
import asyncpg 
import os 
import io
from openai import OpenAI
import tiktoken

enc = tiktoken.encoding_for_model("gpt-4")

## to extract data from a PDF
from PyPDF2 import PdfReader


# Point to the local server
client = OpenAI(base_url="http://localhost:1234/v1", api_key="lm-studio")

global db_connection
global cursor
global js
global nc


db_connection = None
cursor = None
js = None
nc = None

CONTENT_DATABASE_URL = os.getenv("CONTENT_DATABASE")
async def get_db_connection():
    return await asyncpg.connect(CONTENT_DATABASE_URL)

async def run_nats_consumer():
    ## Initialize the database connection and NATS Jetstream connection once only 
    global db_connection
    global cursor
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
        paper_path = msg.data.decode()
        print(f"Received a message on '{subject}': {paper_path}")
        ## read the pdf file
        with open(paper_path, "rb") as f:
            pdf = f.read()
        ## get the text from the pdf using PyPDF2
        pdf_file = io.BytesIO(pdf)
        pdf_reader = PdfReader(pdf_file)
        paper_text = ""
        
        ## extract the first page of the pdf
        first_page = pdf_reader.pages[0]
        paper_text = first_page.extract_text()
        
        
        
        ## get a chatcompletion
        completion = client.chat.completions.create(
            messages=[
                {"role": "system", "content": "You are a paper categorizing agent. Please generate a list of tags that the paper could be classified by."},
                {"role": "user", "content": "Please give the tags for this abstract:" + paper_text}
            ],
            model="TheBloke/Llama-2-13B-chat-GGUF/llama-2-13b-chat.Q4_K_M.gguf",
            temperature=0.7,
        )
        
        ## get the response
        response = completion.choices[0].message.content
        print(response)
        
        ## split the response into tags, split into lines and then remove empty lines and remove the first characters if they're - or a number with a .
        tags = response.split("\n")
        tags = [tag for tag in tags if tag != ""]
        tags = [tag[2:] if tag[0] == "-" else tag for tag in tags]
        tags = [tag[3:] if tag[1] == "." else tag for tag in tags]
        tags = [tag.strip() for tag in tags]
        tags = [tag.lower() for tag in tags if len(tag) > 2]
        print(tags)
        
        
        db_connection = await get_db_connection()
        ## save the tags for this paper in the db, first get the paper 
        paper = await db_connection.fetchrow("SELECT * FROM papers WHERE file_path = $1", paper_path)
        print(paper)
        ## save the tags for this paper in the db
        for tag in tags:
            await db_connection.execute("INSERT INTO tags (paper_id, tag) VALUES ($1, $2)", paper["id"], tag)
        
        ## Publish on the subject PAPERS_DOWNLOADED
        await js.publish("PAPERS_CATEGORIZED", f"{paper_path}".encode())
        print("Summarized the paper")
            
        
        await msg.ack()

    # Subscribe to the subject with the consumer
    await js.pull_subscribe("PAPERS.DOWNLOADED", "categorizer", cb=message_handler)


    print("NATS Jetstream consumer is running, waiting for messages...")

if __name__ == '__main__':
    loop = asyncio.get_event_loop()
    loop.run_until_complete(run_nats_consumer())
    loop.run_forever()
