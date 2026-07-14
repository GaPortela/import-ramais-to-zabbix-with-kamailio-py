#!/bin/bash

################################################################################
# Kamailio to Zabbix Sync - Setup Script
# Este script configura o ambiente Python e instala dependências
################################################################################

set -e  # Exit on error

# Cores para output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Funções de logging
print_header() {
    echo -e "\n${BLUE}╔════════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${BLUE}║${NC} $1"
    echo -e "${BLUE}╚════════════════════════════════════════════════════════════════╝${NC}\n"
}

print_info() {
    echo -e "${BLUE}ℹ${NC}  $1"
}

print_success() {
    echo -e "${GREEN}✓${NC}  $1"
}

print_warning() {
    echo -e "${YELLOW}⚠${NC}  $1"
}

print_error() {
    echo -e "${RED}✗${NC}  $1"
}

# Verificar pré-requisitos
check_prerequisites() {
    print_header "Verificando Pré-requisitos"

    # Verificar Python
    if ! command -v python3 &> /dev/null; then
        print_error "Python 3 não encontrado!"
        echo -e "  Por favor, instale Python 3.8 ou superior:"
        echo -e "  Ubuntu/Debian: sudo apt-get install python3"
        echo -e "  macOS: brew install python3"
        echo -e "  Windows: https://www.python.org/downloads/"
        exit 1
    fi

    PYTHON_VERSION=$(python3 --version | cut -d' ' -f2)
    print_success "Python $PYTHON_VERSION encontrado"

    # Verificar pip
    if ! command -v pip3 &> /dev/null; then
        print_error "pip3 não encontrado!"
        echo -e "  Instale pip: python3 -m ensurepip --upgrade"
        exit 1
    fi

    print_success "pip3 encontrado"

    # Verificar git (opcional)
    if command -v git &> /dev/null; then
        print_success "git encontrado"
    else
        print_warning "git não encontrado (opcional, apenas para versionamento)"
    fi
}

# Criar ambiente virtual
setup_venv() {
    print_header "Configurando Ambiente Virtual"

    VENV_DIR="venv"

    if [ -d "$VENV_DIR" ]; then
        print_warning "Ambiente virtual já existe em $VENV_DIR"
        read -p "Deseja recriá-lo? (s/n) " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Ss]$ ]]; then
            print_info "Removendo venv antigo..."
            rm -rf "$VENV_DIR"
        else
            print_info "Usando venv existente"
            return 0
        fi
    fi

    print_info "Criando virtual environment..."
    python3 -m venv "$VENV_DIR"
    print_success "Virtual environment criado em $VENV_DIR"
}

# Ativar ambiente virtual
activate_venv() {
    VENV_DIR="venv"

    if [ -f "$VENV_DIR/bin/activate" ]; then
        source "$VENV_DIR/bin/activate"
        print_success "Virtual environment ativado"
    else
        print_error "Não foi possível ativar virtual environment"
        exit 1
    fi
}

# Instalar dependências
install_dependencies() {
    print_header "Instalando Dependências"

    if [ ! -f "requirements.txt" ]; then
        print_error "Arquivo requirements.txt não encontrado!"
        exit 1
    fi

    print_info "Atualizando pip..."
    pip install --upgrade pip setuptools wheel > /dev/null 2>&1
    print_success "pip atualizado"

    print_info "Instalando dependências do requirements.txt..."
    pip install -r requirements.txt
    print_success "Dependências instaladas"
}

# Configurar arquivo .env
setup_env_file() {
    print_header "Configurando Arquivo de Ambiente"

    ENV_FILE=".env"
    EXAMPLE_FILE=".env.example"

    if [ -f "$ENV_FILE" ]; then
        print_warning "Arquivo .env já existe"
        read -p "Deseja sobrescrevê-lo? (s/n) " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Ss]$ ]]; then
            print_info "Mantendo .env existente"
            return 0
        fi
    fi

    if [ ! -f "$EXAMPLE_FILE" ]; then
        print_error "Arquivo .env.example não encontrado!"
        exit 1
    fi

    cp "$EXAMPLE_FILE" "$ENV_FILE"
    print_success "Arquivo .env criado de $EXAMPLE_FILE"

    print_warning "IMPORTANTE: Edite o arquivo .env com suas credenciais:"
    echo ""
    echo -e "  ${YELLOW}nano .env${NC}"
    echo ""
    echo -e "  Campos obrigatórios:"
    echo -e "  - KAMAILIO_DB_HOST"
    echo -e "  - KAMAILIO_DB_USER"
    echo -e "  - KAMAILIO_DB_PASSWORD"
    echo -e "  - ZABBIX_URL"
    echo -e "  - ZABBIX_USER"
    echo -e "  - ZABBIX_PASSWORD"
    echo ""
}

# Rodar testes
run_tests() {
    print_header "Executando Testes"

    if ! command -v pytest &> /dev/null; then
        print_warning "pytest não está disponível (pulando testes)"
        return 0
    fi

    print_info "Rodando testes unitários..."
    if pytest test_data_parser.py -q; then
        print_success "Todos os testes passaram!"
    else
        print_error "Alguns testes falharam"
        read -p "Continuar mesmo assim? (s/n) " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Ss]$ ]]; then
            exit 1
        fi
    fi
}

# Testar conectividade
test_connectivity() {
    print_header "Testando Conectividade"

    # Testar PostgreSQL
    print_info "Testando conexão com PostgreSQL..."
    python3 << 'EOF'
import os
from dotenv import load_dotenv

load_dotenv()

try:
    import psycopg2
    
    conn_params = {
        'host': os.getenv('KAMAILIO_DB_HOST'),
        'user': os.getenv('KAMAILIO_DB_USER'),
        'password': os.getenv('KAMAILIO_DB_PASSWORD'),
        'database': os.getenv('KAMAILIO_DB_NAME', 'kamailio'),
    }
    
    if not conn_params['host'] or conn_params['host'] == 'localhost':
        print("⚠  Pulando teste PostgreSQL (credenciais não configuradas)")
    else:
        conn = psycopg2.connect(**conn_params)
        conn.close()
        print("✓  Conexão PostgreSQL OK")
except Exception as e:
    print(f"⚠  Erro ao conectar PostgreSQL: {e}")
    print("   Configure .env e tente novamente depois")
EOF

    print_success "Testes de conectividade concluídos"
}

# Menu final
print_menu() {
    print_header "Setup Concluído! 🎉"

    echo -e "Próximos passos:\n"
    echo -e "  ${YELLOW}1. Edite .env com suas credenciais:${NC}"
    echo -e "     nano .env\n"
    echo -e "  ${YELLOW}2. Teste a conexão com o banco:${NC}"
    echo -e "     source venv/bin/activate"
    echo -e "     python3 -c \"from kamailio_zabbix_sync import KamailioDB, DB_CONFIG; db = KamailioDB(DB_CONFIG); db.conectar(); db.desconectar()\"\n"
    echo -e "  ${YELLOW}3. Execute o script principal:${NC}"
    echo -e "     python3 kamailio_zabbix_sync.py\n"
    echo -e "  ${YELLOW}4. Rode os testes:${NC}"
    echo -e "     pytest test_data_parser.py -v\n"
    echo -e "  ${YELLOW}5. Consulte a documentação:${NC}"
    echo -e "     - README.md (início rápido)"
    echo -e "     - DOCUMENTACAO.md (guia completo)"
    echo -e "     - EXEMPLOS_PRATICOS.md (exemplos e cenários)\n"
    echo -e "  ${YELLOW}6. Use o Makefile (se tiver make instalado):${NC}"
    echo -e "     make help\n"

    echo -e "Boa sorte! 🚀\n"
}

# MAIN
main() {
    print_header "Kamailio to Zabbix Sync - Setup"
    
    check_prerequisites
    setup_venv
    activate_venv
    install_dependencies
    setup_env_file
    
    # Testes e conectividade (opcional)
    read -p "Rodar testes agora? (s/n) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Ss]$ ]]; then
        run_tests
    fi

    read -p "Testar conectividade? (s/n) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Ss]$ ]]; then
        test_connectivity
    fi

    print_menu
}

# Executar main
main
