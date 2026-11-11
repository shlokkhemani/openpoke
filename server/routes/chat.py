from fastapi import APIRouter
from fastapi.responses import JSONResponse

from ..models import ChatHistoryClearResponse, ChatHistoryResponse, ChatRequest
from ..services import get_conversation_log, get_trigger_service, handle_chat_request

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("/send", response_class=JSONResponse, summary="Submit a chat message and receive a completion")
# Handle incoming chat messages and route them to the interaction agent
async def chat_send(
    payload: ChatRequest,
) -> JSONResponse:
    return await handle_chat_request(payload)


@router.get("/history", response_model=ChatHistoryResponse)
# Retrieve the conversation history from the log
def chat_history() -> ChatHistoryResponse:
    log = get_conversation_log()
    return ChatHistoryResponse(messages=log.to_chat_messages())


@router.delete("/history", response_model=ChatHistoryClearResponse)
def clear_history() -> ChatHistoryClearResponse:
    from ..services import get_execution_agent_logs

    # Clear conversation log
    log = get_conversation_log()
    log.clear()

    # Clear execution agent logs
    execution_logs = get_execution_agent_logs()
    execution_logs.clear_all()

    # Clear stored triggers
    trigger_service = get_trigger_service()
    trigger_service.clear_all()

    # Clear agents (ids, contacts, search index)
    from ..services.agents.store import get_agent_store

    get_agent_store().clear()

    return ChatHistoryClearResponse()


__all__ = ["router"]
