PYTHON ?= python3

.PHONY: db-up db-down db-reset db-migrate db-build-seed db-seed db-health db-validate db-test-seed-replay db-test test

db-up:
	docker compose up -d --wait db

db-down:
	docker compose down

db-reset:
	@test "$(CONFIRM_RESET)" = "1" || (echo "Refusing to remove the database volume. Re-run with CONFIRM_RESET=1." && exit 1)
	docker compose down -v
	$(MAKE) db-up
	$(MAKE) db-migrate
	$(MAKE) db-seed

db-migrate:
	$(PYTHON) scripts/db.py migrate

db-build-seed:
	$(PYTHON) scripts/build_seed.py

db-seed:
	$(PYTHON) scripts/build_seed.py --check
	$(PYTHON) scripts/db.py run db/seeds/infra-inventory-v0.1.0/seed.sql

db-health:
	$(PYTHON) scripts/db.py run db/tests/001_extension_health.sql

db-validate:
	$(PYTHON) scripts/db.py run db/tests/001_extension_health.sql db/tests/002_schema_constraints.sql db/tests/003_seed_invariants.sql db/tests/004_spatial_smoke.sql

db-test-seed-replay:
	$(PYTHON) scripts/db.py run db/tests/005_seed_replay_mutate.sql
	$(MAKE) db-seed
	$(PYTHON) scripts/db.py run db/tests/006_seed_replay_preserves_curated_state.sql

db-test:
	$(MAKE) test
	$(MAKE) db-migrate
	$(MAKE) db-seed
	$(MAKE) db-test-seed-replay
	$(PYTHON) scripts/db.py run db/tests/001_extension_health.sql db/tests/002_schema_constraints.sql db/tests/003_seed_invariants.sql db/tests/004_spatial_smoke.sql

test:
	$(PYTHON) -m unittest discover -s tests -v
	$(PYTHON) scripts/build_seed.py --check
