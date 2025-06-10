import datetime
import os.path
from google.auth.transport.requests import Request
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# --- CONFIGURAÇÕES ---
# Define os "escopos" ou permissões que nossa API precisa. Neste caso, ler e escrever na agenda.
SCOPES = ['https://www.googleapis.com/auth/calendar']
# O nome do arquivo de credenciais que você colocou no servidor.
CREDENTIALS_FILE = 'credentials.json'
# O ID da agenda. 'primary' se refere à agenda principal da conta.
# Se você criou uma agenda específica, coloque o ID dela aqui.
CALENDAR_ID = 'primary'

def authenticate_google():
    """Autentica com a API do Google usando a conta de serviço."""
    creds = None
    if os.path.exists(CREDENTIALS_FILE):
        creds = Credentials.from_service_account_file(
            CREDENTIALS_FILE, scopes=SCOPES)
    if not creds:
        raise Exception("Arquivo de credenciais não encontrado ou inválido.")
    return creds

def get_horarios_disponiveis(data_desejada: datetime.date):
    """
    Verifica os horários livres em um dia específico, das 9h às 18h,
    considerando eventos já existentes como ocupados.
    Retorna uma lista de horários de início disponíveis.
    """
    creds = authenticate_google()
    service = build('calendar', 'v3', credentials=creds)

    # Define o período de busca (das 9h às 18h no fuso de São Paulo)
    time_min = datetime.datetime.combine(data_desejada, datetime.time(9, 0)).isoformat() + '-03:00'
    time_max = datetime.datetime.combine(data_desejada, datetime.time(18, 0)).isoformat() + '-03:00'

    try:
        # Busca os eventos existentes no dia para saber os horários ocupados
        events_result = service.events().list(
            calendarId=CALENDAR_ID,
            timeMin=time_min,
            timeMax=time_max,
            singleEvents=True,
            orderBy='startTime'
        ).execute()
        eventos_ocupados = events_result.get('items', [])

        # Lógica para encontrar os horários livres
        horarios_livres = []
        duracao_consulta = datetime.timedelta(hours=1)
        horario_atual = datetime.datetime.fromisoformat(time_min)
        fim_do_dia = datetime.datetime.fromisoformat(time_max)

        while horario_atual < fim_do_dia:
            proximo_horario = horario_atual + duracao_consulta
            esta_livre = True
            
            # Verifica se o slot de 1h conflita com algum evento existente
            for evento in eventos_ocupados:
                evento_inicio = datetime.datetime.fromisoformat(evento['start'].get('dateTime'))
                evento_fim = datetime.datetime.fromisoformat(evento['end'].get('dateTime'))
                # Se o nosso slot começar durante um evento ou terminar durante um evento, está ocupado
                if not (proximo_horario <= evento_inicio or horario_atual >= evento_fim):
                    esta_livre = False
                    break # Já sabemos que está ocupado, podemos pular para o próximo slot
            
            if esta_livre:
                horarios_livres.append(horario_atual.strftime('%H:%M'))

            horario_atual = proximo_horario

        return horarios_livres

    except HttpError as error:
        print(f'Ocorreu um erro: {error}')
        return []

def criar_evento(service, titulo: str, data_hora_inicio: datetime, data_hora_fim: datetime):
    """Cria um novo evento na agenda do Google."""
    evento = {
        'summary': titulo,
        'description': 'Agendamento realizado pelo assistente virtual.',
        'start': {
            'dateTime': data_hora_inicio.isoformat(),
            'timeZone': 'America/Sao_Paulo',
        },
        'end': {
            'dateTime': data_hora_fim.isoformat(),
            'timeZone': 'America/Sao_Paulo',
        },
    }
    try:
        evento_criado = service.events().insert(calendarId=CALENDAR_ID, body=evento).execute()
        print(f"Evento criado: {evento_criado.get('htmlLink')}")
        return evento_criado
    except HttpError as error:
        print(f'Ocorreu um erro ao criar o evento: {error}')
        return None
