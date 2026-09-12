# x-content-os

A production-minded personal editorial operating system for a single X account.

## Features (Phase 3)
- Project skeleton & isolated repository layer
- Structured logging & Content DNA configuration
- Idea & Draft database models (SQLite/SQLAlchemy)
- **Telegram Bot Control Plane**: Single-owner bot for creating ideas, generating drafts, queueing, and editing.
- **Drafting Engine & Quality Gate**:
  - Deterministic template-based generation (`TemplateDraftGenerator`) from configured `config/editorial_structures.yaml`.
  - Comprehensive quality gate scoring hooks, originality, specificity, voice fit.
  - Caches and blocks banned phrases / clichés.
  - X character counting logic (280 weighted limit, counting URLs as 23 and CJK/emojis as 2).
  - Repetition & pattern fatigue detection via 3-gram Jaccard similarity to prevent duplicate content.

## Setup Instructions

1. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

2. **Configuration (.env):**
   - Copy `.env.example` to `.env` and fill in your credentials.
   - Obtain a Telegram bot token by talking to [@BotFather](https://t.me/botfather) on Telegram.
   - Obtain your Telegram owner ID (using a bot like @userinfobot).
   - Edit `config/content_dna.yaml` to define your account's editorial constitution.
   - Edit `config/editorial_structures.yaml` for custom text frameworks.

   *Security Note: Never commit your `.env` file or paste secrets into source code!*

3. **Initialize Database:**
   ```bash
   python -m app --init-db
   ```

4. **Start the Telegram Bot:**
   ```bash
   python -m app --telegram
   ```

5. **Dry Run Mode:**
   Run the application without altering the X account state or publishing anything.
   ```bash
   python -m app --dry-run
   ```

6. **Run Tests:**
   The entire test suite can be run offline without API keys:
   ```bash
   pytest
   ```

## Available Telegram Commands
- `/start` - Check authorization
- `/status` or `/stats` - View current system and queue status
- `/newidea` - Submit a new raw idea interactively
- `/ideas` - List total ideas
- `/generate` - Select an idea and generate draft variants using editorial structures
- `/queue` or `/review` - View and manage the current draft queue (APPROVE, EDIT, REJECT, REGENERATE, PREVIEW)
- `/pause` - Pause publishing (Publishing is not yet implemented)
- `/resume` - Resume publishing
A Python-based content operating system for X with editorial intelligence, draft generation, quality gates, repetition detection, and Telegram review.
