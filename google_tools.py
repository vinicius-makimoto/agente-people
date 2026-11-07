
# Etapa 1: Importar as bibliotecas
import os # Acessa os arquivos do sistema
import unicodedata # Remove caracteres especiais
import uuid # Gera um ID único para solicitar uma reunião do Google Meet
from datetime import datetime # Trabalhar com datas
from google.auth.exceptions import RefreshError # Trata erros de autenticação
from google.auth.transport.requests import Request # Faz requisições para a API do Google
from google.oauth2.credentials import Credentials # Trabalha com credenciais do Google
from google_auth_oauthlib.flow import InstalledAppFlow # Faz o fluxo de autenticação do Google
from googleapiclient.discovery import build # Constrói o serviço da API do Google

# Etapa 2: Criar escopo de autenticação
SCOPES = [
    'https://www.googleapis.com/auth/spreadsheets', # Acesso à planilha do Google
    'https://www.googleapis.com/auth/calendar.events' # Acesso aos eventos do Google Calendar
]

# Dicionário com os nomes das colunas na planilha
CAMPOS_DA_PLANILHA = {
    "nome": {"nome", "nome candidato"},
    "vaga": {"vaga", "cargo"},
    "data": {"data", "dataentrevista"},
    "hora": {"hora", "horario", "horarioentrevista"},
    "email": {"email", "emailcandidato"},
    "status": {"status", "situacao"},
}

# Etapa 3: Função para autenticar e criar o serviço da API do Google
def autenticar_google():
    """Autentica na API do Google e retorna as credenciais."""
    credentials = None # Variável para armazenar as credenciais do Google

    if os.path.exists('token.json'):
        # Carrega as credenciais do arquivo de token
        credentials = Credentials.from_authorized_user_file(
            'token.json', SCOPES
        )

    if credentials and credentials.expired and credentials.refresh_token:
        # Verifica se as credenciais expiraram
        try:
            credentials.refresh(Request()) # Atualiza as credenciais
        except RefreshError as erro:
            # Verifica se ocorreu um erro de concessão inválida
            if "invalid_grant" not in str(erro):
                raise
            credentials = None # Força uma nova autenticação

    if not credentials or not credentials.valid:
        # Cria o fluxo de autenticação
        fluxo = InstalledAppFlow.from_client_secrets_file(
            'credentials.json', SCOPES
        )
        credentials = fluxo.run_local_server(port=0)

    # Salva as credenciais no arquivo de token
    with open('token.json', 'w') as arquivo_token:
        arquivo_token.write(credentials.to_json())

    return credentials # Retorna as credenciais


# Etapa 4: Agendar entrevista no Google Calendar
def agendar_entrevista_com_meet(
    nome_candidato,
    email_candidato,
    data_hora_inicio,
    data_hora_fim,
):
    """Agenda uma entrevista no Google Calendar com link do Google Meet."""

    # Cria o serviço do Google Calendar
    servico = build(
        'calendar',
        'v3',
        credentials=autenticar_google()
    )

    evento = {
        "summary": f"Entrevista com {nome_candidato}", # Título do evento
        "description": "Entrevista de alinhamento com o time de People",
        "start": {
            "dateTime": data_hora_inicio, # Data e hora de início
            "timeZone": "America/Sao_Paulo", # Fuso horário
        },
        "end": {
            "dateTime": data_hora_fim, # Data e hora de término
            "timeZone": "America/Sao_Paulo", # Fuso horário
        },
        "attendees": [
            {"email": email_candidato}, # Adiciona o candidato como participante
        ],
        "conferenceData": {
            "createRequest": {
                "requestId": str(uuid.uuid4()), # ID único da solicitação
                "conferenceSolutionKey": {"type": "hangoutsMeet"},
            }
        },
    }

    # POST - Cria o evento no Google Calendar
    evento_criado = servico.events().insert(
        calendarId='primary',
        body=evento,
        conferenceDataVersion=1,
        sendUpdates='all'
    ).execute()

    link_meet = evento_criado.get("hangoutLink") # Obtém o link do Google Meet

    return link_meet


# Etapa 5: Registrar candidato na planilha
def registrar_candidato_planilha(
    id_planilha,
    nome,
    email,
    vaga=None,
    status=None,
    data_hora_inicio=None,
    data_hora_fim=None
):
    """Prepara os dados do candidato para registro no Google Sheets."""

    servico = build(
        'sheets',
        'v4',
        credentials=autenticar_google()
    )

    # GET - Consulta as propriedades da planilha
    planilha = servico.spreadsheets().get(
        spreadsheetId=id_planilha,
        fields="sheets(properties(sheetId,title))"
    ).execute()

    aba = next(
        (
            item
            for item in planilha.get("sheets", [])
            if item.get("properties", {}).get("sheetId") == 0
        ),
        None
    )

    if not aba: # Se não encontrar a aba
        raise ValueError("Aba da planilha não encontrada.")

    # Obtém o nome da aba selecionada
    nome_aba = aba["properties"]["title"]
    nome_aba_escapado = nome_aba.replace("'", "''")
    intervalo = f"'{nome_aba_escapado}'!A1:F1"

    # GET - Consulta os cabeçalhos da planilha
    resposta = servico.spreadsheets().values().get(
        spreadsheetId=id_planilha,
        range=intervalo
    ).execute()

    linhas = resposta.get("values", [])
    cabecalhos = linhas[0] if linhas else []

    # Normaliza os nomes dos cabeçalhos
    def normalizar(texto):
        texto = unicodedata.normalize("NFKD", str(texto))
        texto = "".join(
            caractere for caractere in texto
            if not unicodedata.combining(caractere)
        )
        return texto.strip().lower().replace(" ", "")

    # Identifica as colunas existentes
    colunas = {}

    for indice, cabecalho in enumerate(cabecalhos):
        cabecalho_normalizado = normalizar(cabecalho)

        for campo, alternativas in CAMPOS_DA_PLANILHA.items():
            alternativas_normalizadas = {
                normalizar(alternativa)
                for alternativa in alternativas
            }

            if cabecalho_normalizado in alternativas_normalizadas:
                colunas[campo] = indice
                break

    # Prepara os dados do candidato
    dados = {
        "nome": nome,
        "email": email,
        "vaga": vaga,
        "status": status,
    }

    if data_hora_inicio and "data" in colunas:
        try:
            inicio = datetime.fromisoformat(data_hora_inicio)
            dados["data"] = inicio.strftime("%d/%m/%Y") # Formata a data

            if "hora" in colunas:
                hora = inicio.strftime("%H:%M") # Formata a hora
                if data_hora_fim:
                    fim = datetime.fromisoformat(data_hora_fim)
                    hora += f" - {fim.strftime('%H:%M')}" # Formata a hora de término

                dados["hora"] = hora
        except ValueError:
            raise ValueError("Formato de data/hora inválido. Use o formato YYYY-MM-DDTHH:MM:SS.")

    # Prepara uma lista com strings para cobrir toda a planilha
    valores = [""] * (max(colunas.values()) + 1) #cria uma lista de strings vazias com o tamanho da maior coluna
    for campo, valor in dados.items():
        if campo in colunas:
            valores[colunas[campo]] = valor #atribui o valor do campo na posição correta da lista

    #adiciona os valores na planilha
    resultado = servico.spreadsheets().values().append(
        spreadsheetId=id_planilha,
        range=intervalo,
        valueInputOption="USER_ENTERED",
        body={"values": [valores]}
    ).execute()

    return "Candidato registrado com sucesso na planilha."