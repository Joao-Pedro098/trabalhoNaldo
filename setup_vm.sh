#!/bin/bash
# ==========================================================
# Script de Configuração Automática do PyMaps no Ubuntu Server
# ==========================================================

set -e

echo ">>> [1/4] Atualizando pacotes do Ubuntu Server..."
sudo apt-get update -y

echo ">>> [2/4] Instalando Python3, pip e venv..."
sudo apt-get install -y python3 python3-pip python3-venv

echo ">>> [3/4] Criando ambiente virtual (venv)..."
if [ ! -d "venv" ]; then
    python3 -m venv venv
    echo "Ambiente virtual 'venv' criado com sucesso."
fi

echo ">>> [4/4] Instalando dependências do requirements.txt..."
./venv/bin/pip install --upgrade pip
./venv/bin/pip install -r requirements.txt

echo ""
echo "=========================================================="
echo " Tudo pronto! Para iniciar o servidor, execute:"
echo "   ./venv/bin/python3 run.py"
echo ""
echo " Ou ative o ambiente com:"
echo "   source venv/bin/activate"
echo "   python3 run.py"
echo "=========================================================="
