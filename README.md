# 🗺️ PyMaps - Mini Google Maps em Python (Arquitetura MVC)

Sistema interativo de mapas, busca de endereços e cálculo de rotas em tempo real com direções passo a passo (turn-by-turn), desenvolvido para rodar dentro de uma Máquina Virtual (**Ubuntu Server**) e ser acessado através do navegador no computador hospedeiro (**Windows**).

---

## 🏛️ Arquitetura do Projeto (Padrão MVC)

O projeto foi rigorosamente estruturado seguindo o padrão **Model-View-Controller (MVC)**:

```text
trabalhoNaldoPython/
│
├── app/
│   ├── __init__.py               # Application Factory (criação da instância Flask)
│   │
│   ├── models/                   # [M] MODEL: Lógica de negócio, integração e dados
│   │   ├── __init__.py
│   │   ├── database.py           # Conexão e inicialização do SQLite
│   │   ├── location_model.py     # Geocodificação (busca de locais e coordenadas via Nominatim)
│   │   ├── route_model.py        # Cálculo de rotas, distâncias e direções (OSRM)
│   │   └── history_model.py      # Persistência do histórico de rotas
│   │
│   ├── controllers/              # [C] CONTROLLER: Recebe requisições e coordena dados/regras
│   │   ├── __init__.py
│   │   ├── map_controller.py     # Renderiza a View inicial
│   │   └── api_controller.py     # Endpoints REST (/api/search, /api/route, /api/history)
│   │
│   ├── views/                    # [V] VIEW: Telas de apresentação do usuário
│   │   └── index.html            # Layout estilo Google Maps em HTML5
│   │
│   └── static/                   # Recursos visuais da View
│       ├── css/
│       │   └── style.css         # Estilização visual (cards flutuantes, responsividade)
│       └── js/
│           └── map.js            # Integração com Leaflet.js, manipulação do mapa e DOM
│
├── setup_vm.sh                   # Script para configurar dependências no Ubuntu Server
├── requirements.txt              # Bibliotecas necessárias (Flask, requests, geopy)
├── run.py                        # Ponto de entrada (executável com host 0.0.0.0)
└── README.md
```

---

## 🚀 Como Executar na Máquina Virtual (Ubuntu Server)

### 1. Configurar Rede no VirtualBox (Port Forwarding)
Para que o navegador do Windows consiga acessar a VM:
1. Abra o **VirtualBox**.
2. Clique na sua VM Ubuntu Server e vá em **Configurações** $\rightarrow$ **Rede** $\rightarrow$ **Avançado** $\rightarrow$ **Redirecionamento de Portas**.
3. Adicione a seguinte regra:
   - **Nome:** `FlaskWeb`
   - **Protocolo:** `TCP`
   - **IP do Hospedeiro:** `127.0.0.1` (ou deixe vazio)
   - **Porta do Hospedeiro:** `5000`
   - **IP do Convidado:** (deixe vazio)
   - **Porta do Convidado:** `5000`

*(Opcional para SSH: adicione Host `2222` $\rightarrow$ Guest `22`)*

---

### 2. Levar os arquivos para o Ubuntu Server
Você pode copiar esta pasta para dentro da VM via:
- **Git:** Criando um repositório no GitHub/GitLab e clonando na VM (`git clone ...`).
- **SCP (Prompt do Windows):**
  ```powershell
  scp -P 2222 -r d:\repositoriosJP\trabalhoNaldoPython usuario@localhost:~/trabalhoNaldoPython
  ```
- **Pasta Compartilhada do VirtualBox:** Mapeando a pasta em `/media/sf_trabalhoNaldoPython`.

---

### 3. Rodar no Ubuntu Server

Dentro da pasta do projeto no Ubuntu Server, você pode executar o script automático:

```bash
chmod +x setup_vm.sh
./setup_vm.sh
```

Ou executar manualmente:

```bash
# 1. Instalar dependências de sistema
sudo apt update && sudo apt install -y python3 python3-pip python3-venv

# 2. Criar e ativar o ambiente virtual
python3 -m venv venv
source venv/bin/activate

# 3. Instalar os pacotes
pip install -r requirements.txt

# 4. Iniciar a aplicação
python3 run.py
```

---

### 4. Acessar a Aplicação

Abra qualquer navegador no seu computador físico (Windows) e acesse:

👉 **[http://localhost:5000](http://localhost:5000)**

---

## ✨ Funcionalidades Incluídas
- **Mapa Interativo Fullscreen:** Zoom, pan e alternância entre mapa de ruas e **satélite**.
- **Busca de Endereços:** Sugestões em tempo real conforme você digita (com geocodificação aberta via Nominatim).
- **Cálculo de Rota Real:** Traçado rodoviário com distância em km e tempo estimado (OSRM).
- **Instruções Passo a Passo (Turn-by-turn):** Lista detalhada de manobras (*"Vire à direita", "Pegue a rotatória"*), com clique que direciona a câmera do mapa para o local da curva.
- **Interação por Clique com Botão Direito:** Clique com o botão direito no mapa para definir partida ou chegada rapidamente.
- **Histórico Persistente (SQLite):** Salva as últimas rotas calculadas para consulta rápida.
