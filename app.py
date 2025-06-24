import os
import logging
from flask import Flask, render_template, request, jsonify
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
import asyncio
from datetime import datetime
import json
import threading
from concurrent.futures import ThreadPoolExecutor
import signal
import sys

# Setup logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', 
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Environment variables
BOT_TOKEN = os.getenv('BOT_API')
ADMIN_ID = int(os.getenv('ADMIN_ID', '0')) if os.getenv('ADMIN_ID') else None
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
                # Use asyncio to run the coroutine in the background
                loop = asyncio.new_event_loop()
                threading.Thread(
                    target=lambda: loop.run_until_complete(notify_admin_share(user_id)),
                    daemon=True
                ).start()
            except Exception as e:
                logger.error(f"Failed to schedule admin notification: {e}")
    
    return jsonify({'status': 'success', 'shares': user_data.get(user_id, {}).get('shares', 0)})

@app.route('/api/stats', methods=['GET'])
def get_stats():
    """Get current stats"""
    return jsonify({
        'total_users': total_users,
        'daily_shares': daily_shares,
        'active_users': len(user_data)
    })

@app.route('/health')
def health_check():
    return jsonify({
        'status': 'healthy',
        'bot_running': bot_application is not None,
        'total_users': total_users,
        'daily_shares': daily_shares
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
    
    try:
        user = update.effective_user
        user_id = user.id
        
        logger.info(f"Start command received from user {user_id}")
        
        # Track new user
        if user_id not in user_data:
            total_users += 1
            user_data[user_id] = {'shares': 0, 'joined': False}
            logger.info(f"New user registered: {user_id}")
        
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
        
        logger.info(f"Welcome message sent to user {user_id}")
        
        # Notify admin about new user
        if ADMIN_ID:
            try:
                await context.bot.send_message(
                    chat_id=ADMIN_ID,
                    text=f"👋 Bagong User!\n\n👤 Pangalan: {user.first_name} {user.last_name or ''}\n🆔 User ID: {user_id}\n📱 Username: @{user.username or 'Walang username'}\n⏰ Sumali: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                )
                logger.info(f"Admin notified about new user {user_id}")
            except Exception as e:
                logger.error(f"Error notifying admin about new user: {e}")
                
    except Exception as e:
        logger.error(f"Error in start command: {e}")
        try:
            await update.message.reply_text("❌ May error sa bot. Subukan ulit mamaya.")
        except:
            pass

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle button callbacks"""
    try:
        query = update.callback_query
        await query.answer()
        
        user_id = query.from_user.id
        data = query.data
        
        logger.info(f"Button callback: {data} from user {user_id}")
        
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
        
        elif data == "back_to_menu":
            # Recreate the main menu
            webapp_button = InlineKeyboardButton(
                text="🔴 Manood ng LIVE TikTok VIP",
                web_app=WebAppInfo(url=f"{WEBAPP_URL}")
            )
            
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
🎉 **Kumusta {query.from_user.first_name}!** 

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
            await query.edit_message_text(welcome_message, reply_markup=reply_markup, parse_mode='Markdown')
            return
        
        # Add back to main menu button for other callbacks
        back_button = InlineKeyboardButton("🔙 Balik sa Menu", callback_data="back_to_menu")
        reply_markup = InlineKeyboardMarkup([[back_button]])
        
        try:
            await query.edit_message_reply_markup(reply_markup=reply_markup)
        except Exception as e:
            logger.error(f"Error editing message markup: {e}")
            
    except Exception as e:
        logger.error(f"Error in button callback: {e}")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Help command"""
    try:
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
        logger.info(f"Help command sent to user {update.effective_user.id}")
    except Exception as e:
        logger.error(f"Error in help command: {e}")

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Stats command"""
    try:
        user_id = update.effective_user.id
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
        await update.message.reply_text(message, parse_mode='Markdown')
        logger.info(f"Stats command sent to user {user_id}")
    except Exception as e:
        logger.error(f"Error in stats command: {e}")

async def main():
    """Main function to run the bot"""
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
        bot_application.add_handler(CommandHandler("stats", stats_command))
        bot_application.add_handler(CallbackQueryHandler(button_callback))
        
        logger.info("Starting Telegram bot...")
        
        # Initialize and start the bot
        await bot_application.initialize()
        await bot_application.start()
        
        # Start polling in the background
        await bot_application.updater.start_polling(drop_pending_updates=True)
        
        logger.info("Bot is running successfully!")
        
        # Keep the bot running
        while True:
            await asyncio.sleep(1)
            
    except Exception as e:
        logger.error(f"Error in bot main: {e}")
    finally:
        if bot_application:
            try:
                await bot_application.stop()
                await bot_application.shutdown()
            except:
                pass

def run_flask():
    """Run Flask app"""
    port = int(os.environ.get('PORT', 8080))
    logger.info(f"Starting Flask app on port {port}")
    app.run(host='0.0.0.0', port=port, debug=False, threaded=True, use_reloader=False)

def run_bot_async():
    """Run bot in async mode"""
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Bot error: {e}")

if __name__ == '__main__':
    if not BOT_TOKEN:
        logger.error("BOT_TOKEN is required!")
        sys.exit(1)
    
    # Start Flask in a separate thread
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    logger.info("Flask thread started")
    
    # Run bot in main thread (required for signal handling)
    logger.info("Starting bot in main thread...")
    run_bot_async()
