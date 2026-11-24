#!/bin/bash
# ==========================================================
# Publica o Falha Viva na internet a partir da VM (Ubuntu Server)
#
#   sudo ./publicar_vm.sh          cria os serviços e mostra o link público
#   ./publicar_vm.sh --link        só mostra o link público atual
#
# Pré-requisito: venv já criado (./setup_vm.sh, ou pip install -r requirements.txt).
#
# Cria dois serviços systemd, que sobem sozinhos junto com a VM:
#   sismofalhas          o sistema (Flask) na porta 5000
#   sismofalhas-tunel    túnel Cloudflare gratuito -> https://xxxx.trycloudflare.com
# O link do túnel muda quando a VM ou o serviço reinicia; use --link para vê-lo.
# ==========================================================

set -e
cd "$(dirname "$0")"
DIR=$(pwd)

mostrar_link() {
    for _ in $(seq 1 30); do
        LINK=$(journalctl -u sismofalhas-tunel --no-pager -o cat 2>/dev/null \
               | grep -o 'https://[a-z0-9-]*\.trycloudflare\.com' | tail -1)
        [ -n "$LINK" ] && break
        sleep 1
    done
    echo ""
    echo "=========================================================="
    if [ -n "$LINK" ]; then
        echo " Link público (qualquer pessoa):  $LINK"
    else
        echo " Link ainda não apareceu. Veja: sudo journalctl -u sismofalhas-tunel -f"
    fi
    IP=$(hostname -I 2>/dev/null | awk '{print $1}')
    echo " Rede local:                       http://${IP}:5000"
    echo "=========================================================="
}

if [ "$1" = "--link" ]; then
    mostrar_link
    exit 0
fi

if [ "$(id -u)" != "0" ]; then
    echo "Rode com sudo:  sudo ./publicar_vm.sh"
    exit 1
fi

USUARIO=${SUDO_USER:-$(stat -c %U "$DIR")}

if [ ! -x "$DIR/venv/bin/python3" ]; then
    echo "ERRO: venv não encontrado. Rode antes ./setup_vm.sh"
    exit 1
fi

echo ">>> [0/3] Acertando fuso e relógio da VM..."
# O VirtualBox entrega a hora local do Windows como se fosse UTC: a VM fica horas atrasada.
timedatectl set-timezone America/Sao_Paulo || true
timedatectl set-ntp true || true
systemctl restart systemd-timesyncd 2>/dev/null || true
sleep 3
if ! timedatectl show -p NTPSynchronized --value 2>/dev/null | grep -q yes; then
    # NTP bloqueado/lento: usa a hora do cabeçalho HTTP de um servidor confiável
    HORA=$(curl -fsSI -m 10 https://www.google.com 2>/dev/null | grep -i '^date:' | cut -d' ' -f2- | tr -d '\r')
    [ -n "$HORA" ] && date -s "$HORA" > /dev/null && echo "Relógio ajustado por HTTP."
fi
date

echo ">>> [1/3] Instalando o cloudflared..."
if ! command -v cloudflared > /dev/null; then
    DEB=""
    for c in "$DIR/cloudflared-linux-amd64.deb" "/home/$USUARIO/cloudflared-linux-amd64.deb"; do
        [ -f "$c" ] && DEB="$c" && break
    done
    if [ -z "$DEB" ]; then
        DEB=/tmp/cloudflared-linux-amd64.deb
        curl -fsSL -o "$DEB" https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb
    fi
    dpkg -i "$DEB"
fi
cloudflared --version

echo ">>> [2/3] Criando o serviço do sistema (sismofalhas)..."
SECRET=$("$DIR/venv/bin/python3" -c 'import secrets; print(secrets.token_hex(32))')
cat > /etc/systemd/system/sismofalhas.service <<EOF
[Unit]
Description=Falha Viva - correlacao entre falhas e epicentros
After=network-online.target
Wants=network-online.target

[Service]
User=$USUARIO
WorkingDirectory=$DIR
Environment=SECRET_KEY=$SECRET
Environment=PORT=5000
ExecStart=$DIR/venv/bin/python3 app.py
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF

echo ">>> [3/3] Criando o serviço do túnel público (sismofalhas-tunel)..."
cat > /etc/systemd/system/sismofalhas-tunel.service <<EOF
[Unit]
Description=Falha Viva - tunel publico Cloudflare
After=network-online.target sismofalhas.service
Wants=network-online.target
Requires=sismofalhas.service

[Service]
User=$USUARIO
ExecStart=/usr/bin/cloudflared tunnel --no-autoupdate --url http://localhost:5000
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

echo ">>> Mostrando o IP da VM na tela de login (janela do VirtualBox)..."
# \4 = IPv4 atual da VM; o agetty atualiza sozinho quando o IP muda.
mkdir -p /etc/issue.d
cat > /etc/issue.d/sismofalhas.issue <<EOF
  ================================================
   Falha Viva - IP desta VM:  \4
   Entrar pelo Windows:  ssh ${USUARIO}@\4
   Link publico:  ~/SismoFalhas/publicar_vm.sh --link
  ================================================

EOF
agetty --reload 2>/dev/null || true

systemctl daemon-reload
systemctl enable sismofalhas sismofalhas-tunel
systemctl restart sismofalhas
systemctl restart sismofalhas-tunel

# Deixa o usuário ler o log do túnel sem sudo (para o --link)
usermod -aG systemd-journal "$USUARIO" || true

echo ""
echo "Serviços ativos. Comandos úteis:"
echo "   ./publicar_vm.sh --link                       mostra o link público"
echo "   sudo systemctl restart sismofalhas            reinicia o sistema"
echo "   sudo journalctl -u sismofalhas -f             log do sistema"
mostrar_link
