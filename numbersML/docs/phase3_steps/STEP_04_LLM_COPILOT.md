# Step 4: Strategy Source Code Management

## Objective

Provide API endpoints for managing user-written strategy source code (store, load, validate, delete).

## Scope

- Strategy source code API:
  - `GET /api/strategies/source` - List all strategy source files
  - `GET /api/strategies/source/{path}` - Load strategy source code
  - `PUT /api/strategies/source/{path}` - Store/update strategy source code
  - `DELETE /api/strategies/source/{path}` - Delete strategy file
  - `POST /api/strategies/source/validate` - Validate strategy syntax/structure
- Source code stored in `src/strategies/user/`
- Validation:
  - Python syntax check
  - Class definition presence
  - Strategy inheritance verification (best-effort)
- Security: Path traversal protection (only allow access to `src/strategies/user/`)

## Out of Scope

- LLM-based strategy generation (user writes code manually)
- Automatic strategy compilation/loading (handled by Step 3 lifecycle service)
- Version control (use git for source code versioning)

## Dependencies

- Step 3 Strategy Lifecycle Service (for loading class-based strategies)
- File system access to `src/strategies/user/`

## Deliverables

- New `src/infrastructure/api/routes/strategy_source.py` with all endpoints
- Update `src/infrastructure/api/app.py` to include new routes
- API documentation and examples
- Unit tests for all endpoints

## Acceptance Criteria

- User can list all strategy source files via API
- User can load strategy source code by class path
- User can save/update strategy source code via API
- User can delete strategy files (except `__init__.py`)
- Validation endpoint catches syntax errors before saving
- Path traversal attacks are prevented (403 for invalid paths)
- All endpoints require authentication (trader role)

## Implementation Prompt (Best Prompt for LLM)

```text
Implement Step 4 only: Strategy Source Code Management API.

Tasks:
1) Create `src/infrastructure/api/routes/strategy_source.py` with:
   - GET /api/strategies/source - List .py files in src/strategies/user/
   - GET /api/strategies/source/{class_path} - Return file content
   - PUT /api/strategies/source/{class_path} - Save file (with overwrite flag)
   - DELETE /api/strategies/source/{class_path} - Delete file (block __init__.py)
   - POST /api/strategies/source/validate - Validate syntax and structure

2) Implement helper functions:
   - Convert between file paths and Python class paths
   - Validate Python syntax using `compile()` or `ast.parse()`
   - Check if class inherits from Strategy (using AST parsing)
   - Path traversal protection (resolve paths, check parent directory)

3) Update `src/infrastructure/api/app.py` to include new router

4) Add response models:
   - StrategySourceResponse (file_path, class_path, size, modified_at)
   - StrategySourceContent (includes content)
   - StrategyValidationResult (valid, errors, warnings, class_found)

Constraints:
- All endpoints require authentication (use require_trader dependency)
- Only allow access to files within src/strategies/user/
- Validate Python syntax before saving
- Return appropriate HTTP status codes (200, 201, 204, 400, 403, 404, 409, 500)

Output:
- New file: src/infrastructure/api/routes/strategy_source.py
- Modified file: src/infrastructure/api/app.py
- Test results summary
```

## Testing Prompt (Best Prompt for LLM)

```text
Validate Step 4 Strategy Source Code Management API.

Tasks:
1) Execute unit tests for strategy_source.py routes.
2) Test security:
   - Path traversal attempts (../../../etc/passwd)
   - Access to files outside user directory
3) Test validation:
   - Invalid Python syntax
   - Missing class definition
   - Class not inheriting from Strategy
4) Test CRUD operations:
   - Create new strategy file
   - Read existing file
   - Update with overwrite flag
   - Delete strategy file
5) Test error handling:
   - File not found (404)
   - File already exists without overwrite (409)
   - Cannot delete __init__.py (400)

Deliver:
- Test results with pass/fail counts
- Security test findings
- Validation accuracy report
- Follow-up fixes backlog
```

## API Examples

### List Strategy Files
```bash
curl -X GET http://localhost:8000/api/strategies/source \
  -H "Authorization: Bearer <token>"
```

Response:
```json
[
  {
    "file_path": "src/strategies/user/example_rsi_strategy.py",
    "class_path": "src.strategies.user.example_rsi_strategy.ExampleRSIStrategy",
    "size": 3500,
    "modified_at": 1746732345.123
  }
]
```

### Get Strategy Source
```bash
curl -X GET http://localhost:8000/api/strategies/source/src.strategies.user.example_rsi_strategy.ExampleRSIStrategy \
  -H "Authorization: Bearer <token>"
```

### Save Strategy Source
```bash
curl -X PUT http://localhost:8000/api/strategies/source/src.strategies.user.my_strategy.MyStrategy \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "content": "from src.domain.strategies.base import Strategy\n\nclass MyStrategy(Strategy):\n    def on_tick(self, tick):\n        return None\n",
    "overwrite": false
  }'
```

### Validate Strategy
```bash
curl -X POST http://localhost:8000/api/strategies/source/validate \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "content": "class BadSyntax(\n",
    "class_name": "BadSyntax"
  }'
```

Response:
```json
{
  "valid": false,
  "errors": ["Syntax error at line 1: unexpected EOF while parsing"],
  "warnings": [],
  "class_found": false,
  "inherits_strategy": false
}
```

## GUI Workflow Integration

When creating a new strategy in the dashboard (Step 6):
1. User clicks "Create Strategy" → selects "Write Python Code"
2. Opens code editor (Monaco/CodeMirror)
3. User writes strategy class inheriting from `Strategy`
4. Click "Validate" → calls `POST /api/strategies/source/validate`
5. If valid, click "Save" → calls `PUT /api/strategies/source/{path}`
6. Strategy becomes available for activation via Step 3 lifecycle service
