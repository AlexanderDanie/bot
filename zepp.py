"""
Web3 Promotion Hub Bot v2.1
- Fixed all undefined variable errors
- Maintains trends, voting, and service features
- Proper error handling and logging
"""

import logging
import os
import sqlite3
import requests
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    CallbackQueryHandler,
    MessageHandler,
    filters
)
from dotenv import load_dotenv

# Configuration
load_dotenv()
TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
ADMIN_IDS = [int(id) for id in os.getenv('ADMIN_IDS', '').split(',') if id]
COINGECKO_API = "https://api.coingecko.com/api/v3"
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Database setup


def init_db():
    """Initialize the database with required tables"""
    with sqlite3.connect('web3_bot.db') as conn:
        conn.executescript('''
        CREATE TABLE IF NOT EXISTS projects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            description TEXT,
            votes INTEGER DEFAULT 0,
            submitted_by INTEGER,
            submission_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        
        CREATE TABLE IF NOT EXISTS services (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            service_type TEXT NOT NULL,
            description TEXT,
            price TEXT,
            is_active BOOLEAN DEFAULT 1,
            post_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        
        CREATE TABLE IF NOT EXISTS votes (
            user_id INTEGER NOT NULL,
            project_id INTEGER NOT NULL,
            PRIMARY KEY (user_id, project_id)
        );
        
        CREATE TABLE IF NOT EXISTS wallets (
            coin TEXT PRIMARY KEY,
            address TEXT NOT NULL
        );
        ''')

        # Insert sample wallets if empty
        if not conn.execute('SELECT 1 FROM wallets LIMIT 1').fetchone():
            conn.executemany(
                'INSERT INTO wallets VALUES (?, ?)',
                [('BTC', '1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa'),
                 ('ETH', '0x742d35Cc6634C0532925a3b844Bc454e4438f44e')]
            )


# Service categories
SERVICE_TYPES = {
    'shilling': "📢 Shilling Services",
    'hype': "🚀 Organic Hype Building",
    'mod': "🛡️ Community Moderation",
    'cm': "👥 Community Management",
    'dev': "💻 Web3 Development",
    'design': "🎨 NFT/Web3 Design",
    'other': "🔮 Other Web3 Services"
}

# ======================
# SERVICE FUNCTIONS
# ======================


async def submit_service(context: ContextTypes.DEFAULT_TYPE, user_id: int, service_type: str, description: str):
    """Store service in database and notify admins"""
    with sqlite3.connect('web3_bot.db') as conn:
        conn.execute(
            'INSERT INTO services (user_id, service_type, description) VALUES (?, ?, ?)',
            (user_id, service_type, description)
        )

    # Notify all admins
    for admin_id in ADMIN_IDS:
        try:
            await context.bot.send_message(
                admin_id,
                f"🆕 New Service Submission:\n\n"
                f"Type: {SERVICE_TYPES.get(service_type, service_type)}\n"
                f"From: @{context.bot.get_chat(user_id).username}\n"
                f"Details: {description[:1000]}"
            )
        except Exception as e:  # pylint: disable=broad-except
            logger.error("Failed to notify admin %d: %s", admin_id, e)

# ======================
# BUTTON HANDLERS
# ======================


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle all inline button presses"""
    query = update.callback_query
    await query.answer()

    data = query.data
    user_id = query.from_user.id

    if data.startswith('vote_'):
        project_id = int(data[5:])
        await process_vote(context, user_id, project_id)
    elif data.startswith('service_'):
        service_type = data[8:]
        await query.edit_message_text(
            f"✍️ Describe your {SERVICE_TYPES[service_type]}:\n\n"
            "Example: \"I provide Twitter shilling for new NFT projects with 10K+ follower network\"\n\n"
            "Type your description now:"
        )
        context.user_data['awaiting_service'] = service_type
    elif data == 'service_menu':
        await show_service_menu(query)
    elif data == 'vote_menu':
        await vote_project(update, context)
    elif data == 'trends':
        await crypto_trends(update, context)
    elif data == 'wallets':
        await show_wallets(update, context)


async def show_service_menu(query):
    """Display service type selection"""
    keyboard = [
        [InlineKeyboardButton(text, callback_data=f'service_{key}')]
        for key, text in SERVICE_TYPES.items()
    ]
    await query.edit_message_text(
        "🎯 Select your service type:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# ======================
# MESSAGE HANDLERS
# ======================


async def handle_service_description(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Process service descriptions after type selection"""
    if 'awaiting_service' not in context.user_data:
        return

    service_type = context.user_data['awaiting_service']
    description = update.message.text
    user = update.effective_user

    await submit_service(context, user.id, service_type, description)
    del context.user_data['awaiting_service']
    await update.message.reply_text("✅ Service submitted to admins!")

# ======================
# VOTING SYSTEM
# ======================


async def process_vote(context: ContextTypes.DEFAULT_TYPE, user_id: int, project_id: int):
    """Record a vote in database"""
    with sqlite3.connect('web3_bot.db') as conn:
        try:
            conn.execute(
                'INSERT INTO votes (user_id, project_id) VALUES (?, ?)',
                (user_id, project_id)
            )
            conn.execute(
                'UPDATE projects SET votes = votes + 1 WHERE id = ?',
                (project_id,)
            )
            await context.bot.send_message(
                user_id,
                "✅ Your vote has been counted! Project ranking updated."
            )
        except sqlite3.IntegrityError:
            await context.bot.send_message(
                user_id,
                "⚠️ You've already voted for this project!"
            )
        except Exception as e:  # pylint: disable=broad-except
            logger.error("Vote processing error: %s", e)
            await context.bot.send_message(
                user_id,
                "⚠️ Failed to process your vote. Please try again."
            )

# ======================
# CORE COMMANDS
# ======================


async def start(update: Update, _: ContextTypes.DEFAULT_TYPE):
    """Enhanced welcome message with all features"""
    keyboard = [
        [InlineKeyboardButton("📊 Vote Projects", callback_data='vote_menu'),
         InlineKeyboardButton("📈 Market Trends", callback_data='trends')],
        [InlineKeyboardButton("🛍️ Offer Services", callback_data='service_menu'),
         InlineKeyboardButton("🔍 Find Services", callback_data='find_services')],
        [InlineKeyboardButton("🔑 Wallet Addresses", callback_data='wallets')]
    ]
    await update.message.reply_text(
        "🌐 Web3 Promotion Hub\n\n"
        "1. Vote for projects ↗️\n"
        "2. Check crypto trends 📊\n"
        "3. Offer/find services 💼\n"
        "4. View official wallets 🔐\n\n"
        "Choose an option:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def crypto_trends(update: Update, _: ContextTypes.DEFAULT_TYPE):
    """Get top 5 trending coins with price changes"""
    try:
        response = requests.get(
            f"{COINGECKO_API}/coins/markets",
            params={
                'vs_currency': 'usd',
                'order': 'market_cap_desc',
                'per_page': 5,
                'price_change_percentage': '24h'
            },
            timeout=10
        )
        response.raise_for_status()

        trends = [
            f"{coin['symbol'].upper()}: ${coin['current_price']:,} "
            f"({coin['price_change_percentage_24h']:+.1f}%)"
            for coin in response.json()
        ]

        await update.message.reply_text(
            "🔥 Top 5 Cryptocurrencies:\n\n" + "\n".join(trends) +
            "\n\n📊 24h price change"
        )
    except requests.RequestException as e:
        logger.error("Trends API error: %s", e)
        await update.message.reply_text(
            "⚠️ Couldn't fetch trends. Try again later.\n"
            "Meanwhile check /wallets or /vote"
        )


async def vote_project(update: Update, _: ContextTypes.DEFAULT_TYPE):
    """Show voting interface"""
    with sqlite3.connect('web3_bot.db') as conn:
        projects = conn.execute(
            '''SELECT id, name, votes 
            FROM projects 
            ORDER BY votes DESC 
            LIMIT 10'''
        ).fetchall()

    if not projects:
        await update.message.reply_text(
            "📭 No projects available for voting yet!\n"
            "Admins can add projects with /addproject"
        )
        return

    keyboard = [
        [InlineKeyboardButton(f"{name} (👍 {votes})",
                              callback_data=f'vote_{id}')]
        for id, name, votes in projects
    ]
    await update.message.reply_text(
        "🗳️ Vote for Web3 Projects\n"
        "Community-ranked top 10:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def promote_service(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Service submission with categories"""
    if not context.args:
        keyboard = [
            [InlineKeyboardButton(text, callback_data=f'service_{key}')]
            for key, text in SERVICE_TYPES.items()
        ]
        await update.message.reply_text(
            "🎯 Select your service type:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return

    await submit_service(context, update.effective_user.id, 'custom', ' '.join(context.args))
    await update.message.reply_text("✅ Service submitted to admins!")


async def show_wallets(update: Update, _: ContextTypes.DEFAULT_TYPE):
    """Display verified wallet addresses"""
    with sqlite3.connect('web3_bot.db') as conn:
        wallets = conn.execute('SELECT coin, address FROM wallets').fetchall()

    response = "🔐 Verified Wallets:\n\n" + "\n".join(
        f"{coin}: <code>{address}</code>"
        for coin, address in wallets
    )
    await update.message.reply_text(response, parse_mode='HTML')

# ======================
# MAIN BOT SETUP
# ======================


def main():
    """Initialize and run the bot"""
    init_db()
    app = Application.builder().token(TOKEN).build()

    # Command handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("trends", crypto_trends))
    app.add_handler(CommandHandler("vote", vote_project))
    app.add_handler(CommandHandler("promote", promote_service))
    app.add_handler(CommandHandler("wallets", show_wallets))

    # Button handlers
    app.add_handler(CallbackQueryHandler(button_handler))

    # Message handlers
    app.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND,
        handle_service_description
    ))

    logger.info("Bot starting with full functionality...")
    app.run_polling()


if __name__ == '__main__':
    main()
