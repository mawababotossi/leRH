import asyncio

from leRH.core.assistants.manager import Assistant


async def test():
    assistant = Assistant(name="Test", country="Togo", activity="Tester")
    res = await assistant.interact("Coucou")
    print("Result:", repr(res))


asyncio.run(test())
