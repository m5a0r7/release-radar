"""Create the integration-test database next to the dev one, if it is missing."""

import asyncio
import os

import asyncpg


async def main() -> None:
    url = os.environ["DATABASE_URL"].replace("+asyncpg", "")
    name = os.environ["TEST_DATABASE_URL"].rsplit("/", 1)[1]
    conn = await asyncpg.connect(url)
    try:
        if not await conn.fetchval("SELECT 1 FROM pg_database WHERE datname = $1", name):
            await conn.execute(f'CREATE DATABASE "{name}"')
    finally:
        await conn.close()


asyncio.run(main())
