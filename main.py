# main.py - Versão 3.1 (Lógica de Preços 100% Consistente)

from fastapi import FastAPI, HTTPException, Depends
from sqlmodel import Field, Session, SQLModel, create_engine, select
from typing import Optional, List, Dict
from datetime import datetime

# --- Modelos de Dados ---
# (Nenhuma mudança aqui)
class Paciente(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    sender_id: str = Field(index=True, unique=True)
    nome_completo: Optional[str] = None
    data_criacao: datetime = Field(default_factory=datetime.utcnow, nullable=False)

class TriageRequest(SQLModel):
    senderId: str
    senderName: Optional[str] = None
    messageText: str
    timestamp: str

class TriageResponse(SQLModel):
    userStatus: str
    analysis: dict
    nextAction: str
    responseText: str

# --- Configuração do Banco de Dados e Funções ---
# (Nenhuma mudança aqui)
DATABASE_URL = "sqlite:///db.sqlite"
engine = create_engine(DATABASE_URL)

def create_db_and_tables():
    SQLModel.metadata.create_all(engine)

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

# --- Lógica do Aplicativo FastAPI ---
app = FastAPI(
    title="Triage API",
    description="API para triagem de pacientes com persistência de dados.",
    on_startup=[create_db_and_tables]
)

@app.get("/")
async def root():
    return {"status": "API online", "versao": "3.1"}

@app.post("/triage", response_model=TriageResponse)
async def triage(request: TriageRequest, session: Session = Depends(get_session)):
    try:
        sender_id_limpo = request.senderId.split('@')[0]
        intent_analysis = classify_intent(request.messageText)
        statement = select(Paciente).where(Paciente.sender_id == sender_id_limpo)
        paciente_existente = session.exec(statement).first()

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