# main.py - Versão da Etapa 2 (com Banco de Dados)

from fastapi import FastAPI, HTTPException, Depends
from sqlmodel import Field, Session, SQLModel, create_engine, select
from typing import Optional, List, Dict
from datetime import datetime

# --- Modelos de Dados ---
# Modelo da Tabela do Banco de Dados
class Paciente(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    sender_id: str = Field(index=True, unique=True)
    nome_completo: Optional[str] = None
    data_criacao: datetime = Field(default_factory=datetime.utcnow, nullable=False)

# Modelo da Requisição (Entrada da API)
class TriageRequest(SQLModel):
    senderId: str
    senderName: Optional[str] = None
    messageText: str
    timestamp: str

# Modelo da Resposta (Saída da API)
class TriageResponse(SQLModel):
    userStatus: str
    analysis: dict
    nextAction: str
    responseText: str

# --- Configuração do Banco de Dados ---
DATABASE_URL = "sqlite:///db.sqlite"
engine = create_engine(DATABASE_URL, echo=True) # echo=True ajuda a ver as queries SQL no log

def create_db_and_tables():
    SQLModel.metadata.create_all(engine)

# --- Gestão de Sessão do Banco de Dados ---
def get_session():
    with Session(engine) as session:
        yield session

# --- Função de Classificação de Intenção ---
def classify_intent(text: str) -> dict:
    """
    Analisa o texto da mensagem e classifica a intenção do usuário.
    Retorna um dicionário com 'intent' e 'confidence'.
    """
    if not text:
        return {"intent": "UNKNOWN", "confidence": 0.0}
    
    text = text.lower()
    
    # Listas de palavras-chave para cada intenção
    agendamento_keywords = ["marcar", "agendar", "agendamento", "consulta", "horário", "horario"]
    orcamento_keywords = ["preço", "preco", "valor", "quanto", "custa", "custo"]
    saudacao_keywords = ["oi", "olá", "ola", "bom dia", "boa tarde", "boa noite", "e aí", "tudo bem"]
    
    # Verifica cada categoria de intenção
    if any(keyword in text for keyword in agendamento_keywords):
        return {"intent": "SCHEDULE_APPOINTMENT", "confidence": 0.9}
    elif any(keyword in text for keyword in orcamento_keywords):
        return {"intent": "REQUEST_PRICE", "confidence": 0.9}
    elif any(keyword in text for keyword in saudacao_keywords):
        return {"intent": "GREETING", "confidence": 0.9}
    
    # Se nenhuma palavra-chave for encontrada
    return {"intent": "UNKNOWN", "confidence": 0.3}

# --- Lógica do Aplicativo FastAPI ---
app = FastAPI(
    title="Triage API",
    description="API para triagem de pacientes com persistência de dados.",
    on_startup=[create_db_and_tables] # Executa na inicialização
)

@app.get("/")
async def root():
    return {"status": "API online", "versao": "2.0 com DB"}

@app.post("/triage", response_model=TriageResponse)
async def triage(request: TriageRequest, session: Session = Depends(get_session)):
    """
    Endpoint de triagem que processa mensagens e retorna uma resposta baseada no status do usuário,
    consultando e salvando em um banco de dados.
    """
    try:
        # 1. Classifica a intenção da mensagem
        intent_analysis = classify_intent(request.messageText)
        
        # 2. Busca o paciente no banco de dados
        statement = select(Paciente).where(Paciente.sender_id == request.senderId)
        paciente_existente = session.exec(statement).first()

        if paciente_existente:
            # 3. Resposta para paciente existente
            response_text = f"Olá {paciente_existente.nome_completo or 'cliente'}! "
            
            # Personaliza a resposta baseada na intenção
            if intent_analysis["intent"] == "SCHEDULE_APPOINTMENT":
                response_text += "Vou te ajudar com o agendamento. Qual o melhor dia e horário para você?"
                next_action = "schedule_appointment"
            elif intent_analysis["intent"] == "REQUEST_PRICE":
                response_text += "Vou verificar os valores para você. Me diz qual procedimento você tem interesse?"
                next_action = "provide_price_info"
            elif intent_analysis["intent"] == "GREETING":
                response_text += "Em que posso ajudar você hoje?"
                next_action = "ask_how_can_help"
            else:
                response_text += "Não entendi muito bem. Você gostaria de marcar uma consulta ou saber mais sobre nossos serviços?"
                next_action = "clarify_intent"
            
            return TriageResponse(
                userStatus="existing_patient",
                analysis=intent_analysis,
                nextAction=next_action,
                responseText=response_text
            )
        else:
            # 4. Cria um novo paciente e salva no banco
            novo_paciente = Paciente(
                sender_id=request.senderId,
                nome_completo=request.senderName
            )
            session.add(novo_paciente)
            session.commit()
            session.refresh(novo_paciente)
            
            # 5. Resposta para novo lead
            response_text = "Olá! Bem-vindo à nossa clínica. "
            
            # Personaliza a resposta baseada na intenção
            if intent_analysis["intent"] == "SCHEDULE_APPOINTMENT":
                response_text += "Antes de agendarmos, preciso de algumas informações. Qual seu nome completo?"
                next_action = "collect_contact_info"
            elif intent_analysis["intent"] == "REQUEST_PRICE":
                response_text += "Fico feliz em ajudar com orçamentos! De qual procedimento você gostaria de saber o valor?"
                next_action = "provide_price_info"
            elif intent_analysis["intent"] == "GREETING":
                response_text += "Em que posso ajudar você hoje?"
                next_action = "ask_how_can_help"
            else:
                response_text += "Poderia me dizer como posso ajudar? Por exemplo, gostaria de marcar uma consulta ou saber mais sobre nossos serviços?"
                next_action = "clarify_intent"
            
            return TriageResponse(
                userStatus="new_lead",
                analysis=intent_analysis,
                nextAction=next_action,
                responseText=response_text
            )
            
    except Exception as e:
        session.rollback() # Garante que transações com erro não sejam salvas
        raise HTTPException(status_code=500, detail=f"Erro ao processar a requisição: {str(e)}")