import os
import logging
from flask import Flask, render_template, request, jsonify
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
import asyncio
from datetime import datetime, date
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
WEBAPP_URL = os.getenv('WEBAPP_URL', 'https://tgreward.shop/tiktokbot.php')

# Flask app for webapp
app = Flask(__name__)

# Global variables for tracking - Enhanced with fake initial stats
user_data = {}
# Initial fake stats - these will increment as real users join
INITIAL_VERIFIED_USERS = 1000
INITIAL_VIP_USERS = 500
INITIAL_ACTIVE_USERS = 800

total_users = 0
daily_shares = 0
share_history = []  # Track share history
today_shares = []   # Track today's shares specifically
last_reset_date = None  # Track when we last reset daily stats

# Global bot application
bot_application = None

# File to save data persistently
DATA_FILE = 'bot_data.json'

def load_data():
    """Load data from file"""
    global user_data, total_users, daily_shares, share_history, today_shares, last_reset_date
    try:
        if os.path.exists(DATA_FILE):
            with open(DATA_FILE, 'r') as f:
                data = json.load(f)
                user_data = data.get('user_data', {})
                total_users = data.get('total_users', 0)
                daily_shares = data.get('daily_shares', 0)
                share_history = data.get('share_history', [])
                today_shares = data.get('today_shares', [])
                last_reset_date = data.get('last_reset_date', None)
                
                # Reset daily stats if it's a new day
                reset_daily_stats_if_needed()
                
                logger.info(f"Data loaded: {total_users} users, {daily_shares} shares")
    except Exception as e:
        logger.error(f"Error loading data: {e}")

def reset_daily_stats_if_needed():
    """Reset daily stats if it's a new day"""
    global daily_shares, today_shares, last_reset_date
    
    current_date = date.today().isoformat()
    
    if last_reset_date != current_date:
        daily_shares = 0
        today_shares = []
        last_reset_date = current_date
        save_data()
        logger.info(f"Daily stats reset for new day: {current_date}")

def save_data():
    """Save data to file"""
    try:
        data = {
            'user_data': user_data,
            'total_users': total_users,
            'daily_shares': daily_shares,
            'share_history': share_history,
            'today_shares': today_shares,
            'last_reset_date': last_reset_date
        }
        with open(DATA_FILE, 'w') as f:
            json.dump(data, f, indent=2)
        logger.info("Data saved successfully")
    except Exception as e:
        logger.error(f"Error saving data: {e}")

def get_display_stats():
    """Get stats with fake initial numbers added"""
    real_users = len(user_data)
    real_vip_users = len([u for u in user_data.values() if u.get('shares', 0) >= 3])
    
    return {
        'verified_users': INITIAL_VERIFIED_USERS + total_users,
        'vip_users': INITIAL_VIP_USERS + real_vip_users,
        'active_users': INITIAL_ACTIVE_USERS + real_users,
        'total_users': total_users,
        'daily_shares': daily_shares,
        'real_users': real_users,
        'real_vip_users': real_vip_users
    }

@app.route('/')
def webapp():
    """Serve the main webapp"""
    return render_template('index.html')

@app.route('/api/share', methods=['POST'])
def track_share():
    """Track user shares - Enhanced with today's shares tracking"""
    global daily_shares
    data = request.json
    user_id = str(data.get('user_id'))  # Convert to string for consistency
    
    # Reset daily stats if needed
    reset_daily_stats_if_needed()
    
    if user_id:
        # Initialize user data if not exists
        if user_id not in user_data:
            user_data[user_id] = {
                'shares': 0, 
                'joined': False,
                'first_name': data.get('first_name', 'Unknown'),
                'username': data.get('username', ''),
                'join_date': datetime.now().isoformat()
            }
        
        # Increment shares
        user_data[user_id]['shares'] += 1
        daily_shares += 1
        
        # Add to share history
        share_entry = {
            'user_id': user_id,
            'first_name': user_data[user_id]['first_name'],
            'username': user_data[user_id]['username'],
            'timestamp': datetime.now().isoformat(),
            'total_shares': user_data[user_id]['shares'],
            'date': date.today().isoformat()
        }
        share_history.append(share_entry)
        today_shares.append(share_entry)
        
        # Keep only last 100 shares in history to avoid too much data
        if len(share_history) > 100:
            share_history = share_history[-100:]
        
        # Save data
        save_data()
        
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
    
    current_shares = user_data.get(user_id, {}).get('shares', 0)
    return jsonify({
        'status': 'success', 
        'shares': current_shares,
        'vip_status': current_shares >= 3
    })

@app.route('/api/stats', methods=['GET'])
def get_stats():
    """Get current stats with fake numbers"""
    reset_daily_stats_if_needed()
    stats = get_display_stats()
    
    return jsonify({
        'verified_users': stats['verified_users'],
        'vip_users': stats['vip_users'], 
        'active_users': stats['active_users'],
        'daily_shares': stats['daily_shares'],
        'total_users': stats['total_users']
    })

@app.route('/api/recent_shares', methods=['GET'])
def get_recent_shares():
    """Get recent shares for admin"""
    reset_daily_stats_if_needed()
    # Return last 20 shares
    recent = share_history[-20:] if len(share_history) > 20 else share_history
    return jsonify({'shares': recent})

@app.route('/api/today_shares', methods=['GET'])
def get_today_shares():
    """Get today's shares specifically"""
    reset_daily_stats_if_needed()
    return jsonify({
        'shares': today_shares,
        'count': len(today_shares),
        'date': date.today().isoformat()
    })

@app.route('/health')
def health_check():
    reset_daily_stats_if_needed()
    stats = get_display_stats()
    return jsonify({
        'status': 'healthy',
        'bot_running': bot_application is not None,
        'verified_users': stats['verified_users'],
        'vip_users': stats['vip_users'],
        'active_users': stats['active_users'],
        'daily_shares': stats['daily_shares']
    })

async def notify_admin_share(user_id):
    """Notify admin about new share - Enhanced"""
    if not ADMIN_ID or not bot_application:
        return
    
    try:
        user_info = user_data.get(user_id, {})
        user_shares = user_info.get('shares', 0)
        first_name = user_info.get('first_name', 'Unknown')
        username = user_info.get('username', '')
        
        status = "🎉 VIP UNLOCKED!" if user_shares >= 3 else f"📊 Progress: {user_shares}/3"
        
        await bot_application.bot.send_message(
            chat_id=ADMIN_ID,
            text=f"🔥 Bagong Share!\n\n👤 User: {first_name}\n🆔 ID: {user_id}\n📱 Username: @{username if username else 'Walang username'}\n📊 Total Shares: {user_shares}\n{status}\n⏰ Oras: {datetime.now().strftime('%H:%M:%S')}\n📅 Today's Total: {len(today_shares)}"
        )
    except Exception as e:
        logger.error(f"Error notifying admin: {e}")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Start command handler - Enhanced"""
    global total_users
    
    try:
        user = update.effective_user
        user_id = str(user.id)
        
        logger.info(f"Start command received from user {user_id}")
        
        # Reset daily stats if needed
        reset_daily_stats_if_needed()
        
        # Track new user
        if user_id not in user_data:
            total_users += 1
            user_data[user_id] = {
                'shares': 0, 
                'joined': True,
                'first_name': user.first_name or 'Unknown',
                'last_name': user.last_name or '',
                'username': user.username or '',
                'join_date': datetime.now().isoformat()
            }
            save_data()  # Save data after new user
            logger.info(f"New user registered: {user_id}")
        
        # Create webapp button
        webapp_button = InlineKeyboardButton(
            text="🔴 Manood ng LIVE TikTok VIP",
            web_app=WebAppInfo(url=f"{WEBAPP_URL}")
        )
        
        # Create VIP button - NEW
        vip_button = InlineKeyboardButton(
            text="💎 Kumuha ng VIP Access",
            url="https://t.me/LapaganXMennuBot"
        )
        
        # Create other buttons
        keyboard = [
            [webapp_button],
            [vip_button],  # Added VIP button
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

📱 **Dalawang paraan para mag-VIP:**

**Option 1: FREE (Share Method)**
1. I-click ang "Manood ng LIVE" button
2. Mag-share sa 3 Telegram groups
3. Automatic VIP access!

**Option 2: INSTANT VIP**
• I-click ang "💎 Kumuha ng VIP Access"
• Direct VIP access kaagad!

✨ Mga benefits ng VIP membership:
• Unlimited viewing
• HD quality streams  
• Exclusive content
• Priority support

👆 **Pumili ng method sa baba!**
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
                stats = get_display_stats()
                await context.bot.send_message(
                    chat_id=ADMIN_ID,
                    text=f"👋 Bagong User!\n\n👤 Pangalan: {user.first_name} {user.last_name or ''}\n🆔 User ID: {user_id}\n📱 Username: @{user.username or 'Walang username'}\n⏰ Sumali: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n📊 Updated Stats:\n👥 Verified Users: {stats['verified_users']:,}\n💎 VIP Users: {stats['vip_users']:,}\n🔥 Active Users: {stats['active_users']:,}"
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
    """Handle button callbacks - Enhanced"""
    try:
        query = update.callback_query
        await query.answer()
        
        user_id = str(query.from_user.id)
        data = query.data
        
        logger.info(f"Button callback: {data} from user {user_id}")
        
        # Reset daily stats if needed
        reset_daily_stats_if_needed()
        
        if data == "how_to_share":
            message = """
📱 **Paano Mag-share sa Telegram Groups?**

**Hakbang 1:** I-click ang "🔴 Manood ng LIVE" button sa taas
**Hakbang 2:** Sa webapp, i-click ang "SHARE NOW" button
**Hakbang 3:** Pipili ka ng 3 Telegram groups na sasalihan mo
**Hakbang 4:** I-send ang link sa bawat group
**Hakbang 5:** Babalik ka sa webapp at makikita mo ang progress
**Hakbang 6:** Pagkatapos ng 3 shares, automatic VIP access na!

💡 **Tips:**
• Hanapin ang mga active Filipino Telegram groups
• I-share sa mga groups na interested sa TikTok content
• Huwag mag-spam sa iisang group

🚀 **Alternative:** I-click ang "💎 Kumuha ng VIP Access" para sa instant VIP!

🔥 Ready na? Pumili ng method sa main menu!
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

🚀 **Dalawang paraan para makakuha:**
• FREE: Mag-share sa 3 groups
• INSTANT: I-click ang "💎 Kumuha ng VIP Access"
"""
            await query.edit_message_text(message, parse_mode='Markdown')
        
        elif data == "stats":
            user_shares = user_data.get(user_id, {}).get('shares', 0)
            stats = get_display_stats()
            
            # Recent sharers list (today's shares)
            recent_sharers = []
            for share in today_shares[-10:]:  # Last 10 shares from today
                name = share.get('first_name', 'Unknown')
                shares = share.get('total_shares', 0)
                time_str = datetime.fromisoformat(share.get('timestamp', '')).strftime('%H:%M') if share.get('timestamp') else ''
                recent_sharers.append(f"• {name} ({shares} shares) - {time_str}")
            
            recent_text = "\n".join(recent_sharers) if recent_sharers else "Walang shares pa ngayong araw"
            
            message = f"""
📊 **Bot Statistics**

👤 **Your Progress:**
• Shares: {user_shares}/3
• Status: {'✅ VIP Member' if user_shares >= 3 else '⏳ Pending'}

🌐 **Global Stats:**
• 🔐 Verified Users: {stats['verified_users']:,}
• 💎 VIP Members: {stats['vip_users']:,}
• 🔥 Active Users: {stats['active_users']:,}
• 📅 Today's Shares: {stats['daily_shares']}

📋 **Today's Recent Sharers:**
{recent_text}

{'🎉 Congratulations! VIP access unlocked!' if user_shares >= 3 else '💪 Mag-share pa para sa VIP access!'}
"""
            await query.edit_message_text(message, parse_mode='Markdown')
        
        elif data == "back_to_menu":
            # Recreate the main menu
            webapp_button = InlineKeyboardButton(
                text="🔴 Manood ng LIVE TikTok VIP",
                web_app=WebAppInfo(url=f"{WEBAPP_URL}")
            )
            
            vip_button = InlineKeyboardButton(
                text="💎 Kumuha ng VIP Access",
                url="https://t.me/LapaganXMennuBot"
            )
            
            keyboard = [
                [webapp_button],
                [vip_button],
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

📱 **Dalawang paraan para mag-VIP:**

**Option 1: FREE (Share Method)**
1. I-click ang "Manood ng LIVE" button
2. Mag-share sa 3 Telegram groups
3. Automatic VIP access!

**Option 2: INSTANT VIP**
• I-click ang "💎 Kumuha ng VIP Access"
• Direct VIP access kaagad!

✨ Mga benefits ng VIP membership:
• Unlimited viewing
• HD quality streams  
• Exclusive content
• Priority support

👆 **Pumili ng method sa baba!**
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
2. Pumili ng method:
   - FREE: I-click "Manood ng LIVE" at mag-share
   - INSTANT: I-click "Kumuha ng VIP Access"
3. Enjoy VIP access!

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
    """Stats command - Enhanced with fake numbers"""
    try:
        user_id = str(update.effective_user.id)
        user_shares = user_data.get(user_id, {}).get('shares', 0)
        
        # Reset daily stats if needed
        reset_daily_stats_if_needed()
        stats = get_display_stats()
        
        # Recent sharers list (today's shares)
        recent_sharers = []
        for share in today_shares[-10:]:  # Last 10 shares from today
            name = share.get('first_name', 'Unknown')
            shares = share.get('total_shares', 0)
            time_str = datetime.fromisoformat(share.get('timestamp', '')).strftime('%H:%M') if share.get('timestamp') else ''
            recent_sharers.append(f"• {name} ({shares} shares) - {time_str}")
        
        recent_text = "\n".join(recent_sharers) if recent_sharers else "Walang shares pa ngayong araw"
        
        message = f"""
📊 **Bot Statistics**

👤 **Your Progress:**
• Shares: {user_shares}/3
• Status: {'✅ VIP Member' if user_shares >= 3 else '⏳ Pending'}

🌐 **Global Stats:**
• 🔐 Verified Users: {stats['verified_users']:,}
• 💎 VIP Members: {stats['vip_users']:,}
• 🔥 Active Users: {stats['active_users']:,}
• 📅 Today's Shares: {stats['daily_shares']}

📋 **Today's Recent Sharers:**
{recent_text}

{'🎉 Congratulations! VIP access unlocked!' if user_shares >= 3 else '💪 Mag-share pa para sa VIP access o kaya i-click ang VIP button!'}
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
    
    # Load saved data
    load_data()
    
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
                save_data()  # Save data before shutdown
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
        save_data()  # Save data on exit
    except Exception as e:
        logger.error(f"Bot error: {e}")
        save_data()  # Save data on error

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
