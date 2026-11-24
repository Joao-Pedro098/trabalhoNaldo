#!/bin/bash
# ==========================================================
# Instalação do Falha Viva no Ubuntu Server
#
#   ./setup_vm.sh            instala dependências e o ambiente virtual
#   ./setup_vm.sh --demo     ... e carrega os dados de demonstração (Coquimbo)
#   ./setup_vm.sh --servico  ... e cria um serviço systemd (inicia junto com a VM)
#
# As opções podem ser combinadas: ./setup_vm.sh --demo --servico
# ==========================================================

set -e
cd "$(dirname "$0")"

DEMO=0
SERVICO=0
for arg in "$@"; do
    case "$arg" in
        --demo) DEMO=1 ;;
        --servico) SERVICO=1 ;;
        *) echo "Opção desconhecida: $arg"; exit 1 ;;
    esac
done

echo ">>> [1/5] Atualizando pacotes do Ubuntu Server..."
sudo apt-get update -y

echo ">>> [2/5] Instalando Python3, pip e venv..."
sudo apt-get install -y python3 python3-pip python3-venv

PY_OK=$(python3 -c 'import sys; print(int(sys.version_info >= (3, 10)))')
if [ "$PY_OK" != "1" ]; then
    echo "ERRO: é necessário Python 3.10 ou superior (encontrado: $(python3 --version))."
    exit 1
fi

echo ">>> [3/5] Criando ambiente virtual (venv)..."
if [ ! -d "venv" ]; then
    python3 -m venv venv
fi

echo ">>> [4/5] Instalando dependências do requirements.txt..."
./venv/bin/pip install --upgrade pip
./venv/bin/pip install -r requirements.txt

echo ">>> [5/5] Conferindo a instalação (testes automáticos)..."
./venv/bin/python3 -m pytest -q

if [ "$DEMO" = "1" ]; then
    echo ">>> Carregando dados de demonstração..."
    ./venv/bin/python3 carregar_demo.py
fi

if [ "$SERVICO" = "1" ]; then
    echo ">>> Criando o serviço systemd 'sismofalhas'..."
    SECRET=$(./venv/bin/python3 -c 'import secrets; print(secrets.token_hex(32))')
    sudo tee /etc/systemd/system/sismofalhas.service > /dev/null <<EOF
[Unit]
Description=Falha Viva - correlacao entre falhas e epicentros
After=network.target

[Service]
User=$USER
WorkingDirectory=$(pwd)
Environment=SECRET_KEY=$SECRET
Environment=PORT=5000
ExecStart=$(pwd)/venv/bin/python3 app.py
Restart=on-failure

[Install]
WantedBy=multi-user.target
EOF
    sudo systemctl daemon-reload
    sudo systemctl enable --now sismofalhas
    echo "Serviço ativo. Comandos úteis:"
    echo "   sudo systemctl status sismofalhas"
    echo "   sudo journalctl -u sismofalhas -f"
fi

IP=$(hostname -I 2>/dev/null | awk '{print $1}')
echo ""
echo "=========================================================="
if [ "$SERVICO" = "1" ]; then
    echo " Pronto! O sistema já está rodando."
else
    echo " Pronto! Para iniciar o servidor:"
    echo "   ./venv/bin/python3 app.py"
fi
echo ""
echo " Acesse no navegador do Windows: http://${IP:-<IP-da-VM>}:5000"
echo "=========================================================="
