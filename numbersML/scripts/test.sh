#!/bin/bash
#
# Test Runner Script for Crypto Trading System
#
# Usage:
#   ./scripts/test.sh                    # Run all tests
#   ./scripts/test.sh unit               # Run unit tests only
#   ./scripts/test.sh integration        # Run integration tests only
#   ./scripts/test.sh pipeline           # Run pipeline integration test
#   ./scripts/test.sh check              # Quick syntax/type check
#
# Exit codes:
#   0 - All tests passed
#   1 - Tests failed
#   2 - Infrastructure not ready
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_DIR"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration - Use system python3 by default (more reliable than venv)
# Override with: export USE_VENV=1
if [ -n "${USE_VENV:-}" ] && [ -f "${PROJECT_DIR}/.venv/bin/python" ]; then
    # Use virtual environment if requested and available
    PYTHON="${PROJECT_DIR}/.venv/bin/python"
    PYTEST="${PROJECT_DIR}/.venv/bin/pytest"
elif [ -n "${GITHUB_ACTIONS:-}" ]; then
    # GitHub Actions - use system python3 and CI database
    PYTHON="python3"
    PYTEST="pytest"
else
    # Default: use system python3
    PYTHON="python3"
    PYTEST="pytest"
fi

# Use TEST_DB_URL if set (for CI), otherwise default to local dev config
if [ -n "${TEST_DB_URL:-}" ]; then
    DB_URL="$TEST_DB_URL"
else
    DB_URL="${DATABASE_URL:-postgresql://crypto:crypto_secret@localhost:5432/crypto_trading}"
fi

# Functions
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[PASS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[FAIL]${NC} $1"
}

print_header() {
    echo ""
    echo "======================================================================"
    echo " $1"
    echo "======================================================================"
    echo ""
}

check_infrastructure() {
    log_info "Checking infrastructure..."

    # Detect if running in GitHub Actions (services: provides PostgreSQL on localhost)
    if [ -n "${GITHUB_ACTIONS:-}" ]; then
        log_info "Running in GitHub Actions - checking localhost PostgreSQL..."
        
        # Parse DB_URL using Python for reliability
        DB_HOST=$(python3 -c "from urllib.parse import urlparse; print(urlparse('$DB_URL').hostname)")
        DB_PORT=$(python3 -c "from urllib.parse import urlparse; print(urlparse('$DB_URL').port)")
        DB_USER=$(python3 -c "from urllib.parse import urlparse; print(urlparse('$DB_URL').username)")
        DB_NAME=$(python3 -c "from urllib.parse import urlparse; print(urlparse('$DB_URL').path.lstrip('/'))")
        
        # Check PostgreSQL on localhost
        if ! pg_isready -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" > /dev/null 2>&1; then
            log_error "PostgreSQL is not ready on ${DB_HOST}:${DB_PORT}"
            exit 2
        fi
        log_success "PostgreSQL is ready (GitHub Actions)"
        
        # Check Redis on localhost
        if ! redis-cli -h localhost -p 6379 ping > /dev/null 2>&1; then
            log_error "Redis is not ready on localhost:6379"
            exit 2
        fi
        log_success "Redis is ready (GitHub Actions)"
        
        # Check Python environment
        if ! command -v python3 &> /dev/null; then
            log_error "Python3 not found"
            exit 2
        fi
        log_success "Python3 environment found"
        
        # Check database connection
        if ! python3 -c "import asyncpg; import asyncio; asyncio.run(asyncpg.connect('$DB_URL'))" > /dev/null 2>&1; then
            log_error "Cannot connect to database"
            exit 2
        fi
        log_success "Database connection OK"
        
        echo ""
        return 0
    fi

    # Local development - check Docker infrastructure
    if ! docker compose -f docker/docker-compose-infra.yml ps > /dev/null 2>&1; then
        log_error "Infrastructure is not running. Start with:"
        echo ""
        echo "  docker compose -f docker/docker-compose-infra.yml up -d"
        echo ""
        exit 2
    fi

    # Check PostgreSQL specifically
    if ! docker exec crypto-postgres pg_isready -U crypto -d crypto_trading > /dev/null 2>&1; then
        log_error "PostgreSQL is not ready. Wait for it to start:"
        echo "  sleep 10"
        exit 2
    fi
    log_success "PostgreSQL is running"

    # Check Redis specifically
    if ! docker exec crypto-redis redis-cli ping > /dev/null 2>&1; then
        log_error "Redis is not ready. Wait for it to start:"
        echo "  sleep 5"
        exit 2
    fi
    log_success "Redis is running"

    # Check Python environment (use python3, not venv)
    if ! command -v python3 &> /dev/null; then
        log_error "Python3 not found"
        exit 2
    fi
    log_success "Python3 environment found"

    # Check database connection
    if ! python3 -c "import asyncpg; import asyncio; asyncio.run(asyncpg.connect('$DB_URL'))" > /dev/null 2>&1; then
        log_error "Cannot connect to database"
        exit 2
    fi
    log_success "Database connection OK"

    echo ""
}

start_infrastructure() {
    log_info "Starting infrastructure..."
    
    if docker compose -f docker/docker-compose-infra.yml ps > /dev/null 2>&1; then
        log_warning "Infrastructure already running"
        docker compose -f docker/docker-compose-infra.yml ps
        return 0
    fi
    
    log_info "Starting PostgreSQL and Redis..."
    docker compose -f docker/docker-compose-infra.yml up -d
    
    log_info "Waiting for services to be ready..."
    sleep 5
    
    # Wait for PostgreSQL
    for i in {1..10}; do
        if docker exec crypto-postgres pg_isready -U crypto -d crypto_trading > /dev/null 2>&1; then
            log_success "PostgreSQL is ready"
            break
        fi
        log_info "Waiting for PostgreSQL... ($i/10)"
        sleep 2
    done
    
    # Wait for Redis
    for i in {1..5}; do
        if docker exec crypto-redis redis-cli ping > /dev/null 2>&1; then
            log_success "Redis is ready"
            break
        fi
        log_info "Waiting for Redis... ($i/5)"
        sleep 2
    done
    
    # Final check
    if ! docker exec crypto-postgres pg_isready -U crypto -d crypto_trading > /dev/null 2>&1; then
        log_error "PostgreSQL failed to start"
        return 1
    fi
    
    log_success "Infrastructure started successfully"
    echo ""
    docker compose -f docker/docker-compose-infra.yml ps
}

stop_infrastructure() {
    log_info "Stopping infrastructure..."
    docker compose -f docker/docker-compose-infra.yml down
    log_success "Infrastructure stopped"
}

run_unit_tests() {
    print_header "UNIT TESTS"
    
    log_info "Running unit tests..."
    
    if pytest tests/unit/ -v --tb=short --timeout=60 "$@"; then
        log_success "Unit tests passed"
        return 0
    else
        log_error "Unit tests failed"
        return 1
    fi
}

run_integration_tests() {
    print_header "INTEGRATION TESTS"
    
    log_info "Running integration tests..."
    
    # Run all integration tests (exclusions handled by pytest.ini)
    if pytest tests/integration/ -v --tb=short --timeout=300 "$@"; then
        log_success "Integration tests passed"
        return 0
    else
        log_error "Integration tests failed"
        return 1
    fi
}

run_pipeline_test() {
    print_header "PIPELINE INTEGRATION TEST"

    log_info "Running indicator pipeline test..."

    if pytest tests/integration/test_indicator_pipeline.py -v --tb=short --timeout=300 "$@"; then
        log_success "Pipeline test passed"
        return 0
    else
        log_error "Pipeline test failed"
        return 1
    fi
}

run_all_tests() {
    print_header "FULL TEST SUITE"
    
    log_info "Running full test suite (unit + integration)..."
    echo ""
    
    FAILED=0
    
    # Run unit tests first
    if ! run_unit_tests "$@"; then
        FAILED=1
    fi
    
    echo ""
    
    # Run integration tests
    if ! run_integration_tests "$@"; then
        FAILED=1
    fi
    
    echo ""
    
    if [ $FAILED -eq 0 ]; then
        print_header "ALL TESTS PASSED"
        log_success "Full test suite completed successfully"
    else
        print_header "TESTS FAILED"
        log_error "Some tests failed"
    fi
    
    return $FAILED
}

quick_check() {
    print_header "QUICK CHECK"

    log_info "Running quick syntax and import check..."

    # Check Python syntax
    if ! python3 -m py_compile src/application/services/enrichment_service.py 2>&1; then
        log_error "Syntax error in enrichment_service.py"
        return 1
    fi

    # Check imports
    if ! python3 -c "from src.application.services.enrichment_service import EnrichmentService" 2>&1; then
        log_error "Import error in enrichment_service.py"
        return 1
    fi

    log_success "Quick check passed"
    return 0
}

show_help() {
    echo "Test Runner for Crypto Trading System"
    echo ""
    echo "Usage: $0 [command] [pytest_options]"
    echo ""
    echo "Commands:"
    echo "  (none)        Run all tests (requires running infrastructure)"
    echo "  start         Start infrastructure (PostgreSQL + Redis)"
    echo "  stop          Stop infrastructure"
    echo "  restart       Restart infrastructure"
    echo "  status        Check infrastructure and test status"
    echo "  unit          Run unit tests only"
    echo "  integration   Run integration tests only"
    echo "  pipeline      Run pipeline integration test (critical)"
    echo "  check         Quick syntax/import check"
    echo "  help          Show this help message"
    echo ""
    echo "Quick Start:"
    echo "  $0 start      # Start PostgreSQL + Redis"
    echo "  $0 pipeline   # Run pipeline test"
    echo "  $0            # Run all tests"
    echo ""
    echo "Examples:"
    echo "  $0 start                    # Start infrastructure"
    echo "  $0 status                   # Check status"
    echo "  $0 unit                     # Run unit tests"
    echo "  $0 integration -v           # Run integration tests verbose"
    echo "  $0 pipeline                 # Run critical pipeline test"
    echo "  $0 check                    # Quick check"
    echo "  $0 stop                     # Stop infrastructure"
    echo ""
    echo "Exit codes:"
    echo "  0 - All tests passed"
    echo "  1 - Tests failed"
    echo "  2 - Infrastructure not ready"
    echo ""
}

# Main
main() {
    case "${1:-}" in
        start)
            start_infrastructure
            ;;
        stop)
            stop_infrastructure
            ;;
        restart)
            stop_infrastructure
            start_infrastructure
            ;;
        status)
            check_infrastructure
            docker compose -f docker/docker-compose-infra.yml ps
            ;;
        unit)
            check_infrastructure
            run_unit_tests "${@:2}"
            ;;
        integration)
            check_infrastructure
            run_integration_tests "${@:2}"
            ;;
        pipeline)
            check_infrastructure
            run_pipeline_test "${@:2}"
            ;;
        check)
            quick_check
            ;;
        help|--help|-h)
            show_help
            ;;
        "")
            check_infrastructure
            run_all_tests "${@:2}"
            ;;
        *)
            log_error "Unknown command: $1"
            show_help
            exit 1
            ;;
    esac
}

main "$@"
