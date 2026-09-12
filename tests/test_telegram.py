import pytest
from unittest.mock import AsyncMock, MagicMock
from telegram import Update, User, Message, Chat
from core.telegram_bot import require_owner, get_owner_id
import os

@pytest.fixture
def mock_update():
    update = MagicMock(spec=Update)
    update.effective_user = MagicMock(spec=User)
    update.effective_user.id = 12345
    update.message = AsyncMock(spec=Message)
    update.message.reply_text = AsyncMock()
    return update

@pytest.fixture
def mock_context():
    return AsyncMock()

@pytest.mark.asyncio
async def test_require_owner_unauthorized(mock_update, mock_context):
    os.environ["TELEGRAM_OWNER_ID"] = "99999" # Not matching 12345
    
    @require_owner
    async def dummy_handler(update, context):
        return "SUCCESS"
        
    result = await dummy_handler(mock_update, mock_context)
    
    mock_update.message.reply_text.assert_called_once_with("Unauthorized access.")
    assert result == -1 # ConversationHandler.END

@pytest.mark.asyncio
async def test_require_owner_authorized(mock_update, mock_context):
    os.environ["TELEGRAM_OWNER_ID"] = "12345" # Matching
    
    @require_owner
    async def dummy_handler(update, context):
        return "SUCCESS"
        
    result = await dummy_handler(mock_update, mock_context)
    
    mock_update.message.reply_text.assert_not_called()
    assert result == "SUCCESS"
