"""
FastAPI application for dashboard.

This module creates and configures the FastAPI application with:
- All API routes
- Database connection pool
- CORS middleware
- Static files for frontend
- Lifespan management

Usage:
    from src.infrastructure.api.app import create_app
    app = create_app()
"""

import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

import asyncpg
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from src.infrastructure.api.routes import (
    dashboard_router,
    symbols_router,
    indicators_router,
    config_router,
    pipeline_router,
)
from src.infrastructure.database import set_db_pool, get_db_pool, get_db_pool_async
from src.pipeline.service import PipelineManager, set_pipeline_manager

logger = logging.getLogger(__name__)

# Database configuration
DATABASE_URL = "postgresql://crypto:crypto_secret@localhost:5432/crypto_trading"

# Pipeline manager is managed in src.pipeline.service


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """
    Manage application lifespan.

    Handles:
        - Database pool creation on startup
        - Pipeline manager initialization
        - Database pool cleanup on shutdown
    """
    global db_pool

    # Startup
    logger.info("Starting dashboard application...")
    logger.info(f"Connecting to database: {DATABASE_URL.split('@')[-1]}")

    try:
        db_pool = await asyncpg.create_pool(
            DATABASE_URL,
            min_size=2,
            max_size=10,
            timeout=30,
        )
        set_db_pool(db_pool)
        
        # Initialize pipeline manager
        pipeline_manager = PipelineManager(db_pool)
        set_pipeline_manager(pipeline_manager)
        
        logger.info("Database pool created successfully")
        logger.info("Pipeline manager initialized")

    except Exception as e:
        logger.error(f"Failed to create database pool: {e}")
        raise

    yield

    # Shutdown
    logger.info("Shutting down dashboard application...")

    if db_pool:
        await db_pool.close()
        logger.info("Database pool closed")


def create_app() -> FastAPI:
    """
    Create and configure FastAPI application.
    
    Returns:
        Configured FastAPI application
    """
    # Create application
    app = FastAPI(
        title="Crypto Trading Dashboard",
        description="""
## Real-time monitoring and control for crypto trading data pipeline

### Features
- **Dashboard**: Monitor collector status and SLA compliance
- **Symbols**: Manage active symbols for data collection
- **Indicators**: Register and configure technical indicators
- **Configuration**: Edit system configuration tables

### Authentication
Currently no authentication. Add authentication middleware for production use.
        """,
        version="1.0.0",
        lifespan=lifespan,
    )
    
    # Configure CORS for local development
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:8000",
            "http://127.0.0.1:8000",
            "http://localhost:3000",  # React dev server
            "http://127.0.0.1:3000",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    # Include API routers
    app.include_router(dashboard_router)
    app.include_router(symbols_router)
    app.include_router(indicators_router)
    app.include_router(config_router)
    app.include_router(pipeline_router)
    
    # Mount static files for frontend (dashboard)
    # Note: Frontend files will be created in Step 022.6
    try:
        app.mount(
            "/dashboard",
            StaticFiles(directory="dashboard", html=True),
            name="dashboard",
        )
        logger.info("Frontend static files mounted at /dashboard")
    except Exception:
        logger.warning("Frontend directory not found - dashboard UI not available")
    
    # Root endpoint
    @app.get("/", tags=["root"])
    async def root() -> dict:
        """
        Root endpoint.
        
        Returns:
            Welcome message and links
        """
        return {
            "message": "Crypto Trading Dashboard API",
            "version": "1.0.0",
            "docs": "/docs",
            "redoc": "/redoc",
            "dashboard": "/dashboard",
        }
    
    # Health check endpoint
    @app.get("/health", tags=["health"])
    async def health_check() -> dict:
        """
        Health check endpoint.
        
        Returns:
            Health status
        """
        try:
            pool = get_db_pool()
            db_status = "connected"
        except RuntimeError:
            db_status = "disconnected"
        
        return {
            "status": "healthy",
            "database": db_status,
        }
    
    logger.info("FastAPI application created successfully")
    
    return app


# Create application instance
app = create_app()


if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        "app:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
    )
