
"""Interpreta pedidos dos usuários e executa as ações do Google."""

import json #converter os dados das ferramentas do Google em JSON
import os #interagir com o sistema operacional / arquivos
import unicodedata #normalizar strings Unicode (data/hora)

from dotenv import load_dotenv #carregar variáveis de ambiente do arquivo .env
from openai import OpenAI #interagir com a API compatível com OpenAI

from google_tools import autenticar_google, agendar_entrevista_com_meet, registrar_candidato_planilha #importa funções do módulo google_tools

#carregar a groq_api_key
load_dotenv() #carrega as variáveis de ambiente do arquivo .env
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

client = OpenAI(
    api_key=GROQ_API_KEY,
    base_url="https://api.groq.com/openai/v1",
) if GROQ_API_KEY else None

#definir o modelo e indicar o id da planilha
MODELO_GROQ = "openai/gpt-oss-20b" #modelo open source da OpenAI
PLANILHA_ID = os.environ.get("PLANILHA_ID") #ID da planilha do Google Sheets (armazenado no arquivo .env)

#criando as ferramentas do agente
FERRAMENTAS = [
    {
        "type": "function", #tipo de ferramenta (função)
        "function": {
            "name": "agendar_entrevista_com_meet", #nome da função
            "description": "Agendar uma entrevista no Google Calendar com link do Google Meet.", #descrição da função
            "parameters": {
                "type": "object",
                "properties": {
                    "nome_candidato": {"type": "string"},
                    "email_candidato": {"type": "string"},
                    "vaga": {"type": "string"},
                    "status": {"type": "string"},
                    "data_hora_inicio": {
                        "type": "string",
                        "description": "Data e hora de início da entrevista no formato ISO 8601 (ex: 2026-11-10T14:00:00)."
                    },
                    "data_hora_fim": {
                        "type": "string",
                        "description": "Data e hora de término da entrevista no formato ISO 8601 (ex: 2026-11-10T15:00:00)."
                    }
                },
                "required": [
                    "nome_candidato",
                    "email_candidato",
                    "data_hora_inicio",
                    "data_hora_fim"
                ]
            }
        }
    },
    {
        "type": "function", #tipo de ferramenta (função)
        "function": {
            "name": "registrar_candidato_planilha", #nome da função
            "description": "Registrar informações do candidato na planilha do Google Sheets.", #descrição da função
            "parameters": {
                "type": "object", #tipo de parâmetro (objeto)
                "properties": { #propriedades do objeto candidato
                    "nome": {"type": "string"},
                    "email": {"type": "string"},
                    "vaga": {"type": "string"},
                    "status": {"type": "string"},
                    "data_hora_inicio": {"type": "string"},
                    "data_hora_fim": {"type": "string"}
                },
                "required": ["nome", "email"]
            }
        }
    }
]

#prompt para definir as regras do agente e os padrões para os dados informados
PROMPT = (
    "Você é um agente de recrutamento que interage com recrutadores e gerencia entrevistas. "
    "Seu objetivo é coletar informações dos candidatos, agendar entrevistas no Google Calendar com link do Google Meet, "
    "e registrar os dados na planilha do Google Sheets. "
    "Siga as ações solicitadas pelo usuário. Para agendar uma nova entrevista, obtenha nome, e-mail, vaga, status e data/hora de início "
    "no formato ISO 8601 (ex: 2026-11-10T14:00:00); se não houver horário de término, use duração padrão de 1 hora. "
    "Sempre que agendar uma entrevista, registre também o candidato na planilha com os mesmos dados e horários. "
    "Se o usuário pedir apenas para registrar os dados, ou informar que a reunião já está agendada, use somente a ferramenta da planilha "
    "e não crie outro evento no Calendar."
)

#função para normalizar os dados de entrada do usuário
def normalizar(texto):
    """Normalizar, removendo acentos e convertendo o pedido para minúsculas."""
    sem_acento = unicodedata.normalize("NFKD", texto)
    return "".join(
        letra for letra in sem_acento
        if not unicodedata.combining(letra)
    ).lower()

#função para executar o agente de recrutamento
def executar_agente_rh(mensagem_usuario):
    """Executa o agente de recrutamento, interpretando a mensagem do usuário e chamando as funções apropriadas."""

    if client is None:
        return [("erro", "Configure a chave de API do Groq para usar o agente.")]

    #enviar a mensagem do usuário para o modelo gpt-oss-20b hospedado na Groq
    resposta = client.chat.completions.create(
        model=MODELO_GROQ,
        messages=[
            {"role": "system", "content": PROMPT}, #papel/comportamento do agente
            {"role": "user", "content": mensagem_usuario} #mensagem do usuário
        ],
        tools=FERRAMENTAS, #ferramentas disponíveis para o agente
        tool_choice="auto" #o agente escolhe automaticamente a ferramenta apropriada
    )

    #extrair a mensagem retornada pela IA dentro da resposta da API
    mensagem = resposta.choices[0].message

    #busca as ferramentas disponíveis pelo modelo
    tool_calls = mensagem.tool_calls or []

    #se não chamar nenhuma ferramenta, retorna a resposta textual
    if not tool_calls:
        return [("texto", mensagem.content or "Ops, não sei fazer isso.")]

    resultados = []
    argumentos_agendamento = None
    argumentos_planilha = None

    for chamada in tool_calls:
        nome = chamada.function.name
        argumentos = json.loads(chamada.function.arguments)
        if nome == "agendar_entrevista_com_meet":
            argumentos_agendamento = argumentos
        elif nome == "registrar_candidato_planilha":
            argumentos_planilha = argumentos
        else:
            resultados.append(("erro", f"Função desconhecida: {nome}"))

    agendamento_concluido = False
    if argumentos_agendamento:
        try:
            link_meet = agendar_entrevista_com_meet(
                argumentos_agendamento["nome_candidato"],
                argumentos_agendamento["email_candidato"],
                argumentos_agendamento["data_hora_inicio"],
                argumentos_agendamento["data_hora_fim"]
            )
            resultados.append(("calendar", link_meet))
            agendamento_concluido = True
        except Exception as erro:
            resultados.append(("erro", f"Falha ao agendar entrevista: {erro}"))

    if argumentos_planilha or agendamento_concluido:
        dados_candidato = {
            **(argumentos_agendamento or {}),
            **(argumentos_planilha or {}),
        }
        nome = dados_candidato.get("nome") or dados_candidato.get("nome_candidato")
        email = dados_candidato.get("email") or dados_candidato.get("email_candidato")

        if not PLANILHA_ID:
            resultados.append(("erro", "Configure PLANILHA_ID no arquivo .env para registrar candidatos."))
        elif not nome or not email:
            resultados.append(("erro", "Nome e e-mail são obrigatórios para registrar o candidato na planilha."))
        else:
            try:
                resultado = registrar_candidato_planilha(
                    PLANILHA_ID,
                    nome,
                    email,
                    vaga=dados_candidato.get("vaga", "Não informada"),
                    status=dados_candidato.get("status", ""),
                    data_hora_inicio=dados_candidato.get("data_hora_inicio"),
                    data_hora_fim=dados_candidato.get("data_hora_fim"),
                )
                resultados.append(("sheets", resultado))
            except Exception as erro:
                resultados.append(("erro", f"Falha ao registrar candidato no Google Sheets: {erro}"))

    return resultados
