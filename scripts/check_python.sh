#!/bin/bash
set -e

# Define directories to check
TARGETS="src tests terminal-container"

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${YELLOW}Checking Python environment...${NC}"

# Check if tools are installed
if ! command -v ruff &> /dev/null; then
    echo -e "${RED}Error: 'ruff' is not installed.${NC}"
    echo "Please install dev requirements: pip install -r requirements-dev.txt"
    exit 1
fi

if ! command -v mypy &> /dev/null; then
    echo -e "${RED}Error: 'mypy' is not installed.${NC}"
    echo "Please install dev requirements: pip install -r requirements-dev.txt"
    exit 1
fi

echo -e "${GREEN}Environment looks good.${NC}"
echo ""

# 1. Formatting Check (Black/Isort equivalent via Ruff)
echo -e "${YELLOW}1. Checking Code Formatting (ruff format)...${NC}"
if ruff format --check $TARGETS; then
    echo -e "${GREEN}✓ Formatting checks passed.${NC}"
else
    echo -e "${RED}✗ Formatting checks failed.${NC}"
    echo "Run 'ruff format .' to fix."
    EXIT_CODE=1
fi
echo ""

# 2. Linting (Flake8 equivalent via Ruff)
echo -e "${YELLOW}2. Running Linter (ruff check)...${NC}"
if ruff check $TARGETS; then
    echo -e "${GREEN}✓ Linting checks passed.${NC}"
else
    echo -e "${RED}✗ Linting checks failed.${NC}"
    echo "Run 'ruff check --fix .' to attempt automatic fixes."
    EXIT_CODE=1
fi
echo ""

# 3. Type Checking (MyPy)
echo -e "${YELLOW}3. Running Type Checker (mypy)...${NC}"
# We ignore missing imports for now as setting up perfect types for all deps might be overkill for this script
if mypy --ignore-missing-imports --install-types --non-interactive $TARGETS; then
    echo -e "${GREEN}✓ Type checks passed.${NC}"
else
    echo -e "${RED}✗ Type checks failed.${NC}"
    EXIT_CODE=1
fi

if [ -z "$EXIT_CODE" ]; then
    echo ""
    echo -e "${GREEN}All checks passed! Great job!${NC}"
    exit 0
else
    echo ""
    echo -e "${RED}Some checks failed. See above for details.${NC}"
    exit 1
fi
