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

# Configuration
PYTHON="${PROJECT_DIR}/.venv/bin/python"
PYTEST="${PROJECT_DIR}/.venv/bin/pytest"
DB_URL="${DATABASE_URL:-postgresql://crypto:crypto_secret@localhost:5432/crypto_trading}"

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
    
    # Check if infrastructure is running
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
    
    # Check Python environment
    if [ ! -f "$PYTHON" ]; then
        log_error "Python virtual environment not found at $PYTHON"
        exit 2
    fi
    log_success "Python environment found"
    
    # Check database connection
    if ! $PYTHON -c "import asyncpg; import asyncio; asyncio.run(asyncpg.connect('$DB_URL'))" > /dev/null 2>&1; then
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
    
    if $PYTEST tests/unit/ -v --tb=short --timeout=60 "$@"; then
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
    
    if $PYTEST tests/integration/ -v --tb=short --timeout=300 "$@"; then
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
    
    if $PYTHON tests/integration/test_indicator_pipeline.py "$@"; then
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
    if ! $PYTHON -m py_compile src/cli/generate_wide_vector.py 2>&1; then
        log_error "Syntax error in generate_wide_vector.py"
        return 1
    fi
    
    if ! $PYTHON -m py_compile src/application/services/enrichment_service.py 2>&1; then
        log_error "Syntax error in enrichment_service.py"
        return 1
    fi
    
    # Check imports
    if ! $PYTHON -c "from src.cli.generate_wide_vector import WideVectorGenerator" 2>&1; then
        log_error "Import error in generate_wide_vector.py"
        return 1
    fi
    
    if ! $PYTHON -c "from src.application.services.enrichment_service import EnrichmentService" 2>&1; then
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
