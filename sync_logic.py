"""Core two-way synchronization logic between Google Sheets and Trello."""
from typing import List, Dict, Optional, Tuple
from datetime import datetime
from lead_client import LeadClient
from task_client import TaskClient
from utils.logger import get_logger, normalize_status, get_current_timestamp

logger = get_logger(__name__)


class SyncEngine:
    """Engine to perform two-way synchronization between Google Sheets and Trello."""
    
    def __init__(self):
        """Initialize the sync engine with both clients."""
        self.lead_client = LeadClient()
        self.task_client = TaskClient()
        self.sync_stats = {
            'leads_created': 0,
            'leads_updated': 0,
            'tasks_created': 0,
            'tasks_updated': 0,
            'status_synced_to_sheets': 0,
            'errors': 0,
            'skipped': 0
        }
    
    def run_sync(self) -> Dict[str, int]:
        """
        Run the complete two-way sync process.
        
        Flow A: Lead → Task (initial sync + updates)
        Flow B: Task → Lead (reverse sync)
        
        Returns:
            Dictionary with sync statistics
        """
        logger.info("=" * 70)
        logger.info("STARTING TWO-WAY SYNC: Google Sheets ↔ Trello")
        logger.info("=" * 70)
        
        # Reset stats
        self.sync_stats = {
            'leads_created': 0,
            'leads_updated': 0,
            'tasks_created': 0,
            'tasks_updated': 0,
            'status_synced_to_sheets': 0,
            'errors': 0,
            'skipped': 0
        }
        
        try:
            # FLOW B: Task → Lead (Trello to Sheets) - RUN FIRST!
            # This ensures Trello status changes update the Sheet BEFORE Flow A runs
            logger.info("\n[FLOW B] Task → Lead: Syncing Trello → Google Sheets")
            logger.info("-" * 70)
            self._sync_tasks_to_leads()
            
            # FLOW A: Lead → Task (Sheets to Trello) - RUN SECOND!
            # Now Flow A syncs the updated Sheet data (including status changes from Flow B)
            logger.info("\n[FLOW A] Lead → Task: Syncing Google Sheets → Trello")
            logger.info("-" * 70)
            self._sync_leads_to_tasks()
            
            # Summary
            logger.info("\n" + "=" * 70)
            logger.info("SYNC COMPLETED")
            logger.info("=" * 70)
            self._log_sync_summary()
            
        except Exception as e:
            logger.error(f"Critical sync error: {e}", exc_info=True)
            self.sync_stats['errors'] += 1
        
        return self.sync_stats
    
    def sync(self) -> Dict[str, int]:
        """
        Perform a full two-way sync (legacy method name).
        Calls run_sync() for compatibility.
        
        Returns:
            Dictionary with sync statistics
        """
        return self.run_sync()
    
    def _sync_leads_to_tasks(self):
        """
        FLOW A: Lead → Task (initial sync + updates)
        
        Process:
        1. Fetch all leads from Google Sheets
        2. For each lead:
           - If status == LOST: optionally skip or update to LOST list
           - If trello_task_id is empty: CREATE card, write ID back
           - If trello_task_id exists: UPDATE card if fields changed
        3. Idempotent: safe to re-run multiple times
        """
        try:
            # Fetch all leads
            logger.info("Fetching all leads from Google Sheets...")
            leads = self.lead_client.get_all_leads()
            logger.info(f"✓ Found {len(leads)} leads to process")
            
            if not leads:
                logger.warning("No leads found in sheet")
                return
            
            # Process each lead with error handling
            for idx, lead in enumerate(leads, 1):
                try:
                    logger.debug(f"\n[{idx}/{len(leads)}] Processing lead row {lead.get('row_number')}")
                    self._process_lead_to_task(lead)
                    
                except Exception as e:
                    # Per-record error handling - don't crash entire sync
                    lead_id = lead.get('id', 'unknown')
                    lead_name = lead.get('name', 'unknown')
                    row_num = lead.get('row_number', 'unknown')
                    
                    logger.error(
                        f"❌ Error processing lead (ID: {lead_id}, Name: {lead_name}, Row: {row_num}): {e}",
                        exc_info=True
                    )
                    self.sync_stats['errors'] += 1
                    # Continue to next lead
            
            # Log Flow A summary
            logger.info(f"\n✓ Flow A complete: {self.sync_stats['tasks_created']} tasks created, "
                       f"{self.sync_stats['tasks_updated']} tasks updated, "
                       f"{self.sync_stats['skipped']} skipped")
            
        except Exception as e:
            logger.error(f"Critical error in Lead → Task sync: {e}", exc_info=True)
            raise
    
    def _process_lead_to_task(self, lead: Dict[str, str]):
        """
        Process a single lead and sync to Trello.
        Uses trello_task_id as idempotency anchor:
        - If trello_task_id is empty: CREATE new card and write card ID back
        - If trello_task_id exists: UPDATE that card instead of creating new one
        
        Args:
            lead: Lead dictionary from Google Sheets
        """
        lead_id = lead.get('id', '').strip()
        name = lead.get('name', '').strip()
        email = lead.get('email', '').strip()
        source = lead.get('source', '').strip()
        status = normalize_status(lead.get('status', ''))
        trello_task_id = lead.get('trello_task_id', '').strip()
        row_number = lead['row_number']
        
        # Skip empty leads
        if not name:
            logger.debug(f"⊘ Skipping empty lead at row {row_number}")
            self.sync_stats['skipped'] += 1
            return
        
        # Optional: Skip LOST leads (or still sync them to LOST list)
        # Uncomment to skip LOST leads entirely:
        # if status == 'lost':
        #     logger.debug(f"⊘ Skipping LOST lead: {name} (ID: {lead_id})")
        #     self.sync_stats['skipped'] += 1
        #     return
        
        # IDEMPOTENCY: Check trello_task_id column
        # Case 1: No trello_task_id - CREATE new card and write ID back to sheet
        if not trello_task_id:
            logger.info(f"[CREATE] New Trello card for lead: {name} (ID: {lead_id}, row {row_number})")
            
            # Use create_task_for_lead method
            card_id = self.task_client.create_task_for_lead(lead)
            
            if card_id:
                # IDEMPOTENCY: Write card ID to trello_task_id column
                logger.info(f"  → Writing trello_task_id={card_id} to row {row_number}")
                self.lead_client.update_lead_by_row(row_number, {'trello_task_id': card_id})
                
                self.sync_stats['tasks_created'] += 1
                logger.info(f"✓ Task created: card_id={card_id}, lead_id={lead_id}, name={name}")
            else:
                logger.error(f"❌ Failed to create task for lead {name} (ID: {lead_id})")
                self.sync_stats['errors'] += 1
        
        # Case 2: Has trello_task_id - UPDATE that card (idempotency in action)
        else:
            logger.info(f"[UPDATE] Found trello_task_id={trello_task_id} for lead {name} (ID: {lead_id})")
            card = self.task_client.get_card(trello_task_id)
            
            if card:
                # Check if updates are needed
                needs_update = False
                update_fields = {}
                
                # Check name
                if card['name'] != name:
                    update_fields['name'] = name
                    needs_update = True
                    logger.debug(f"  Name change: '{card['name']}' → '{name}'")
                
                # Check description
                expected_desc = self.task_client.format_card_description(email, source, lead_id)
                if card['desc'] != expected_desc:
                    update_fields['description'] = expected_desc
                    needs_update = True
                    logger.debug(f"  Description updated")
                
                # Check status (list) - this moves the card
                card_status = self.task_client.get_status_from_list_id(card['idList'])
                if card_status != status:
                    update_fields['status'] = status
                    needs_update = True
                    logger.debug(f"  Status change: {card_status} → {status}")
                
                if needs_update:
                    logger.info(f"  Updating Trello card {trello_task_id} with changes")
                    self.task_client.update_task(trello_task_id, update_fields)
                    self.sync_stats['tasks_updated'] += 1
                    logger.info(f"✓ Task updated: card_id={trello_task_id}, lead_id={lead_id}, fields={list(update_fields.keys())}")
                else:
                    logger.debug(f"  ✓ No updates needed for {name} (card {trello_task_id})")
            else:
                # Card was deleted in Trello - create a new one and update trello_task_id
                logger.warning(
                    f"⚠️  Trello card {trello_task_id} not found for {name}. Creating new card."
                )
                
                card_id = self.task_client.create_task_for_lead(lead)
                
                if card_id:
                    # Update trello_task_id with new card ID
                    self.lead_client.update_lead_by_row(row_number, {'trello_task_id': card_id})
                    self.sync_stats['tasks_created'] += 1
                    logger.info(f"✓ Replacement task created: card_id={card_id}, lead_id={lead_id}")
    
    def _sync_tasks_to_leads(self):
        """
        FLOW B: Task → Lead (reverse sync)
        
        Process:
        1. Fetch all cards from Trello board
        2. For each card:
           - Extract lead_id from description OR match by trello_task_id
           - Map card list to desired lead status
           - If sheet status differs, update the sheet row
        3. Per-record error handling
        """
        try:
            # Fetch all cards from Trello
            logger.info("Fetching all cards from Trello board...")
            cards = self.task_client.get_cards_on_board()
            logger.info(f"✓ Found {len(cards)} cards to process")
            
            if not cards:
                logger.warning("No cards found on Trello board")
                return
            
            # Fetch all leads and build lookup map
            logger.info("Building lead lookup map...")
            leads = self.lead_client.get_all_leads()
            
            # Create map: trello_task_id → lead (for quick lookup)
            lead_map = {}
            for lead in leads:
                task_id = lead.get('trello_task_id', '').strip()
                if task_id:
                    lead_map[task_id] = lead
            
            logger.info(f"✓ Mapped {len(lead_map)} leads with trello_task_id")
            
            # Process each card with error handling
            for idx, card in enumerate(cards, 1):
                try:
                    logger.debug(f"\n[{idx}/{len(cards)}] Processing card {card['id']}")
                    self._process_task_to_lead(card, lead_map)
                    
                except Exception as e:
                    # Per-record error handling - don't crash entire sync
                    card_id = card.get('id', 'unknown')
                    card_name = card.get('name', 'unknown')
                    
                    logger.error(
                        f"❌ Error processing card (ID: {card_id}, Name: {card_name}): {e}",
                        exc_info=True
                    )
                    self.sync_stats['errors'] += 1
                    # Continue to next card
            
            # Log Flow B summary
            logger.info(f"\n✓ Flow B complete: {self.sync_stats['status_synced_to_sheets']} statuses synced to sheets")
            
        except Exception as e:
            logger.error(f"Critical error in Task → Lead sync: {e}", exc_info=True)
            raise
    
    def _process_task_to_lead(self, card: Dict, lead_map: Dict[str, Dict]):
        """
        Process a single card and sync status back to Google Sheets.
        
        Args:
            card: Trello card dictionary
            lead_map: Map of trello_task_id → lead for quick lookup
        """
        card_id = card['id']
        card_name = card.get('name', 'Unnamed')
        
        # Try to find matching lead by trello_task_id
        if card_id not in lead_map:
            logger.debug(f"  ⊘ Card {card_id} ({card_name}) not linked to any lead (no trello_task_id match)")
            self.sync_stats['skipped'] += 1
            return
        
        lead = lead_map[card_id]
        lead_id = lead.get('id', 'unknown')
        lead_name = lead.get('name', 'unknown')
        row_number = lead['row_number']
        
        # Get card status from list
        card_status = self.task_client.get_status_from_list_id(card['idList'])
        sheet_status = normalize_status(lead.get('status', ''))
        
        logger.debug(f"  Card: {card_name}, Lead: {lead_name} (ID: {lead_id})")
        logger.debug(f"  Trello status: {card_status}, Sheet status: {sheet_status}")
        
        # Check if status changed
        if card_status != sheet_status:
            logger.info(
                f"Status divergence detected: "
                f"card={card_name} (Trello: {card_status}) vs "
                f"lead={lead_name} (Sheet: {sheet_status})"
            )
            logger.info(f"  → Updating sheet row {row_number}: {sheet_status} → {card_status}")
            
            # Update lead status in sheet
            self.lead_client.update_lead_by_row(row_number, {'status': card_status.upper()})
            
            self.sync_stats['status_synced_to_sheets'] += 1
            logger.info(f"✓ Status synced: lead_id={lead_id}, row={row_number}, new_status={card_status}")
        else:
            logger.debug(f"  ✓ Status in sync (both {card_status})")
    
    def _log_sync_summary(self):
        """Log detailed sync summary with statistics."""
        logger.info("📊 SYNC STATISTICS:")
        logger.info(f"  Tasks created:          {self.sync_stats['tasks_created']}")
        logger.info(f"  Tasks updated:          {self.sync_stats['tasks_updated']}")
        logger.info(f"  Statuses synced:        {self.sync_stats['status_synced_to_sheets']}")
        logger.info(f"  Records skipped:        {self.sync_stats['skipped']}")
        logger.info(f"  Errors encountered:     {self.sync_stats['errors']}")
        
        total_operations = (
            self.sync_stats['tasks_created'] + 
            self.sync_stats['tasks_updated'] + 
            self.sync_stats['status_synced_to_sheets']
        )
        logger.info(f"  Total operations:       {total_operations}")
        
        if self.sync_stats['errors'] == 0:
            logger.info("✓ All operations completed successfully")
        else:
            logger.warning(f"⚠️  {self.sync_stats['errors']} error(s) occurred during sync")
    
    def get_sync_report(self) -> str:
        """
        Generate a human-readable sync report.
        
        Returns:
            Formatted report string
        """
        report = [
            "\n" + "=" * 70,
            "SYNC REPORT",
            "=" * 70,
            f"Tasks created:              {self.sync_stats['tasks_created']}",
            f"Tasks updated:              {self.sync_stats['tasks_updated']}",
            f"Statuses synced to sheets:  {self.sync_stats['status_synced_to_sheets']}",
            f"Records skipped:            {self.sync_stats['skipped']}",
            f"Errors encountered:         {self.sync_stats['errors']}",
            "=" * 70
        ]
        return "\n".join(report)
