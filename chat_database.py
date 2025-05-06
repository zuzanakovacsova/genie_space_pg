import threading
from fastapi import HTTPException
from datetime import datetime
import logging
from db_config import get_connection, release_connection
from psycopg2.extras import Json
from contextlib import contextmanager
from models import MessageResponse, ChatHistoryResponse, ChatHistoryItem
logger = logging.getLogger(__name__)

class ChatDatabase:
    def __init__(self):
        self.db_lock = threading.Lock()
        self.first_message_cache = {}
        self.init_db()
    
    @contextmanager
    def get_db_connection(self):
        """Context manager for database connections"""
        conn = None
        try:
            conn = get_connection()
            yield conn
        finally:
            if conn:
                release_connection(conn)
    
    def init_db(self):
        """Initialize the database with required tables and indexes"""
        with self.db_lock:
            with self.get_db_connection() as conn:
                cursor = conn.cursor()
                try:
                    # # Drop existing tables if they exist
                    # cursor.execute('''
                    # DROP TABLE IF EXISTS genie_message_ratings;
                    # DROP TABLE IF EXISTS genie_messages;
                    # DROP TABLE IF EXISTS genie_sessions;
                    # ''')
                    
                    # Create genie_sessions table with minimal fields
                    cursor.execute('''
                    CREATE TABLE IF NOT EXISTS genie_sessions (
                        session_id TEXT PRIMARY KEY,
                        user_id TEXT NOT NULL,
                        conversation_id TEXT NOT NULL,
                        first_query TEXT,
                        created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                        is_active BOOLEAN DEFAULT TRUE
                    )
                    ''')
                    
                    # Create genie_messages table with essential fields
                    cursor.execute('''
                    CREATE TABLE IF NOT EXISTS genie_messages (
                        message_id TEXT PRIMARY KEY,
                        genie_message_id TEXT NOT NULL,
                        session_id TEXT NOT NULL,
                        conversation_id TEXT NOT NULL,
                        user_id TEXT NOT NULL,
                        content TEXT NOT NULL,
                        role TEXT NOT NULL,
                        status TEXT DEFAULT 'PENDING',
                        query_text TEXT,
                        created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                    )
                    ''')
                    
                    # Create genie_message_ratings table
                    cursor.execute('''
                    CREATE TABLE IF NOT EXISTS genie_message_ratings (
                        message_id TEXT NOT NULL,
                        user_id TEXT NOT NULL,
                        rating TEXT CHECK(rating IN ('up', 'down')),
                        created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                        PRIMARY KEY (message_id, user_id)
                    )
                    ''')
                    
                    conn.commit()
                except Exception as e:
                    conn.rollback()
                    logger.error(f"Error initializing database: {str(e)}")
                    raise
                finally:
                    cursor.close()
    
    def save_message_to_session(self, session_id: str, user_id: str, message: MessageResponse, conversation_id: str, query_text: str = None):
        """Save a message to a chat session, creating the session if it doesn't exist"""
        with self.db_lock:
            with self.get_db_connection() as conn:
                cursor = conn.cursor()
                try:
                    # Start transaction
                    cursor.execute('BEGIN')
                    
                    logger.info(f"Saving message: session_id={session_id}, user_id={user_id}, message_id={message.message_id}")
                    
                    # Check if session exists
                    cursor.execute('SELECT session_id FROM genie_sessions WHERE session_id = %s AND user_id = %s', (session_id, user_id))
                    if not cursor.fetchone():
                        logger.info(f"Creating new session: session_id={session_id}, user_id={user_id}")
                        # Create new session
                        cursor.execute('''
                        INSERT INTO genie_sessions (session_id, user_id, conversation_id, first_query, created_at, is_active)
                        VALUES (%s, %s, %s, %s, %s, %s)
                        ''', (
                            session_id,
                            user_id,
                            conversation_id,
                            message.content,
                            message.timestamp,
                            True
                        ))
                    
                    # Save message
                    cursor.execute('''
                    INSERT INTO genie_messages (
                        message_id, genie_message_id, session_id, conversation_id, user_id, content, role, 
                        status, query_text, created_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ''', (
                        message.message_id,
                        message.genie_message_id,
                        session_id,
                        conversation_id,
                        user_id,
                        message.content,
                        message.role,
                        'COMPLETED',
                        query_text,
                        message.timestamp
                    ))
                    
                    conn.commit()
                except Exception as e:
                    conn.rollback()
                    logger.error(f"Error saving message to session: {str(e)}")
                    raise
                finally:
                    cursor.close()
    
    def get_chat_history(self, user_id: str = None) -> ChatHistoryResponse:
        """Retrieve chat sessions with their messages for a specific user"""
        with self.db_lock:
            with self.get_db_connection() as conn:
                cursor = conn.cursor()
                try:
                    if user_id:
                        cursor.execute('''
                        SELECT s.session_id, s.first_query, s.created_at, s.is_active,
                               m.message_id, m.genie_message_id, m.content, m.role, m.status, m.query_text, m.created_at as message_timestamp
                        FROM genie_sessions s
                        LEFT JOIN genie_messages m ON s.session_id = m.session_id AND m.user_id = s.user_id
                        WHERE s.user_id = %s
                        ORDER BY s.created_at DESC, m.created_at ASC
                        ''', (user_id,))
                    else:
                        cursor.execute('''
                        SELECT s.session_id, s.first_query, s.created_at, s.is_active,
                               m.message_id, m.genie_message_id, m.content, m.role, m.status, m.query_text, m.created_at as message_timestamp
                        FROM genie_sessions s
                        LEFT JOIN genie_messages m ON s.session_id = m.session_id AND m.user_id = s.user_id
                        ORDER BY s.created_at DESC, m.created_at ASC
                        ''')
                    
                    sessions = {}
                    for row in cursor.fetchall():
                        session_id = row[0]
                        if session_id not in sessions:
                            sessions[session_id] = ChatHistoryItem(
                                sessionId=session_id,
                                firstQuery=row[1],
                                messages=[],
                                timestamp=row[2],
                                isActive=row[3]
                            )
                        
                        if row[4]:  # message_id exists
                            sessions[session_id].messages.append(MessageResponse(
                                message_id=row[4],
                                genie_message_id=row[5],
                                content=row[6],
                                role=row[7],
                                timestamp=row[10],
                                created_at=row[10]
                            ))
                    
                    # Sort messages by created_at for each session
                    for session in sessions.values():
                        session.messages.sort(key=lambda x: x.created_at)
                    
                    return ChatHistoryResponse(sessions=list(sessions.values()))
                except Exception as e:
                    logger.error(f"Error getting chat history: {str(e)}")
                    raise
                finally:
                    cursor.close()
    
    def get_chat(self, session_id: str, user_id: str = None) -> ChatHistoryItem:
        """Retrieve a specific chat session"""
        with self.db_lock:
            with self.get_db_connection() as conn:
                cursor = conn.cursor()
                try:
                    logger.info(f"Getting chat for session_id: {session_id}, user_id: {user_id}")
                    
                    # Get session info with user check
                    if user_id:
                        cursor.execute('''
                        SELECT first_query, created_at, is_active
                        FROM genie_sessions
                        WHERE session_id = %s AND user_id = %s
                        ''', (session_id, user_id))
                    else:
                        cursor.execute('''
                        SELECT first_query, created_at, is_active
                        FROM genie_sessions
                        WHERE session_id = %s
                        ''', (session_id,))
                    
                    session_data = cursor.fetchone()
                    if not session_data:
                        logger.error(f"Session not found: session_id={session_id}, user_id={user_id}")
                        raise HTTPException(status_code=404, detail="Chat not found")
                    
                    # Get messages ordered by created_at
                    cursor.execute('''
                    SELECT message_id, genie_message_id, content, role, status, query_text, user_id, created_at
                    FROM genie_messages
                    WHERE session_id = %s AND user_id = %s
                    ORDER BY created_at ASC
                    ''', (session_id, user_id))
                    
                    messages = []
                    for row in cursor.fetchall():
                        logger.info(f"Found message: message_id={row[0]}, user_id={row[6]}")
                        messages.append(MessageResponse(
                            message_id=row[0],
                            genie_message_id=row[1],
                            content=row[2],
                            role=row[3],
                            timestamp=row[7],
                            created_at=row[7]
                        ))
                    
                    return ChatHistoryItem(
                        sessionId=session_id,
                        firstQuery=session_data[0],
                        messages=messages,
                        timestamp=session_data[1],
                        isActive=session_data[2]
                    )
                except Exception as e:
                    logger.error(f"Error getting chat: {str(e)}")
                    raise
                finally:
                    cursor.close()
    
    def clear_session(self, session_id: str, user_id: str):
        """Clear a session and its messages"""
        with self.db_lock:
            with self.get_db_connection() as conn:
                cursor = conn.cursor()
                try:
                    cursor.execute('BEGIN')
                    
                    # Delete messages
                    cursor.execute('DELETE FROM messages WHERE session_id = %s AND user_id = %s', (session_id, user_id))
                    # Delete session
                    cursor.execute('DELETE FROM sessions WHERE session_id = %s AND user_id = %s', (session_id, user_id))
                    # Clear cache
                    if session_id in self.first_message_cache:
                        del self.first_message_cache[session_id]
                    
                    conn.commit()
                except Exception as e:
                    conn.rollback()
                    logger.error(f"Error clearing session: {str(e)}")
                    raise
                finally:
                    cursor.close()
    
    def is_first_message(self, session_id: str, user_id: str) -> bool:
        """Check if this is the first message in a session"""
        # Check cache first
        if session_id in self.first_message_cache:
            return self.first_message_cache[session_id]
            
        with self.db_lock:
            with self.get_db_connection() as conn:
                cursor = conn.cursor()
                try:
                    cursor.execute('''
                    SELECT COUNT(*) FROM messages 
                    WHERE session_id = %s AND user_id = %s
                    ''', (session_id, user_id))
                    
                    count = cursor.fetchone()[0]
                    is_first = count == 0
                    
                    # Update cache
                    self.first_message_cache[session_id] = is_first
                    return is_first
                except Exception as e:
                    logger.error(f"Error checking first message: {str(e)}")
                    raise
                finally:
                    cursor.close()

    def update_message_rating(self, message_id: str, user_id: str, rating: str | None) -> bool:
        """
        Update or remove the rating for a message.
        If rating is None, the rating is removed.
        Otherwise, rating should be 'up' or 'down'.
        """
        with self.db_lock:
            with self.get_db_connection() as conn:
                cursor = conn.cursor()
                try:
                    cursor.execute('BEGIN')
                    if rating is None:
                        # Remove the rating
                        cursor.execute('''
                            DELETE FROM genie_message_ratings 
                            WHERE message_id = %s AND user_id = %s
                        ''', (message_id, user_id))
                    else:
                        # Insert or update the rating
                        cursor.execute('''
                            INSERT INTO genie_message_ratings (message_id, user_id, rating)
                            VALUES (%s, %s, %s)
                            ON CONFLICT(message_id, user_id) DO UPDATE SET rating = EXCLUDED.rating
                        ''', (message_id, user_id, rating))
                    conn.commit()
                    return True
                except Exception as e:
                    conn.rollback()
                    logger.error(f"Error updating message rating: {str(e)}")
                    return False
                finally:
                    cursor.close()

    def get_message_rating(self, message_id: str, user_id: str) -> str | None:
        """Get the rating of a message"""
        with self.db_lock:
            with self.get_db_connection() as conn:
                cursor = conn.cursor()
                try:
                    cursor.execute('''
                    SELECT rating
                    FROM message_ratings
                    WHERE message_id = %s AND user_id = %s
                    ''', (message_id, user_id))
                    
                    result = cursor.fetchone()
                    return result[0] if result else None
                except Exception as e:
                    logger.error(f"Error getting message rating: {str(e)}")
                    return None
                finally:
                    cursor.close()