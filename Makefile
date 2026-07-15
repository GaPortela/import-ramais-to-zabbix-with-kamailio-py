.PHONY: help install test lint format run clean setup docker-build docker-run docker-test docker-shell

# Configuração
PYTHON ?= python3
PIP ?= pip3
VENV := venv
SCRIPT := kamailio_zabbix_sync.py
TESTS := test_data_parser.py test_runtime_config.py
DOCKER_IMAGE ?= kamailio-zabbix-sync

ifeq ($(OS),Windows_NT)
VENV_PYTHON := $(VENV)/Scripts/python.exe
VENV_PIP := $(VENV)/Scripts/pip.exe
else
VENV_PYTHON := $(VENV)/bin/python
VENV_PIP := $(VENV)/bin/pip
endif

help:
	@echo "╔══════════════════════════════════════════════════════════════╗"
	@echo "║  Kamailio to Zabbix Sync - Makefile Targets                 ║"
	@echo "╚══════════════════════════════════════════════════════════════╝"
	@echo ""
	@echo "Setup & Installation:"
	@echo "  make setup              - Criar ambiente virtual e instalar deps"
	@echo "  make install            - Instalar dependências"
	@echo ""
	@echo "Development:"
	@echo "  make run                - Executar script principal"
	@echo "  make test               - Rodar testes unitários"
	@echo "  make docker-build       - Construir imagem Docker"
	@echo "  make docker-run         - Rodar container Docker"
	@echo "  make docker-test        - Rodar testes no container"
	@echo ""
	@echo "  make test-verbose       - Testes com saída detalhada"
	@echo "  make coverage           - Testes com cobertura"
	@echo "  make lint               - Verificar código (pylint, flake8)"
	@echo "  make format             - Formatar código (black)"
	@echo "  make check              - Lint + Format check"
	@echo ""
	@echo "Database:"
	@echo "  make db-connect         - Conectar ao banco Kamailio"
	@echo "  make db-test-data       - Inserir dados de teste"
	@echo ""
	@echo "Maintenance:"
	@echo "  make clean              - Limpar arquivos temp (__pycache__, etc)"
	@echo "  make clean-logs         - Remover logs antigos"
	@echo ""
	@echo "Info:"
	@echo "  make version            - Mostrar versão Python/deps"
	@echo "  make help               - Este menu"

# ============================================================================
# SETUP & INSTALLATION
# ============================================================================

setup:
	@echo "📦 Configurando ambiente..."
	@if [ ! -d "$(VENV)" ]; then \
		echo "  ├─ Criando virtual env..."; \
		$(PYTHON) -m venv $(VENV); \
	fi
	@echo "  ├─ Instalando dependências..."
	@$(VENV_PIP) install -r requirements.txt
	@echo "  └─ ✓ Setup completo!"
	@echo ""
	@echo "📝 Próximo passo:"
	@echo "   1. source venv/bin/activate"
	@echo "   2. cp .env.example .env"
	@echo "   3. Edite .env com suas credenciais"
	@echo "   4. make run"

install:
	@echo "📦 Instalando dependências..."
	@$(VENV_PIP) install -r requirements.txt
	@echo "✓ Dependências instaladas"

# ============================================================================
# DEVELOPMENT
# ============================================================================

run:
	@echo "▶️  Executando script principal..."
	@$(VENV_PYTHON) $(SCRIPT)

test:
	@echo "🧪 Rodando testes unitários..."
	@$(VENV_PYTHON) -m pytest $(TESTS) -q

test-verbose:
	@echo "🧪 Rodando testes (verbose)..."
	@$(VENV_PYTHON) -m pytest $(TESTS) -v

coverage:
	@echo "📊 Executando testes com cobertura..."
	@$(VENV_PYTHON) -m pytest $(TESTS) \
		--cov=kamailio_zabbix_sync \
		--cov-report=term-missing \
		--cov-report=html
	@echo ""
	@echo "📈 Relatório salvo em htmlcov/index.html"

lint:
	@echo "🔍 Verificando código (pylint, flake8)..."
	@$(VENV_PYTHON) -m pylint $(SCRIPT) $(TESTS) || true
	@$(VENV_PYTHON) -m flake8 $(SCRIPT) $(TESTS) || true

format:
	@echo "🎨 Formatando código com Black..."
	@$(VENV_PYTHON) -m black $(SCRIPT) $(TESTS)
	@echo "✓ Código formatado"

format-check:
	@echo "🎨 Verificando formatação..."
	@$(VENV_PYTHON) -m black --check $(SCRIPT) $(TESTS)

check: lint format-check
	@echo "✓ Verificações passaram"

# ============================================================================
# DATABASE
# ============================================================================

db-connect:
	@echo "🔗 Conectando ao banco Kamailio..."
	@echo "   (Digite 'exit' para sair)"
	@echo ""
	psql -h localhost -U kamailio -d kamailio

db-test-data:
	@echo "📋 Inserindo dados de teste..."
	@. $(VENV)/bin/activate && $(PYTHON) -c "from kamailio_zabbix_sync import KamailioDB, DB_CONFIG; \
		db = KamailioDB(DB_CONFIG); \
		db.conectar(); \
		ramais = db.buscar_ramais_ativos(); \
		print(f'✓ {len(ramais)} ramais encontrados'); \
		db.desconectar()"

# ============================================================================
# MAINTENANCE
# ============================================================================

clean:
	@echo "🧹 Limpando arquivos temporários..."
	@find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	@find . -type f -name "*.pyc" -delete
	@find . -type f -name "*.pyo" -delete
	@find . -type f -name ".pytest_cache" -delete
	@find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	@find . -type d -name ".coverage" -exec rm -rf {} + 2>/dev/null || true
	@find . -type d -name "htmlcov" -exec rm -rf {} + 2>/dev/null || true
	@echo "✓ Limpeza concluída"

clean-logs:
	@echo "🧹 Removendo logs antigos..."
	@find . -name "*.log.old" -delete
	@find . -name "*.log.*.gz" -delete
	@echo "✓ Logs antigos removidos"

# ============================================================================
# INFO
# ============================================================================

version:
	@echo "📊 Informações do Ambiente"
	@echo ""
	@echo "Python:"
	@$(VENV_PYTHON) --version
	@echo ""
	@echo "Dependências instaladas:"
	@$(VENV_PIP) list | grep -E "psycopg2|requests|pyzabbix|pytest"
	@echo ""
	@echo "Arquivos do projeto:"
	@wc -l $(SCRIPT) $(TESTS) 2>/dev/null | tail -1

# ============================================================================
# DOCKER
# ============================================================================

docker-build:
	@echo "🐳 Construindo imagem Docker..."
	docker build -t $(DOCKER_IMAGE) .

docker-run:
	@echo "🐳 Executando container Docker..."
	docker run --rm -e DRY_RUN=true $(DOCKER_IMAGE)

docker-test:
	@echo "🐳 Executando testes no container..."
	docker run --rm $(DOCKER_IMAGE) python -m pytest test_data_parser.py test_runtime_config.py -q

docker-shell:
	@echo "🐳 Abrindo shell no container..."
	docker run --rm -it $(DOCKER_IMAGE) /bin/bash

# ============================================================================
# SHORTCUTS
# ============================================================================

# Aliases para comandos comuns
t: test
tv: test-verbose
c: coverage
l: lint
f: format
r: run
s: setup

.SILENT: help version
