#!/bin/bash
set -e

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_ROOT"

echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BLUE}        Terminal Server - Test Runner${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

# Check if pytest is installed
if ! command -v pytest &> /dev/null; then
    echo -e "${RED}✗ pytest not found${NC}"
    echo ""
    echo "Please install pytest and pytest-asyncio:"
    echo "  pip install pytest pytest-asyncio pytest-cov"
    echo ""
    exit 1
fi

# Parse arguments
MODE="all"
VERBOSE=""
COVERAGE=""
FAILFAST=""
SPECIFIC_TEST=""

show_help() {
    echo "Usage: $0 [OPTIONS]"
    echo ""
    echo "Run tests for the Terminal Server project"
    echo ""
    echo "Options:"
    echo "  -h, --help              Show this help message"
    echo "  -u, --unit              Run only unit tests"
    echo "  -i, --integration       Run only integration tests"
    echo "  -a, --all               Run all tests (default)"
    echo "  -v, --verbose           Verbose output"
    echo "  -c, --coverage          Show coverage report"
    echo "  -x, --failfast          Stop on first failure"
    echo "  -t, --test FILE         Run specific test file or test function"
    echo "                          Example: -t tests/test_api.py"
    echo "                          Example: -t tests/test_api.py::test_function_name"
    echo ""
    echo "Examples:"
    echo "  $0                      # Run all tests"
    echo "  $0 -u                   # Run only unit tests"
    echo "  $0 -i -v                # Run integration tests with verbose output"
    echo "  $0 -c                   # Run all tests with coverage"
    echo "  $0 -t tests/test_api.py # Run specific test file"
    echo ""
}

while [[ $# -gt 0 ]]; do
    case $1 in
        -h|--help)
            show_help
            exit 0
            ;;
        -u|--unit)
            MODE="unit"
            shift
            ;;
        -i|--integration)
            MODE="integration"
            shift
            ;;
        -a|--all)
            MODE="all"
            shift
            ;;
        -v|--verbose)
            VERBOSE="-vv"
            shift
            ;;
        -c|--coverage)
            COVERAGE="yes"
            shift
            ;;
        -x|--failfast)
            FAILFAST="-x"
            shift
            ;;
        -t|--test)
            SPECIFIC_TEST="$2"
            shift 2
            ;;
        *)
            echo -e "${RED}Unknown option: $1${NC}"
            echo ""
            show_help
            exit 1
            ;;
    esac
done

# Build pytest command
PYTEST_CMD="pytest"

# Add verbosity
if [ -n "$VERBOSE" ]; then
    PYTEST_CMD="$PYTEST_CMD $VERBOSE"
fi

# Add failfast
if [ -n "$FAILFAST" ]; then
    PYTEST_CMD="$PYTEST_CMD $FAILFAST"
fi

# Add coverage
if [ "$COVERAGE" = "yes" ]; then
    if ! command -v pytest-cov &> /dev/null; then
        echo -e "${YELLOW}Warning: pytest-cov not installed, skipping coverage${NC}"
        echo "  Install with: pip install pytest-cov"
        echo ""
    else
        PYTEST_CMD="$PYTEST_CMD --cov=src --cov=terminal-container --cov-report=term-missing --cov-report=html"
    fi
fi

# Add test selection
if [ -n "$SPECIFIC_TEST" ]; then
    echo -e "${YELLOW}Running specific test: ${SPECIFIC_TEST}${NC}"
    PYTEST_CMD="$PYTEST_CMD $SPECIFIC_TEST"
elif [ "$MODE" = "unit" ]; then
    echo -e "${YELLOW}Running unit tests only${NC}"
    PYTEST_CMD="$PYTEST_CMD -m unit"
elif [ "$MODE" = "integration" ]; then
    echo -e "${YELLOW}Running integration tests only${NC}"
    PYTEST_CMD="$PYTEST_CMD -m integration"
else
    echo -e "${YELLOW}Running all tests${NC}"
    PYTEST_CMD="$PYTEST_CMD tests/ terminal-container/container_tests/"
fi

echo ""
echo -e "${BLUE}Command: ${PYTEST_CMD}${NC}"
echo ""
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

# Run tests
if $PYTEST_CMD; then
    echo ""
    echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${GREEN}         ✓ ALL TESTS PASSED${NC}"
    echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

    if [ "$COVERAGE" = "yes" ]; then
        echo ""
        echo -e "${BLUE}Coverage report saved to: htmlcov/index.html${NC}"
        echo -e "${BLUE}View with: open htmlcov/index.html${NC}"
    fi

    exit 0
else
    EXIT_CODE=$?
    echo ""
    echo -e "${RED}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${RED}         ✗ TESTS FAILED${NC}"
    echo -e "${RED}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo ""
    exit $EXIT_CODE
fi
