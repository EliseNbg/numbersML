# LLM Agent Requirements - Summary

## Quick Reference for LLM Agents

**Copy this into your prompts when requesting code from LLM agents.**

---

## Mandatory Requirements

### 1. Architecture Principles

```
✅ KISS (Keep It Simple, Stupid)
   - Simple is better than complex
   - Readable is better than clever
   - Functions < 50 lines, do ONE thing

✅ DDD (Domain-Driven Design)
   - Domain Layer: Pure Python, business logic
   - Application Layer: Orchestration, use cases
   - Infrastructure Layer: Implementations, adapters
   - Dependencies point inward only

✅ Hexagonal Architecture (Ports & Adapters)
   - Ports: Interfaces in domain layer
   - Adapters: Implementations in infrastructure
   - Dependency injection throughout
```

### 2. Code Quality

```python
# ✅ Type Hints (MANDATORY)
def calculate_sma(
    prices: Sequence[Decimal],
    period: int
) -> Optional[Decimal]:
    """Calculate Simple Moving Average."""

# ✅ Documentation (COMPREHENSIVE)
class TickerCollector:
    """
    Collects 24hr ticker statistics from Binance.
    
    Purpose: ...
    Example: ...
    Attributes: ...
    """

# ✅ Error Handling (EXPLICIT)
try:
    await self.conn.execute(query, params)
except asyncpg.PostgresError as e:
    logger.error(f"Database error: {e}", extra={'context': ...})
    raise TickerStorageError("Failed to store") from e
```

### 3. Layer Rules

```
┌─────────────────────────────────────┐
│   DOMAIN LAYER (Pure Python)        │
│   - Entities, Value Objects         │
│   - NO external dependencies        │
└─────────────────────────────────────┘
              ↓
┌─────────────────────────────────────┐
│ APPLICATION LAYER (Orchestration)   │
│   - Use Cases, Commands, Queries    │
│   - Depends on Domain only          │
└─────────────────────────────────────┘
              ↓
┌─────────────────────────────────────┐
│ INFRASTRUCTURE LAYER (Adapters)     │
│   - PostgreSQL, Binance, Redis      │
│   - Implements Domain interfaces    │
└─────────────────────────────────────┘
```

### 4. Testing Requirements

```python
# ✅ Test Structure (Arrange-Act-Assert)
def test_create_valid_symbol(self) -> None:
    # Arrange
    symbol_data = {'id': 1, 'symbol': 'BTC/USDT', ...}
    
    # Act
    symbol = Symbol(**symbol_data)
    
    # Assert
    assert symbol.id == 1
    assert symbol.symbol == 'BTC/USDT'

# ✅ Coverage Targets
Domain Layer:      90%+
Application Layer: 80%+
Infrastructure:    70%+
```

---

## Prompt Template for LLM Agents

```
Implement [FEATURE] following these standards:

ARCHITECTURE:
- Use DDD with strict layer separation
- Domain layer: Pure Python, business logic
- Application layer: Use cases, orchestration
- Infrastructure layer: Adapters for DB/external services
- Hexagonal architecture (ports & adapters)

CODE QUALITY:
- KISS principle (simple, readable)
- Complete type hints for all parameters and returns
- Comprehensive docstrings (Args, Returns, Raises, Examples)
- Explicit error handling with context
- Functions < 50 lines, single responsibility

TESTING:
- Unit tests for domain logic
- Integration tests for repositories
- Coverage: 90%+ domain, 80%+ application
- Arrange-Act-Assert pattern

DOCUMENTATION:
- Module docstring
- Class docstrings with examples
- Method docstrings with Args/Returns/Raises
- Inline comments for complex logic

EXAMPLE:
See docs/CODING-STANDARDS.md for complete examples.

QUALITY OVER QUANTITY: Better to have less, working code 
than more, buggy code.
```

---

## Code Review Checklist

Before accepting code from LLM agent, verify:

### Architecture
- [ ] Domain layer has no external dependencies
- [ ] Application layer depends only on domain
- [ ] Infrastructure implements domain interfaces
- [ ] No circular dependencies

### Code Quality
- [ ] All functions have type hints
- [ ] All public methods have docstrings
- [ ] Error handling is explicit
- [ ] Functions are short and focused

### Testing
- [ ] Unit tests exist for domain logic
- [ ] Tests follow Arrange-Act-Assert
- [ ] Test coverage meets targets
- [ ] Tests are isolated

### Documentation
- [ ] Module has docstring
- [ ] Classes have docstrings with examples
- [ ] Methods document Args/Returns/Raises
- [ ] Complex logic is commented

---

## Example: Good vs Bad

### ❌ BAD Code

```python
def process(ticks, db):
    for t in ticks:
        try:
            db.execute("INSERT ...", t)
        except:
            pass
```

**Problems**:
- ❌ No type hints
- ❌ No docstring
- ❌ Bare `except:`
- ❌ No error context
- ❌ Does multiple things
- ❌ No layer separation

### ✅ GOOD Code

```python
class ProcessTicks(UseCase):
    """
    Use Case: Process and store tick data.
    
    Purpose: Validates ticks and stores in database.
    """
    
    def __init__(
        self,
        tick_repo: TickRepository,
        validator: TickValidator,
    ) -> None:
        """
        Initialize use case.
        
        Args:
            tick_repo: Repository for storing ticks (Port)
            validator: Validator for tick validation
        """
        self.tick_repo: TickRepository = tick_repo
        self.validator: TickValidator = validator
    
    async def execute(self, ticks: List[Tick]) -> ProcessTicksResult:
        """
        Process and store ticks.
        
        Args:
            ticks: List of ticks to process
        
        Returns:
            ProcessTicksResult with processing statistics
        
        Raises:
            TickProcessingError: If processing fails
        """
        logger.info(f"Processing {len(ticks)} ticks")
        
        try:
            valid_ticks: List[Tick] = [
                tick for tick in ticks
                if self.validator.validate(tick).passed
            ]
            
            await self.tick_repo.save_all(valid_ticks)
            
            return ProcessTicksResult(
                success=True,
                ticks_processed=len(valid_ticks),
            )
        
        except RepositoryError as e:
            logger.error(f"Failed to save ticks: {e}")
            raise TickProcessingError(
                f"Failed to process {len(ticks)} ticks",
                len(ticks)
            ) from e
```

**Qualities**:
- ✅ Complete type hints
- ✅ Comprehensive docstrings
- ✅ Explicit error handling
- ✅ Single responsibility
- ✅ Layer separation
- ✅ Dependency injection

---

## Key Documents

| Document | Purpose |
|----------|---------|
| [CODING-STANDARDS.md](CODING-STANDARDS.md) | Complete coding standards |
| [database-configuration-schema.md](database-configuration-schema.md) | Database configuration |
| [regional-configuration-eu.md](regional-configuration-eu.md) | EU compliance |
| [ticker-collector-design.md](ticker-collector-design.md) | Ticker collector design |
| [modular-service-architecture.md](modular-service-architecture.md) | Service architecture |

---

## Remember

> **Quality over Quantity**
> 
> Better to have less, working, well-documented code
> than more, buggy, undocumented code.

---

**These standards are MANDATORY for all code generated by LLM agents.**
