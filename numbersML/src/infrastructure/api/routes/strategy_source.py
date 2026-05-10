"""Strategy Source Code Management API endpoints.

Provides REST API for managing user-written strategy source code:
- List all strategy source files
- Load strategy source code
- Store/update strategy source code
- Delete strategy files
- Validate strategy syntax and structure

Architecture: Infrastructure Layer (API)
Dependencies: Domain models, file system access
"""

import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

router = APIRouter(prefix="/api/strategies/source", tags=["strategy-source"])
logger = logging.getLogger(__name__)

# Base directory for user strategies
USER_STRATEGIES_DIR = Path(__file__).parent.parent.parent.parent / "strategies" / "user"


# ============================================================================
# Request/Response Models
# ============================================================================


class StrategySourceResponse(BaseModel):
    """Strategy source file information."""

    file_path: str
    class_path: str
    size: int
    modified_at: float | None = None


class StrategySourceContent(BaseModel):
    """Strategy source code content."""

    file_path: str
    class_path: str
    content: str
    size: int
    modified_at: float | None = None


class StrategySourceUpdate(BaseModel):
    """Strategy source code update request."""

    content: str
    overwrite: bool = False


class StrategyValidationRequest(BaseModel):
    """Strategy validation request."""

    content: str
    class_name: str | None = None


class StrategyValidationResult(BaseModel):
    """Strategy validation result."""

    valid: bool
    errors: list[str] = []
    warnings: list[str] = []
    class_found: bool = False
    inherits_strategy: bool = False


# ============================================================================
# Helper Functions
# ============================================================================


def _get_user_strategies_dir() -> Path:
    """Get the user strategies directory, creating it if needed."""
    USER_STRATEGIES_DIR.mkdir(parents=True, exist_ok=True)
    return USER_STRATEGIES_DIR


def _python_file_to_class_path(file_path: Path) -> str:
    """Convert file path to Python module class path."""
    rel_path = file_path.relative_to(Path(__file__).parent.parent.parent.parent)
    module_path = str(rel_path.with_suffix("")).replace("/", ".")
    # Add "src." prefix to make it a valid class path
    return "src." + module_path


def _class_path_to_file_path(class_path: str) -> Path:
    """Convert Python module class path to file path."""
    # Extract module path (remove class name)
    parts = class_path.rsplit(".", 1)
    module_path = parts[0] if len(parts) > 1 else class_path

    # Strip "src." prefix if present, since we're joining from the src directory
    if module_path.startswith("src."):
        module_path = module_path[4:]

    # Convert to file path
    file_path = Path(__file__).parent.parent.parent.parent / (module_path.replace(".", "/") + ".py")
    return file_path


def _is_safe_path(file_path: Path) -> bool:
    """Check if file path is within user strategies directory."""
    try:
        file_path.resolve().relative_to(USER_STRATEGIES_DIR.resolve())
        return True
    except ValueError:
        return False


def _validate_strategy_code(
    content: str, class_name: str | None = None
) -> StrategyValidationResult:
    """Validate strategy source code.

    Checks:
    - Python syntax is valid
    - File contains a class definition
    - Class inherits from Strategy (if possible to detect)
    """
    errors: list[str] = []
    warnings: list[str] = []
    class_found = False
    inherits_strategy = False

    # Check Python syntax
    try:
        compile(content, "<string>", "exec")
    except SyntaxError as e:
        errors.append(f"Syntax error at line {e.lineno}: {e.msg}")
        return StrategyValidationResult(
            valid=False,
            errors=errors,
            warnings=warnings,
        )

    # Check for class definition
    import ast

    try:
        tree = ast.parse(content)
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                if class_name and node.name == class_name:
                    class_found = True
                elif not class_name:
                    class_found = True

                # Check if inherits from Strategy
                for base in node.bases:
                    if isinstance(base, ast.Name) and base.id == "Strategy":
                        inherits_strategy = True
                    elif isinstance(base, ast.Attribute) and base.attr == "Strategy":
                        inherits_strategy = True

                if class_found:
                    break
    except Exception as e:
        warnings.append(f"Could not parse AST: {e}")

    if not class_found:
        errors.append(f"Class definition not found{f' for {class_name}' if class_name else ''}")

    if not inherits_strategy:
        warnings.append("Could not verify Strategy inheritance (may require runtime check)")

    return StrategyValidationResult(
        valid=len(errors) == 0,
        errors=errors,
        warnings=warnings,
        class_found=class_found,
        inherits_strategy=inherits_strategy,
    )


# ============================================================================
# API Endpoints
# ============================================================================


@router.get("", response_model=list[StrategySourceResponse])
async def list_strategy_sources() -> list[StrategySourceResponse]:
    """List all strategy source files in src/strategies/user/."""
    user_dir = _get_user_strategies_dir()

    results = []
    for py_file in user_dir.glob("*.py"):
        if py_file.name.startswith("_"):
            continue

        class_path = _python_file_to_class_path(py_file)
        stat = py_file.stat()

        results.append(
            StrategySourceResponse(
                file_path=str(py_file.relative_to(Path(__file__).parent.parent.parent.parent)),
                class_path=class_path,
                size=stat.st_size,
                modified_at=stat.st_mtime,
            )
        )

    return results


@router.get("/{class_path:path}", response_model=StrategySourceContent)
async def get_strategy_source(
    class_path: str,
) -> StrategySourceContent:
    """Get strategy source code by class path."""
    file_path = _class_path_to_file_path(class_path)

    # Security check
    if not _is_safe_path(file_path):
        raise HTTPException(status_code=403, detail="Access denied: invalid path")

    if not file_path.exists():
        raise HTTPException(status_code=404, detail=f"Strategy file not found: {class_path}")

    try:
        content = file_path.read_text(encoding="utf-8")
        stat = file_path.stat()

        return StrategySourceContent(
            file_path=str(file_path.relative_to(Path(__file__).parent.parent.parent.parent)),
            class_path=class_path,
            content=content,
            size=stat.st_size,
            modified_at=stat.st_mtime,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read file: {e}")


@router.put("/{class_path:path}", response_model=StrategySourceContent)
async def save_strategy_source(
    class_path: str,
    req: StrategySourceUpdate,
) -> StrategySourceContent:
    """Save/update strategy source code."""
    file_path = _class_path_to_file_path(class_path)

    # Security check
    if not _is_safe_path(file_path):
        raise HTTPException(status_code=403, detail="Access denied: invalid path")

    # Validate syntax before saving
    validation = _validate_strategy_code(req.content)
    if not validation.valid:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid strategy code: {'; '.join(validation.errors)}",
        )

    # Check if file exists and overwrite flag
    if file_path.exists() and not req.overwrite:
        raise HTTPException(
            status_code=409,
            detail="File already exists. Set overwrite=true to replace.",
        )

    try:
        # Ensure parent directory exists
        file_path.parent.mkdir(parents=True, exist_ok=True)

        # Write file
        file_path.write_text(req.content, encoding="utf-8")
        stat = file_path.stat()

        logger.info(f"Strategy source saved: {class_path}")

        return StrategySourceContent(
            file_path=str(file_path.relative_to(Path(__file__).parent.parent.parent.parent)),
            class_path=class_path,
            content=req.content,
            size=stat.st_size,
            modified_at=stat.st_mtime,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save file: {e}")


@router.delete("/{class_path:path}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_strategy_source(
    class_path: str,
) -> None:
    """Delete strategy source file."""
    file_path = _class_path_to_file_path(class_path)

    # Security check
    if not _is_safe_path(file_path):
        raise HTTPException(status_code=403, detail="Access denied: invalid path")

    if not file_path.exists():
        raise HTTPException(status_code=404, detail=f"Strategy file not found: {class_path}")

    # Don't delete __init__.py
    if file_path.name == "__init__.py":
        raise HTTPException(status_code=400, detail="Cannot delete __init__.py")

    try:
        file_path.unlink()
        logger.info(f"Strategy source deleted: {class_path}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete file: {e}")


@router.post("/validate", response_model=StrategyValidationResult)
async def validate_strategy_source(
    req: StrategyValidationRequest,
) -> StrategyValidationResult:
    """Validate strategy source code without saving."""
    return _validate_strategy_code(req.content, req.class_name)
