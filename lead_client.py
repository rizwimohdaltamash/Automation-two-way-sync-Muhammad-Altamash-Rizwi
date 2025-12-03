"""Google Sheets client for reading and writing lead data."""
from typing import List, Dict, Optional
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from config import Config
from utils.logger import get_logger, retry_with_backoff

logger = get_logger(__name__)


class LeadClient:
    """Client for interacting with Google Sheets API."""
    
    SCOPES = ['https://www.googleapis.com/auth/spreadsheets']
    
    def __init__(self):
        """Initialize the Google Sheets client."""
        self.creds = None
        self.service = None
        self._authenticate()
    
    def _authenticate(self):
        """Authenticate with Google Sheets API using service account."""
        try:
            self.creds = Credentials.from_service_account_file(
                Config.GOOGLE_CREDS_PATH,
                scopes=self.SCOPES
            )
            self.service = build('sheets', 'v4', credentials=self.creds)
            logger.info("Successfully authenticated with Google Sheets API")
        except Exception as e:
            logger.error(f"Failed to authenticate with Google Sheets: {e}")
            raise
    
    def get_all_leads(self) -> List[Dict[str, any]]:
        """
        Get all leads from the Google Sheet.
        
        Returns:
            List of lead dictionaries with keys: row_number, id, name, email,
            status, source, trello_task_id
        """
        return self.read_leads()
    
    @retry_with_backoff(max_retries=3)
    def read_leads(self) -> List[Dict[str, any]]:
        """
        Read all leads from the Google Sheet.
        
        Returns:
            List of lead dictionaries with keys: row_number, id, name, email,
            status, source, trello_task_id
        """
        try:
            result = self.service.spreadsheets().values().get(
                spreadsheetId=Config.SHEET_ID,
                range=Config.SHEET_RANGE
            ).execute()
            
            values = result.get('values', [])
            
            if not values:
                logger.warning("No data found in sheet")
                return []
            
            # First row is header: id, name, email, status, source, trello_task_id
            headers = values[0]
            leads = []
            
            # Process data rows (skip header)
            for idx, row in enumerate(values[1:], start=2):
                # Pad row if it has fewer columns than headers
                while len(row) < 6:
                    row.append('')
                
                lead = {
                    'row_number': idx,
                    'id': row[0] if len(row) > 0 else '',
                    'name': row[1] if len(row) > 1 else '',
                    'email': row[2] if len(row) > 2 else '',
                    'status': row[3] if len(row) > 3 else '',
                    'source': row[4] if len(row) > 4 else '',
                    'trello_task_id': row[5] if len(row) > 5 else ''
                }
                leads.append(lead)
            
            logger.info(f"Successfully read {len(leads)} leads from sheet")
            return leads
            
        except HttpError as e:
            logger.error(f"HTTP error reading leads: {e}")
            raise
        except Exception as e:
            logger.error(f"Error reading leads: {e}")
            raise
    
    def find_row_by_lead_id(self, lead_id: str) -> Optional[int]:
        """
        Find the row number for a lead by its ID.
        
        Args:
            lead_id: The lead ID to search for
        
        Returns:
            Row number (1-indexed) if found, None otherwise
        """
        try:
            leads = self.read_leads()
            for lead in leads:
                if lead.get('id', '').strip() == lead_id.strip():
                    return lead['row_number']
            
            logger.warning(f"Lead ID {lead_id} not found in sheet")
            return None
            
        except Exception as e:
            logger.error(f"Error finding lead by ID {lead_id}: {e}")
            return None
    
    def update_lead_by_row(self, row_index: int, updates: Dict[str, str]) -> bool:
        """
        Update a lead by row index with partial updates.
        
        Args:
            row_index: The row number to update (1-indexed)
            updates: Dictionary with fields to update (partial update supported)
        
        Returns:
            True if successful, False otherwise
        """
        try:
            # Read current lead data
            leads = self.read_leads()
            current_lead = None
            
            for lead in leads:
                if lead['row_number'] == row_index:
                    current_lead = lead
                    break
            
            if not current_lead:
                logger.error(f"Row {row_index} not found")
                return False
            
            # Merge updates with current data
            current_lead.update(updates)
            
            # Update the row
            return self.update_lead(row_index, current_lead)
            
        except Exception as e:
            logger.error(f"Error updating lead by row {row_index}: {e}")
            return False
    
    @retry_with_backoff(max_retries=3)
    def update_lead(self, row_number: int, lead_data: Dict[str, str]) -> bool:
        """
        Update a specific lead row in the sheet.
        
        Args:
            row_number: The row number to update (1-indexed)
            lead_data: Dictionary with keys: id, name, email, status,
                      source, trello_task_id
        
        Returns:
            True if successful, False otherwise
        """
        try:
            # Prepare the values to update
            values = [[
                lead_data.get('id', ''),
                lead_data.get('name', ''),
                lead_data.get('email', ''),
                lead_data.get('status', ''),
                lead_data.get('source', ''),
                lead_data.get('trello_task_id', '')
            ]]
            
            body = {'values': values}
            
            # Update the row (A to F columns)
            # Extract sheet name from Config.SHEET_RANGE (e.g., "Leeds!A:F" -> "Leeds")
            sheet_name = Config.SHEET_RANGE.split('!')[0]
            range_name = f"{sheet_name}!A{row_number}:F{row_number}"
            
            result = self.service.spreadsheets().values().update(
                spreadsheetId=Config.SHEET_ID,
                range=range_name,
                valueInputOption='RAW',
                body=body
            ).execute()
            
            logger.info(f"Updated row {row_number}: {result.get('updatedCells')} cells updated")
            return True
            
        except HttpError as e:
            logger.error(f"HTTP error updating lead at row {row_number}: {e}")
            raise
        except Exception as e:
            logger.error(f"Error updating lead at row {row_number}: {e}")
            raise
    
    @retry_with_backoff(max_retries=3)
    def append_lead(self, lead_data: Dict[str, str]) -> Optional[int]:
        """
        Append a new lead to the sheet.
        
        Args:
            lead_data: Dictionary with keys: id, name, email, status,
                      source, trello_task_id
        
        Returns:
            Row number of the appended lead, or None if failed
        """
        try:
            values = [[
                lead_data.get('id', ''),
                lead_data.get('name', ''),
                lead_data.get('email', ''),
                lead_data.get('status', ''),
                lead_data.get('source', ''),
                lead_data.get('trello_task_id', '')
            ]]
            
            body = {'values': values}
            
            result = self.service.spreadsheets().values().append(
                spreadsheetId=Config.SHEET_ID,
                range=Config.SHEET_RANGE,
                valueInputOption='RAW',
                insertDataOption='INSERT_ROWS',
                body=body
            ).execute()
            
            # Extract the row number from the updated range
            updated_range = result.get('updates', {}).get('updatedRange', '')
            if updated_range:
                # Format: 'Leads!A10:F10'
                row_number = int(updated_range.split('!A')[1].split(':')[0])
                logger.info(f"Appended new lead at row {row_number}")
                return row_number
            
            return None
            
        except HttpError as e:
            logger.error(f"HTTP error appending lead: {e}")
            raise
        except Exception as e:
            logger.error(f"Error appending lead: {e}")
            raise
