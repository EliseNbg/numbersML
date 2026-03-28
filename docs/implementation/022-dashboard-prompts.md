# Step 022: Web Dashboard - LLM Coder Agent Prompts

**Use these prompts sequentially** to implement the dashboard. Each prompt is self-contained and builds on previous steps.

---

## 📋 How to Use

1. **Copy one prompt at a time**
2. **Paste to LLM Coder Agent**
3. **Review generated code**
4. **Test before proceeding to next prompt**
5. **Commit after each successful step**

---

## Prompt 1: Domain Models (Step 022.1)

```markdown
# Task: Create Domain Models for Dashboard

**Context**: Building a web dashboard for crypto trading data pipeline monitoring (Step 022).

**Architecture**: Domain-Driven Design (DDD)
- Domain layer: Pure Python, no external dependencies
- Location: `src/domain/models/`

## Requirements

Create the following domain models:

### 1. `src/domain/models/dashboard.py`

```python
"""Dashboard entities for pipeline monitoring."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional


@dataclass
class CollectorStatus:
    """Status of the ticker collector service."""
    is_running: bool
    pid: Optional[int]
    uptime_seconds: Optional[float]
    last_tick_time: Optional[datetime]
    ticks_processed: int
    errors: int


@dataclass
class SLAMetric:
    """Single SLA measurement."""
    timestamp: datetime
    avg_time_ms: float
    max_time_ms: float
    sla_violations: int
    ticks_processed: int


@dataclass
class DashboardStats:
    """Quick statistics for dashboard."""
    ticks_per_minute: int
    avg_processing_time_ms: float
    sla_compliance_pct: float
    active_symbols_count: int
    active_indicators_count: int
```

### 2. `src/domain/models/config.py`

```python
"""Configuration entities."""

from dataclasses import dataclass
from datetime import datetime
from typing import Dict, Any, Optional


@dataclass
class ConfigEntry:
    """Single configuration entry."""
    id: int
    key: str
    value: Dict[str, Any]
    description: Optional[str]
    is_sensitive: bool
    is_editable: bool
    version: int
    updated_at: datetime
    updated_by: Optional[str]


@dataclass
class SymbolConfig:
    """Symbol configuration."""
    symbol_id: int
    symbol: str
    base_asset: str
    quote_asset: str
    is_active: bool
    is_allowed: bool
    tick_size: float
    step_size: float
    min_notional: float


@dataclass
class IndicatorConfig:
    """Indicator configuration."""
    name: str
    class_name: str
    module_path: str
    category: str
    params: Dict[str, Any]
    is_active: bool
    created_at: datetime
    updated_at: datetime
```

## Coding Standards

Per CODING-STANDARDS.md:
- ✅ Type hints on all fields and functions
- ✅ Comprehensive docstrings
- ✅ Dataclasses for entities
- ✅ No external dependencies in domain layer
- ✅ Pure Python (no framework annotations)

## Deliverables

1. `src/domain/models/dashboard.py` - Dashboard entities
2. `src/domain/models/config.py` - Configuration entities
3. Update `src/domain/models/__init__.py` to export new models

## Tests

Create basic unit tests:
- `tests/unit/domain/models/test_dashboard.py`
- `tests/unit/domain/models/test_config.py`

Test:
- Entity creation
- Field types
- Default values

---

**Start Implementation**: Create the domain models following DDD principles.
```

---

## Prompt 2: Application Services (Step 022.2)

```markdown
# Task: Create Application Services for Dashboard

**Context**: Building web dashboard (Step 022). Domain models created in Step 022.1.

**Architecture**: Application Layer (orchestration)
- Location: `src/application/services/`
- Dependencies: Domain layer only

## Requirements

Create the following application services:

### 1. `src/application/services/pipeline_monitor.py`

```python
"""Pipeline monitoring service."""

from typing import List, Optional
import asyncpg

from src.domain.models.dashboard import CollectorStatus, SLAMetric, DashboardStats


class PipelineMonitor:
    """
    Monitor pipeline performance and collector status.
    
    Responsibilities:
    - Check if collector process is running
    - Start/stop collector
    - Fetch SLA metrics from database
    - Calculate dashboard statistics
    """
    
    def __init__(self, db_pool: asyncpg.Pool) -> None:
        """Initialize with database pool."""
        pass
    
    async def get_collector_status(self) -> CollectorStatus:
        """Get current collector service status."""
        pass
    
    async def start_collector(self) -> bool:
        """Start collector service."""
        pass
    
    async def stop_collector(self) -> bool:
        """Stop collector service."""
        pass
    
    async def get_sla_metrics(self, seconds: int = 60) -> List[SLAMetric]:
        """Get SLA metrics for last N seconds."""
        pass
    
    async def get_dashboard_stats(self) -> DashboardStats:
        """Get quick dashboard statistics."""
        pass
```

### 2. `src/application/services/symbol_manager.py`

```python
"""Symbol management service."""

from typing import List, Optional
import asyncpg

from src.domain.models.config import SymbolConfig


class SymbolManager:
    """
    Manage symbol activation/deactivation.
    
    Responsibilities:
    - List all symbols
    - Activate/deactivate symbols
    - Update symbol configuration
    """
    
    def __init__(self, db_pool: asyncpg.Pool) -> None:
        """Initialize with database pool."""
        pass
    
    async def list_symbols(
        self,
        active_only: bool = False
    ) -> List[SymbolConfig]:
        """List all symbols, optionally filtered by active status."""
        pass
    
    async def activate_symbol(self, symbol_id: int) -> bool:
        """Activate a symbol."""
        pass
    
    async def deactivate_symbol(self, symbol_id: int) -> bool:
        """Deactivate a symbol."""
        pass
    
    async def update_symbol(self, symbol: SymbolConfig) -> bool:
        """Update symbol configuration."""
        pass
```

### 3. `src/application/services/indicator_manager.py`

```python
"""Indicator management service."""

from typing import List, Optional, Dict, Any
import asyncpg

from src.domain.models.config import IndicatorConfig


class IndicatorManager:
    """
    Manage indicator registration and activation.
    
    Responsibilities:
    - List all indicators
    - Register new indicators
    - Activate/deactivate indicators
    - Update indicator parameters
    """
    
    def __init__(self, db_pool: asyncpg.Pool) -> None:
        """Initialize with database pool."""
        pass
    
    async def list_indicators(
        self,
        active_only: bool = False,
        category: Optional[str] = None
    ) -> List[IndicatorConfig]:
        """List indicators with optional filters."""
        pass
    
    async def register_indicator(
        self,
        name: str,
        class_name: str,
        module_path: str,
        category: str,
        params: Dict[str, Any],
        is_active: bool = True
    ) -> bool:
        """Register a new indicator."""
        pass
    
    async def activate_indicator(self, name: str) -> bool:
        """Activate an indicator."""
        pass
    
    async def deactivate_indicator(self, name: str) -> bool:
        """Deactivate an indicator."""
        pass
    
    async def unregister_indicator(self, name: str) -> bool:
        """Unregister an indicator (soft delete)."""
        pass
```

### 4. `src/application/services/config_manager.py`

```python
"""Configuration management service."""

from typing import List, Dict, Any, Optional
import asyncpg


class ConfigManager:
    """
    Manage system configuration tables.
    
    Responsibilities:
    - Load configuration tables
    - Update configuration entries
    - Validate configuration changes
    """
    
    def __init__(self, db_pool: asyncpg.Pool) -> None:
        """Initialize with database pool."""
        pass
    
    async def get_table_data(
        self,
        table_name: str,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """Get data from configuration table."""
        pass
    
    async def update_entry(
        self,
        table_name: str,
        entry_id: int,
        data: Dict[str, Any]
    ) -> bool:
        """Update configuration entry."""
        pass
    
    async def insert_entry(
        self,
        table_name: str,
        data: Dict[str, Any]
    ) -> int:
        """Insert new configuration entry. Returns new ID."""
        pass
    
    async def delete_entry(
        self,
        table_name: str,
        entry_id: int
    ) -> bool:
        """Delete configuration entry."""
        pass
```

## Coding Standards

Per CODING-STANDARDS.md:
- ✅ Type hints on all functions
- ✅ Comprehensive docstrings
- ✅ Error handling with context
- ✅ Dependencies only on domain layer
- ✅ Functions < 50 lines
- ✅ Single responsibility per function

## Deliverables

1. `src/application/services/pipeline_monitor.py`
2. `src/application/services/symbol_manager.py`
3. `src/application/services/indicator_manager.py`
4. `src/application/services/config_manager.py`
5. Update `src/application/services/__init__.py`

## Tests

Create unit tests with mocked database:
- `tests/unit/application/services/test_pipeline_monitor.py`
- `tests/unit/application/services/test_symbol_manager.py`
- `tests/unit/application/services/test_indicator_manager.py`
- `tests/unit/application/services/test_config_manager.py`

---

**Start Implementation**: Create application services following DDD principles.
```

---

## Prompt 3: Infrastructure Repositories (Step 022.3)

```markdown
# Task: Create Infrastructure Repositories

**Context**: Building web dashboard (Step 022). Application services created in Step 022.2.

**Architecture**: Infrastructure Layer (data access)
- Location: `src/infrastructure/repositories/`
- Dependencies: Domain + Application layers

## Requirements

Create repository implementations:

### 1. `src/infrastructure/repositories/pipeline_metrics_repo.py`

```python
"""Pipeline metrics data access."""

from typing import List, Optional
from datetime import datetime, timedelta
import asyncpg

from src.domain.models.dashboard import SLAMetric


class PipelineMetricsRepository:
    """Repository for pipeline_metrics table."""
    
    def __init__(self, db_pool: asyncpg.Pool) -> None:
        """Initialize with database pool."""
        self.db_pool = db_pool
    
    async def get_sla_metrics(
        self,
        seconds: int = 60
    ) -> List[SLAMetric]:
        """
        Get SLA metrics for last N seconds.
        
        Query:
            SELECT 
                DATE_TRUNC('second', timestamp) as second,
                AVG(total_time_ms) as avg_time_ms,
                MAX(total_time_ms) as max_time_ms,
                COUNT(*) FILTER (WHERE total_time_ms > 1000) as sla_violations,
                COUNT(*) as ticks_processed
            FROM pipeline_metrics
            WHERE timestamp > NOW() - INTERVAL 'N seconds'
            GROUP BY DATE_TRUNC('second', timestamp)
            ORDER BY second
        """
        pass
    
    async def get_collector_pid(self) -> Optional[int]:
        """Get collector process PID from service_status table."""
        pass
    
    async def get_last_tick_time(self) -> Optional[datetime]:
        """Get last tick timestamp from ticker_24hr_stats."""
        pass
```

### 2. `src/infrastructure/repositories/symbol_repo.py`

```python
"""Symbol data access."""

from typing import List, Optional
import asyncpg

from src.domain.models.config import SymbolConfig


class SymbolRepository:
    """Repository for symbols table."""
    
    def __init__(self, db_pool: asyncpg.Pool) -> None:
        """Initialize with database pool."""
        self.db_pool = db_pool
    
    async def list_all(
        self,
        active_only: bool = False
    ) -> List[SymbolConfig]:
        """List all symbols."""
        pass
    
    async def get_by_id(self, symbol_id: int) -> Optional[SymbolConfig]:
        """Get symbol by ID."""
        pass
    
    async def update_active(
        self,
        symbol_id: int,
        is_active: bool
    ) -> bool:
        """Update symbol active status."""
        pass
    
    async def update(self, symbol: SymbolConfig) -> bool:
        """Update symbol configuration."""
        pass
```

### 3. `src/infrastructure/repositories/indicator_repo.py`

```python
"""Indicator data access."""

from typing import List, Optional, Dict, Any
import asyncpg
import json

from src.domain.models.config import IndicatorConfig


class IndicatorRepository:
    """Repository for indicator_definitions table."""
    
    def __init__(self, db_pool: asyncpg.Pool) -> None:
        """Initialize with database pool."""
        self.db_pool = db_pool
    
    async def list_all(
        self,
        active_only: bool = False,
        category: Optional[str] = None
    ) -> List[IndicatorConfig]:
        """List indicators with optional filters."""
        pass
    
    async def get_by_name(self, name: str) -> Optional[IndicatorConfig]:
        """Get indicator by name."""
        pass
    
    async def insert(
        self,
        name: str,
        class_name: str,
        module_path: str,
        category: str,
        params: Dict[str, Any],
        is_active: bool = True
    ) -> bool:
        """Register new indicator."""
        pass
    
    async def update_active(
        self,
        name: str,
        is_active: bool
    ) -> bool:
        """Update indicator active status."""
        pass
    
    async def delete(self, name: str) -> bool:
        """Soft delete indicator (set is_active=false)."""
        pass
```

## Coding Standards

Per CODING-STANDARDS.md:
- ✅ Type hints on all functions
- ✅ Comprehensive docstrings with SQL queries
- ✅ Error handling with context
- ✅ Use asyncpg for database access
- ✅ Parse JSONB fields properly
- ✅ Close database connections properly

## Deliverables

1. `src/infrastructure/repositories/pipeline_metrics_repo.py`
2. `src/infrastructure/repositories/symbol_repo.py`
3. `src/infrastructure/repositories/indicator_repo.py`
4. Update `src/infrastructure/repositories/__init__.py`

## Tests

Create integration tests with real database:
- `tests/integration/repositories/test_pipeline_metrics_repo.py`
- `tests/integration/repositories/test_symbol_repo.py`
- `tests/integration/repositories/test_indicator_repo.py`

---

**Start Implementation**: Create repository implementations.
```

---

## Prompt 4: FastAPI Routes (Step 022.4)

```markdown
# Task: Create FastAPI API Routes

**Context**: Building web dashboard (Step 022). Repositories created in Step 022.3.

**Architecture**: Infrastructure Layer (API)
- Location: `src/infrastructure/api/routes/`
- Dependencies: Application services

## Requirements

Create FastAPI route modules:

### 1. `src/infrastructure/api/routes/dashboard.py`

```python
"""Dashboard API endpoints."""

from fastapi import APIRouter, Depends, HTTPException
from typing import List

from src.application.services.pipeline_monitor import PipelineMonitor
from src.domain.models.dashboard import CollectorStatus, SLAMetric, DashboardStats

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("/status", response_model=CollectorStatus)
async def get_collector_status(
    monitor: PipelineMonitor = Depends()
) -> CollectorStatus:
    """Get collector service status."""
    pass


@router.post("/collector/start")
async def start_collector(
    monitor: PipelineMonitor = Depends()
) -> dict:
    """Start collector service."""
    pass


@router.post("/collector/stop")
async def stop_collector(
    monitor: PipelineMonitor = Depends()
) -> dict:
    """Stop collector service."""
    pass


@router.get("/metrics", response_model=List[SLAMetric])
async def get_sla_metrics(
    seconds: int = 60,
    monitor: PipelineMonitor = Depends()
) -> List[SLAMetric]:
    """Get SLA metrics for last N seconds."""
    pass


@router.get("/stats", response_model=DashboardStats)
async def get_dashboard_stats(
    monitor: PipelineMonitor = Depends()
) -> DashboardStats:
    """Get quick dashboard statistics."""
    pass
```

### 2. `src/infrastructure/api/routes/symbols.py`

```python
"""Symbol management API endpoints."""

from fastapi import APIRouter, Depends, HTTPException
from typing import List

from src.application.services.symbol_manager import SymbolManager
from src.domain.models.config import SymbolConfig

router = APIRouter(prefix="/api/symbols", tags=["symbols"])


@router.get("", response_model=List[SymbolConfig])
async def list_symbols(
    active_only: bool = False,
    manager: SymbolManager = Depends()
) -> List[SymbolConfig]:
    """List all symbols."""
    pass


@router.put("/{symbol_id}/activate")
async def activate_symbol(
    symbol_id: int,
    manager: SymbolManager = Depends()
) -> dict:
    """Activate a symbol."""
    pass


@router.put("/{symbol_id}/deactivate")
async def deactivate_symbol(
    symbol_id: int,
    manager: SymbolManager = Depends()
) -> dict:
    """Deactivate a symbol."""
    pass


@router.put("/{symbol_id}")
async def update_symbol(
    symbol_id: int,
    symbol: SymbolConfig,
    manager: SymbolManager = Depends()
) -> dict:
    """Update symbol configuration."""
    pass
```

### 3. `src/infrastructure/api/routes/indicators.py`

```python
"""Indicator management API endpoints."""

from fastapi import APIRouter, Depends, HTTPException
from typing import List, Optional

from src.application.services.indicator_manager import IndicatorManager
from src.domain.models.config import IndicatorConfig

router = APIRouter(prefix="/api/indicators", tags=["indicators"])


@router.get("", response_model=List[IndicatorConfig])
async def list_indicators(
    active_only: bool = False,
    category: Optional[str] = None,
    manager: IndicatorManager = Depends()
) -> List[IndicatorConfig]:
    """List indicators with optional filters."""
    pass


@router.post("")
async def register_indicator(
    indicator: IndicatorConfig,
    manager: IndicatorManager = Depends()
) -> dict:
    """Register a new indicator."""
    pass


@router.put("/{name}/activate")
async def activate_indicator(
    name: str,
    manager: IndicatorManager = Depends()
) -> dict:
    """Activate an indicator."""
    pass


@router.put("/{name}/deactivate")
async def deactivate_indicator(
    name: str,
    manager: IndicatorManager = Depends()
) -> dict:
    """Deactivate an indicator."""
    pass


@router.delete("/{name}")
async def unregister_indicator(
    name: str,
    manager: IndicatorManager = Depends()
) -> dict:
    """Unregister an indicator."""
    pass
```

### 4. `src/infrastructure/api/routes/config.py`

```python
"""Configuration API endpoints."""

from fastapi import APIRouter, Depends, HTTPException
from typing import List, Dict, Any

from src.application.services.config_manager import ConfigManager

router = APIRouter(prefix="/api/config", tags=["config"])


@router.get("/{table_name}")
async def get_table_data(
    table_name: str,
    limit: int = 100,
    manager: ConfigManager = Depends()
) -> List[Dict[str, Any]]:
    """Get data from configuration table."""
    pass


@router.put("/{table_name}/{entry_id}")
async def update_entry(
    table_name: str,
    entry_id: int,
    data: Dict[str, Any],
    manager: ConfigManager = Depends()
) -> dict:
    """Update configuration entry."""
    pass


@router.post("/{table_name}")
async def insert_entry(
    table_name: str,
    data: Dict[str, Any],
    manager: ConfigManager = Depends()
) -> dict:
    """Insert new configuration entry."""
    pass


@router.delete("/{table_name}/{entry_id}")
async def delete_entry(
    table_name: str,
    entry_id: int,
    manager: ConfigManager = Depends()
) -> dict:
    """Delete configuration entry."""
    pass
```

## Coding Standards

Per CODING-STANDARDS.md:
- ✅ Type hints on all endpoints
- ✅ Comprehensive docstrings
- ✅ Error handling with HTTPException
- ✅ Use Depends for dependency injection
- ✅ Response models for all endpoints
- ✅ Tags for OpenAPI documentation

## Deliverables

1. `src/infrastructure/api/routes/dashboard.py`
2. `src/infrastructure/api/routes/symbols.py`
3. `src/infrastructure/api/routes/indicators.py`
4. `src/infrastructure/api/routes/config.py`
5. Update `src/infrastructure/api/routes/__init__.py`

## Tests

Create API integration tests:
- `tests/integration/api/test_dashboard_api.py`
- `tests/integration/api/test_symbols_api.py`
- `tests/integration/api/test_indicators_api.py`
- `tests/integration/api/test_config_api.py`

---

**Start Implementation**: Create FastAPI route modules.
```

---

## Prompt 5: FastAPI Application (Step 022.5)

```markdown
# Task: Create FastAPI Application & CLI

**Context**: Building web dashboard (Step 022). Routes created in Step 022.4.

**Architecture**: Infrastructure Layer (Application bootstrap)
- Location: `src/infrastructure/api/`

## Requirements

### 1. Create FastAPI Application

`src/infrastructure/api/app.py`:

```python
"""FastAPI application for dashboard."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import asyncpg
from contextlib import asynccontextmanager

from src.infrastructure.api.routes import (
    dashboard,
    symbols,
    indicators,
    config,
)


# Database pool
db_pool = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifespan."""
    global db_pool
    
    # Startup: Create database pool
    db_pool = await asyncpg.create_pool(
        "postgresql://crypto:crypto_secret@localhost:5432/crypto_trading",
        min_size=2,
        max_size=10,
    )
    
    yield
    
    # Shutdown: Close database pool
    if db_pool:
        await db_pool.close()


# Create FastAPI application
app = FastAPI(
    title="Crypto Trading Dashboard",
    description="Real-time monitoring and control for crypto trading data pipeline",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS for local development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8000", "http://127.0.0.1:8000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(dashboard.router)
app.include_router(symbols.router)
app.include_router(indicators.router)
app.include_router(config.router)

# Serve static files (dashboard frontend)
app.mount("/dashboard", StaticFiles(directory="dashboard", html=True), name="dashboard")


@app.get("/")
async def root():
    """Root endpoint - redirect to dashboard."""
    return {"message": "Dashboard API", "docs": "/docs"}
```

### 2. Create CLI Entry Point

`src/cli/start_dashboard.py`:

```python
#!/usr/bin/env python3
"""
Start Dashboard CLI

Usage:
    python -m src.cli.start_dashboard

Or:
    .venv/bin/python src/cli/start_dashboard.py
"""

import uvicorn
import argparse
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def main():
    """Start dashboard server."""
    parser = argparse.ArgumentParser(description='Start Crypto Trading Dashboard')
    parser.add_argument(
        '--host',
        type=str,
        default='0.0.0.0',
        help='Host to bind to (default: 0.0.0.0)'
    )
    parser.add_argument(
        '--port',
        type=int,
        default=8000,
        help='Port to bind to (default: 8000)'
    )
    parser.add_argument(
        '--reload',
        action='store_true',
        help='Enable auto-reload for development'
    )
    
    args = parser.parse_args()
    
    logger.info("=" * 60)
    logger.info("Starting Crypto Trading Dashboard")
    logger.info("=" * 60)
    logger.info(f"Host: {args.host}")
    logger.info(f"Port: {args.port}")
    logger.info(f"Reload: {args.reload}")
    logger.info("=" * 60)
    logger.info("Dashboard: http://localhost:8000/dashboard/")
    logger.info("API Docs:  http://localhost:8000/docs")
    logger.info("=" * 60)
    
    uvicorn.run(
        "src.infrastructure.api.app:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
    )


if __name__ == '__main__':
    main()
```

## Deliverables

1. `src/infrastructure/api/app.py` - FastAPI application
2. `src/cli/start_dashboard.py` - CLI entry point
3. Update `src/infrastructure/api/__init__.py`

## Test

```bash
# Start dashboard
.venv/bin/python src/cli/start_dashboard.py --reload

# Verify:
# - Dashboard: http://localhost:8000/dashboard/
# - API Docs: http://localhost:8000/docs
```

---

**Start Implementation**: Create FastAPI application and CLI.
```

---

**Continue with Prompts 6-12** for frontend implementation in next message...
