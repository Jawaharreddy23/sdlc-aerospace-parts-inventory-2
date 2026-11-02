# Deployment Notes - SDLC-003

## Execution order

1. create_database.sql
2. create_schema.sql
3. create_tables.sql
4. create_views.sql
5. procedures.sql
6. tasks.sql
7. validation_queries.sql (all checks must pass)

## Rollback

Drop the application schema, then the database if required.
All objects are created with IF NOT EXISTS / OR REPLACE, so a
re-run of the package is safe.

## Sign-off

- Tests: 12/12 passed, coverage 100.0%
- Story approved and released via the SDLC Orchestration Platform.