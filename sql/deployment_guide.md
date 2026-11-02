# Deployment Guide - Meeting: Aerospace Parts Inventory Data Integration Date: 22-Sep-2026 Teams: Supply Chain,

## Package contents
| File | Purpose |
| --- | --- |
| create_database.sql | Creates the logical database |
| create_schema.sql | Creates the application schema |
| create_tables.sql | Creates core tables |
| create_views.sql | Creates reporting views |
| procedures.sql | Creates operational procedures |
| tasks.sql | Seeds story task data |
| validation_queries.sql | Post-deployment smoke checks |

## Execution order
1. Run `create_database.sql`
2. Run `create_schema.sql`
3. Run `create_tables.sql`
4. Run `create_views.sql`
5. Run `procedures.sql`
6. Run `tasks.sql`
7. Run `validation_queries.sql` and confirm all checks pass

## Rollback plan
The deployment is additive (CREATE IF NOT EXISTS / OR REPLACE), so rollback
is safe: drop the schema `aerospace_parts_inventory_2_db.core` and, if desired, the database `aerospace_parts_inventory_2_db`.

## Notes
* Generated for story: Meeting: Aerospace Parts Inventory Data Integration Date: 22-Sep-2026 Teams: Supply Chain,
* Acceptance criteria covered: 2
* Tasks seeded: 4
