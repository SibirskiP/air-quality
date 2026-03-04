SHELL := /bin/bash

.PHONY: dev-up dev-down logs test lint k8s-deploy

dev-up:
	docker compose up --build -d

dev-down:
	docker compose down

logs:
	docker compose logs -f --tail=200

test:
	PYTHONPATH=services/common pytest -q tests

lint:
	PYTHONPATH=services/common python -m compileall services

k8s-deploy:
	kubectl apply -f infra/k8s/airq-stack.yaml

