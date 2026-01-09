#!/usr/bin/env python3
"""
Utility script to run raw SQL queries against the terminal server database.
Usage: python scripts/db_query.py "SELECT * FROM terminals"
"""

import sys
import json
from datetime import datetime
from sqlalchemy import text
from src.database.session import engine

def json_serial(obj):
    """JSON serializer for objects not serializable by default json code"""
    if isinstance(obj, datetime):
        return obj.isoformat()
    raise TypeError(f"Type {type(obj)} not serializable")

def run_query(query_string):
    """Execute a raw SQL query and print the results"""
    try:
        with engine.connect() as connection:
            result = connection.execute(text(query_string))
            
            # If the query returns rows (like SELECT)
            if result.returns_rows:
                columns = result.keys()
                rows = [dict(zip(columns, row)) for row in result]
                
                if not rows:
                    print("No results found.")
                else:
                    print(json.dumps(rows, indent=2, default=json_serial))
            else:
                # For non-SELECT queries (UPDATE, DELETE, etc.)
                connection.commit()
                print(f"Query executed successfully. Rows affected: {result.rowcount}")
                
    except Exception as e:
        print(f"Error executing query: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python scripts/db_query.py \"YOUR SQL QUERY\"")
        sys.exit(1)
        
    query = " ".join(sys.argv[1:])
    run_query(query)
