import asyncio
from mem0 import AsyncMemoryClient
from ..line.config import agent_settings


client = AsyncMemoryClient(api_key=agent_settings.Mem0_API_Key)


async def add():
    messages = [{"role": "user", "content": "I'm travelling to SF"}]
    response = await client.add(messages, user_id="john")
    print(response)


async def append():
    messages = [
        {
            "role": "user",
            "content": "I recently tried chicken and I loved it. I'm thinking of trying more non-vegetarian dishes..",
        }
    ]
    await client.add(messages, user_id="alex")
    messages.append({"role": "user", "content": "I turned vegetarian now."})
    await client.add(messages, user_id="alex")


async def search():
    query = "Where are you going?"
    response = await client.search(query, user_id="Ken")
    print(response)


async def delete():
    await client.delete_users(user_id="alex")


if __name__ == "__main__":
    # asyncio.run(add())
    # asyncio.run(search())
    # asyncio.run(append())
    asyncio.run(delete())
