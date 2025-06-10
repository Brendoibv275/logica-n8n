# Sistema de Triagem para Clínica Odontológica

API de triagem inteligente para clínica odontológica que processa mensagens do WhatsApp, classifica intenções e gerencia o cadastro de pacientes.

## Funcionalidades

- Classificação de intenções das mensagens dos pacientes
- Cadastro automático de novos pacientes
- Respostas personalizadas baseadas no histórico do paciente
- Integração com banco de dados SQLite para persistência
- API RESTful com FastAPI
asd
## Requisitos

- Python 3.8+
- pip

## Instalação

1. Clone o repositório:
   ```bash
   git clone <url-do-seu-repositorio>
   cd nome-do-repositorio
   ```

2. Crie e ative um ambiente virtual (recomendado):
   ```bash
   python -m venv .venv
   # No Windows:
   .venv\Scripts\activate
   # No Linux/Mac:
   source .venv/bin/activate
   ```

3. Instale as dependências:
   ```bash
   pip install -r requirements.txt
   ```

## Uso

1. Inicie o servidor:
   ```bash
   uvicorn main:app --reload
   ```

2. Acesse a documentação interativa em:
   - http://localhost:8000/docs
   - http://localhost:8000/redoc

## Estrutura do Projeto

- `main.py`: Ponto de entrada da aplicação
- `requirements.txt`: Dependências do projeto
- `db.sqlite`: Banco de dados SQLite (criado automaticamente)

## Endpoints

- `GET /`: Verifica se a API está online
- `POST /triage`: Processa mensagens e retorna respostas de triagem

## Licença

Este projeto está sob a licença MIT. Veja o arquivo [LICENSE](LICENSE) para mais detalhes.
