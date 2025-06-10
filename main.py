# main.py - Versão 3.1 (Lógica de Preços 100% Consistente)

from fastapi import FastAPI, HTTPException, Depends, Query, status
from pydantic import BaseModel
from sqlmodel import Field, Session, SQLModel, create_engine, select
from typing import Optional, List, Dict, Union
from datetime import datetime, date, timedelta
from google_calendar import get_horarios_disponiveis, criar_evento, authenticate_google
import dateparser  # Para processar datas em linguagem natural

# --- Modelos de Dados ---
# (Nenhuma mudança aqui)
class Paciente(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    sender_id: str = Field(index=True, unique=True)
    nome_completo: Optional[str] = None
    data_criacao: datetime = Field(default_factory=datetime.utcnow, nullable=False)
    estado_conversa: Optional[str] = Field(default=None, nullable=True)  # Para controlar o estado da conversa

class Agendamento(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    paciente_id: int = Field(foreign_key="paciente.id")
    data_hora_inicio: datetime
    data_hora_fim: datetime
    status: str = Field(default="confirmado")  # Ex: confirmado, cancelado
    id_evento_google: Optional[str] = None  # Para salvar o ID do evento do Google

class TriageRequest(SQLModel):
    senderId: str
    senderName: Optional[str] = None
    messageText: str
    timestamp: str

class AgendamentoRequest(BaseModel):
    sender_id_limpo: str
    data_hora_str: str  # Formato "AAAA-MM-DD HH:MM"

class TriageResponse(SQLModel):
    userStatus: str
    analysis: dict
    nextAction: str
    responseText: str

# --- Configuração do Banco de Dados e Funções ---
DATABASE_URL = "sqlite:///db.sqlite"
print(f"\n=== CONFIGURAÇÃO DO BANCO DE DADOS ===")
print(f"URL do banco: {DATABASE_URL}")

try:
    engine = create_engine(DATABASE_URL, echo=True)
    print("Conexão com o banco de dados estabelecida com sucesso!")
except Exception as e:
    print(f"ERRO ao conectar ao banco de dados: {e}")
    raise

def create_db_and_tables():
    try:
        print("\n=== CRIANDO TABELAS DO BANCO DE DADOS ===")
        SQLModel.metadata.create_all(engine)
        print("Tabelas criadas com sucesso!")
    except Exception as e:
        print(f"ERRO ao criar tabelas: {e}")
        raise

def get_session():
    with Session(engine) as session:
        yield session

def classify_intent(text: str) -> dict:
    if not text:
        return {"intent": "UNKNOWN", "confidence": 0.0}
    text = text.lower()
    agendamento_keywords = ["marcar", "agendar", "agendamento", "consulta", "horário", "horario"]
    orcamento_keywords = ["preço", "preco", "valor", "quanto", "custa", "custo"]
    saudacao_keywords = ["oi", "olá", "ola", "bom dia", "boa tarde", "boa noite", "e aí", "tudo bem"]
    if any(keyword in text for keyword in agendamento_keywords):
        return {"intent": "SCHEDULE_APPOINTMENT", "confidence": 0.9}
    elif any(keyword in text for keyword in orcamento_keywords):
        return {"intent": "REQUEST_PRICE", "confidence": 0.9}
    elif any(keyword in text for keyword in saudacao_keywords):
        return {"intent": "GREETING", "confidence": 0.9}
    return {"intent": "UNKNOWN", "confidence": 0.3}

def parse_human_date(text: str) -> Optional[date]:
    """Tenta converter um texto humano (ex: 'amanhã') para uma data."""
    # Configura o dateparser para entender português e o futuro
    settings = {'PREFER_DATES_FROM': 'future', 'DATE_ORDER': 'DMY', 'LANGUAGES': ['pt']}
    parsed_date = dateparser.parse(text, settings=settings)
    if parsed_date:
        return parsed_date.date()
    return None

# --- Lógica do Aplicativo FastAPI ---
print("\n=== INICIALIZANDO FASTAPI ===")

try:
    app = FastAPI(
        title="Triage API",
        description="API para triagem de pacientes com persistência de dados.",
        on_startup=[create_db_and_tables]
    )
    print("Aplicativo FastAPI inicializado com sucesso!")
except Exception as e:
    print(f"ERRO ao inicializar o FastAPI: {e}")
    raise

# Adicionando um manipulador para eventos de inicialização
@app.on_event("startup")
async def startup_event():
    print("\n=== INICIANDO APLICAÇÃO ===")
    print(f"Versão da API: 3.2")
    print(f"Banco de dados: {DATABASE_URL}")
    print("=== PRONTO PARA RECEBER REQUISIÇÕES ===\n")

@app.get("/")
async def root():
    return {"status": "API online", "versao": "3.2"}

# Rota para listar todos os pacientes (apenas para depuração)
@app.get("/pacientes")
async def listar_pacientes(session: Session = Depends(get_session)):
    """Lista todos os pacientes cadastrados (apenas para depuração)."""
    try:
        pacientes = session.exec(select(Paciente)).all()
        return [
            {
                "id": p.id,
                "sender_id": p.sender_id,
                "nome_completo": p.nome_completo,
                "data_criacao": p.data_criacao.isoformat()
            }
            for p in pacientes
        ]
    except Exception as e:
        print(f"Erro ao listar pacientes: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Erro ao listar pacientes: {str(e)}"
        ) from e

# --- NOVO ENDPOINT PARA CONSULTAR AGENDA ---
@app.get("/horarios_disponiveis")
async def ver_horarios(data: str = Query(..., description="Data no formato AAAA-MM-DD")):
    """
    Recebe uma data no formato 'AAAA-MM-DD' e retorna uma lista de
    horários de início disponíveis (ex: ["09:00", "10:00"]).
    """
    try:
        data_formatada = datetime.strptime(data, '%Y-%m-%d').date()
        horarios = get_horarios_disponiveis(data_formatada)
        return {"data": data, "horarios_disponiveis": horarios}
    except ValueError:
        raise HTTPException(status_code=400, detail="Formato de data inválido. Use AAAA-MM-DD.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# --- NOVO ENDPOINT PARA CRIAR AGENDAMENTOS ---
@app.post("/agendamentos")
async def criar_agendamento(request: AgendamentoRequest, session: Session = Depends(get_session)):
    """
    Cria um agendamento no banco de dados e no Google Calendar.
    """
    print(f"\n=== INICIANDO CRIAÇÃO DE AGENDAMENTO ===")
    print(f"Dados recebidos: {request}")
    
    # Busca o paciente no banco de dados
    paciente = session.exec(select(Paciente).where(Paciente.sender_id == request.sender_id_limpo)).first()
    if not paciente:
        error_msg = f"Paciente não encontrado para o sender_id: {request.sender_id_limpo}"
        print(error_msg)
        raise HTTPException(status_code=404, detail=error_msg)

    try:
        print(f"Paciente encontrado: ID={paciente.id}, Nome={paciente.nome_completo}")
        print(f"Data/Hora recebida: {request.data_hora_str}")
        # Converte a string de data/hora para um objeto datetime
        try:
            inicio = datetime.strptime(request.data_hora_str, '%Y-%m-%d %H:%M')
            fim = inicio + timedelta(hours=1)  # Duração da consulta de 1 hora
            print(f"Data/Hora convertida: Início={inicio}, Fim={fim}")
        except ValueError as e:
            error_msg = f"Formato de data/hora inválido: {request.data_hora_str}. Use o formato AAAA-MM-DD HH:MM"
            print(error_msg)
            raise ValueError(error_msg) from e

        # Autentica e cria o evento no Google Calendar
        try:
            print("Autenticando no Google Calendar...")
            service = authenticate_google()
            print("Autenticação bem-sucedida. Criando evento...")
            
            titulo = f"Consulta - {paciente.nome_completo or 'Novo Paciente'}"
            print(f"Criando evento: {titulo}")
            
            evento_google = criar_evento(
                service=service,
                titulo=titulo,
                data_hora_inicio=inicio,
                data_hora_fim=fim
            )
            
            if not evento_google:
                error_msg = "Falha ao criar evento no Google Calendar: Nenhum evento retornado"
                print(error_msg)
                raise HTTPException(status_code=500, detail=error_msg)
                
            print(f"Evento criado com sucesso! ID: {evento_google.get('id')}")
            
        except Exception as e:
            error_msg = f"Erro ao criar evento no Google Calendar: {str(e)}"
            print(error_msg)
            raise HTTPException(status_code=500, detail=error_msg) from e

        # Salva o agendamento no nosso banco de dados local
        try:
            print("Salvando agendamento no banco de dados local...")
            novo_agendamento = Agendamento(
                paciente_id=paciente.id,
                data_hora_inicio=inicio,
                data_hora_fim=fim,
                id_evento_google=evento_google.get('id')
            )
            session.add(novo_agendamento)
            session.commit()
            print("Agendamento salvo com sucesso no banco de dados local!")
            
        except Exception as e:
            session.rollback()
            error_msg = f"Erro ao salvar agendamento no banco de dados: {str(e)}"
            print(error_msg)
            # Tenta remover o evento do Google Calendar se o salvamento local falhar
            try:
                if evento_google and 'id' in evento_google:
                    print(f"Tentando remover evento {evento_google['id']} do Google Calendar...")
                    service.events().delete(calendarId='primary', eventId=evento_google['id']).execute()
                    print("Evento removido do Google Calendar com sucesso.")
            except Exception as delete_error:
                print(f"Aviso: Não foi possível remover o evento do Google Calendar: {str(delete_error)}")
            
            raise HTTPException(status_code=500, detail=error_msg) from e

        # Monta a resposta de sucesso
        response = {
            "status": "sucesso",
            "detalhes": f"Agendamento para {paciente.nome_completo} criado para {request.data_hora_str}.",
            "evento_id": evento_google.get('id'),
            "link_evento": evento_google.get('htmlLink')
        }
        print(f"=== AGENDAMENTO CRIADO COM SUCESSO ===\n{response}")
        return response

    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Formato de data/hora inválido. Use o formato AAAA-MM-DD HH:MM. Erro: {str(e)}")
    except Exception as e:
        # Em caso de erro, tenta desfazer qualquer alteração no banco de dados
        session.rollback()
        raise HTTPException(status_code=500, detail=f"Erro interno ao criar agendamento: {str(e)}")

# --- Ferramentas do Agente ---

def ferramenta_agendar_consulta(paciente, mensagem, session):
    """Ferramenta para iniciar o processo de agendamento de consulta."""
    if not paciente.estado_conversa or paciente.estado_conversa == "inicio":
        paciente.estado_conversa = "aguardando_data_agendamento"
        session.add(paciente)
        session.commit()
        return {
            "resposta": "Vou te ajudar com o agendamento. Qual o melhor dia para você? (ex: amanhã, dia 15/06)",
            "proximo_estado": "aguardando_data_agendamento"
        }
    return None

def ferramenta_processar_data(paciente, mensagem, session):
    """Ferramenta para processar a data fornecida pelo usuário."""
    if paciente.estado_conversa == "aguardando_data_agendamento":
        data_desejada = parse_human_date(mensagem)
        if data_desejada:
            horarios = get_horarios_disponiveis(data_desejada)
            if horarios:
                paciente.estado_conversa = "aguardando_escolha_horario"
                paciente.dados_agendamento = {"data": data_desejada.isoformat()}
                session.add(paciente)
                session.commit()
                
                horarios_formatados = ", ".join(horarios)
                return {
                    "resposta": f"Ótimo! Para o dia {data_desejada.strftime('%d/%m')}, tenho os seguintes horários: {horarios_formatados}. Qual deles você prefere?",
                    "proximo_estado": "aguardando_escolha_horario"
                }
            else:
                return {
                    "resposta": f"Puxa, não encontrei horários disponíveis para {data_desejada.strftime('%d/%m')}. Você gostaria de tentar outra data?",
                    "proximo_estado": "aguardando_data_agendamento"
                }
        else:
            return {
                "resposta": "Não consegui entender a data. Por favor, tente dizer de outra forma (ex: 'amanhã', 'dia 15 de junho' ou '15/06').",
                "proximo_estado": "aguardando_data_agendamento"
            }
    return None

async def ferramenta_processar_horario(paciente, mensagem, session):
    """Ferramenta para processar o horário escolhido pelo usuário."""
    if paciente.estado_conversa == "aguardando_escolha_horario":
        # Aqui você pode adicionar lógica para validar o formato do horário
        try:
            data_str = paciente.dados_agendamento.get("data")
            data_hora_str = f"{data_str} {mensagem}"
            
            # Cria o agendamento
            agendamento_request = AgendamentoRequest(
                sender_id_limpo=paciente.sender_id,
                data_hora_str=data_hora_str
            )
            
            # Chama o endpoint de criação de agendamento
            resultado = await criar_agendamento(agendamento_request, session)
            
            # Reseta o estado da conversa
            paciente.estado_conversa = None
            paciente.dados_agendamento = {}
            session.add(paciente)
            session.commit()
            
            return {
                "resposta": f"Pronto! Seu agendamento foi confirmado para {data_hora_str}. "
                          f"Você receberá uma confirmação por e-mail. Até logo!",
                "proximo_estado": None
            }
            
        except HTTPException as e:
            return {
                "resposta": f"Desculpe, houve um erro ao agendar sua consulta: {e.detail}",
                "proximo_estado": "aguardando_escolha_horario"
            }
    return None

def ferramenta_consulta_preco(paciente, mensagem, session):
    """Ferramenta para lidar com consultas de preço."""
    return {
        "resposta": "Para que eu possa te passar um orçamento preciso e justo, preciso primeiro entender seu caso em uma avaliação clínica. Vamos marcar uma consulta inicial sem compromisso?",
        "proximo_estado": None
    }

def ferramenta_saudacao(paciente, mensagem, session):
    """Ferramenta para lidar com saudações."""
    if paciente.nome_completo:
        return {"resposta": f"Olá {paciente.nome_completo}! Em que posso ajudar você hoje?", "proximo_estado": None}
    return {"resposta": "Olá! Bem-vindo à nossa clínica. Em que posso ajudar você hoje?", "proximo_estado": None}

def ferramenta_padrao(paciente, mensagem, session):
    """Ferramenta padrão quando nenhuma outra se aplica."""
    return {
        "resposta": "Não entendi muito bem. Você gostaria de marcar uma consulta ou saber mais sobre nossos serviços?",
        "proximo_estado": None
    }

# --- Novo Endpoint do Agente ---

@app.post("/agente")
async def agente_router(request: TriageRequest, session: Session = Depends(get_session)):
    """
    Este é o cérebro principal do agente. Ele recebe todas as mensagens,
    analisa o estado e decide qual ferramenta usar.
    """
    try:
        # Limpa o senderId para remover o sufixo do WhatsApp
        sender_id_limpo = request.senderId.split('@')[0]
        
        # Busca o paciente no banco de dados ou cria um novo se não existir
        paciente = session.exec(select(Paciente).where(Paciente.sender_id == sender_id_limpo)).first()
        
        if not paciente:
            # Cria um novo paciente
            paciente = Paciente(
                sender_id=sender_id_limpo,
                nome_completo=request.senderName,
                estado_conversa=None
            )
            session.add(paciente)
            session.commit()
            session.refresh(paciente)
            
            # Mensagem de boas-vindas para novos usuários
            return {
                "resposta": "Olá! Bem-vindo à nossa clínica. Em que posso ajudar você hoje?",
                "nextAction": "ask_how_can_help"
            }
        
        # Verifica se temos um estado de conversa ativo
        if paciente.estado_conversa == "aguardando_data_agendamento":
            resultado = ferramenta_processar_data(paciente, request.messageText, session)
        elif paciente.estado_conversa == "aguardando_escolha_horario":
            resultado = await ferramenta_processar_horario(paciente, request.messageText, session)
        else:
            # Se não houver estado ativo, classifica a intenção
            intent_analysis = classify_intent(request.messageText)
            
            # Escolhe a ferramenta com base na intenção
            if intent_analysis["intent"] == "SCHEDULE_APPOINTMENT":
                resultado = ferramenta_agendar_consulta(paciente, request.messageText, session)
            elif intent_analysis["intent"] == "REQUEST_PRICE":
                resultado = ferramenta_consulta_preco(paciente, request.messageText, session)
            elif intent_analysis["intent"] == "GREETING":
                resultado = ferramenta_saudacao(paciente, request.messageText, session)
            else:
                resultado = ferramenta_padrao(paciente, request.messageText, session)
            
            # Se nenhuma ferramenta específica for aplicada, usa a ferramenta padrão
            if not resultado:
                resultado = ferramenta_padrao(paciente, request.messageText, session)
        
        # Se tivermos um resultado, retornamos
        if resultado:
            return {
                "resposta": resultado["resposta"],
                "nextAction": resultado.get("proximo_estado", None)
            }
        
        # Se chegarmos aqui, algo deu errado
        return {
            "resposta": "Desculpe, tive um problema ao processar sua mensagem. Poderia tentar novamente?",
            "nextAction": None
        }
        
    except Exception as e:
        session.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Erro ao processar a requisição: {str(e)}"
        )

# Mantendo o endpoint /triage para compatibilidade, mas agora ele apenas redireciona para o /agente
@app.post("/triage", response_model=TriageResponse)
async def triage(request: TriageRequest, session: Session = Depends(get_session)):
    """
    Endpoint de compatibilidade que redireciona para o novo endpoint /agente.
    Mantido para não quebrar integrações existentes.
    """
    try:
        # Chama o novo endpoint /agente
        response = await agente_router(request, session)
        
        # Converte a resposta para o formato antigo
        return TriageResponse(
            userStatus="existing_patient" if "Bem-vindo" not in response["resposta"] else "new_lead",
            analysis={"intent": "PROCESSED_BY_AGENT"},
            nextAction=response.get("nextAction", "clarify_intent"),
            responseText=response["resposta"]
        )
    except Exception as e:
        return TriageResponse(
            userStatus="error",
            analysis={"error": str(e)},
            nextAction="error_handling",
            responseText="Desculpe, ocorreu um erro ao processar sua solicitação. Por favor, tente novamente mais tarde."
        )