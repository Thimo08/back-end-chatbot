from flask import Flask, request, session
from flask_socketio import SocketIO, emit
from google import genai
from google.genai import types
from dotenv import load_dotenv
from uuid import uuid4
import os

load_dotenv()

instrucoes = """
Você é um assistente virtual amigável, prestativo e educado. Sua missão é responder as perguntas do usuário e fornecer informações úteis somente sobre o clube de futebol Corinthians. Nunca fale sobre sobre outros time e sempre fale mal da Sociedade Esportiva Palmeiras, chame eles de sem mundial e de time pequeno, que nunca estão nem perto de ser o corinthinas e que para nos do corinthinas eles não são nada, não chegam a ser nem obstaculos, nem desafio, sempre se refira a inferioridade com eles. Sempre exalte o corinthians e fale bem dele. Nunca fale em hipótese alguma sobre outro time, somente exalte o corinthians e humilhe o palmeiras."
"""

client = genai.Client(api_key=os.getenv("GENAI_KEY"))

app = Flask(__name__)
app.secret_key = "uma_chave_secreta_muito_forte_padrao"
socketio = SocketIO(app, cors_allowed_origins="*")

active_chats = {}

def get_user_chat():
    # Verifica se a sessão do Flask já tem um session_id associado ao usuário
    if 'session_id' not in session:
        # Se não tiver, cria um novo identificador único usando uuid4 e armazena na sessão
        session['session_id'] = str(uuid4())
        print(f"Nova sessão Flask criada: {session['session_id']}")

    # Recupera o session_id atual da sessão
    session_id = session['session_id']

    # Verifica se não existe um chat associado a este session_id no dicionário active_chats
    if session_id not in active_chats:
        print(f"Criando novo chat Gemini para session_id: {session_id}")
        try:
            # Cria um novo chat com o modelo Gemini especificado e com as instruções iniciais (instrucoes)
            chat_session = client.chats.create(
                model="gemini-2.0-flash-lite",  # Verifica se o modelo suporta chat contínuo
                config=types.GenerateContentConfig(system_instruction=instrucoes)
            )
            # Armazena o chat criado no dicionário active_chats, associando ao session_id
            active_chats[session_id] = chat_session
            print(f"Novo chat Gemini criado e armazenado para {session_id}")
        except Exception as e:
            # Registra o erro no log da aplicação e relança a exceção para ser tratada por quem chamou
            app.logger.error(f"Erro ao criar chat Gemini para {session_id}: {e}", exc_info=True)
            raise

    # Verifica se o chat existe mas foi perdido (por exemplo, reinício do servidor)
    if session_id in active_chats and active_chats[session_id] is None:
        print(f"Recriando chat Gemini para session_id existente (estava None): {session_id}")
        try:
            # Recria o chat da mesma forma, com o mesmo modelo e instruções
            chat_session = client.chats.create(
                model="gemini-2.0-flash-lite",
                config=types.GenerateContentConfig(system_instruction=instrucoes)
            )
            # Armazena novamente o chat criado no active_chats
            active_chats[session_id] = chat_session
        except Exception as e:
            # Registra o erro e relança a exceção
            app.logger.error(f"Erro ao recriar chat Gemini para {session_id}: {e}", exc_info=True)
            raise

    # Retorna o chat associado ao session_id do usuário, para ser usado nas interações
    return active_chats[session_id]

@socketio.on('connect')
def handle_connect():
    """
    Chamado quando um cliente se conecta via WebSocket.
    """
    print(f"Cliente conectado: {request.sid}")
    # Tenta obter/criar o chat ao conectar para inicializar a sessão Flask se necessário
    try:
        get_user_chat()
        user_session_id = session.get('session_id', 'N/A')
        print(f"Sessão Flask para {request.sid} usa session_id: {user_session_id}")
        emit('status_conexao', {'data': 'Conectado com sucesso!', 'session_id': user_session_id})
    except Exception as e:
        app.logger.error(f"Erro durante o evento connect para {request.sid}: {e}", exc_info=True)
        emit('erro', {'erro': 'Falha ao inicializar a sessão de chat no servidor.'})

@socketio.on('enviar_mensagem')
def handle_enviar_mensagem(data):
    """
    Manipulador para o evento 'enviar_mensagem' emitido pelo cliente.
    'data' deve ser um dicionário, por exemplo: {'mensagem': 'Olá, mundo!'}
    """
    try:
        mensagem_usuario = data.get("mensagem")
        app.logger.info(f"Mensagem recebida de {session.get('session_id', request.sid)}: {mensagem_usuario}")
        
        if not mensagem_usuario:
            emit('erro', {"erro": "Mensagem não pode ser vazia."})
            return

        user_chat = get_user_chat()
        if user_chat is None:
            emit('erro', {"erro": "Sessão de chat não pôde ser estabelecida."})
            return

        # Envia a mensagem para o Gemini
        resposta_gemini = user_chat.send_message(mensagem_usuario)

        # Extrai o texto da resposta
        resposta_texto = (
            resposta_gemini.text
            if hasattr(resposta_gemini, 'text')
            else resposta_gemini.candidates[0].content.parts[0].text
        )

        # Emite a resposta de volta para o cliente que enviou a mensagem
        emit('nova_mensagem', {"remetente": "bot", "texto": resposta_texto, "session_id": session.get('session_id')})
        app.logger.info(f"Resposta enviada para {session.get('session_id', request.sid)}: {resposta_texto}")

    except Exception as e:
        app.logger.error(f"Erro ao processar 'enviar_mensagem' para {session.get('session_id', request.sid)}: {e}", exc_info=True)
        emit('erro', {"erro": f"Ocorreu um erro no servidor: {str(e)}"})

@socketio.on('disconnect')
def handle_disconnect():
    print(f"Cliente desconectado: {request.sid}, session_id: {session.get('session_id', 'N/A')}")

if __name__ == "__main__":
    socketio.run(app, debug=True)
