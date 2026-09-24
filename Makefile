# Convenience shortcuts for the battery-optimiser monorepo.
.PHONY: help backend-install backend-test backend-dev ingest backtest frontend-install frontend-dev frontend-build deploy-backend

help:
	@echo "backend-install   pip install backend deps"
	@echo "backend-test      run backend tests"
	@echo "backend-dev       run FastAPI locally on :8080"
	@echo "ingest            pull 30 days of Elexon prices into backend/prices.duckdb"
	@echo "backtest          run the optimiser over every stored day and benchmark it"
	@echo "frontend-install  npm install frontend deps"
	@echo "frontend-dev      run Next.js dev server on :3000"
	@echo "frontend-build    static export to frontend/out"
	@echo "deploy-backend    deploy backend to Cloud Run"

backend-install:
	cd backend && pip install -r requirements.txt

backend-test:
	cd backend && python -m pytest -q

backend-dev:
	cd backend && uvicorn app.main:app --reload --port 8080

frontend-install:
	cd frontend && npm install

frontend-dev:
	cd frontend && npm run dev

frontend-build:
	cd frontend && npm run build

deploy-backend:
	cd backend && bash deploy/cloudrun.sh

ingest:
	cd backend && python -m app.ingest --days 30

backtest:
	cd backend && python -m app.backtest
