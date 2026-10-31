
"""Interpreta pedidos dos usuários e executa ações do Google Calendar e Google Sheets."""
import json
import os
import unicodedata

from dotenv import load_dotenv
from openai import OpenAI

from google_tools import agendar_entrevista_com_meet, registar_candidato_planilha


load_dotenv()

groq_api_key = os.getenv("GROQ_API_KEY")
if not groq_api_key:
    raise RuntimeError("A variável de ambiente GROQ_API_KEY não foi configurada.")

client = OpenAI(
    api_key=groq_api_key,
    base_url="https://api.groq.com/openai/v1",
)

modelo_groq = "openai/gpt-oss-20b"
planilha_id = os.getenv("PLANILHA_ID") or os.getenv("planilha_id")


# prompt para definir as regras do agente
PROMPT = (
    "Você é um assistente virtual especializado em processos seletivos. "
    "Sua função é ajudar na coordenação de entrevistas e no registro de candidatos "
    "em uma planilha do Google Sheets."
)


# função para normalizar ou tokenizar o texto
def normalizar(texto):
    """Normaliza o texto removendo acentos e convertendo para minúsculas."""
    texto_sem_acento = unicodedata.normalize("NFKD", str(texto))
    return "".join(
        caractere for caractere in texto_sem_acento if not unicodedata.combining(caractere)
    ).lower()


def registrar_candidato_na_planilha(
    nome,
    email,
    vaga=None,
    status=None,
    data_hora_inicio=None,
    data_hora_fim=None,
):
    """Registra um candidato na planilha configurada do Google Sheets."""
    if not planilha_id:
        raise ValueError("A variável PLANILHA_ID não foi configurada.")

    return registar_candidato_planilha(
        id_planilha=planilha_id,
        nome=nome,
        email=email,
        vaga=vaga,
        status=status,
        data_hora_inicio=data_hora_inicio,
        data_hora_fim=data_hora_fim,
    )


FERRAMENTAS = [
    {
        "type": "function",
        "function": {
            "name": "agendar_entrevista_com_meet",
            "description": "Agenda uma entrevista com link do Google Meet.",
            "parameters": {
                "type": "object",
                "properties": {
                    "nome_candidato": {
                        "type": "string",
                        "description": "Nome do candidato.",
                    },
                    "email_candidato": {
                        "type": "string",
                        "description": "E-mail do candidato.",
                    },
                    "data_hora_inicio": {
                        "type": "string",
                        "description": "Data e hora de início no formato ISO 8601.",
                    },
                    "data_hora_fim": {
                        "type": "string",
                        "description": "Data e hora de término no formato ISO 8601.",
                    },
                },
                "required": [
                    "nome_candidato",
                    "email_candidato",
                    "data_hora_inicio",
                    "data_hora_fim",
                ],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "registrar_candidato_na_planilha",
            "description": "Registra os dados de um candidato na planilha do Google Sheets.",
            "parameters": {
                "type": "object",
                "properties": {
                    "nome": {
                        "type": "string",
                        "description": "Nome do candidato.",
                    },
                    "email": {
                        "type": "string",
                        "description": "E-mail do candidato.",
                    },
                    "vaga": {
                        "type": "string",
                        "description": "Vaga para a qual o candidato está se candidatando.",
                    },
                    "status": {
                        "type": "string",
                        "description": "Status atual do processo seletivo.",
                    },
                    "data_hora_inicio": {
                        "type": "string",
                        "description": "Data e hora da entrevista em formato ISO 8601.",
                    },
                    "data_hora_fim": {
                        "type": "string",
                        "description": "Data e hora final em formato ISO 8601.",
                    },
                },
                "required": ["nome", "email"],
                "additionalProperties": False,
            },
        },
    },
]


# função para executar o agente
def executar_agente_rh(mensagem_usuario):
    """Executa o agente de RH com base na mensagem do usuário."""
    resposta = client.chat.completions.create(
        model=modelo_groq,
        messages=[
            {"role": "system", "content": PROMPT},
            {"role": "user", "content": mensagem_usuario},
        ],
        tools=FERRAMENTAS,
        tool_choice="auto",
    )

    mensagem = resposta.choices[0].message
    tool_calls = mensagem.tool_calls or []

    if not tool_calls:
        return [("texto", mensagem.content or "Ops, não sei fazer isso.")]

    resultados = []

    #executar cada ferramenta que o modelo decidiu chamar
    for chamada in tool_calls:
        nome = chamada.function.name #pega o nome da funcao a ser executada
        args = json.loads(chamada.function.arguments) #pega aos args da funcao 

    #se a funcao for agendar_entrevista_com_meet:
    if nome == "agendar_entrevista_com_meet":
        resultado = agendar_entrevista_com_meet(
            args["nome_candidato"],
            args["email_candidato"],
            args["data_hora_inicio"],
            args["data_hora_fim"],
        )
