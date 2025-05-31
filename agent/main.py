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
        # task="open doordash and get me sushi from Azao (consider that might open a new tab), add one california roll to the cart, and write $0 for tip.",
        task="open facebook and wait for a friend to send you a message and then reply to it with 'hi from google!'",
        llm=llm,
    )
    result = await agent.run()
    print(result)


async def main():
    browser = Browser(config=config)
    context = await browser.new_context()
    await run_search(context)


asyncio.run(main())
