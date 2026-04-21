"""APScheduler nightly cron for the Digital Sleep Cycle."""

from __future__ import annotations

import asyncio

import structlog
from apscheduler.schedulers.background import BackgroundScheduler

from memory_layer.config import Settings
from memory_layer.graph.driver import GraphDriver
from memory_layer.graph.repository import GraphRepository

log = structlog.get_logger()

_scheduler: BackgroundScheduler | None = None


def _run_sleep_cycle(driver: GraphDriver, settings: Settings) -> None:
    """Run the sleep cycle for all users. Called by APScheduler."""
    asyncio.run(_async_sleep_cycle(driver, settings))


async def _async_sleep_cycle(driver: GraphDriver, settings: Settings) -> None:
    from memory_layer.core.key_manager import KeyManager
    from memory_layer.core.security import KeyEncryptor
    from memory_layer.llm.router import LLMRouter
    from memory_layer.sleep.consolidator import Consolidator
    from memory_layer.sleep.pruner import Pruner

    repo = GraphRepository(driver)
    encryptor = KeyEncryptor(settings.fernet_keys)
    key_mgr = KeyManager(repo, encryptor)
    llm_router = LLMRouter()

    # Get all users
    async with driver.session() as session:
        result = await session.run("MATCH (u:User) RETURN u.id AS id")
        users = [record["id"] async for record in result]

    for user_id_str in users:
        from uuid import UUID
        user_id = UUID(user_id_str)
        try:
            # Try to get an API key for this user
            for provider in ["openai", "anthropic", "google"]:
                try:
                    api_key = await key_mgr.get_key_for_provider(user_id, provider)
                    client = llm_router.get_client(provider, api_key)
                    break
                except ValueError:
                    continue
            else:
                log.info("sleep_skip_no_key", user_id=user_id_str)
                continue

            pruner = Pruner(repo)
            consolidator = Consolidator(client, repo)

            pruned = await pruner.prune(user_id)
            consolidated = await consolidator.consolidate(user_id)
            log.info("sleep_cycle_user", user_id=user_id_str, pruned=pruned, consolidated=consolidated)
        except Exception as e:
            log.error("sleep_cycle_error", user_id=user_id_str, error=str(e))


def start_scheduler(driver: GraphDriver, settings: Settings) -> None:
    """Start the background sleep cycle scheduler."""
    global _scheduler
    if _scheduler is not None:
        return

    _scheduler = BackgroundScheduler()
    _scheduler.add_job(
        _run_sleep_cycle,
        "cron",
        hour=settings.sleep_cron_hour,
        minute=settings.sleep_cron_minute,
        args=[driver, settings],
        id="sleep_cycle",
        replace_existing=True,
    )
    _scheduler.start()
    log.info("scheduler_started", hour=settings.sleep_cron_hour, minute=settings.sleep_cron_minute)


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler:
        _scheduler.shutdown(wait=False)
        _scheduler = None
