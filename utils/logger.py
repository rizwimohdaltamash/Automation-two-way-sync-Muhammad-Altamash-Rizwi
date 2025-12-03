"""Logging and utility functions with retry/backoff logic."""
import logging
import logging.handlers
import time
import functools
import os
from typing import Callable, Any
from datetime import datetime
from config import Config


def get_logger(name: str) -> logging.Logger:
    """
    Get a configured logger instance with console and optional file output.
    
    Log format includes: timestamp, logger name, level, and message
    Optional rotating file handler controlled by environment.
    
    Args:
        name: Logger name (usually __name__)
    
    Returns:
        Configured logger instance
    """
    logger = logging.getLogger(name)
    
    # Only configure if not already configured
    if not logger.handlers:
        log_level = getattr(logging, Config.LOG_LEVEL, logging.INFO)
        logger.setLevel(log_level)
        
        # Enhanced formatter with timestamp, action, object type, IDs
        formatter = logging.Formatter(
            '%(asctime)s | %(name)-20s | %(levelname)-8s | %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        
        # Console handler
        console_handler = logging.StreamHandler()
        console_handler.setLevel(log_level)
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)
        
        # Optional: Rotating file handler
        # Uncomment to enable file logging:
        enable_file_logging = os.getenv('ENABLE_FILE_LOGGING', 'false').lower() == 'true'
        
        if enable_file_logging:
            log_dir = os.getenv('LOG_DIR', './logs')
            os.makedirs(log_dir, exist_ok=True)
            
            log_file = os.path.join(log_dir, 'sync.log')
            
            # Rotating file handler: max 10MB, keep 5 backups
            file_handler = logging.handlers.RotatingFileHandler(
                log_file,
                maxBytes=10 * 1024 * 1024,  # 10MB
                backupCount=5
            )
            file_handler.setLevel(log_level)
            file_handler.setFormatter(formatter)
            logger.addHandler(file_handler)
            
            logger.info(f"File logging enabled: {log_file}")
    
    return logger


def retry_with_backoff(max_retries: int = 3, base_delay: float = 1.0, 
                       backoff_factor: float = 2.0) -> Callable:
    """
    Decorator to retry a function with exponential backoff.
    
    Handles transient errors intelligently:
    - For HTTP 429 (rate limit) or 5xx (server error): retry with backoff
    - For HTTP 401/403 (auth error) or 400 (bad request): log and skip (don't retry)
    - For other exceptions: retry with backoff
    
    Backoff schedule: 1s, 2s, 4s (default with 3 retries)
    
    Args:
        max_retries: Maximum number of retry attempts
        base_delay: Initial delay in seconds (default: 1.0)
        backoff_factor: Multiplier for exponential backoff (default: 2.0)
    
    Returns:
        Decorated function
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            logger = get_logger(func.__module__)
            
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                    
                except Exception as e:
                    # Check if it's an HTTP error with status code
                    status_code = None
                    if hasattr(e, 'response') and hasattr(e.response, 'status_code'):
                        status_code = e.response.status_code
                    
                    # Don't retry on auth errors or bad requests
                    if status_code in [401, 403, 400]:
                        logger.error(
                            f"Non-retryable error (HTTP {status_code}) in {func.__name__}: {e}"
                        )
                        logger.error(f"  → Skipping retries for auth/bad request errors")
                        raise
                    
                    # Last attempt - raise the error
                    if attempt == max_retries:
                        logger.error(
                            f"❌ {func.__name__} failed after {max_retries} retries: {e}"
                        )
                        if status_code:
                            logger.error(f"  → Final HTTP status: {status_code}")
                        raise
                    
                    # Calculate delay with exponential backoff
                    delay = base_delay * (backoff_factor ** attempt)
                    
                    # Log warning with retry info
                    retry_msg = (
                        f"⚠️  {func.__name__} failed (attempt {attempt + 1}/{max_retries + 1})"
                    )
                    if status_code:
                        retry_msg += f" | HTTP {status_code}"
                        if status_code == 429:
                            retry_msg += " (Rate Limited)"
                        elif status_code >= 500:
                            retry_msg += " (Server Error)"
                    
                    logger.warning(retry_msg)
                    logger.warning(f"  → Error: {e}")
                    logger.warning(f"  → Retrying in {delay:.1f}s...")
                    
                    time.sleep(delay)
        
        return wrapper
    return decorator


def safe_get(dictionary: dict, key: str, default: Any = None) -> Any:
    """
    Safely get a value from a dictionary.
    
    Args:
        dictionary: The dictionary to get value from
        key: The key to look up
        default: Default value if key not found
    
    Returns:
        Value from dictionary or default
    """
    return dictionary.get(key, default) if dictionary else default


def normalize_status(status: str) -> str:
    """
    Normalize status string to match expected values.
    
    Status values: NEW, CONTACTED, QUALIFIED, LOST
    Maps to Trello lists: TODO, IN_PROGRESS, DONE, LOST
    
    Args:
        status: Raw status string
    
    Returns:
        Normalized status (new, contacted, qualified, lost)
    """
    if not status:
        return 'new'
    
    status_lower = status.lower().strip().replace(' ', '_').replace('-', '_')
    
    # Map common variations to the four main statuses
    status_map = {
        'new': 'new',
        'todo': 'new',
        'pending': 'new',
        'contacted': 'contacted',
        'in_progress': 'contacted',
        'inprogress': 'contacted',
        'working': 'contacted',
        'active': 'contacted',
        'reach_out': 'contacted',
        'qualified': 'qualified',
        'done': 'qualified',
        'complete': 'qualified',
        'completed': 'qualified',
        'finished': 'qualified',
        'won': 'qualified',
        'success': 'qualified',
        'lost': 'lost',
        'rejected': 'lost',
        'cancelled': 'lost',
        'closed_lost': 'lost',
        'dead': 'lost'
    }
    
    return status_map.get(status_lower, 'new')


def get_current_timestamp() -> str:
    """
    Get current timestamp as ISO format string.
    
    Returns:
        ISO format timestamp string
    """
    from datetime import datetime
    return datetime.utcnow().isoformat() + 'Z'
