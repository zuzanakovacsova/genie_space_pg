import pandas as pd
import time
import requests
import os
from dotenv import load_dotenv
from typing import Dict, Any, Optional, List, Union, Tuple
import logging
import backoff
import uuid
from token_minter import tokenminter
from chat_database import ChatDatabase
from models import MessageResponse
from datetime import datetime, timezone
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()

# Load environment variables
SPACE_ID = os.environ.get("SPACE_ID")
DATABRICKS_HOST = os.environ.get("DATABRICKS_HOST")

class GenieClient:
    def __init__(self, host: str, space_id: str):
        self.host = host
        self.space_id = space_id
        self.db = ChatDatabase()
        self.base_url = f"https://{host}/api/2.0/genie/spaces/{space_id}"
        self.update_headers()
        logger.info(f"Initialized GenieClient with host: {host}, space_id: {space_id}")
    
    def update_headers(self) -> None:
        """Update headers with fresh token from token_minter"""
        try:
            token = tokenminter.get_token()
            if not token:
                raise ValueError("Failed to get token from token_minter")
            
            self.headers = {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json"
            }
            logger.debug("Successfully updated headers with new token")
        except Exception as e:
            logger.error(f"Error updating headers: {str(e)}")
            raise

    def save_to_database(self, conversation_id: str, genie_message_id: str, content: str, role: str = "assistant", query_text: str = None):
        """Save message to database"""
        try:
            session_id = str(uuid.uuid4())  # Generate a unique session ID
            user_id = "default_user"  
            message_id = str(uuid.uuid4())  # Generate a unique message ID
            
            # Convert timestamp to UTC datetime
            current_time = datetime.now(timezone.utc)
            
            message = MessageResponse(
                message_id=message_id,
                genie_message_id=genie_message_id,
                content=content,
                role=role,
                timestamp=current_time
            )
            
            self.db.save_message_to_session(
                session_id=session_id,
                user_id=user_id,
                message=message,
                conversation_id=conversation_id,
                query_text=query_text
            )
            logger.debug(f"Successfully saved message to database: message_id={message_id}, genie_message_id={genie_message_id}")
        except Exception as e:
            logger.error(f"Error saving to database: {str(e)}")
            raise
    
    @backoff.on_exception(
        backoff.expo,
        Exception,  
        max_tries=5,
        factor=2,
        jitter=backoff.full_jitter,
        on_backoff=lambda details: logger.warning(
            f"API request failed. Retrying in {details['wait']:.2f} seconds (attempt {details['tries']})"
        )
    )
    def start_conversation(self, question: str) -> Dict[str, Any]:
        """Start a new conversation with the given question"""
        self.update_headers()  # Refresh token before API call
        url = f"{self.base_url}/start-conversation"
        payload = {"content": question}
        
        logger.info(f"Starting conversation with question: {question[:50]}...")
        
        try:
            response = requests.post(url, headers=self.headers, json=payload)
            response.raise_for_status()
            result = response.json()
            
            # Save user's question to database
            self.save_to_database(
                conversation_id=result.get("conversation_id"),
                genie_message_id=result.get("message_id"),
                content=question,
                role="user"
            )
            
            return result
        except Exception as e:
            logger.error(f"Error in start_conversation: {str(e)}")
            raise

    @backoff.on_exception(
        backoff.expo,
        Exception,
        max_tries=5,
        factor=2,
        jitter=backoff.full_jitter,
        on_backoff=lambda details: logger.warning(
            f"API request failed. Retrying in {details['wait']:.2f} seconds (attempt {details['tries']})"
        )
    )
    def send_message(self, conversation_id: str, message: str) -> Dict[str, Any]:
        """Send a follow-up message to an existing conversation"""
        self.update_headers()
        url = f"{self.base_url}/conversations/{conversation_id}/messages"
        payload = {"content": message}
        
        try:
            response = requests.post(url, headers=self.headers, json=payload)
            response.raise_for_status()
            result = response.json()
            
            # Save user's message to database
            self.save_to_database(
                conversation_id=conversation_id,
                genie_message_id=result.get("message_id"),
                content=message,
                role="user"
            )
            
            return result
        except Exception as e:
            logger.error(f"Error in send_message: {str(e)}")
            raise

    @backoff.on_exception(
        backoff.expo,
        Exception,  # Retry on any exception
        max_tries=5,
        factor=2,
        jitter=backoff.full_jitter,
        on_backoff=lambda details: logger.warning(
            f"API request failed. Retrying in {details['wait']:.2f} seconds (attempt {details['tries']})"
        )
    )
    def get_message(self, conversation_id: str, message_id: str) -> Dict[str, Any]:
        """Get the details of a specific message"""
        self.update_headers()  # Refresh token before API call
        url = f"{self.base_url}/conversations/{conversation_id}/messages/{message_id}"
        
        response = requests.get(url, headers=self.headers)
        response.raise_for_status()
        return response.json()

    @backoff.on_exception(
        backoff.expo,
        Exception,  # Retry on any exception
        max_tries=5,
        factor=2,
        jitter=backoff.full_jitter,
        on_backoff=lambda details: logger.warning(
            f"API request failed. Retrying in {details['wait']:.2f} seconds (attempt {details['tries']})"
        )
    )
    def get_query_result(self, conversation_id: str, message_id: str, attachment_id: str) -> Dict[str, Any]:
        """Get the query result using the attachment_id endpoint"""
        self.update_headers()  # Refresh token before API call
        url = f"{self.base_url}/conversations/{conversation_id}/messages/{message_id}/attachments/{attachment_id}/query-result"
        
        response = requests.get(url, headers=self.headers)
        response.raise_for_status()
        result = response.json()
        
        # Extract data_array from the correct nested location
        data_array = []
        if 'statement_response' in result:
            if 'result' in result['statement_response']:
                data_array = result['statement_response']['result'].get('data_array', [])
            
        return {
                    'data_array': data_array,
                    'schema': result.get('statement_response', {}).get('manifest', {}).get('schema', {})
                }

    @backoff.on_exception(
        backoff.expo,
        Exception,  # Retry on any exception
        max_tries=5,
        factor=2,
        jitter=backoff.full_jitter,
        on_backoff=lambda details: logger.warning(
            f"API request failed. Retrying in {details['wait']:.2f} seconds (attempt {details['tries']})"
        )
    )
    def execute_query(self, conversation_id: str, message_id: str, attachment_id: str) -> Dict[str, Any]:
        """Execute a query using the attachment_id endpoint"""
        self.update_headers()  # Refresh token before API call
        url = f"{self.base_url}/conversations/{conversation_id}/messages/{message_id}/attachments/{attachment_id}/execute-query"
        
        response = requests.post(url, headers=self.headers)
        response.raise_for_status()
        return response.json()
    

    def wait_for_message_completion(self, conversation_id: str, message_id: str, timeout: int = 300, poll_interval: int = 2) -> Dict[str, Any]:
        """
        Wait for a message to reach a terminal state (COMPLETED, ERROR, etc.).
        
        Args:
            conversation_id: The ID of the conversation
            message_id: The ID of the message
            timeout: Maximum time to wait in seconds
            poll_interval: Time between status checks in seconds
            
        Returns:
            The completed message
        """
        
        start_time = time.time()
        attempt = 1
        
        while time.time() - start_time < timeout:
            
            message = self.get_message(conversation_id, message_id)
            status = message.get("status")
            
            if status in ["COMPLETED", "ERROR", "FAILED"]:
                return message
                
            time.sleep(poll_interval)
            attempt += 1
            
        raise TimeoutError(f"Message processing timed out after {timeout} seconds")

def process_genie_response(client, conversation_id, message_id, complete_message) -> Tuple[Union[str, pd.DataFrame], Optional[str], str]:
    """Process the response from Genie"""
    # Check attachments first
    attachments = complete_message.get("attachments", [])
    for attachment in attachments:
        attachment_id = attachment.get("attachment_id")
        
        # If there's text content in the attachment, return it
        if "text" in attachment and "content" in attachment["text"]:
            content = attachment["text"]["content"]
            # Save assistant's response to database
            client.save_to_database(
                conversation_id=conversation_id,
                genie_message_id=message_id,
                content=content,
                role="assistant"
            )
            return content, None, message_id
        
        # If there's a query, get the result
        elif "query" in attachment:
            query_text = attachment.get("query", {}).get("query", "")
            query_result = client.get_query_result(conversation_id, message_id, attachment_id)
           
            data_array = query_result.get('data_array', [])
            schema = query_result.get('schema', {})
            columns = [col.get('name') for col in schema.get('columns', [])]
            
            # If we have data, return as DataFrame
            if data_array:
                # If no columns from schema, create generic ones
                if not columns and data_array and len(data_array) > 0:
                    columns = [f"column_{i}" for i in range(len(data_array[0]))]
                
                df = pd.DataFrame(data_array, columns=columns)
                # Save query result to database
                client.save_to_database(
                    conversation_id=conversation_id,
                    genie_message_id=message_id,
                    content=str(df.to_dict()),
                    role="assistant",
                    query_text=query_text
                )
                return df, query_text, message_id
    
    # If no attachments or no data in attachments, return text content
    if 'content' in complete_message:
        content = complete_message.get('content', '')
        # Save assistant's response to database
        client.save_to_database(
            conversation_id=conversation_id,
            genie_message_id=message_id,
            content=content,
            role="assistant"
        )
        return content, None, message_id
    
    return "No response available", None, message_id

def start_new_conversation(question: str) -> Tuple[str, Union[str, pd.DataFrame], Optional[str], str]:
    """Start a new conversation with Genie"""
    client = GenieClient(
        host=DATABRICKS_HOST,
        space_id=SPACE_ID
    )
    
    try:
        # Start a new conversation
        response = client.start_conversation(question)
        conversation_id = response.get("conversation_id")
        message_id = response.get("message_id")
        
        # Wait for the message to complete
        complete_message = client.wait_for_message_completion(conversation_id, message_id)
        
        # Process the response
        result, query_text, message_id = process_genie_response(client, conversation_id, message_id, complete_message)
        
        return conversation_id, result, query_text, message_id
        
    except Exception as e:
        logger.error(f"Error in start_new_conversation: {str(e)}")
        return None, f"Sorry, an error occurred: {str(e)}. Please try again.", None, None

def continue_conversation(conversation_id: str, question: str) -> Tuple[Union[str, pd.DataFrame], Optional[str]]:
    """Send a follow-up message in an existing conversation"""
    logger.info(f"Continuing conversation {conversation_id} with question: {question[:30]}...")
    
    client = GenieClient(
        host=DATABRICKS_HOST,
        space_id=SPACE_ID
    )
    
    try:
        # Send follow-up message in existing conversation
        response = client.send_message(conversation_id, question)
        message_id = response.get("message_id")
        
        # Wait for the message to complete
        complete_message = client.wait_for_message_completion(conversation_id, message_id)
        
        # Process the response
        result, query_text, message_id = process_genie_response(client, conversation_id, message_id, complete_message)
        
        return result, query_text
        
    except Exception as e:
        logger.error(f"Error in continue_conversation: {str(e)}")
        if "429" in str(e) or "Too Many Requests" in str(e):
            return "Sorry, the system is currently experiencing high demand. Please try again in a few moments.", None
        elif "Conversation not found" in str(e):
            return "Sorry, the previous conversation has expired. Please try your query again to start a new conversation.", None
        else:
            return f"Sorry, an error occurred: {str(e)}", None

def genie_query(question: str) -> Union[Tuple[str, Optional[str], str], Tuple[pd.DataFrame, str, str]]:
    """
    Main entry point for querying Genie.
    
    Args:
        question: The question to ask
        
    Returns:
        Tuple containing either:
        - (text_response, None, message_id) for text responses
        - (dataframe, sql_query, message_id) for data responses
    """
    try:
        # Start a new conversation for each query
        conversation_id, result, query_text, message_id = start_new_conversation(question)
        return result, query_text, message_id
            
    except Exception as e:
        logger.error(f"Error in conversation: {str(e)}. Please try again.")
        return f"Sorry, an error occurred: {str(e)}. Please try again.", None, None
