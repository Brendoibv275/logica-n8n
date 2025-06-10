# main.py - Versão 3.1 (Lógica de Preços 100% Consistente)

from fastapi import FastAPI, HTTPException, Depends, Query, status
from pydantic import BaseModel
from sqlmodel import Field, Session, SQLModel, create_engine, select
from typing import Optional, List, Dict, Union
from datetime import datetime, date
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
    messageText: str
    nomeCompleto: Optional[str] = None

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

@app.post("/triage", response_model=TriageResponse)
async def triage(request: TriageRequest, session: Session = Depends(get_session)):
    try:
        # Limpa o senderId para remover o sufixo do WhatsApp e garantir consistência
        sender_id_limpo = request.senderId.split('@')[0]
        
        # Busca o paciente no banco de dados
        statement = select(Paciente).where(Paciente.sender_id == sender_id_limpo)
        paciente_existente = session.exec(statement).first()
        
        # --- LÓGICA DE ESTADO ---
        # Primeiro, verifica se já estamos no meio de uma conversa
        if paciente_existente and paciente_existente.estado_conversa == "aguardando_data_agendamento":
            # O usuário está respondendo a data!
            data_desejada = parse_human_date(request.messageText)
            
            if data_desejada:
                # Se entendemos a data, buscamos os horários
                horarios = get_horarios_disponiveis(data_desejada)
                if horarios:
                    # Atualiza o estado para o próximo passo
                    paciente_existente.estado_conversa = "aguardando_escolha_horario"
                    session.add(paciente_existente)
                    session.commit()
                    
                    horarios_formatados = ", ".join(horarios)
                    return TriageResponse(
                        userStatus="existing_patient",
                        analysis={"intent": "CONTINUE_APPOINTMENT"},
                        nextAction="present_horarios",
                        responseText=f"Ótimo! Para o dia {data_desejada.strftime('%d/%m')}, tenho os seguintes horários: {horarios_formatados}. Qual deles você prefere?"
                    )
                else:
                    # Não achamos horários
                    return TriageResponse(
                        userStatus="existing_patient",
                        analysis={"intent": "CONTINUE_APPOINTMENT"},
                        nextAction="ask_another_date",
                        responseText=f"Puxa, não encontrei horários disponíveis para {data_desejada.strftime('%d/%m')}. Você gostaria de tentar outra data?"
                    )
            else:
                # Não entendemos a data
                return TriageResponse(
                    userStatus="existing_patient",
                    analysis={"intent": "CONTINUE_APPOINTMENT"},
                    nextAction="ask_date_again",
                    responseText="Não consegui entender a data. Por favor, tente dizer de outra forma (ex: 'amanhã', 'dia 15 de junho' ou '15/06')."
                )

        # Se não estivermos em um estado de conversa, faz a classificação normal de intenção
        intent_analysis = classify_intent(request.messageText)

        if paciente_existente:
            # Lógica para paciente existente (JÁ ESTAVA CORRETA)
            response_text = f"Olá {paciente_existente.nome_completo or 'cliente'}! "
            if intent_analysis["intent"] == "SCHEDULE_APPOINTMENT":
                response_text += "Vou te ajudar com o agendamento. Qual o melhor dia e horário para você?"
                next_action = "schedule_appointment"
            elif intent_analysis["intent"] == "REQUEST_PRICE":
                response_text += "Entendo seu interesse nos valores. Para te passar um orçamento preciso e justo, que é o correto, eu preciso primeiro fazer uma avaliação clínica. Vamos marcar uma consulta sem compromisso para eu entender seu caso?"
                next_action = "pivot_to_schedule"
            elif intent_analysis["intent"] == "GREETING":
                response_text += "Em que posso ajudar você hoje?"
                next_action = "ask_how_can_help"
            else:
                response_text += "Não entendi muito bem. Você gostaria de marcar uma consulta ou saber mais sobre nossos serviços?"
                next_action = "clarify_intent"
            return TriageResponse(userStatus="existing_patient", analysis=intent_analysis, nextAction=next_action, responseText=response_text)
        else:
            # Lógica para novo lead
            novo_paciente = Paciente(sender_id=sender_id_limpo, nome_completo=request.senderName)
            session.add(novo_paciente)
            session.commit()
            session.refresh(novo_paciente)
            
            response_text = "Olá! Bem-vindo à nossa clínica. "
            if intent_analysis["intent"] == "SCHEDULE_APPOINTMENT":
                response_text += "Antes de agendarmos, preciso de algumas informações. Qual seu nome completo?"
                next_action = "collect_contact_info"

            # <<< ESTA É A CORREÇÃO QUE FIZEMOS >>>
            elif intent_analysis["intent"] == "REQUEST_PRICE":
                response_text += "Para que eu possa te passar um orçamento preciso e justo, preciso primeiro entender seu caso em uma avaliação clínica. Vamos marcar uma consulta inicial sem compromisso?"
                next_action = "pivot_to_schedule"

            elif intent_analysis["intent"] == "GREETING":
                response_text += "Em que posso ajudar você hoje?"
                next_action = "ask_how_can_help"
            else:
                response_text += "Poderia me dizer como posso ajudar? Por exemplo, gostaria de marcar uma consulta ou saber mais sobre nossos serviços?"
                next_action = "clarify_intent"
            return TriageResponse(userStatus="new_lead", analysis=intent_analysis, nextAction=next_action, responseText=response_text)
            
    except Exception as e:
        session.rollback()
        raise HTTPException(status_code=500, detail=f"Erro ao processar a requisição: {str(e)}")