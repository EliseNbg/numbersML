#!/usr/bin/env python3
"""
Start Dashboard CLI

Starts the FastAPI dashboard server.

Usage:
    python -m src.cli.start_dashboard

Or:
    .venv/bin/python src/cli/start_dashboard.py

Options:
    --host HOST     Host to bind to (default: 0.0.0.0)
    --port PORT     Port to bind to (default: 8000)
    --reload        Enable auto-reload for development
    --log-level     Logging level (default: INFO)
"""

# Add user site-packages AND .venv FIRST (before any other imports)
import os
import sys

# Get project root (parent of src/cli/)
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(script_dir))

# Add .venv site-packages if it exists
venv_site = os.path.join(project_root, ".venv", "lib", "python3.13", "site-packages")
if os.path.exists(venv_site) and venv_site not in sys.path:
    sys.path.insert(0, venv_site)

# Add user site-packages as fallback
USER_SITE = "/home/andy/.local/lib/python3.13/site-packages"
if USER_SITE not in sys.path:
    sys.path.insert(0, USER_SITE)

import argparse
import logging
import sys

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    """
    Parse command line arguments.

    Returns:
        Parsed arguments
    """
    parser = argparse.ArgumentParser(
        description="Start Crypto Trading Dashboard",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Start with defaults
  python -m src.cli.start_dashboard

  # Start on specific port
  python -m src.cli.start_dashboard --port 8080

  # Enable auto-reload for development
  python -m src.cli.start_dashboard --reload

  # Set log level to debug
  python -m src.cli.start_dashboard --log-level DEBUG
        """,
    )

    parser.add_argument(
        "--host", type=str, default="0.0.0.0", help="Host to bind to (default: 0.0.0.0)"
    )

    parser.add_argument("--port", type=int, default=8000, help="Port to bind to (default: 8000)")

    parser.add_argument("--reload", action="store_true", help="Enable auto-reload for development")

    parser.add_argument(
        "--log-level",
        type=str,
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Logging level (default: INFO)",
    )

    return parser.parse_args()


def main() -> int:
    """
    Start dashboard server.

    Returns:
        Exit code (0 for success, 1 for error)
    """
    args = parse_args()

    # Set logging level
    logging.getLogger().setLevel(getattr(logging, args.log_level))

    logger.info("=" * 70)
    logger.info("Starting Crypto Trading Dashboard")
    logger.info("=" * 70)
    logger.info(f"Host: {args.host}")
    logger.info(f"Port: {args.port}")
    logger.info(f"Reload: {args.reload}")
    logger.info(f"Log Level: {args.log_level}")
    logger.info("=" * 70)
    logger.info("Dashboard UI: http://localhost:8000/dashboard/")
    logger.info("API Docs:     http://localhost:8000/docs")
    logger.info("ReDoc:        http://localhost:8000/redoc")
    logger.info("Health Check: http://localhost:8000/health")
    logger.info("=" * 70)

    try:
        import uvicorn

        uvicorn.run(
            "src.infrastructure.api.app:app",
            host=args.host,
            port=args.port,
            reload=args.reload,
            log_level=args.log_level.lower(),
        )

        return 0

    except ImportError:
        logger.error("uvicorn not installed. Install with: pip install uvicorn")
        return 1

    except KeyboardInterrupt:
        logger.info("\nDashboard stopped by user")
        return 0

    except Exception as e:
        logger.error(f"Failed to start dashboard: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
