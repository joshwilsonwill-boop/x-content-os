# x-content-os

A personal editorial operating system for a single X account. It is a local-first Python application designed to assist in idea capture, source intelligence, deterministic draft generation, quality scoring, and Telegram review.

> **Status:** Phase 5 (Content Intelligence, Sources & Opportunity Discovery) Complete. Not yet fully production-ready.

---

## System Architecture

```text
               SOURCE LAYER
      ┌────────────┬─────────────┐
      │            │             │
     RSS      Manual Notes  Future X API
      │            │             │
      └────────────┴─────────────┘
                   ↓
              INGESTION
                   ↓
            NORMALIZATION
                   ↓
            SOURCE SIGNAL
                   ↓
             DEDUPLICATION
                   ↓
          OPPORTUNITY SCORING
                   ↓
         OPPORTUNITY DATABASE
                   ↓
          TELEGRAM CONTROL PLANE
                   ↓
        SAVE / DRAFT / IGNORE
                   ↓
    DRAFT GENERATOR & QUALITY GATE
                   ↓
          TELEGRAM PREVIEW
```

---

## Features (Phases 1–5)

1. **Core Data & Logging**: SQLite with SQLAlchemy ORM, clean repository/service isolation, and JSON structured logging.
2. **Telegram Bot Control Plane**: Single-owner bot interface with strict authorization, pause/resume state management, and conversational draft/idea review.
3. **Drafting Engine & Quality Gate**:
   - Deterministic template-based draft generation from 10 configured rhetorical structures (`config/editorial_structures.yaml`).
   - Editorial heuristics evaluating Hook, Specificity, Voice Fit, Usefulness, and Originality.
   - Categorical blocking on banned phrases/clichés and over-limit characters.
   - X character counting adhering to official 280-character weighting rules (URLs = 23, Emojis/CJK = 2, ASCII = 1).
   - Repetition detection (3-gram lexical Jaccard index and opening phrase fatigue tracking).
4. **Deterministic Preview Engine**: Telegram HTML preview formatting displaying real-time character counts, quality breakdown, pillar, and status indicators.
5. **Content Intelligence & Opportunity Discovery (Phase 5)**:
   - Configurable source feeds (`config/sources.yaml`).
   - Standard-library RSS 2.0 / 1.0 and Atom adapter (`core/sources.py`).
   - Normalization: HTML stripping, entity unescaping, whitespace cleanup, and tracking parameter removal.
   - Deduplication: Multi-layer checking via external ID, canonical URL, SHA-256 content hash, and conservative lexical similarity.
   - Deterministic Opportunity Scoring (0–100 scale across Relevance, Freshness, Original Angle, Audience Value, Conversation, and Spam Risk).
   - Full Opportunity lifecycle (`NEW`, `REVIEWED`, `SAVED`, `DRAFTED`, `IGNORED`, `EXPIRED`).
   - Provenance tracking connecting discovered signals to created ideas and drafts.
   - Telegram `/opportunities` (or `/signals`) queue with compact callback actions (`DRAFT`, `SAVE`, `IGNORE`, `OPEN SOURCE`).

---

## Configuration

### 1. Sources (`config/sources.yaml`)
Define active RSS or external feeds without changing Python code:
```yaml
sources:
  - id: python_news
    type: rss
    name: Python Software Foundation News
    url: https://feeds.feedburner.com/PythonSoftwareFoundationNews
    enabled: true
    topics:
      - technology
      - software
```

### 2. Content DNA (`config/content_dna.yaml`)
Defines the editorial constitution: positioning, audience, pillars, preferred vocabulary, and banned phrases.

### 3. Settings (`config/settings.yaml`)
Defines preview identity defaults (`display_name`, `handle`).

---

## How to Run

### Setup
```bash
pip install -r requirements.txt
cp .env.example .env
# Edit .env with your TELEGRAM_BOT_TOKEN and TELEGRAM_OWNER_ID
```

### Initialize Database
```bash
python app.py --init-db
```

### Ingestion & Opportunity Discovery (CLI)
Run manual ingestion from configured sources:
```bash
python app.py --ingest
```
Outputs a structured summary:
```text
Ingestion complete

Sources checked: 1
Items fetched: 10
New items: 10
Duplicates: 0
High-opportunity items: 2
Errors: 0
```

### Run Telegram Bot
```bash
python app.py --telegram
```

### Run Tests (Offline)
```bash
pytest -v
```

---

## Telegram Commands

- `/start` - Check owner authorization.
- `/status` or `/stats` - View system mode, idea counts, and draft queue status.
- `/opportunities` or `/signals` - Review high-opportunity content signals.
  - `[OPEN SOURCE]` - Open original external link directly in client.
  - `[DRAFT]` - Convert opportunity to an Idea and immediately generate 3 draft variants.
  - `[SAVE]` - Keep opportunity in saved state for later review.
  - `[IGNORE]` - Dismiss opportunity from queue.
- `/ingest` - Trigger source ingestion directly from Telegram.
- `/newidea` - Submit a new raw idea interactively.
- `/ideas` - List recorded ideas.
- `/generate` - Select an idea and generate draft variants using editorial structures.
- `/queue` or `/review` - Review drafts awaiting approval (`APPROVE`, `EDIT`, `REJECT`, `REGENERATE`, `PREVIEW`).
- `/pause` / `/resume` - Toggle global application publishing pause state.

---

## Opportunity Scoring Methodology

The opportunity score answers: *"Is this source signal worth turning into content?"*
It evaluates signals deterministically on a 0–100 scale:

| Dimension | Weight | Heuristic |
|---|---|---|
| **Relevance** | 0–20 | Keyword and topical alignment with Content DNA pillars and preferred vocabulary. |
| **Freshness** | 0–20 | Decay curve based on publication timestamp (<12h = 20, <24h = 18, <48h = 14, older decaying to 2). |
| **Original Angle** | 0–20 | Intersections with core arguments, beliefs, and contrarian / trade-off signals. |
| **Audience Value** | 0–20 | Concrete substance for technical audience (architecture, benchmarks, vulnerabilities, numbers). |
| **Conversation** | 0–10 | Discussion-provoking indicators (comparisons, questions, debates, postmortems). |
| **Spam Risk** | 0–10 | Penalty for marketing fluff, buzzwords, crypto hype, and banned phrases. |

---

## Known Limitations

- **Heuristic Lexical Intelligence**: Ingestion, deduplication, and scoring rely on deterministic heuristics and N-gram lexical similarity, not deep semantic embeddings.
- **No Ingestion Daemon**: Ingestion is triggered manually via CLI (`--ingest`) or Telegram (`/ingest`). Scheduled background execution belongs to a later phase.
- **No Full Article Scraping**: The RSS adapter relies on feed titles, summaries, and descriptions. It intentionally avoids full-page DOM scraping.

---

## Intentionally NOT Implemented

- No X API publishing or automated posting.
- No automated replies, likes, follows, or quote tweets.
- No browser automation (Selenium, Playwright, cookie injection).
- No external LLM dependencies or paid API keys.
- No vector databases or embeddings.
- No Celery, Redis, or Docker background workers.
