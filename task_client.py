"""Trello client for creating, reading, and updating cards (tasks)."""
from typing import List, Dict, Optional
import requests
from datetime import datetime
from config import Config
from utils.logger import get_logger, retry_with_backoff, normalize_status

logger = get_logger(__name__)


class TaskClient:
    """Client for interacting with Trello REST API."""
    
    BASE_URL = "https://api.trello.com/1"
    
    def __init__(self):
        """Initialize the Trello client."""
        self.key = Config.TRELLO_KEY
        self.token = Config.TRELLO_TOKEN
        self.board_id = Config.TRELLO_BOARD_ID
        # Map status values to Trello list IDs
        # Status: NEW -> TODO, CONTACTED -> IN_PROGRESS, QUALIFIED -> DONE, LOST -> LOST
        self.list_ids = {
            'new': Config.TRELLO_LIST_TODO_ID,
            'contacted': Config.TRELLO_LIST_IN_PROGRESS_ID,
            'qualified': Config.TRELLO_LIST_DONE_ID,
            'lost': Config.TRELLO_LIST_LOST_ID
        }
        self._validate_connection()
    
    def _get_auth_params(self) -> Dict[str, str]:
        """Get authentication parameters for API requests."""
        return {
            'key': self.key,
            'token': self.token
        }
    
    def _request_wrapper(self, method: str, url: str, **kwargs) -> requests.Response:
        """
        Wrapper for requests that logs response status and body on error.
        
        Args:
            method: HTTP method (GET, POST, PUT, DELETE)
            url: Full URL to request
            **kwargs: Additional arguments for requests
        
        Returns:
            Response object
        """
        try:
            # Ensure auth params are included
            params = kwargs.get('params', {})
            params.update(self._get_auth_params())
            kwargs['params'] = params
            
            # Make request
            response = requests.request(method, url, **kwargs)
            
            # Log on error
            if response.status_code >= 400:
                logger.error(
                    f"Trello API error: {method} {url} - "
                    f"Status {response.status_code} - {response.text}"
                )
            
            response.raise_for_status()
            return response
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Request failed: {method} {url} - {e}")
            raise
    
    def _validate_connection(self):
        """Validate that the Trello connection works."""
        try:
            response = requests.get(
                f"{self.BASE_URL}/boards/{self.board_id}",
                params=self._get_auth_params(),
                timeout=10
            )
            response.raise_for_status()
            logger.info("Successfully connected to Trello API")
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to connect to Trello API: {e}")
            raise
    
    @retry_with_backoff(max_retries=3)
    def create_card(self, name: str, description: str, status: str = 'todo') -> Optional[Dict]:
        """
        Create a new Trello card using REST API.
        
        API Endpoint: POST https://api.trello.com/1/cards
        
        Args:
            name: Card name (lead name)
            description: Card description (email, source, etc.)
            status: Initial status (new, contacted, qualified, lost)
        
        Returns:
            Card data dict with 'id', 'name', 'desc', 'idList', 'dateLastActivity'
        """
        try:
            list_id = self.list_ids.get(status.lower(), self.list_ids['new'])
            
            params = {
                'name': name,
                'desc': description,
                'idList': list_id
            }
            
            # REST API: POST https://api.trello.com/1/cards
            response = self._request_wrapper(
                'POST',
                f"{self.BASE_URL}/cards",
                params=params,
                timeout=10
            )
            
            card = response.json()
            logger.info(f"Created Trello card: {card['id']} - {name}")
            return card
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Error creating Trello card '{name}': {e}")
            raise
    
    @retry_with_backoff(max_retries=3)
    def get_card(self, card_id: str) -> Optional[Dict]:
        """
        Get a Trello card by ID using REST API.
        
        API Endpoint: GET https://api.trello.com/1/cards/{id}
        
        Args:
            card_id: The Trello card ID
        
        Returns:
            Card data dict or None if not found
        """
        try:
            # REST API: GET https://api.trello.com/1/cards/{id}
            response = self._request_wrapper(
                'GET',
                f"{self.BASE_URL}/cards/{card_id}",
                timeout=10
            )
            
            card = response.json()
            logger.debug(f"Retrieved Trello card: {card_id}")
            return card
            
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 404:
                logger.warning(f"Trello card not found: {card_id}")
                return None
            logger.error(f"Error getting Trello card {card_id}: {e}")
            raise
        except requests.exceptions.RequestException as e:
            logger.error(f"Error getting Trello card {card_id}: {e}")
            raise
    
    @retry_with_backoff(max_retries=3)
    def update_card(self, card_id: str, name: Optional[str] = None, 
                    description: Optional[str] = None, status: Optional[str] = None) -> bool:
        """
        Update an existing Trello card using REST API.
        
        API Endpoint: PUT https://api.trello.com/1/cards/{id}
        
        Args:
            card_id: The Trello card ID
            name: New card name (optional)
            description: New card description (optional)
            status: New status to move card to (optional)
        
        Returns:
            True if successful, False otherwise
        """
        try:
            params = {}
            
            # Add fields to update
            if name is not None:
                params['name'] = name
            if description is not None:
                params['desc'] = description
            if status is not None:
                list_id = self.list_ids.get(status.lower())
                if list_id:
                    params['idList'] = list_id
            
            # REST API: PUT https://api.trello.com/1/cards/{id}
            response = self._request_wrapper(
                'PUT',
                f"{self.BASE_URL}/cards/{card_id}",
                params=params,
                timeout=10
            )
            
            logger.info(f"Updated Trello card: {card_id}")
            return True
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Error updating Trello card {card_id}: {e}")
            raise
    
    @retry_with_backoff(max_retries=3)
    def get_all_cards(self) -> List[Dict]:
        """
        Get all cards from the Trello board using REST API.
        
        API Endpoint: GET https://api.trello.com/1/boards/{boardId}/cards
        
        Returns:
            List of card dictionaries
        """
        try:
            # REST API: GET https://api.trello.com/1/boards/{boardId}/cards
            response = self._request_wrapper(
                'GET',
                f"{self.BASE_URL}/boards/{self.board_id}/cards",
                timeout=10
            )
            
            cards = response.json()
            logger.info(f"Retrieved {len(cards)} cards from Trello board")
            return cards
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Error getting all Trello cards: {e}")
            raise
    
    def get_status_from_list_id(self, list_id: str) -> str:
        """
        Convert Trello list ID to status string.
        
        Args:
            list_id: The Trello list ID
        
        Returns:
            Status string (new, contacted, qualified, lost)
        """
        for status, lid in self.list_ids.items():
            if lid == list_id:
                return status
        return 'new'  # Default fallback
    
    def format_card_description(self, email: str, source: str = '', lead_id: str = '') -> str:
        """
        Format a card description from lead data.
        Includes lead_id marker for searching: lead_id: L123
        
        Args:
            email: Lead email
            source: Lead source
            lead_id: Stable lead ID
        
        Returns:
            Formatted description string with lead_id marker
        """
        desc_parts = []
        if lead_id:
            desc_parts.append(f"lead_id: {lead_id}")  # Machine-readable marker
            desc_parts.append(f"🆔 Lead ID: {lead_id}")
        if email:
            desc_parts.append(f"📧 Email: {email}")
        if source:
            desc_parts.append(f"📍 Source: {source}")
        
        return "\n".join(desc_parts) if desc_parts else "No information available"
    
    def create_task_for_lead(self, lead: Dict[str, str]) -> Optional[str]:
        """
        Create a Trello task (card) for a lead.
        
        Args:
            lead: Lead dictionary with keys: id, name, email, status, source
        
        Returns:
            Card ID if successful, None otherwise
        """
        name = lead.get('name', 'Unnamed Lead')
        email = lead.get('email', '')
        source = lead.get('source', '')
        lead_id = lead.get('id', '')
        status = normalize_status(lead.get('status', ''))
        
        description = self.format_card_description(email, source, lead_id)
        
        card = self.create_card(name, description, status)
        return card['id'] if card else None
    
    def update_task(self, card_id: str, fields: Dict[str, any]) -> bool:
        """
        Update a Trello task with the given fields.
        Supports: name, description, status (which moves card to list), labels
        
        Args:
            card_id: The Trello card ID
            fields: Dictionary with fields to update
                   - name: New card name
                   - description: New card description
                   - status: New status (moves to list)
        
        Returns:
            True if successful, False otherwise
        """
        return self.update_card(
            card_id,
            name=fields.get('name'),
            description=fields.get('description'),
            status=fields.get('status')
        )
    
    def get_cards_on_board(self) -> List[Dict]:
        """
        Get all cards on the Trello board.
        Alias for get_all_cards() for consistency.
        
        Returns:
            List of card dictionaries
        """
        return self.get_all_cards()
    
    def search_card_by_lead_id(self, lead_id: str) -> Optional[Dict]:
        """
        Search for a card by lead ID in the description.
        Looks for 'lead_id: L123' marker in card description.
        
        Args:
            lead_id: The lead ID to search for
        
        Returns:
            Card dictionary if found, None otherwise
        """
        try:
            cards = self.get_all_cards()
            
            # Look for lead_id marker in description
            search_marker = f"lead_id: {lead_id}"
            
            for card in cards:
                desc = card.get('desc', '')
                if search_marker in desc:
                    logger.debug(f"Found card {card['id']} for lead_id {lead_id}")
                    return card
            
            logger.debug(f"No card found for lead_id {lead_id}")
            return None
            
        except Exception as e:
            logger.error(f"Error searching for card by lead_id {lead_id}: {e}")
            return None
    
    def delete_card(self, card_id: str) -> bool:
        """
        Delete a Trello card.
        
        Args:
            card_id: The Trello card ID to delete
        
        Returns:
            True if successful, False otherwise
        """
        try:
            url = f"{self.BASE_URL}/cards/{card_id}"
            params = self._get_auth_params()
            
            response = self._request_wrapper('DELETE', url, params=params)
            
            if response.status_code == 200:
                logger.info(f"✓ Deleted card {card_id}")
                return True
            else:
                logger.error(f"Failed to delete card {card_id}: {response.status_code} {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"Error deleting card {card_id}: {e}")
            return False
