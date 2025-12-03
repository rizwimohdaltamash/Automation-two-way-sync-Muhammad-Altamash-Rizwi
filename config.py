"""Configuration loader for the two-way sync automation."""
import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


class Config:
    """Configuration class to hold all environment variables."""
    
    # Google Sheets Configuration
    GOOGLE_CREDS_PATH = os.getenv('GOOGLE_CREDS_PATH', './service-account.json')
    SHEET_ID = os.getenv('SHEET_ID')
    SHEET_RANGE = os.getenv('SHEET_RANGE', 'Leads!A:F')  # id, name, email, status, source, trello_task_id
    
    # Trello Configuration
    TRELLO_KEY = os.getenv('TRELLO_KEY')
    TRELLO_TOKEN = os.getenv('TRELLO_TOKEN')
    TRELLO_BOARD_ID = os.getenv('TRELLO_BOARD_ID')
    TRELLO_LIST_TODO_ID = os.getenv('TRELLO_LIST_TODO_ID')
    TRELLO_LIST_IN_PROGRESS_ID = os.getenv('TRELLO_LIST_IN_PROGRESS_ID')
    TRELLO_LIST_DONE_ID = os.getenv('TRELLO_LIST_DONE_ID')
    TRELLO_LIST_LOST_ID = os.getenv('TRELLO_LIST_LOST_ID')
    
    # Logging Configuration
    LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
    
    @classmethod
    def validate(cls):
        """Validate that all required configuration is present."""
        required_vars = [
            ('SHEET_ID', cls.SHEET_ID),
            ('TRELLO_KEY', cls.TRELLO_KEY),
            ('TRELLO_TOKEN', cls.TRELLO_TOKEN),
            ('TRELLO_BOARD_ID', cls.TRELLO_BOARD_ID),
            ('TRELLO_LIST_TODO_ID', cls.TRELLO_LIST_TODO_ID),
            ('TRELLO_LIST_IN_PROGRESS_ID', cls.TRELLO_LIST_IN_PROGRESS_ID),
            ('TRELLO_LIST_DONE_ID', cls.TRELLO_LIST_DONE_ID),
            ('TRELLO_LIST_LOST_ID', cls.TRELLO_LIST_LOST_ID),
        ]
        
        missing_vars = [name for name, value in required_vars if not value]
        
        if missing_vars:
            raise ValueError(
                f"Missing required environment variables: {', '.join(missing_vars)}"
            )
        
        # Check if Google credentials file exists
        if not os.path.exists(cls.GOOGLE_CREDS_PATH):
            raise FileNotFoundError(
                f"Google credentials file not found at: {cls.GOOGLE_CREDS_PATH}"
            )
        
        return True
