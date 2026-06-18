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
# Root directory
cd "$PROJECT_ROOT"

echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BLUE}        Sandbox Server - Test Runner${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

# 1. Linting and Syntax Checks
echo -e "${BLUE}[1/2] Running Linting and Syntax Checks...${NC}"

# Check for syntax errors using ast.parse (read-only, avoids permission issues)
echo -n "Checking for syntax errors... "
SYNTAX_ERRORS=$(find src -name "*.py" -exec python3 -c "import ast; ast.parse(open('{}').read())" 2>&1 \;)
if [ -z "$SYNTAX_ERRORS" ]; then
    echo -e "${GREEN}PASS${NC}"
else
    echo -e "${RED}FAIL${NC}"
    echo -e "${RED}Syntax errors detected in src directory!${NC}"
    echo "$SYNTAX_ERRORS"
    exit 1
fi

# Run ruff check if available
if command -v ruff &> /dev/null; then
    echo -n "Running ruff linter... "
    if ruff check src/ --select E9,F; then
        echo -e "${GREEN}PASS${NC}"
    else
        echo -e "${RED}FAIL${NC}"
        echo -e "${RED}Linter detected critical issues (syntax or undefined variables)!${NC}"
        exit 1
    fi
else
    echo -e "${YELLOW}Skipping ruff check (not installed)${NC}"
fi

echo ""

# 2. Running Pytest
echo -e "${BLUE}[2/2] Running Pytest...${NC}"

# Parse arguments

MODE="all"
VERBOSE=""
COVERAGE=""
FAILFAST=""
SPECIFIC_TEST=""

show_help() {
    echo "Usage: $0 [OPTIONS]"
    echo ""
    echo "Run tests for the Sandbox Server project"
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
PYTEST_CMD="python3 -m pytest"

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
    else
        PYTEST_CMD="$PYTEST_CMD --cov=src --cov=containers/base --cov-report=term-missing --cov-report=html"
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
    PYTEST_CMD="$PYTEST_CMD tests/ containers/base/"
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
