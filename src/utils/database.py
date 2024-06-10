import json
from typing import Any
import logging as log

import asyncpg

from config import *
from utils.settings import BotSettings

class Database:
    def __init__(self, loop) -> None:
        self._loop = loop
        self._pool = None
    
    async def setup_database(self, tables):
        async with self._pool.acquire() as connection:
            for table_name, columns in tables.items():
                table_exists_query = f"""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_name = '{table_name}'
                );
                """
                table_exists = await connection.fetchval(table_exists_query)
                
                if not table_exists: # If the table does not exist, create it
                    columns_definitions = ', '.join([f"{col} {typ}" for col, typ in columns.items()])
                    create_table_query = f"CREATE TABLE {table_name} ({columns_definitions});"
                    await connection.execute(create_table_query)
                    log.info(f"[Database] Table '{table_name}' created.")
                else: # If the table exists, check for new columns
                    existing_columns_query = f"""
                    SELECT column_name 
                    FROM information_schema.columns 
                    WHERE table_name = '{table_name}';
                    """
                    existing_columns = await connection.fetch(existing_columns_query)
                    existing_columns = {row['column_name'] for row in existing_columns}

                    for col, typ in columns.items():
                        if col not in existing_columns: # Add new column if it does not exist
                            add_column_query = f"ALTER TABLE {table_name} ADD COLUMN {col} {typ};"
                            await connection.execute(add_column_query)
                            log.info(f"[Database] Column '{col}' added to table '{table_name}'.")
    
    async def start(self, url: str):
        self._pool = await asyncpg.create_pool(url)
        log.info("[Database] Pool created!")
    
    async def fetch_one(self, table: str, **conditions) -> Any:
        async with self._pool.acquire() as connection:
            where_clause = ' AND '.join(f"{key} = ${i+1}" for i, key in enumerate(conditions.keys()))
            query = f"SELECT * FROM {table} FETCH FIRST WHERE {where_clause}"
            return await connection.fetch(query, *conditions.values())[0]
    
    async def fetch(self, table: str, **conditions) -> list:
        async with self._pool.acquire() as connection:
            where_clause = ' AND '.join(f"{key} = ${i+1}" for i, key in enumerate(conditions.keys()))
            query = f"SELECT * FROM {table} WHERE {where_clause}"
            return await connection.fetch(query, *conditions.values())
    
    async def push(self, table: str, **data) -> None:
        async with self._pool.acquire() as connection:
            keys = list(data.keys())
            query = f'''
                INSERT INTO {table} ({', '.join(keys)})
                VALUES ({", ".join(f"${i+1}" for i in range(len(list(data.values()))))})
                ON CONFLICT ({keys[0]})
                DO UPDATE SET {", ".join(f"{col} = EXCLUDED.{col}" for col in keys[1:])}
            '''
            await connection.execute(query, *data.values())
    
    async def get_settings(self, guild_id: int) -> BotSettings:
        data = []
        async with self._pool.acquire() as connection:
            query = f"SELECT * FROM bot_settings WHERE guild_id=$1 LIMIT 1"
            data = await connection.fetch(query, guild_id)
            if data: data = data[0]
        return BotSettings(data)
