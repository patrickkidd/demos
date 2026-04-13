import asyncio
import logging

from claude_agent_sdk import query, ClaudeAgentOptions

log = logging.getLogger(__name__)

MAX_RETRIES = 3
BACKOFF_BASE = 5


async def retry_query(*, prompt, options, on_message=None, retries=MAX_RETRIES):
    for attempt in range(retries + 1):
        try:
            async for msg in query(prompt=prompt, options=options):
                if on_message:
                    on_message(msg)
            return
        except Exception as e:
            if attempt == retries:
                raise
            wait = BACKOFF_BASE * (2 ** attempt)
            log.warning(f"query() failed (attempt {attempt + 1}/{retries + 1}): {e}. Retrying in {wait}s")
            await asyncio.sleep(wait)
