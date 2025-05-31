from langchain_openai import ChatOpenAI
from langchain_google_genai import ChatGoogleGenerativeAI
from browser_use import Agent, Browser, BrowserContextConfig
from browser_use import BrowserConfig
from dotenv import load_dotenv
import os

load_dotenv()

import asyncio

config = BrowserConfig(
    headless=False,
    browser_binary_path="/usr/bin/chromium-browser",
)

llm = ChatGoogleGenerativeAI(
    model="gemini-2.0-flash-exp", api_key=os.getenv("GEMINI_API_KEY")
)


async def run_search(browser_context):
    agent = Agent(
        browser_context=browser_context,
        task="open facebook marketplace and create vehicle listing. wait for the user to upload the images for 15 seconds, then continue filling the rest of the information: toyota corolla, price 15000",
        llm=llm,
    )
    result = await agent.run()
    print(result)


async def main():
    browser = Browser(config=config)
    context = await browser.new_context()
    await run_search(context)


asyncio.run(main())
