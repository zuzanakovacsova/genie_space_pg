import threading
from fastapi import HTTPException
from datetime import datetime
import logging
from db_config import db_manager
from models import MessageResponse
from sqlalchemy import text
import time

logger = logging.getLogger(__name__)

class ChatDatabase:
    _initialized = False
    _init_lock = threading.Lock()

    def __init__(self):
        self.first_message_cache = {}
        self._init_db()
    
    def _init_db(self):
        """Initialize database tables if they don't exist."""
        if not ChatDatabase._initialized:
            with ChatDatabase._init_lock:
                if not ChatDatabase._initialized:  # Double-check pattern
                    try:
                        logger.info("Initializing database tables")
                        with db_manager.managed_connection() as conn:
                            # Create genie_sessions table
                            conn.execute(text("""
                                CREATE TABLE IF NOT EXISTS genie_sessions (
                                    session_id TEXT PRIMARY KEY,
                                    user_id TEXT NOT NULL,
                                    conversation_id TEXT NOT NULL,
                                    first_query TEXT,
                                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                                    is_active BOOLEAN DEFAULT TRUE
                                )
                            """))
                            
                            # Create genie_messages table
                            conn.execute(text("""
                                CREATE TABLE IF NOT EXISTS genie_messages (
                                    message_id TEXT PRIMARY KEY,
                                    genie_message_id TEXT NOT NULL,
                                    session_id TEXT NOT NULL,
                                    conversation_id TEXT NOT NULL,
                                    user_id TEXT NOT NULL,
                                    content TEXT NOT NULL,
                                    role TEXT NOT NULL,
                                    status TEXT DEFAULT 'completed',
                                    query_text TEXT,
                                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                                    FOREIGN KEY (session_id) REFERENCES genie_sessions(session_id)
                                )
                            """))
                            
                            # Create genie_message_ratings table
                            conn.execute(text("""
                                CREATE TABLE IF NOT EXISTS genie_message_ratings (
                                    message_id TEXT NOT NULL,
                                    user_id TEXT NOT NULL,
                                    rating TEXT,
                                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                                    PRIMARY KEY (message_id, user_id),
                                    FOREIGN KEY (message_id) REFERENCES genie_messages(message_id)
                                )
                            """))
                            
                            conn.commit()
                            ChatDatabase._initialized = True
                            logger.info("Database initialized successfully")
                    except Exception as e:
                        logger.error(f"Error initializing database: {str(e)}")
                        raise

    def save_message_to_session(self, session_id: str, user_id: str, message: MessageResponse, conversation_id: str, query_text: str = None):
        """Save a message to a chat session, creating the session if it doesn't exist"""
        try:
            logger.info(f"Starting to save message: session_id={session_id}, user_id={user_id}, message_id={message.message_id}")
            with db_manager.managed_connection() as conn:
                # Check if session exists
                result = conn.execute(text(
                    'SELECT session_id FROM genie_sessions WHERE session_id = :session_id AND user_id = :user_id'
                ), {'session_id': session_id, 'user_id': user_id})
                
                if not result.fetchone():
                    logger.info(f"Creating new session: session_id={session_id}, user_id={user_id}")
                    # Create new session
                    conn.execute(text("""
                        INSERT INTO genie_sessions (session_id, user_id, conversation_id, first_query, created_at, is_active)
                        VALUES (:session_id, :user_id, :conversation_id, :first_query, :created_at, :is_active)
                    """), {
                        'session_id': session_id,
                        'user_id': user_id,
                        'conversation_id': conversation_id,
                        'first_query': message.content,
                        'created_at': message.timestamp,
                        'is_active': True
                    })
                
                # Save message
                logger.debug("Saving message to database")
                conn.execute(text("""
                    INSERT INTO genie_messages (
                        message_id, genie_message_id, session_id, conversation_id, user_id, content, role, 
                        status, query_text, created_at
                    ) VALUES (
                        :message_id, :genie_message_id, :session_id, :conversation_id, :user_id, :content, :role,
                        :status, :query_text, :created_at
                    )
                """), {
                    'message_id': message.message_id,
                    'genie_message_id': message.genie_message_id,
                    'session_id': session_id,
                    'conversation_id': conversation_id,
                    'user_id': user_id,
                    'content': message.content,
                    'role': message.role,
                    'status': 'COMPLETED',
                    'query_text': query_text,
                    'created_at': message.timestamp
                })
                
                conn.commit()
                logger.info("Message saved successfully")
        except Exception as e:
            logger.error(f"Error saving message to session: {str(e)}")
            raise

    def update_message_rating(self, message_id: str, user_id: str, rating: str | None) -> bool:
        """Update or remove the rating for a message."""
        try:
            logger.info(f"Updating message rating: message_id={message_id}, user_id={user_id}, rating={rating}")
            with db_manager.managed_connection() as conn:
                if rating is None:
                    # Remove the rating
                    conn.execute(text("""
                        DELETE FROM genie_message_ratings 
                        WHERE message_id = :message_id AND user_id = :user_id
                    """), {'message_id': message_id, 'user_id': user_id})
                else:
                    # Insert or update the rating
                    conn.execute(text("""
                        INSERT INTO genie_message_ratings (message_id, user_id, rating)
                        VALUES (:message_id, :user_id, :rating)
                        ON CONFLICT(message_id, user_id) DO UPDATE SET rating = EXCLUDED.rating
                    """), {'message_id': message_id, 'user_id': user_id, 'rating': rating})
                conn.commit()
                logger.info("Message rating updated successfully")
                return True
        except Exception as e:
            logger.error(f"Error updating message rating: {str(e)}")
            return False

    def get_message_rating(self, message_id: str, user_id: str) -> str | None:
        """Get the rating of a message"""
        try:
            logger.debug(f"Getting message rating: message_id={message_id}, user_id={user_id}")
            with db_manager.managed_connection() as conn:
                result = conn.execute(text("""
                    SELECT rating
                    FROM genie_message_ratings
                    WHERE message_id = :message_id AND user_id = :user_id
                """), {'message_id': message_id, 'user_id': user_id})
                
                row = result.fetchone()
                rating = row[0] if row else None
                logger.debug(f"Retrieved rating: {rating}")
                return rating
        except Exception as e:
            logger.error(f"Error getting message rating: {str(e)}")
            return None