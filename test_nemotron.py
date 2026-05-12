import asyncio
import os

from dotenv import load_dotenv
from openai import AsyncOpenAI

load_dotenv(".env")


async def test():
    client = AsyncOpenAI(
        api_key=os.environ["OPENAI_API_KEY"],
        base_url=os.environ.get("OPENAI_BASE_URL", "https://integrate.api.nvidia.com/v1"),
    )
    try:
        res = await client.chat.completions.create(
            model="nvidia/nemotron-4-340b-instruct",
            messages=[
                {"role": "system", "content": "Tu es un assistant."},
                {"role": "user", "content": "Coucou"},
            ],
            max_tokens=1024,
        )
        print("Response:", repr(res.choices[0].message.content))
        print("Finish reason:", res.choices[0].finish_reason)
    except Exception as e:
        print("Error:", e)


asyncio.run(test())
