.DEFAULT_GOAL := help
PY := uv run

help: ## Komutları listele
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

sync: ## Bağımlılıkları kur
	uv sync --all-extras --dev

lint: ## ruff kontrolü
	$(PY) ruff check .

format: ## ruff biçimlendirme
	$(PY) ruff format .
	$(PY) ruff check --fix .

type: ## mypy (strict)
	$(PY) mypy

test: ## testler
	$(PY) pytest

cov: ## kapsamlı testler
	$(PY) pytest --cov=sentinel --cov-report=term-missing

check: lint type test ## Tüm kalite kapıları

demo: ## Örnek fixture'lar üzerinde nöbetçiyi çalıştır (kimlik bilgisi gerekmez)
	$(PY) sentinel scan --fixtures examples/data

state: ## Son durum dosyasını göster
	$(PY) sentinel state show --state examples/data/state.json

profiles: ## Aktif kanalları ve alan eşlemesini listele
	$(PY) sentinel profiles --fixtures examples/data

demo-svg: ## README için SVG çıktı üret
	$(PY) python scripts/make_demo_svg.py

clean: ## Temizlik
	rm -rf .pytest_cache .mypy_cache .ruff_cache htmlcov .coverage dist build
	find . -name __pycache__ -type d -prune -exec rm -rf {} +

.PHONY: help sync lint format type test cov check demo state profiles demo-svg clean
