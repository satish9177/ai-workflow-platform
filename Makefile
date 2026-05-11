dev:
	docker compose up

prod:
	docker compose -f docker-compose.prod.yml up -d

migrate:
	docker compose run --rm api alembic upgrade head

worker:
	arq app.queue.settings.WorkerSettings

test:
	pytest tests/ -v --cov=app

shell:
	docker compose run --rm api python

backup:
	docker compose exec db pg_dump -U postgres workflows > backup.sql
