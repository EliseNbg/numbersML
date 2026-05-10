#!/usr/bin/env python3
"""
Health Check CLI - Service health monitoring.

Checks health of database, Redis, and services.

Usage:
    python -m src.cli.health_check
    python -m src.cli.health_check --db-url postgresql://user:pass@localhost/db
"""

import asyncio
import logging
import sys
from datetime import UTC, datetime
from typing import Any, Optional

import asyncpg
import click

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


@click.command()
@click.option(
    "--db-url",
    envvar="DATABASE_URL",
    default="postgresql://crypto:crypto@localhost:5432/crypto_trading",
    help="Database URL",
)
@click.option("--redis-url", envvar="REDIS_URL", default="redis://localhost:6379", help="Redis URL")
@click.option("--timeout", default=5, help="Connection timeout in seconds")
@click.option("--verbose", "-v", is_flag=True, help="Verbose output")
def main(
    db_url: str,
    redis_url: str,
    timeout: int,
    verbose: bool,
) -> None:
    """
    Check health of crypto trading system services.

    Performs health checks on:
    \b
    - PostgreSQL database
    - Redis message queue
    - Network connectivity

    Returns exit code 0 if all checks pass, 1 otherwise.

    Examples:

    \b
    python -m src.cli.health_check
    python -m src.cli.health_check --verbose
    """
    if verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    exit_code = asyncio.run(
        run_health_checks(
            db_url=db_url,
            redis_url=redis_url,
            timeout=timeout,
        )
    )

    sys.exit(exit_code)


async def run_health_checks(
    db_url: str,
    redis_url: str,
    timeout: int,
) -> int:
    """
    Run health checks.

    Args:
        db_url: Database URL
        redis_url: Redis URL
        timeout: Connection timeout

    Returns:
        Exit code (0 = healthy, 1 = unhealthy)
    """
    results: dict[str, dict[str, Any]] = {}
    all_healthy = True

    # Check database
    logger.info("Checking database health...")
    db_result = await check_database_health(db_url, timeout)
    results["database"] = db_result
    if not db_result["healthy"]:
        all_healthy = False
        logger.error(f"Database unhealthy: {db_result.get('error', 'Unknown error')}")
    else:
        logger.info(f"Database healthy: {db_result.get('message', '')}")

    # Check Redis
    logger.info("Checking Redis health...")
    redis_result = await check_redis_health(redis_url, timeout)
    results["redis"] = redis_result
    if not redis_result["healthy"]:
        all_healthy = False
        logger.error(f"Redis unhealthy: {redis_result.get('error', 'Unknown error')}")
    else:
        logger.info(f"Redis healthy: {redis_result.get('message', '')}")

    # Check service status from database
    logger.info("Checking service status...")
    service_result = await check_service_status(db_url, timeout)
    results["services"] = service_result

    # Print summary
    print("\n" + "=" * 50)
    print("HEALTH CHECK SUMMARY")
    print("=" * 50)

    for check_name, result in results.items():
        status = "✓ HEALTHY" if result.get("healthy") else "✗ UNHEALTHY"
        print(f"{check_name.upper()}: {status}")

        if verbose and "details" in result:
            for key, value in result["details"].items():
                print(f"  {key}: {value}")

        if "error" in result:
            print(f"  Error: {result['error']}")

    print("=" * 50)

    if all_healthy:
        print("OVERALL: ✓ ALL SYSTEMS HEALTHY")
        return 0
    else:
        print("OVERALL: ✗ SYSTEMS UNHEALTHY")
        return 1


async def _init_utc(conn):
    await conn.execute("SET timezone = 'UTC'")


async def check_database_health(
    db_url: str,
    timeout: int,
) -> dict[str, Any]:
    """
    Check database health.

    Args:
        db_url: Database URL
        timeout: Connection timeout

    Returns:
        Health check result dictionary
    """
    start_time = datetime.now(UTC)
    db_pool: Optional[asyncpg.Pool] = None

    try:
        # Try to connect
        db_pool = await asyncio.wait_for(
            asyncpg.create_pool(
                dsn=db_url,
                min_size=1,
                max_size=2,
                timeout=timeout,
                init=_init_utc,
            ),
            timeout=timeout,
        )

        # Execute simple query
        async with db_pool.acquire() as conn:
            result = await conn.fetchval("SELECT 1")
            if result != 1:
                return {
                    "healthy": False,
                    "error": "Query returned unexpected result",
                }

        latency_ms = (datetime.now(UTC) - start_time).total_seconds() * 1000

        return {
            "healthy": True,
            "message": f"Connection successful ({latency_ms:.1f}ms)",
            "latency_ms": round(latency_ms, 1),
        }

    except asyncio.TimeoutError:
        return {
            "healthy": False,
            "error": f"Connection timeout after {timeout}s",
        }

    except asyncpg.PostgresError as e:
        return {
            "healthy": False,
            "error": f"PostgreSQL error: {str(e)}",
        }

    except Exception as e:
        return {
            "healthy": False,
            "error": f"Unexpected error: {str(e)}",
        }

    finally:
        if db_pool is not None:
            await db_pool.close()


async def check_redis_health(
    redis_url: str,
    timeout: int,
) -> dict[str, Any]:
    """
    Check Redis health.

    Args:
        redis_url: Redis URL
        timeout: Connection timeout

    Returns:
        Health check result dictionary
    """
    start_time = datetime.now(UTC)

    try:
        # Import redis here to avoid dependency if not used
        import redis.asyncio as redis

        # Try to connect
        client = redis.from_url(redis_url)

        # Ping with timeout
        await asyncio.wait_for(
            client.ping(),
            timeout=timeout,
        )

        latency_ms = (datetime.now(UTC) - start_time).total_seconds() * 1000

        await client.close()

        return {
            "healthy": True,
            "message": f"Connection successful ({latency_ms:.1f}ms)",
            "latency_ms": round(latency_ms, 1),
        }

    except asyncio.TimeoutError:
        return {
            "healthy": False,
            "error": f"Connection timeout after {timeout}s",
        }

    except ImportError:
        return {
            "healthy": True,
            "message": "Redis not installed (optional)",
            "warning": "redis-py not installed",
        }

    except Exception as e:
        return {
            "healthy": False,
            "error": f"Redis error: {str(e)}",
        }


async def check_service_status(
    db_url: str,
    timeout: int,
) -> dict[str, Any]:
    """
    Check service status from database.

    Args:
        db_url: Database URL
        timeout: Connection timeout

    Returns:
        Health check result dictionary
    """
    db_pool: Optional[asyncpg.Pool] = None

    try:
        db_pool = await asyncpg.create_pool(
            dsn=db_url,
            min_size=1,
            max_size=2,
            timeout=timeout,
            init=_init_utc,
        )

        async with db_pool.acquire() as conn:
            # Check if service_health table exists and has recent heartbeats
            try:
                rows = await conn.fetch("""
                    SELECT service_name, status, last_heartbeat
                    FROM service_health
                    WHERE last_heartbeat > NOW() - INTERVAL '5 minutes'
                    ORDER BY service_name
                    """)

                services: list[dict[str, str]] = []
                for row in rows:
                    services.append(
                        {
                            "name": row["service_name"],
                            "status": row["status"],
                            "heartbeat": str(row["last_heartbeat"]),
                        }
                    )

                return {
                    "healthy": True,
                    "details": {
                        "active_services": len(services),
                        "services": services,
                    },
                }

            except asyncpg.UndefinedTableError:
                return {
                    "healthy": True,
                    "details": {
                        "active_services": 0,
                        "note": "service_health table not found (first run)",
                    },
                }

    except Exception as e:
        return {
            "healthy": False,
            "error": f"Service status check failed: {str(e)}",
        }

    finally:
        if db_pool is not None:
            await db_pool.close()


if __name__ == "__main__":
    main()
