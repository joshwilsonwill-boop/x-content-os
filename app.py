import argparse
import os
import sys
from dotenv import load_dotenv

from core.logging import get_logger, log_action
from core.db import init_db

logger = get_logger("app")

def load_environment():
    load_dotenv()
    # Basic validation
    if not os.getenv("TELEGRAM_BOT_TOKEN") and not os.getenv("DRY_RUN"):
        logger.warning("TELEGRAM_BOT_TOKEN not found in environment", extra={"component": "startup", "action": "env_check", "status": "warning"})

def main():
    parser = argparse.ArgumentParser(description="x-content-os")
    parser.add_argument("--dry-run", action="store_true", help="Run in dry-run mode (no publishing/API mutations)")
    parser.add_argument("--init-db", action="store_true", help="Initialize the database schema")
    parser.add_argument("--telegram", action="store_true", help="Start the Telegram bot")
    parser.add_argument("--ingest", action="store_true", help="Run source ingestion and opportunity discovery")
    parser.add_argument("--x-ingest", action="store_true", help="Run official X API read-only search ingestion")
    
    args = parser.parse_args()

    load_environment()
    
    if args.dry_run:
        os.environ["DRY_RUN"] = "true"
        log_action(logger, 20, "app", "startup", "success", msg="Starting in DRY RUN mode")
    else:
        log_action(logger, 20, "app", "startup", "success", msg="Starting in normal mode")

    if args.init_db:
        os.makedirs("data", exist_ok=True)
        init_db()
        log_action(logger, 20, "db", "init", "success", msg="Database initialized.")
        sys.exit(0)
        
    if args.ingest:
        from core.db import SessionLocal
        from core.services.ingestion_service import run_ingestion
        db = SessionLocal()
        try:
            print("Starting source ingestion...")
            result = run_ingestion(db)
            print("\nIngestion complete\n")
            print(f"Sources checked: {result.sources_checked}")
            print(f"Items fetched: {result.items_fetched}")
            print(f"New items: {result.new_items}")
            print(f"Duplicates: {result.duplicates}")
            print(f"High-opportunity items: {result.high_opportunity_items}")
            print(f"Errors: {result.errors}")
            if result.error_details:
                print("\nError summary:")
                for err in result.error_details:
                    print(f"- {err}")
        finally:
            db.close()
        sys.exit(0)

    if args.x_ingest:
        from core.db import SessionLocal
        from core.services.ingestion_service import run_x_ingestion
        db = SessionLocal()
        try:
            print("Starting X API read-only search ingestion...")
            result = run_x_ingestion(db)
            print("\nX Ingestion complete\n")
            print(f"Queries checked: {result.sources_checked}")
            print(f"Items fetched: {result.items_fetched}")
            print(f"New items: {result.new_items}")
            print(f"Duplicates: {result.duplicates}")
            print(f"High-opportunity items: {result.high_opportunity_items}")
            print(f"Errors: {result.errors}")
            if result.error_details:
                print("\nError summary:")
                for err in result.error_details:
                    print(f"- {err}")
        finally:
            db.close()
        sys.exit(0)

    if args.telegram:
        token = os.getenv("TELEGRAM_BOT_TOKEN")
        if not token:
            logger.error("TELEGRAM_BOT_TOKEN not set.", extra={"component": "startup", "action": "telegram_start", "status": "error"})
            sys.exit(1)
            
        from core.telegram_bot import setup_application
        application = setup_application(token)
        log_action(logger, 20, "app", "telegram", "success", msg="Starting Telegram bot...")
        application.run_polling()
        sys.exit(0)
    
    # Rest of application logic will go here
    log_action(logger, 20, "app", "run", "success", msg="Application is running. Use --init-db to set up or --telegram to run bot.")

if __name__ == "__main__":
    main()
