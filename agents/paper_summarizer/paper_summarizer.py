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
        for page in range(len(pdf_reader.pages)):
            paper_text += pdf_reader.pages[page].extract_text()

        ## find out how long the paper is in tokens
        paper_text_encoding = enc.encode(paper_text)
        
        tokens = len(paper_text_encoding)
        print(f"Number of tokens in the paper: {tokens}")
        if tokens > 4096:
            ## recursively summarize by sending each page to the summarizer
            current_page = 0
            pages = []
            for page in range(len(pdf_reader.pages)):
                
                page_text = pdf_reader.pages[page].extract_text()
                pages.append({
                    "page_text": page_text,
                    "page_summary": ""
                })
                messages = [
                        {"role": "system", "content": "You are a paper summarizing agent. This long paper needs to be summarized in parts, and you're on page " + str(current_page) + "."}
                ]
                if current_page > 1:
                    messages.append({"role": "user", "content": "What is the page about? Be sure to include all formulae or examples. \n\nHere's the summary of the previous page: " + pages[current_page - 1]["page_summary"] + "Here is the abstract:\n\n" + pages[0]["page_summary"] + "\n\nHere's the page:" + page_text})
                elif current_page == 1:
                    messages.append({"role": "user", "content": "What is this page about? Be sure to include all formulae or examples. \n\nHere's the abstract:\n\n" + pages[0]["page_summary"] + "\n\nHere's the page:" + page_text})
                else:
                    messages.append({"role": "user", "content": "What is the paper about?\n\nHere's the first page:" + page_text})
                
                completion = client.chat.completions.create(
                    messages=messages,
                    model="TheBloke/Llama-2-13B-chat-GGUF/llama-2-13b-chat.Q4_K_M.gguf",
                    temperature=0.7,
                )
                response = completion.choices[0].message.content
                print(response)
                pages[current_page]["page_summary"] = response
                current_page += 1
            ## combine the summaries
            response = ""
            for page in pages:
                response += page["page_summary"]
                
            ## summarize the summaries
            completion = client.chat.completions.create(
                messages=[
                    {"role": "system", "content": "You are a paper summarizing agent. This long paper has been summarized in parts."},
                    {"role": "user", "content": "What is the paper about?\n\n" + response},
                ],
                model="TheBloke/Llama-2-13B-chat-GGUF/llama-2-13b-chat.Q4_K_M.gguf",
                temperature=0.7,
            )
            abstract = pages[0]["page_summary"]
            
            summary = completion.choices[0].message.content
            db_connection = await get_db_connection()
            ## save the response to the database
            await db_connection.execute("UPDATE papers SET summary = $1, abstract = $2 WHERE file_path = $3", summary, abstract, paper_path)
            ## Publish on the subject PAPERS_DOWNLOADED
            await js.publish("PAPERS.SUMMARIZED", f"{paper_path}".encode())
        else:
            ## get a chatcompletion
            completion = client.chat.completions.create(
                messages=[
                    {"role": "system", "content": "You are a paper summarizing agent."},
                    {"role": "user", "content": "What is the paper about? Please include all formulae and examples.\n\n" + paper_text},
                ],
                model="gpt-3.5-turbo",
                temperature=0.7,
            )
            
            ## get the response
            response = completion.choices[0].message.content
            print(response)
            db_connection = await get_db_connection()
            ## save the response to the database
            await db_connection.execute("UPDATE papers SET summary = $1 WHERE file_path = $2", response, paper_path)
                
            ## Publish on the subject PAPERS_DOWNLOADED
            await js.publish("PAPERS.SUMMARIZED", f"{paper_path}".encode())
            print("Summarized the paper")
            
        
        await msg.ack()

    # Subscribe to the subject with the consumer
    await js.pull_subscribe("PAPERS.DOWNLOADED", "summarizer", cb=message_handler)

    print("NATS Jetstream consumer is running, waiting for messages...")

if __name__ == '__main__':
    loop = asyncio.get_event_loop()
    loop.run_until_complete(run_nats_consumer())
    loop.run_forever()
