from dataclasses import dataclass
from datetime import datetime
from typing import Optional, List, Dict, Any

@dataclass
class MessageResponse:
    message_id: str
    genie_message_id: str
    content: str
    role: str
    timestamp: datetime
    model: Optional[str] = None
    sources: Optional[List[Dict[str, Any]]] = None
    metrics: Optional[Dict[str, Any]] = None
    created_at: Optional[datetime] = None

@dataclass
class ChatHistoryResponse:
    sessions: List['ChatHistoryItem']

@dataclass
class ChatHistoryItem:
    conversationId: str
    firstQuery: str
    messages: List[MessageResponse]
    timestamp: datetime
    isActive: bool
    created_at: Optional[datetime] = None
