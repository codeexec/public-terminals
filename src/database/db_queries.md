# Troubleshooting DB


```
PYTHONPATH=. python3 scripts/db_query.py "SELECT status, count(*) FROM terminals GROUP BY status"
```

List all terminals

```
PYTHONPATH=. python3 scripts/db_query.py "SELECT * FROM terminals WHERE deleted_at IS NOT NULL"
```