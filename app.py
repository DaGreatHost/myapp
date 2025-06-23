import os
import logging
from flask import Flask, render_template, request, jsonify
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
import asyncio
from datetime import datetime
import json
import threading

# Setup logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', 
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Environment variables
BOT_TOKEN = os.getenv('BOT_API')
ADMIN_ID = int(os.getenv('ADMIN_ID', '0'))
WEBAPP_URL = os.getenv('WEBAPP_URL', 'https://tgreward.shop/tiktok.php')

# Flask app for webapp
app = Flask(__name__)

# Global variables for tracking
user_data = {}
total_users = 0
daily_shares = 0

# Global bot application
bot_application = None

@app.route('/')
def webapp():
    """Serve the main webapp"""
    return render_template('index.html')

@app.route('/api/share', methods=['POST'])
def track_share():
    """Track user shares"""
    global daily_shares
    data = request.json
    user_id = data.get('user_id')
    
    if user_id:
        if user_id not in user_data:
            user_data[user_id] = {'shares': 0, 'joined': False}
        
        user_data[user_id]['shares'] += 1
        daily_shares += 1
        
        # Schedule notification to admin
        if ADMIN_ID and bot_application:
            try:
                asyncio.create_task(notify_admin_share(user_id))
            except:
                logger.error("Failed to schedule admin notification")
    
    return jsonify({'status': 'success', 'shares': user_data.get(user_id, {}).get('shares', 0)})

@app.route('/api/stats', methods=['GET'])
def get_stats():
    """Get current stats"""
    return jsonify({
        'total_users': total_users,
        'daily_shares': daily_shares,
        'active_users': len(user_data)
    })

async def notify_admin_share(user_id):
    """Notify admin about new share"""
    if not ADMIN_ID or not bot_application:
        return
    
    try:
        await bot_application.bot.send_message(
            chat_id=ADMIN_ID,
            text=f"🔥 Bagong Share!\n\n👤 User ID: {user_id}\n📊 Total Shares ngayon: {daily_shares}\n⏰ Oras: {datetime.now().strftime('%H:%M:%S')}"
        )
    except Exception as e:
        logger.error(f"Error notifying admin: {e}")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Start command handler"""
    global total_users
    user = update.effective_user
    user_id = user.id
    
    # Track new user
    if user_id not in user_data:
        total_users += 1
        user_data[user_id] = {'shares': 0, 'joined': False}
    
    # Create webapp button
    webapp_button = InlineKeyboardButton(
        text="🔴 Manood ng LIVE TikTok VIP",
        web_app=WebAppInfo(url=f"{WEBAPP_URL}")
    )
    
    # Create other buttons
    keyboard = [
        [webapp_button],
        [
            InlineKeyboardButton("📱 Paano Mag-share?", callback_data="how_to_share"),
            InlineKeyboardButton("💎 VIP Benefits", callback_data="vip_benefits")
        ],
        [
            InlineKeyboardButton("👥 Join Group", url="https://t.me/+i7hIT6gq23s3ZmU1"),
            InlineKeyboardButton("📊 Stats", callback_data="stats")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    welcome_message = f"""
🎉 **Kumusta {user.first_name}!** 

Maligayang pagdating sa **TikTok VIP Bot**! 🔥

🌟 **Ano ang makakakuha mo:**
• Access sa exclusive TikTok VIP content
• Live streaming ng mga sikat na Pinay creators
• Premium features at walang ads!

📱 **Paano mag-start:**
1. I-click ang "Manood ng LIVE" button
2. Mag-share sa 3 Telegram groups
3. Automatic access sa VIP content!

✨ Mga benefits ng VIP membership:
• Unlimited viewing
• HD quality streams  
• Exclusive content
• Priority support

👆 **I-click ang button sa baba para magsimula!**
"""
    
    await update.message.reply_text(
        welcome_message, 
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )
    
    # Notify admin about new user
    if ADMIN_ID:
        try:
            await context.bot.send_message(
                chat_id=ADMIN_ID,
                text=f"👋 Bagong User!\n\n👤 Pangalan: {user.first_name} {user.last_name or ''}\n🆔 User ID: {user_id}\n📱 Username: @{user.username or 'Walang username'}\n⏰ Sumali: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            )
        except Exception as e:
            logger.error(f"Error notifying admin about new user: {e}")

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle button callbacks"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    data = query.data
    
    if data == "how_to_share":
        message = """
📱 **Paano Mag-share sa Telegram Groups?**

**Hakbang 1:** I-click ang "SHARE NOW" button sa webapp
**Hakbang 2:** Pipili ka ng 3 Telegram groups na sasalihan mo
**Hakbang 3:** I-send ang link sa bawat group
**Hakbang 4:** Babalik ka sa webapp at makikita mo ang progress
**Hakbang 5:** Pagkatapos ng 3 shares, automatic access na sa VIP!

💡 **Tips:**
• Hanapin ang mga active Filipino Telegram groups
• I-share sa mga groups na interested sa TikTok content
• Huwag mag-spam sa iisang group

🔥 Ready na? I-click ang "Manood ng LIVE" button!
"""
        await query.edit_message_text(message, parse_mode='Markdown')
    
    elif data == "vip_benefits":
        message = """
💎 **TikTok VIP Benefits**

🎯 **Exclusive Content:**
• Premium Pinay TikTok videos
• Live streaming events
• Behind-the-scenes content

📱 **App Features:**
• HD quality playback
• No advertisements
• Offline download option
• Priority customer support

🌟 **Community Access:**
• VIP-only Telegram group
• Direct chat with creators
• Early access to new content
• Special contests and giveaways

⭐ **Bonus Features:**
• Daily new content updates
• Request specific content
• VIP badge sa profile
• Monthly exclusive events

🚀 Mag-share na para ma-unlock lahat ng benefits!
"""
        await query.edit_message_text(message, parse_mode='Markdown')
    
    elif data == "stats":
        user_shares = user_data.get(user_id, {}).get('shares', 0)
        message = f"""
📊 **Bot Statistics**

👤 **Your Progress:**
• Shares: {user_shares}/3
• Status: {'✅ VIP Member' if user_shares >= 3 else '⏳ Pending'}

🌐 **Overall Stats:**
• Total Users: {total_users}
• Today's Shares: {daily_shares}
• Active Users: {len(user_data)}

{'🎉 Congratulations! VIP access unlocked!' if user_shares >= 3 else '💪 Mag-share pa para sa VIP access!'}
"""
        await query.edit_message_text(message, parse_mode='Markdown')
    
    # Add back to main menu button
    back_button = InlineKeyboardButton("🔙 Balik sa Menu", callback_data="back_to_menu")
    reply_markup = InlineKeyboardMarkup([[back_button]])
    
    try:
        await query.edit_message_reply_markup(reply_markup=reply_markup)
    except:
        pass

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Help command"""
    help_text = """
🆘 **TikTok VIP Bot - Tulong**

**Mga Available Commands:**
• /start - Simulan ang bot
• /help - Ipakita ang tulong
• /stats - Tingnan ang inyong progress

**Paano Gamitin:**
1. I-type ang /start
2. I-click ang "Manood ng LIVE" 
3. Mag-share sa 3 groups
4. Enjoy VIP access!

**May Problema?**
• Siguruhing connected kayo sa internet
• I-refresh ang webapp kung hindi gumagana
• I-restart ang bot gamit ang /start

**Admin Contact:** @ldentifyAphrodite (kung may emergency)

🔥 Happy watching sa TikTok VIP content!
"""
    await update.message.reply_text(help_text, parse_mode='Markdown')

def run_bot():
    """Run the Telegram bot in a separate thread"""
    global bot_application
    
    if not BOT_TOKEN:
        logger.error("BOT_API environment variable not set!")
        return
    
    try:
        # Create application
        bot_application = Application.builder().token(BOT_TOKEN).build()
        
        # Add handlers
        bot_application.add_handler(CommandHandler("start", start))
        bot_application.add_handler(CommandHandler("help", help_command))
        bot_application.add_handler(CallbackQueryHandler(button_callback))
        
        logger.info("Starting Telegram bot...")
        # Start the bot
        bot_application.run_polling(drop_pending_updates=True)
        
    except Exception as e:
        logger.error(f"Error starting bot: {e}")

def start_bot_thread():
    """Start bot in a separate thread"""
    bot_thread = threading.Thread(target=run_bot, daemon=True)
    bot_thread.start()
    logger.info("Bot thread started")

# Start bot when module is imported
if BOT_TOKEN:
    start_bot_thread()
else:
    logger.warning("BOT_TOKEN not found, bot will not start")

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    logger.info(f"Starting Flask app on port {port}")
    app.run(host='0.0.0.0', port=port, debug=False)
