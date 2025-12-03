"""Main entry point for the two-way sync automation."""
import sys
import argparse
from config import Config
from sync_logic import SyncEngine
from utils.logger import get_logger

logger = get_logger(__name__)


def main():
    """Main function to run the sync process."""
    parser = argparse.ArgumentParser(
        description='Two-way sync between Google Sheets (Lead Tracker) and Trello (Work Tracker)',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py                              # Run full two-way sync
  python main.py --direction both             # Same as above
  python main.py --direction leads-to-tasks   # Only sync Sheets → Trello
  python main.py --direction tasks-to-leads   # Only sync Trello → Sheets
  python main.py --dry-run                    # Simulate without writing
  python main.py --verbose                    # Enable detailed logging
        """
    )
    parser.add_argument(
        '--direction',
        choices=['both', 'leads-to-tasks', 'tasks-to-leads'],
        default='both',
        help='Sync direction: both (default), leads-to-tasks (Sheets→Trello), or tasks-to-leads (Trello→Sheets)'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Simulate sync without making any changes (read-only mode)'
    )
    parser.add_argument(
        '--verbose',
        action='store_true',
        help='Enable verbose (DEBUG) logging'
    )
    
    args = parser.parse_args()
    
    # Set log level if verbose
    if args.verbose:
        import logging
        logging.getLogger().setLevel(logging.DEBUG)
        logger.info("Verbose logging enabled (DEBUG level)")
    
    try:
        logger.info("=" * 70)
        logger.info("Google Sheets ↔ Trello Two-Way Sync")
        logger.info("=" * 70)
        
        # Show sync direction
        if args.direction == 'both':
            logger.info("Direction: BOTH (Sheets ↔ Trello)")
        elif args.direction == 'leads-to-tasks':
            logger.info("Direction: LEADS → TASKS (Sheets → Trello only)")
        else:
            logger.info("Direction: TASKS → LEADS (Trello → Sheets only)")
        
        # Show dry-run mode
        if args.dry_run:
            logger.warning("Mode: DRY RUN (read-only, no changes)")
        else:
            logger.info("Mode: LIVE (changes will be written)")
        
        # Validate configuration
        logger.info("\nValidating configuration...")
        Config.validate()
        logger.info("✓ Configuration validated")
        
        if args.dry_run:
            logger.warning("\n" + "=" * 70)
            logger.warning("⚠️  DRY RUN MODE - No changes will be made")
            logger.warning("=" * 70)
            logger.info("\nDry-run simulation:")
            logger.info("  ✓ Read all leads from Google Sheets")
            logger.info("  ✓ Read all cards from Trello")
            logger.info("  ✓ Compare and identify changes")
            logger.info("  ✓ Log what actions would be taken")
            logger.info("  ✗ Make NO actual changes (read-only)")
            logger.info("\nRun without --dry-run to perform actual sync\n")
            return
        
        # Initialize sync engine
        logger.info("\nInitializing sync engine...")
        sync_engine = SyncEngine()
        logger.info("✓ Sync engine initialized")
        
        # Perform sync based on direction
        logger.info("\nStarting synchronization...\n")
        
        if args.direction == 'both':
            # Full two-way sync
            stats = sync_engine.run_sync()
        elif args.direction == 'leads-to-tasks':
            # Only Sheets → Trello
            logger.info("[PARTIAL SYNC] Running Lead → Task flow only\n")
            sync_engine._sync_leads_to_tasks()
            stats = sync_engine.sync_stats
        else:  # tasks-to-leads
            # Only Trello → Sheets
            logger.info("[PARTIAL SYNC] Running Task → Lead flow only\n")
            sync_engine._sync_tasks_to_leads()
            stats = sync_engine.sync_stats
        
        # Print report
        print(sync_engine.get_sync_report())
        
        # Exit with appropriate code
        if stats['errors'] > 0:
            logger.warning(f"\n⚠️  Sync completed with {stats['errors']} error(s)")
            sys.exit(1)
        else:
            logger.info("\n✓ Sync completed successfully!")
            sys.exit(0)
            
    except FileNotFoundError as e:
        logger.error(f"\n❌ Configuration error: {e}")
        logger.error("Please ensure your .env file and service-account.json are properly set up")
        sys.exit(1)
    except ValueError as e:
        logger.error(f"\n❌ Configuration error: {e}")
        logger.error("Please check your .env file and ensure all required variables are set")
        sys.exit(1)
    except KeyboardInterrupt:
        logger.warning("\n\n⚠️  Sync interrupted by user")
        sys.exit(130)
    except Exception as e:
        logger.error(f"\n❌ Unexpected error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == '__main__':
    main()
