import os
from functools import wraps
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    ContextTypes,
    ConversationHandler,
)

import html
from telegram.constants import ParseMode
from core.db import SessionLocal
from core.services import idea_service, draft_service, system_service, opportunity_service, ingestion_service
from core.services.draft_generation_service import generate_drafts, get_draft_quality_report
from core.draft_generator import TemplateDraftGenerator
from core.logging import get_logger, log_action

logger = get_logger("telegram")

WAITING_FOR_IDEA = 1
WAITING_FOR_EDIT = 2
WAITING_FOR_GENERATE_IDEA_ID = 3

def get_owner_id() -> int:
    try:
        return int(os.environ.get("TELEGRAM_OWNER_ID", "0"))
    except ValueError:
        return 0

def require_owner(func):
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        user_id = update.effective_user.id
        owner_id = get_owner_id()
        if owner_id == 0 or user_id != owner_id:
            log_action(logger, 30, "telegram", "unauthorized_access", "blocked", object_id=str(user_id))
            if update.message:
                await update.message.reply_text("Unauthorized access.")
            elif update.callback_query:
                await update.callback_query.answer("Unauthorized access.", show_alert=True)
            return ConversationHandler.END
        
        # log command if it's a command
        if update.message and update.message.text and update.message.text.startswith("/"):
            log_action(logger, 20, "telegram", "command", "received", msg=update.message.text.split(" ")[0])
        
        return await func(update, context, *args, **kwargs)
    return wrapper

@require_owner
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Welcome to X Content OS. You are authorized.")

@require_owner
async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db = SessionLocal()
    try:
        mode = system_service.get_system_mode(db)
        stats = system_service.get_stats(db)
        
        text = (
            f"X CONTENT OS\n\n"
            f"Mode: {mode}\n\n"
            f"Ideas: {stats['ideas']}\n"
            f"Drafts awaiting review: {stats['drafts_review']}\n"
            f"Approved: {stats['approved']}\n"
            f"Rejected: {stats['rejected']}\n\n"
            f"Telegram: CONNECTED\n"
            f"Database: CONNECTED\n\n"
            f"X: NOT CONFIGURED"
        )
        await update.message.reply_text(text)
    finally:
        db.close()

@require_owner
async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await status(update, context) # Alias for status in Phase 2

@require_owner
async def pause_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db = SessionLocal()
    try:
        system_service.set_system_mode(db, "PAUSED")
        await update.message.reply_text("Application state set to PAUSED.\nPublishing is not implemented yet.")
    finally:
        db.close()

@require_owner
async def resume_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db = SessionLocal()
    try:
        system_service.set_system_mode(db, "RUNNING")
        await update.message.reply_text("Application state set to RUNNING.\nPublishing is not implemented yet.")
    finally:
        db.close()

@require_owner
async def newidea_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Send me the raw idea. Don't polish it.")
    return WAITING_FOR_IDEA

@require_owner
async def newidea_receive(update: Update, context: ContextTypes.DEFAULT_TYPE):
    raw_text = update.message.text
    db = SessionLocal()
    try:
        idea = idea_service.create_idea(db, raw_text=raw_text)
        await update.message.reply_text(
            f"IDEA SAVED\n\nID: idea_{idea.id}\n\nPillar:\nNone\n\nStatus:\nRAW\n\nPotential:\nNot scored yet"
        )
    finally:
        db.close()
    return ConversationHandler.END

@require_owner
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Action cancelled.")
    return ConversationHandler.END

@require_owner
async def ideas(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db = SessionLocal()
    try:
        all_ideas = idea_service.get_all_ideas(db)
        count = len(all_ideas)
        await update.message.reply_text(f"Total ideas in database: {count}")
    finally:
        db.close()

def build_draft_keyboard(draft_id: int):
    keyboard = [
        [
            InlineKeyboardButton("PREVIEW", callback_data=f"preview_{draft_id}"),
            InlineKeyboardButton("APPROVE", callback_data=f"approve_{draft_id}"),
        ],
        [
            InlineKeyboardButton("EDIT", callback_data=f"edit_{draft_id}"),
            InlineKeyboardButton("REJECT", callback_data=f"reject_{draft_id}"),
        ],
        [
            InlineKeyboardButton("REGENERATE", callback_data=f"regenerate_{draft_id}")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

@require_owner
async def queue_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db = SessionLocal()
    try:
        drafts = draft_service.get_drafts_awaiting_review(db)
        if not drafts:
            await update.message.reply_text("No drafts awaiting review.")
            return

        for draft in drafts:
            text = (
                f"DRAFT #{draft.id}\n\n"
                f"Format:\n{draft.format}\n\n"
                f"Status:\n{draft.status.replace('_', ' ')}\n\n"
                f"Text:\n\n{draft.text}"
            )
            await update.message.reply_text(text, reply_markup=build_draft_keyboard(draft.id))
    finally:
        db.close()

@require_owner
async def review_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await queue_cmd(update, context) # Alias for Phase 2

@require_owner
async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    data = query.data
    log_action(logger, 20, "telegram", "callback", "received", msg=data)

    action, draft_id_str = data.split("_", 1)
    draft_id = int(draft_id_str)
    
    db = SessionLocal()
    try:
        if action == "approve":
            draft = draft_service.update_draft_status(db, draft_id, "APPROVED")
            await query.edit_message_text(f"Draft #{draft.id} APPROVED.")
        
        elif action == "reject":
            draft = draft_service.update_draft_status(db, draft_id, "REJECTED")
            await query.edit_message_text(f"Draft #{draft.id} REJECTED.")
            
        elif action == "preview":
            draft = db.query(Draft).filter(Draft.id == draft_id).first()
            if draft:
                from core.preview import generate_preview_html
                from telegram.constants import ParseMode
                html_text = generate_preview_html(db, draft)
                await query.edit_message_text(html_text, reply_markup=build_draft_keyboard(draft_id), parse_mode=ParseMode.HTML)
            else:
                await query.edit_message_text("Draft not found.")
                
        elif action == "edit":
            context.user_data['edit_draft_id'] = draft_id
            await query.message.reply_text("Send the complete replacement text.")
            return WAITING_FOR_EDIT
            
        elif action == "regenerate":
            draft = db.query(Draft).filter(Draft.id == draft_id).first()
            if draft:
                idea_id = draft.idea_id
                format_str = draft.format
                generator = TemplateDraftGenerator()
                drafts = generate_drafts(db, idea_id, format_str, generator, variant_count=3)
                await query.edit_message_text(f"Draft #{draft_id} regenerated. 3 new variants added to queue.")
            else:
                await query.edit_message_text("Draft not found.")
            
    finally:
        db.close()
    
    return ConversationHandler.END

@require_owner
async def edit_receive(update: Update, context: ContextTypes.DEFAULT_TYPE):
    draft_id = context.user_data.get('edit_draft_id')
    if not draft_id:
        await update.message.reply_text("Error: No draft to edit.")
        return ConversationHandler.END
        
    replacement_text = update.message.text
    db = SessionLocal()
    try:
        draft = draft_service.update_draft_text(db, draft_id, replacement_text)
        await update.message.reply_text(f"Draft #{draft.id} updated and returned to UNDER REVIEW.")
    finally:
        db.close()
    
    # clear user data
    context.user_data.pop('edit_draft_id', None)
    return ConversationHandler.END

@require_owner
async def generate_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db = SessionLocal()
    try:
        ideas = idea_service.get_all_ideas(db)
        recent_ideas = ideas[-5:] if ideas else []
        if not recent_ideas:
            await update.message.reply_text("No ideas available.")
            return ConversationHandler.END
            
        text = "Select an idea ID to generate from:\n\n"
        for i in recent_ideas:
            text += f"ID: {i.id} - {i.raw_text[:50]}...\n"
        await update.message.reply_text(text)
    finally:
        db.close()
    return WAITING_FOR_GENERATE_IDEA_ID

@require_owner
async def generate_receive_idea(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        idea_id = int(update.message.text.strip())
    except ValueError:
        await update.message.reply_text("Invalid ID. Cancelled.")
        return ConversationHandler.END
        
    db = SessionLocal()
    try:
        idea = idea_service.get_idea(db, idea_id)
        if not idea:
            await update.message.reply_text("Idea not found.")
            return ConversationHandler.END
            
        context.user_data['generate_idea_id'] = idea_id
        
        keyboard = [
            [InlineKeyboardButton("OBSERVATION", callback_data="gen_observation"),
             InlineKeyboardButton("CONTRARIAN", callback_data="gen_contrarian")],
            [InlineKeyboardButton("LESSON", callback_data="gen_lesson"),
             InlineKeyboardButton("FRAMEWORK", callback_data="gen_framework")]
        ]
        await update.message.reply_text(f"IDEA #{idea.id}\n\n{idea.raw_text}\n\nSelect format:", reply_markup=InlineKeyboardMarkup(keyboard))
    finally:
        db.close()
    return ConversationHandler.END

@require_owner
async def generate_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    data = query.data
    _, format_str = data.split("_", 1)
    
    idea_id = context.user_data.get('generate_idea_id')
    if not idea_id:
        await query.edit_message_text("No idea selected.")
        return ConversationHandler.END
        
    db = SessionLocal()
    try:
        generator = TemplateDraftGenerator()
        drafts = generate_drafts(db, idea_id, format_str, generator, variant_count=3)
        
        await query.edit_message_text(f"Generated {len(drafts)} variants.")
        
        for d in drafts:
            warnings_text = ""
            report = get_draft_quality_report(db, d.id)
            if report and report.warnings:
                warnings_text = "\nWarnings:\n" + "\n".join(report.warnings)
                
            text = (
                f"Variant #{d.variant_number}\n"
                f"Format: {d.format}\n"
                f"Status: {d.status}\n"
                f"Score: {d.quality_score}/10\n"
                f"Chars: {d.character_count}/280\n"
                f"{warnings_text}\n\n"
                f"{d.text}"
            )
            
            # Don't show APPROVE if it failed
            keyboard = []
            if d.status != "FAILED":
                keyboard.append([InlineKeyboardButton("APPROVE", callback_data=f"approve_{d.id}")])
            keyboard.append([InlineKeyboardButton("EDIT", callback_data=f"edit_{d.id}"), InlineKeyboardButton("REJECT", callback_data=f"reject_{d.id}")])
            keyboard.append([InlineKeyboardButton("REGENERATE", callback_data=f"regenerate_{d.id}")])
            
            await query.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
            
    finally:
        db.close()
def format_opportunity_card(opp) -> str:
    s_id = html.escape(str(opp.source_id))
    s_topic = html.escape(str(opp.topic or "Technology"))
    s_title = html.escape(str(opp.title or "Untitled"))
    s_author = html.escape(str(opp.author or ""))
    s_content = html.escape(str(opp.content or opp.title or ""))
    
    score = int(opp.opportunity_score or 0)
    rel = int(opp.relevance_score or 0)
    fresh = int(opp.freshness_score or 0)
    orig = int(opp.original_angle_score or 0)
    aud = int(opp.audience_value_score or 0)
    conv = int(opp.conversation_score or 0)
    risk = int(opp.spam_risk_score or 0)
    risk_label = "Low" if risk <= 3 else ("Medium" if risk <= 6 else "High")
    
    if opp.source_type == "x":
        metrics = (opp.raw_metadata or {}).get("public_metrics") or {}
        replies = metrics.get("reply_count", 0)
        reposts = metrics.get("retweet_count", 0)
        likes = metrics.get("like_count", 0)
        
        why_it_matters = html.escape(
            f"Active X discussion on '{opp.topic or 'Technology'}' with {replies} replies and freshness {fresh}/20."
        )
        suggested_angle = html.escape(
            f"Perspective on '{opp.topic or 'Technology'}': Address the engineering trade-offs discussed in the post."
        )
        
        return (
            f"<b>POTENTIAL X CONVERSATION #{opp.id}</b>\n\n"
            f"<b>Author:</b> {s_author}\n"
            f"<b>Topic:</b> {s_topic}\n\n"
            f"<b>Post:</b>\n{s_content}\n\n"
            f"<b>Why it matters:</b>\n{why_it_matters}\n\n"
            f"<b>Opportunity Score:</b> {score}/100\n\n"
            f"Relevance: {rel}/20 | Freshness: {fresh}/20\n"
            f"Original Angle: {orig}/20 | Audience Value: {aud}/20\n"
            f"Conversation: {conv}/10 | Risk: {risk_label}\n\n"
            f"<b>Engagement:</b> {replies} replies | {reposts} reposts | {likes} likes\n\n"
            f"<b>Suggested angle:</b>\n{suggested_angle}"
        )
    else:
        why_it_matters = html.escape(f"Matches pillar '{opp.topic or 'Technology'}' with freshness {fresh}/20 and developer audience signal.")
        suggested_angle = html.escape(f"Contrarian observation on {opp.topic or 'Technology'}: highlight systems trade-offs over hype.")
        
        return (
            f"<b>OPPORTUNITY #{opp.id}</b>\n\n"
            f"<b>Source:</b> {s_id}\n"
            f"<b>Topic:</b> {s_topic}\n\n"
            f"<b>Title:</b>\n{s_title}\n\n"
            f"<b>Why it matters:</b>\n{why_it_matters}\n\n"
            f"<b>Opportunity Score:</b> {score}/100\n\n"
            f"Relevance: {rel}/20 | Freshness: {fresh}/20\n"
            f"Original Angle: {orig}/20 | Audience Value: {aud}/20\n"
            f"Conversation: {conv}/10 | Risk: {risk_label}\n\n"
            f"<b>Suggested angle:</b>\n{suggested_angle}"
        )

def build_opportunity_keyboard(opp) -> InlineKeyboardMarkup:
    row1 = []
    btn_label = "OPEN POST" if opp.source_type == "x" else "OPEN SOURCE"
    if opp.url and opp.url.startswith(("http://", "https://")):
        row1.append(InlineKeyboardButton(btn_label, url=opp.url))
    else:
        row1.append(InlineKeyboardButton(btn_label, callback_data=f"opp_open_{opp.id}"))
    row1.append(InlineKeyboardButton("DRAFT", callback_data=f"opp_draft_{opp.id}"))
    
    row2 = [
        InlineKeyboardButton("SAVE", callback_data=f"opp_save_{opp.id}"),
        InlineKeyboardButton("IGNORE", callback_data=f"opp_ignore_{opp.id}")
    ]
    return InlineKeyboardMarkup([row1, row2])

@require_owner
async def opportunities_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db = SessionLocal()
    try:
        opps = opportunity_service.get_opportunities(db, status="NEW", limit=5)
        if not opps:
            opps = opportunity_service.get_opportunities(db, status="SAVED", limit=5)
        if not opps:
            await update.message.reply_text("No active opportunities found. Use /ingest to discover new source signals.")
            return
            
        await update.message.reply_text(f"Found {len(opps)} active opportunity signals:")
        for opp in opps:
            card_text = format_opportunity_card(opp)
            reply_markup = build_opportunity_keyboard(opp)
            await update.message.reply_text(card_text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)
    finally:
        db.close()

@require_owner
async def xsignals_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db = SessionLocal()
    try:
        opps = opportunity_service.get_opportunities(db, status="NEW", source_type="x", limit=5)
        if not opps:
            opps = opportunity_service.get_opportunities(db, status="SAVED", source_type="x", limit=5)
        if not opps:
            await update.message.reply_text("No active X signals found. Run python app.py --x-ingest to search recent X posts.")
            return

        await update.message.reply_text(f"Found {len(opps)} active X conversation signal(s):")
        for opp in opps:
            card_text = format_opportunity_card(opp)
            reply_markup = build_opportunity_keyboard(opp)
            await update.message.reply_text(card_text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)
    finally:
        db.close()

@require_owner
async def ingest_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Running source ingestion...")
    db = SessionLocal()
    try:
        res = ingestion_service.run_ingestion(db)
        text = (
            f"Ingestion complete\n\n"
            f"Sources checked: {res.sources_checked}\n"
            f"Items fetched: {res.items_fetched}\n"
            f"New items: {res.new_items}\n"
            f"Duplicates: {res.duplicates}\n"
            f"High-opportunity items: {res.high_opportunity_items}\n"
            f"Errors: {res.errors}"
        )
        await update.message.reply_text(text)
    finally:
        db.close()

@require_owner
async def opportunity_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    data = query.data or ""
    # Expected format: opp_<action>_<id>
    parts = data.split("_")
    if len(parts) != 3 or parts[0] != "opp":
        logger.warning(f"Malformed opportunity callback data: {data}")
        await query.edit_message_text("Invalid action payload.")
        return

    action = parts[1]
    try:
        opp_id = int(parts[2])
    except ValueError:
        logger.warning(f"Invalid opportunity ID in callback data: {data}")
        await query.edit_message_text("Invalid opportunity ID.")
        return
    
    db = SessionLocal()
    try:
        if action == "save":
            opportunity_service.save_opportunity(db, opp_id)
            await query.edit_message_text(f"Opportunity #{opp_id} SAVED.")
        elif action == "ignore":
            opportunity_service.ignore_opportunity(db, opp_id)
            await query.edit_message_text(f"Opportunity #{opp_id} IGNORED.")
        elif action == "open":
            item = opportunity_service.get_opportunity(db, opp_id)
            url = item.url if item and item.url else "No URL available."
            await query.message.reply_text(f"Source URL for #{opp_id}:\n{url}")
        elif action == "draft":
            idea = opportunity_service.draft_opportunity(db, opp_id)
            if not idea:
                await query.edit_message_text(f"Opportunity #{opp_id} could not be drafted.")
                return
            await query.edit_message_text(f"Opportunity #{opp_id} converted to Idea #{idea.id}!\nGenerating 3 draft variants...")
            
            generator = TemplateDraftGenerator()
            drafts = generate_drafts(db, idea.id, "observation", generator, variant_count=3)
            for d in drafts:
                warnings_text = ""
                report = get_draft_quality_report(db, d.id)
                if report and report.warnings:
                    warnings_text = "\nWarnings:\n" + "\n".join(report.warnings)
                    
                text = (
                    f"Variant #{d.variant_number}\n"
                    f"Format: {d.format}\n"
                    f"Status: {d.status}\n"
                    f"Score: {d.quality_score}/10\n"
                    f"Chars: {d.character_count}/280\n"
                    f"{warnings_text}\n\n"
                    f"{d.text}"
                )
                keyboard = []
                if d.status != "FAILED":
                    keyboard.append([InlineKeyboardButton("APPROVE", callback_data=f"approve_{d.id}")])
                keyboard.append([InlineKeyboardButton("EDIT", callback_data=f"edit_{d.id}"), InlineKeyboardButton("REJECT", callback_data=f"reject_{d.id}")])
                keyboard.append([InlineKeyboardButton("REGENERATE", callback_data=f"regenerate_{d.id}")])
                await query.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
    finally:
        db.close()

def setup_application(token: str) -> Application:
    application = Application.builder().token(token).build()

    newidea_conv = ConversationHandler(
        entry_points=[CommandHandler("newidea", newidea_start)],
        states={
            WAITING_FOR_IDEA: [MessageHandler(filters.TEXT & ~filters.COMMAND, newidea_receive)]
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    edit_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(button_callback, pattern="^edit_")],
        states={
            WAITING_FOR_EDIT: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_receive)]
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    generate_conv = ConversationHandler(
        entry_points=[CommandHandler("generate", generate_start)],
        states={
            WAITING_FOR_GENERATE_IDEA_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, generate_receive_idea)]
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    application.add_handler(newidea_conv)
    application.add_handler(edit_conv)
    application.add_handler(generate_conv)
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("status", status))
    application.add_handler(CommandHandler("stats", stats))
    application.add_handler(CommandHandler("pause", pause_cmd))
    application.add_handler(CommandHandler("resume", resume_cmd))
    application.add_handler(CommandHandler("ideas", ideas))
    application.add_handler(CommandHandler("queue", queue_cmd))
    application.add_handler(CommandHandler("review", review_cmd))
    application.add_handler(CommandHandler("opportunities", opportunities_cmd))
    application.add_handler(CommandHandler("signals", opportunities_cmd))
    application.add_handler(CommandHandler("xsignals", xsignals_cmd))
    application.add_handler(CommandHandler("ingest", ingest_cmd))
    
    application.add_handler(CallbackQueryHandler(button_callback, pattern="^(approve|reject|preview|regenerate)_"))
    application.add_handler(CallbackQueryHandler(generate_callback, pattern="^gen_"))
    application.add_handler(CallbackQueryHandler(opportunity_callback, pattern="^opp_"))

    return application
