# x-content-os

A personal editorial operating system for a single X account. It is a local-first Python application designed to assist in idea capture, source intelligence, deterministic draft generation, quality scoring, and Telegram review.

> **Status:** Phase 6 (X Read-Only Intelligence) Complete. Not yet fully production-ready.

---

## System Architecture

```text
                 SOURCE LAYER
        ┌────────────┬─────────────┐
        │            │             │
       RSS      Manual Notes   Official X API v2
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
          (/opportunities, /xsignals)
                     ↓
            SAVE / DRAFT / IGNORE
                     ↓
        DRAFT GENERATOR & QUALITY GATE
                     ↓
              TELEGRAM PREVIEW
```

---

## Features (Phases 1–6)

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
   - Configurable RSS feeds (`config/sources.yaml`).
   - Standard-library RSS 2.0 / 1.0 and Atom adapter (`core/sources.py`) with 5 MB response caps.
   - Normalization: HTML stripping, entity unescaping, whitespace cleanup, and tracking parameter removal.
   - Deduplication: Multi-layer checking via external ID, canonical URL, SHA-256 content hash, and conservative lexical similarity.
   - Deterministic Opportunity Scoring (0–100 scale across Relevance, Freshness, Original Angle, Audience Value, Conversation, and Spam Risk).
   - Idempotent drafting and full opportunity lifecycle (`NEW`, `REVIEWED`, `SAVED`, `DRAFTED`, `IGNORED`, `EXPIRED`).
6. **X Read-Only Intelligence (Phase 6)**:
   - Official X API v2 recent search adapter (`core/x_source.py`) using App-Only Bearer Token auth.
   - Small, focused query configuration (`config/x_sources.yaml`) derived from Content DNA.
   - Bounded pagination (max 1–2 pages) and rate-limit awareness (HTTP 429 reset handling).
   - Multi-query cross-deduplication ensuring the same X post ID is never stored twice.
   - Opportunity scoring integration factoring in verified conversation and engagement metrics.
   - Telegram `/xsignals` command surfacing potential technical discussions with author info, metrics, and safe direct `[OPEN POST]` links.
   - Provenance tracking connecting discovered X posts directly to generated draft variants.

---

## Configuration

### 1. RSS Sources (`config/sources.yaml`)
Define active RSS or external feeds without changing Python code:
```yaml
sources:
  - id: python_news
    type: rss
    name: Python Insider News
    url: https://blog.python.org/feeds/posts/default
    enabled: true
    topics:
      - technology
      - software
```

### 2. X API Search Queries (`config/x_sources.yaml`)
Define focused official X search queries using supported operators (`-is:retweet`, `-is:reply`, `lang:en`):
```yaml
queries:
  - id: ai_software_architecture
    query: "(AI OR LLM) (architecture OR \"systems engineering\" OR database) -is:retweet -is:reply lang:en"
    enabled: true
    max_results: 10
    topic: "Technology"
```

### 3. Content DNA (`config/content_dna.yaml`)
Defines the editorial constitution: positioning, audience, pillars, preferred vocabulary, and banned phrases.

### 4. Settings (`config/settings.yaml`)
Defines preview identity defaults (`display_name`, `handle`).

---

## How to Run

### Setup
```bash
pip install -r requirements.txt
cp .env.example .env
# Edit .env with TELEGRAM_BOT_TOKEN, TELEGRAM_OWNER_ID, and X_BEARER_TOKEN
```

### Initialize Database
```bash
python app.py --init-db
```

### Source Ingestion (CLI)
- **RSS Ingestion:**
  ```bash
  python app.py --ingest
  ```
- **X API Read-Only Search Ingestion:**
  ```bash
  python app.py --x-ingest
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
- `/opportunities` or `/signals` - Review active opportunity signals across all sources.
- `/xsignals` - Review active discussions discovered via official X API search.
  - `[OPEN POST]` - Open original X post directly in client (browser or app).
  - `[DRAFT]` - Convert opportunity to an Idea and immediately generate 3 draft variants.
  - `[SAVE]` - Keep opportunity in saved state for later review.
  - `[IGNORE]` - Dismiss opportunity from queue.
- `/ingest` - Trigger RSS ingestion directly from Telegram.
- `/newidea` - Submit a new raw idea interactively.
- `/ideas` - List recorded ideas.
- `/generate` - Select an idea and generate draft variants using editorial structures.
- `/queue` or `/review` - Review drafts awaiting approval (`APPROVE`, `EDIT`, `REJECT`, `REGENERATE`, `PREVIEW`).
- `/pause` / `/resume` - Toggle global application publishing pause state.

---

## Opportunity Scoring Methodology

The opportunity score answers: *"Is this source signal worth turning into content or engaging with?"*
It evaluates signals deterministically on a 0–100 scale:

| Dimension | Weight | Heuristic |
|---|---|---|
| **Relevance** | 0–20 | Keyword and topical alignment with Content DNA pillars and preferred vocabulary. |
| **Freshness** | 0–20 | Decay curve based on publication timestamp (<12h = 20, <24h = 18, <48h = 14, older decaying to 2; future timestamps bounded). |
| **Original Angle** | 0–20 | Intersections with core arguments, beliefs, and contrarian / trade-off signals. |
| **Audience Value** | 0–20 | Concrete substance for technical audience (architecture, benchmarks, vulnerabilities, numbers, verified engagement). |
| **Conversation** | 0–10 | Discussion-provoking indicators (questions, debates, comparisons, active reply counts). |
| **Spam Risk** | 0–10 | Penalty for marketing fluff, buzzwords, crypto airdrop hype, and banned phrases. |

*Note: High engagement (e.g. 50,000 likes) on an irrelevant viral post will NOT produce a high opportunity score because Relevance is strictly bounded by Content DNA.*

---

## Rate-Limit & API Behavior

- X API v2 Recent Search uses App-Only Bearer Token authentication.
- Bounded queries (`max_results` defaults to 10, max pages capped at 2) prevent burning rate limits.
- On HTTP 429 (Too Many Requests), the adapter parses `x-rate-limit-reset` and halts immediately.
- X API errors are isolated per query and do not interrupt RSS or other application services.

---

## Important Automation Boundaries

Phase 6 is strictly **READ-ONLY INTELLIGENCE**:
- NO browser automation (Selenium, Playwright, cookie injection).
- NO scraping of x.com.
- NO automated likes.
- NO automated follows.
- NO automated replies.
- NO automated quote posts.
- NO automated publishing to X.
- Discovered signals produce recommendations in Telegram; any human engagement or publication remains manual and outside this automated loop.
