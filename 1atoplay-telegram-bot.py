import sqlite3
import uuid
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters
import os
import warnings
import logging

# Enable logging for debugging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Suppress ALL warnings
warnings.filterwarnings("ignore")

# Get token from environment variable
TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN', '8505602493:AAF8fznj0OA3OqVstBDt-Zn9MkQ8DjPh5vw')
ADMIN_IDS = [5911406948, 5510368247]  # Initial admins - 5911406948 is super admin

# Make prices editable
PRODUCT_PRICES = {
    '3d': 280,
    '10d': 560,
    '30d': 1250
}

PAYMENT_METHODS = {
    'easypaisa': {'name': 'Easypaisa', 'number': '03431178575'},
    'binance': {'name': 'Binance', 'number': '335277914'},
    'upi': {'name': 'UPI', 'number': 'trustedprem9719472@ybl', 'qr_code': None}
}

def get_products():
    """Get products with current prices"""
    return {
        'product_3d': {'name': '3-Day Key', 'price': PRODUCT_PRICES['3d'], 'days': 3},
        'product_10d': {'name': '10-Day Key', 'price': PRODUCT_PRICES['10d'], 'days': 10},
        'product_30d': {'name': '30-Day Key', 'price': PRODUCT_PRICES['30d'], 'days': 30}
    }

def init_db():
    conn = sqlite3.connect('atoplay_bot.db')
    cursor = conn.cursor()
    
    # USERS table with ALL columns
    cursor.execute('''CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY AUTOINCREMENT,
        telegram_id INTEGER UNIQUE,
        username TEXT,
        balance REAL DEFAULT 0,
        unique_id TEXT UNIQUE,
        is_blocked INTEGER DEFAULT 0,
        blocked_reason TEXT,
        blocked_at TIMESTAMP,
        is_admin INTEGER DEFAULT 0,
        added_by INTEGER
    )''')
    
    cursor.execute('''CREATE TABLE IF NOT EXISTS transactions (
        transaction_id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        amount REAL,
        payment_method TEXT,
        screenshot TEXT,
        status TEXT DEFAULT 'pending',
        admin_id INTEGER,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    
    cursor.execute('''CREATE TABLE IF NOT EXISTS keys_stock (
        key_id INTEGER PRIMARY KEY AUTOINCREMENT,
        key_value TEXT UNIQUE,
        key_type TEXT,  -- '3d', '10d', '30d'
        status TEXT DEFAULT 'available',  -- 'available', 'used'
        used_by INTEGER,
        used_at TIMESTAMP,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    
    cursor.execute('''CREATE TABLE IF NOT EXISTS user_keys (
        user_key_id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        key_value TEXT,
        key_type TEXT,
        purchased_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        status TEXT DEFAULT 'active'  -- 'active', 'expired'
    )''')
    
    cursor.execute('''CREATE TABLE IF NOT EXISTS admin_logs (
        log_id INTEGER PRIMARY KEY AUTOINCREMENT,
        admin_id INTEGER,
        action TEXT,
        target_user_id INTEGER,
        details TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    
    cursor.execute('''CREATE TABLE IF NOT EXISTS settings (
        setting_id INTEGER PRIMARY KEY AUTOINCREMENT,
        setting_key TEXT UNIQUE,
        setting_value TEXT,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    
    # Add initial super admin (5911406948)
    cursor.execute('''INSERT OR IGNORE INTO users 
                      (telegram_id, username, is_admin) 
                      VALUES (?, 'Super Admin', 1)''', (5911406948,))
    
    # Add other initial admin
    cursor.execute('''INSERT OR IGNORE INTO users 
                      (telegram_id, username, is_admin) 
                      VALUES (?, 'Admin', 1)''', (5510368247,))
    
    conn.commit()
    conn.close()
    print("✅ Database tables created successfully with ALL columns!")
    print("✅ Super Admin (5911406948) added!")
    print("✅ Admin (5510368247) added!")

def add_sample_keys():
    """Add real keys provided by user - ONLY REAL KEYS"""
    conn = sqlite3.connect('atoplay_bot.db')
    cursor = conn.cursor()
    
    # ONLY REAL KEYS FROM USER'S MESSAGES
    real_keys = {
        '3d': [
            'EZwXVP',  # 3-day key
            'ZyQiee',  # 3-day key
            'KuU4fy',  # 3-day key
            'ZKyyPO'   # 3-day key
        ],
        '10d': [
            'UbhtLb',  # 10-day key
            'FIrCnj',  # 10-day key  
            'PsXM5W'   # 10-day key
        ],
        '30d': [
            # 30-day keys (none provided by user)
        ]
    }
    
    for key_type, keys in real_keys.items():
        for key_value in keys:
            cursor.execute('''INSERT OR IGNORE INTO keys_stock (key_value, key_type) 
                              VALUES (?, ?)''', (key_value, key_type))
    
    conn.commit()
    conn.close()
    print("✅ ONLY REAL KEYS ADDED (EXACTLY AS PROVIDED)!")

def get_stock_info():
    """Get current stock information"""
    conn = sqlite3.connect('atoplay_bot.db')
    cursor = conn.cursor()
    
    cursor.execute('''SELECT key_type, 
                             SUM(CASE WHEN status = 'available' THEN 1 ELSE 0 END) as available
                      FROM keys_stock 
                      GROUP BY key_type''')
    
    stock_data = cursor.fetchall()
    conn.close()
    
    stock_info = {}
    for key_type, available in stock_data:
        stock_info[key_type] = available
    
    return stock_info

def is_admin(user_id):
    """Check if user is admin"""
    conn = sqlite3.connect('atoplay_bot.db')
    cursor = conn.cursor()
    
    cursor.execute('SELECT is_admin FROM users WHERE telegram_id = ?', (user_id,))
    result = cursor.fetchone()
    conn.close()
    
    return result and result[0] == 1

def is_super_admin(user_id):
    """Check if user is super admin (5911406948)"""
    return user_id == 5911406948

def get_all_admins():
    """Get all admin users"""
    conn = sqlite3.connect('atoplay_bot.db')
    cursor = conn.cursor()
    
    cursor.execute('''SELECT telegram_id, username, is_admin 
                      FROM users WHERE is_admin = 1''')
    admins = cursor.fetchall()
    conn.close()
    
    return admins

def log_admin_action(admin_id, action, target_user_id, details=""):
    """Log admin actions"""
    conn = sqlite3.connect('atoplay_bot.db')
    cursor = conn.cursor()
    
    cursor.execute('''INSERT INTO admin_logs (admin_id, action, target_user_id, details) 
                      VALUES (?, ?, ?, ?)''',
                   (admin_id, action, target_user_id, details))
    
    conn.commit()
    conn.close()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info(f"Start command received from user: {update.effective_user.id}")
    
    try:
        user = update.effective_user
        user_id = user.id
        
        conn = sqlite3.connect('atoplay_bot.db')
        cursor = conn.cursor()
        
        cursor.execute('SELECT balance, unique_id, is_blocked, is_admin FROM users WHERE telegram_id = ?', (user_id,))
        user_data = cursor.fetchone()
        
        # Check if user is blocked
        if user_data and user_data[2] == 1:
            await update.message.reply_text("❌ You are blocked from using this bot!")
            conn.close()
            return
        
        if not user_data:
            unique_id = str(uuid.uuid4())[:8].upper()
            is_admin_user = 1 if user_id in ADMIN_IDS else 0
            cursor.execute('INSERT INTO users (telegram_id, username, unique_id, balance, is_blocked, is_admin) VALUES (?, ?, ?, ?, 0, ?)', 
                          (user_id, user.username, unique_id, 0, is_admin_user))
            conn.commit()
            
            welcome_text = f"""👋 Welcome to Atoplay Shop!

🆔 Your Unique ID: {unique_id}
💳 Balance: ₹0

📞 Contact: @Aarifseller
📢 Channel: @SnakeEngine105

Use /buy to purchase keys!
Use /mykeys to see your purchased keys!"""
        else:
            balance, unique_id, is_blocked, is_admin_user = user_data
            
            welcome_text = f"""👋 Welcome back {user.first_name}!

🆔 Your Unique ID: {unique_id}
💳 Balance: ₹{balance}

📞 Contact: @Aarifseller
📢 Channel: @SnakeEngine105

Use /buy to purchase keys!
Use /balance to check your balance!
Use /mykeys to see your purchased keys!"""
        
        conn.close()
        
        # Different keyboard for admin vs regular user
        if is_admin(user_id):
            keyboard = [
                [KeyboardButton("🛒 Buy Keys"), KeyboardButton("🔧 Admin Panel")],
                [KeyboardButton("💳 Check Balance"), KeyboardButton("🔑 My Keys")],
                [KeyboardButton("📞 Contact"), KeyboardButton("📢 Channel")]
            ]
        else:
            keyboard = [
                [KeyboardButton("🛒 Buy Keys")],
                [KeyboardButton("💳 Check Balance"), KeyboardButton("🔑 My Keys")],
                [KeyboardButton("📞 Contact"), KeyboardButton("📢 Channel")]
            ]
        
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        
        await update.message.reply_text(welcome_text, reply_markup=reply_markup)
        logger.info(f"Welcome message sent to user: {user_id}")
        
    except Exception as e:
        logger.error(f"Error in start command: {e}")
        await update.message.reply_text("⚠️ An error occurred. Please try again.")

async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show admin panel"""
    admin_id = update.effective_user.id
    
    if not is_admin(admin_id):
        await update.message.reply_text("❌ Unauthorized!")
        return
    
    # Get stock information
    stock_info = get_stock_info()
    products = get_products()
    
    text = f"""🔧 ADMIN PANEL

📊 Stock Status:
• 3-Day Keys: {stock_info.get('3d', 0)} available - ₹{PRODUCT_PRICES['3d']}
• 10-Day Keys: {stock_info.get('10d', 0)} available - ₹{PRODUCT_PRICES['10d']}
• 30-Day Keys: {stock_info.get('30d', 0)} available - ₹{PRODUCT_PRICES['30d']}

🛠️ KEY MANAGEMENT:
📝 Add Keys:
• /addkey_3d KEY - Add 3-day key
• /addkey_10d KEY - Add 10-day key  
• /addkey_30d KEY - Add 30-day key

🗑️ Delete Key:
• /delkey KEY - Delete any key

💰 PRICE MANAGEMENT:
• /price_3d NEW_PRICE - Change 3-day price
• /price_10d NEW_PRICE - Change 10-day price
• /price_30d NEW_PRICE - Change 30-day price

👤 USER MANAGEMENT:
• /block USER_ID REASON - Block a user
• /unblock USER_ID - Unblock a user
• /userinfo USER_ID - Get user information

🔄 PAYMENT METHODS:
• /setupi NUMBER - Change UPI number
• /setqr - Set UPI QR code (send photo after command)

👑 ADMIN MANAGEMENT (Super Admin Only):
• /addadmin USER_ID - Add new admin
• /removeadmin USER_ID - Remove admin
• /listadmins - List all admins

📊 STOCK CHECK:
• /stock - Show all keys
• /stats - Show statistics

📋 Examples:
• /addkey_3d ABC123
• /delkey XYZ789
• /price_3d 300
• /block 123456 "Spamming"
• /setupi newnumber@upi"""
    
    await update.message.reply_text(text)

async def buy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info(f"Buy command received from user: {update.effective_user.id}")
    
    try:
        user = update.effective_user
        user_id = user.id
        
        # Check if user is blocked
        conn = sqlite3.connect('atoplay_bot.db')
        cursor = conn.cursor()
        cursor.execute('SELECT is_blocked FROM users WHERE telegram_id = ?', (user_id,))
        user_data = cursor.fetchone()
        conn.close()
        
        if user_data and user_data[0] == 1:
            await update.message.reply_text("❌ You are blocked from using this bot!")
            return
        
        if update.callback_query:
            query = update.callback_query
            await query.answer()
            message = query.message
            reply_func = query.edit_message_text
        else:
            message = update.message
            reply_func = message.reply_text
        
        # Get stock information
        stock_info = get_stock_info()
        products = get_products()
        
        keyboard = [
            [
                InlineKeyboardButton(f"3-Day Key - ₹{PRODUCT_PRICES['3d']}", callback_data='product_3d'),
                InlineKeyboardButton(f"10-Day Key - ₹{PRODUCT_PRICES['10d']}", callback_data='product_10d')
            ],
            [
                InlineKeyboardButton(f"30-Day Key - ₹{PRODUCT_PRICES['30d']}", callback_data='product_30d'),
                InlineKeyboardButton("💳 Add Balance", callback_data='add_balance')
            ],
            [
                InlineKeyboardButton("❌ Cancel", callback_data='cancel')
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        # Get UPI QR code if available
        upi_info = PAYMENT_METHODS.get('upi', {})
        upi_qr_info = ""
        if upi_info.get('qr_code'):
            upi_qr_info = "\n📱 UPI QR: Available (Send /setqr to update)"
        
        text = f"""🛒 Select Product:

1. 3-Day Atoplay Key - ₹{PRODUCT_PRICES['3d']}
2. 10-Day Atoplay Key - ₹{PRODUCT_PRICES['10d']}
3. 30-Day Atoplay Key - ₹{PRODUCT_PRICES['30d']}

📦 Current Stock:
• 3-Day Keys: {stock_info.get('3d', 0)} available
• 10-Day Keys: {stock_info.get('10d', 0)} available
• 30-Day Keys: {stock_info.get('30d', 0)} available

💸 Payment Methods:
• Easypaisa: {PAYMENT_METHODS.get('easypaisa', {}).get('number', 'N/A')}
• Binance: {PAYMENT_METHODS.get('binance', {}).get('number', 'N/A')}
• UPI: {upi_info.get('number', 'N/A')}{upi_qr_info}"""
        
        await reply_func(text, reply_markup=reply_markup)
        logger.info(f"Buy menu shown to user: {user_id}")
        
    except Exception as e:
        logger.error(f"Error in buy command: {e}")
        await update.message.reply_text("⚠️ An error occurred. Please try again.")

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        query = update.callback_query
        await query.answer()
        
        user_id = query.from_user.id
        data = query.data
        
        logger.info(f"Callback from user: {user_id}, data: {data}")
        
        # Handle cancel
        if data == 'cancel':
            try:
                await query.edit_message_text("❌ Cancelled!")
            except Exception as e:
                logger.error(f"Error editing message: {e}")
            return
        
        # Handle add balance
        if data == 'add_balance':
            keyboard = [
                [
                    InlineKeyboardButton("₹500", callback_data='amount_500'),
                    InlineKeyboardButton("₹1000", callback_data='amount_1000'),
                    InlineKeyboardButton("₹2000", callback_data='amount_2000')
                ],
                [
                    InlineKeyboardButton("Other Amount", callback_data='amount_other'),
                    InlineKeyboardButton("❌ Cancel", callback_data='cancel')
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            try:
                await query.edit_message_text(
                    "💳 Add Balance\n\nSelect amount or choose 'Other Amount':",
                    reply_markup=reply_markup
                )
            except Exception as e:
                logger.error(f"Error editing message: {e}")
            return
        
        # Handle product selection
        products = get_products()
        if data in products:
            product = products[data]
            context.user_data['selected_product'] = product
            context.user_data['product_id'] = data
            
            conn = sqlite3.connect('atoplay_bot.db')
            cursor = conn.cursor()
            cursor.execute('SELECT balance FROM users WHERE telegram_id = ?', (user_id,))
            result = cursor.fetchone()
            user_balance = result[0] if result else 0
            conn.close()
            
            # Get stock for this specific product
            stock_info = get_stock_info()
            key_type = '3d' if product['days'] == 3 else ('10d' if product['days'] == 10 else '30d')
            available_stock = stock_info.get(key_type, 0)
            
            if available_stock == 0:
                try:
                    await query.edit_message_text(f"""❌ Out of Stock!

{product['name']} is currently out of stock.

📞 Contact @Aarifseller for availability.
Or choose another product.""")
                except Exception as e:
                    logger.error(f"Error editing message: {e}")
                return
            
            if user_balance >= product['price']:
                keyboard = [
                    [
                        InlineKeyboardButton("💳 Use Balance", callback_data='use_balance'),
                        InlineKeyboardButton("💸 New Payment", callback_data='new_payment')
                    ],
                    [InlineKeyboardButton("❌ Cancel", callback_data='cancel')]
                ]
                text = f"""🛒 Product: {product['name']}
💰 Price: ₹{product['price']}
📦 Available: {available_stock} keys

💳 Your Balance: ₹{user_balance}

Choose payment method:"""
            else:
                text = f"""🛒 Product: {product['name']}
💰 Price: ₹{product['price']}
📦 Available: {available_stock} keys

💸 Please select payment method:"""
                keyboard = [
                    [
                        InlineKeyboardButton("Easypaisa", callback_data='payment_easypaisa'),
                        InlineKeyboardButton("Binance", callback_data='payment_binance')
                    ],
                    [
                        InlineKeyboardButton("UPI", callback_data='payment_upi'),
                        InlineKeyboardButton("❌ Cancel", callback_data='cancel')
                    ]
                ]
            
            reply_markup = InlineKeyboardMarkup(keyboard)
            try:
                await query.edit_message_text(text, reply_markup=reply_markup)
            except Exception as e:
                logger.error(f"Error editing message: {e}")
            logger.info(f"Product {product['name']} selected by user: {user_id}")
            return
        
        # Handle payment method selection
        if data.startswith('payment_'):
            payment_method = data.replace('payment_', '')
            
            if payment_method in PAYMENT_METHODS:
                context.user_data['payment_method'] = payment_method
                payment_info = PAYMENT_METHODS[payment_method]
                
                # Set flag to await screenshot
                context.user_data['awaiting_screenshot'] = True
                
                # Check if this is for product purchase
                if 'selected_product' in context.user_data:
                    product = context.user_data.get('selected_product')
                    amount = product['price']
                    purpose = "Product Purchase"
                    
                    text = f"""💳 Payment Details:

🔸 Product: {product['name']}
🔸 Purpose: {purpose}
🔸 Method: {payment_info['name']}
🔸 Number/ID: `{payment_info['number']}`
🔸 Amount: ₹{amount}"""
                    
                    # Add QR code info for UPI
                    if payment_method == 'upi' and payment_info.get('qr_code'):
                        text += f"\n📱 QR Code Available"
                    
                    text += f"""

📋 Instructions:
1. Send ₹{amount} to above {payment_info['name']} number
2. Take a clear screenshot of successful payment
3. Send the screenshot here

⚠️ Make sure screenshot shows:
• Transaction ID/Reference
• Amount
• Date & Time

📸 After payment, send the screenshot now."""
                
                # If adding balance
                elif 'amount' in context.user_data and context.user_data.get('is_adding_balance', False):
                    amount = context.user_data.get('amount')
                    purpose = "Add Balance"
                    
                    text = f"""💳 Payment Details:

🔸 Purpose: {purpose}
🔸 Method: {payment_info['name']}
🔸 Number/ID: `{payment_info['number']}`
🔸 Amount: ₹{amount}"""
                    
                    # Add QR code info for UPI
                    if payment_method == 'upi' and payment_info.get('qr_code'):
                        text += f"\n📱 QR Code Available"
                    
                    text += f"""

📋 Instructions:
1. Send ₹{amount} to above {payment_info['name']} number
2. Take a clear screenshot of successful payment
3. Send the screenshot here

⚠️ Make sure screenshot shows:
• Transaction ID/Reference
• Amount
• Date & Time

📸 After payment, send the screenshot now."""
                
                keyboard = [[InlineKeyboardButton("❌ Cancel", callback_data='cancel')]]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                try:
                    await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
                except Exception as e:
                    logger.error(f"Error editing message: {e}")
                logger.info(f"Payment method {payment_method} selected by user: {user_id}")
            return
        
        # Handle amount selection for balance
        if data.startswith('amount_'):
            if data == 'amount_other':
                try:
                    await query.edit_message_text(
                        "💳 Add Balance\n\nPlease enter the amount you want to add (in INR).\nExample: 750\n\nMinimum: ₹100"
                    )
                except Exception as e:
                    logger.error(f"Error editing message: {e}")
                context.user_data['awaiting_amount'] = True
                return
            
            amount = int(data.replace('amount_', ''))
            context.user_data['amount'] = amount
            context.user_data['is_adding_balance'] = True
            
            keyboard = [
                [
                    InlineKeyboardButton("Easypaisa", callback_data='payment_easypaisa'),
                    InlineKeyboardButton("Binance", callback_data='payment_binance')
                ],
                [
                    InlineKeyboardButton("UPI", callback_data='payment_upi'),
                    InlineKeyboardButton("❌ Cancel", callback_data='cancel')
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            try:
                await query.edit_message_text(
                    f"💳 Add Balance: ₹{amount}\n\nPlease select payment method:",
                    reply_markup=reply_markup
                )
            except Exception as e:
                logger.error(f"Error editing message: {e}")
            return
        
        # Handle use balance
        if data == 'use_balance':
            await process_balance_purchase(update, context)
            return
        
        # Handle new payment
        if data == 'new_payment':
            product = context.user_data.get('selected_product')
            if product:
                context.user_data['amount'] = product['price']
                context.user_data['is_adding_balance'] = False
            
            keyboard = [
                [
                    InlineKeyboardButton("Easypaisa", callback_data='payment_easypaisa'),
                    InlineKeyboardButton("Binance", callback_data='payment_binance')
                ],
                [
                    InlineKeyboardButton("UPI", callback_data='payment_upi'),
                    InlineKeyboardButton("❌ Cancel", callback_data='cancel')
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            try:
                await query.edit_message_text(
                    "💸 Please select payment method:",
                    reply_markup=reply_markup
                )
            except Exception as e:
                logger.error(f"Error editing message: {e}")
            return
            
    except Exception as e:
        logger.error(f"Error in callback handler: {e}")

async def process_balance_purchase(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Process purchase using balance"""
    query = update.callback_query
    user_id = query.from_user.id
    
    if 'selected_product' not in context.user_data:
        try:
            await query.edit_message_text("❌ No product selected!")
        except Exception as e:
            logger.error(f"Error editing message: {e}")
        return
    
    product = context.user_data.get('selected_product')
    
    conn = sqlite3.connect('atoplay_bot.db')
    cursor = conn.cursor()
    
    try:
        # Get user balance and info
        cursor.execute('SELECT user_id, balance, unique_id FROM users WHERE telegram_id = ?', (user_id,))
        user_data = cursor.fetchone()
        
        if not user_data:
            try:
                await query.edit_message_text("❌ User not found!")
            except Exception as e:
                logger.error(f"Error editing message: {e}")
            conn.close()
            return
        
        user_db_id, user_balance, unique_id = user_data
        
        # Check if user has enough balance
        if user_balance < product['price']:
            try:
                await query.edit_message_text(f"""❌ Insufficient Balance!

💰 Price: ₹{product['price']}
💳 Your Balance: ₹{user_balance}

💸 Please add balance or use another payment method.""")
            except Exception as e:
                logger.error(f"Error editing message: {e}")
            conn.close()
            return
        
        # Get stock for this product
        key_type = '3d' if product['days'] == 3 else ('10d' if product['days'] == 10 else '30d')
        cursor.execute('''SELECT key_id, key_value FROM keys_stock 
                          WHERE key_type = ? AND status = 'available' 
                          LIMIT 1''', (key_type,))
        
        key_data = cursor.fetchone()
        
        if not key_data:
            try:
                await query.edit_message_text(f"""❌ Out of Stock!

{product['name']} is currently out of stock.

📞 Contact @Aarifseller for availability.
Or choose another product.""")
            except Exception as e:
                logger.error(f"Error editing message: {e}")
            conn.close()
            return
        
        key_id, key_value = key_data
        
        # Deduct balance
        new_balance = user_balance - product['price']
        cursor.execute('UPDATE users SET balance = ? WHERE user_id = ?',
                       (new_balance, user_db_id))
        
        # Update key status
        cursor.execute('''UPDATE keys_stock 
                          SET status = 'used', used_by = ?, used_at = CURRENT_TIMESTAMP
                          WHERE key_id = ?''',
                       (user_db_id, key_id))
        
        # Add to user_keys table
        cursor.execute('''INSERT INTO user_keys (user_id, key_value, key_type) 
                          VALUES (?, ?, ?)''',
                       (user_db_id, key_value, key_type))
        
        # Create transaction record
        cursor.execute('''INSERT INTO transactions 
                          (user_id, amount, payment_method, status, admin_id) 
                          VALUES (?, ?, 'balance', 'approved', 0)''',
                       (user_db_id, product['price']))
        
        conn.commit()
        
        # Send key to user
        key_message = f"""✅ Purchase Successful!

🎉 Congratulations! Your purchase is complete.

📦 Product: {product['name']}
💰 Price: ₹{product['price']}
💳 New Balance: ₹{new_balance}
🔑 Your Key: `{key_value}`

📋 Instructions:
1. Open Atoplay application
2. Go to settings or activation section
3. Enter the key: {key_value}
4. Enjoy your {product['days']} days subscription!

⚠️ Important:
• This key is for ONE-TIME use only
• Do not share with anyone
• Key will expire after {product['days']} days

📞 Contact @Aarifseller for any issues.
📢 Join: @SnakeEngine105"""
        
        try:
            await query.edit_message_text(key_message, parse_mode='Markdown')
        except Exception as e:
            logger.error(f"Error editing message: {e}")
        
        # Log the purchase
        logger.info(f"User {user_id} purchased {product['name']} with balance. Key: {key_value}")
        
        # Clear user data
        context.user_data.clear()
        
    except Exception as e:
        logger.error(f"Error in process_balance_purchase: {e}")
        try:
            await query.edit_message_text("❌ An error occurred during purchase. Please try again.")
        except:
            pass
    finally:
        conn.close()

async def handle_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle text messages for various purposes"""
    try:
        if update.message:
            user_id = update.message.from_user.id
            text = update.message.text
            
            logger.info(f"Text message from user: {user_id}, text: {text}")
            
            # Check if user is blocked
            conn = sqlite3.connect('atoplay_bot.db')
            cursor = conn.cursor()
            cursor.execute('SELECT is_blocked FROM users WHERE telegram_id = ?', (user_id,))
            user_data = cursor.fetchone()
            conn.close()
            
            if user_data and user_data[0] == 1 and text not in ["/start"]:
                await update.message.reply_text("❌ You are blocked from using this bot!")
                return
            
            # Handle menu button presses for ALL users
            if text == "🛒 Buy Keys":
                return await buy(update, context)
            elif text == "💳 Check Balance":
                await check_balance(update, context)
            elif text == "🔑 My Keys":
                await my_keys(update, context)
            elif text == "🔧 Admin Panel":
                await admin_panel(update, context)
            elif text == "📞 Contact":
                await update.message.reply_text("📞 Contact: @Aarifseller\n📢 Channel: @SnakeEngine105")
            elif text == "📢 Channel":
                await update.message.reply_text("📢 Channel: @SnakeEngine105")
            elif 'awaiting_amount' in context.user_data and context.user_data['awaiting_amount']:
                try:
                    amount = float(text)
                    if amount <= 0:
                        await update.message.reply_text("❌ Amount must be greater than 0!")
                        return
                    
                    if amount < 100:
                        await update.message.reply_text("❌ Minimum amount is ₹100!")
                        return
                    
                    context.user_data['amount'] = amount
                    context.user_data['is_adding_balance'] = True
                    context.user_data.pop('awaiting_amount', None)
                    
                    keyboard = [
                        [
                            InlineKeyboardButton("Easypaisa", callback_data='payment_easypaisa'),
                            InlineKeyboardButton("Binance", callback_data='payment_binance')
                        ],
                        [
                            InlineKeyboardButton("UPI", callback_data='payment_upi'),
                            InlineKeyboardButton("❌ Cancel", callback_data='cancel')
                        ]
                    ]
                    reply_markup = InlineKeyboardMarkup(keyboard)
                    
                    await update.message.reply_text(
                        f"💳 Add Balance: ₹{amount}\n\nPlease select payment method:",
                        reply_markup=reply_markup
                    )
                except ValueError:
                    await update.message.reply_text("❌ Invalid amount! Please send a valid number.")
                return
            elif 'awaiting_reject_reason' in context.user_data and context.user_data['awaiting_reject_reason']:
                await handle_reject_reason(update, context)
                return
                
    except Exception as e:
        logger.error(f"Error in handle_text_message: {e}")

async def handle_add_key(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle adding keys by admin - CASE SENSITIVE"""
    admin_id = update.effective_user.id
    
    if not is_admin(admin_id):
        await update.message.reply_text("❌ Unauthorized!")
        return
    
    command_text = update.message.text
    parts = command_text.split()
    
    if len(parts) < 2:
        await update.message.reply_text("❌ Invalid format! Use: /addkey_3d KEYVALUE")
        return
    
    command = parts[0]
    
    # Extract key value exactly as admin sent it (including case)
    key_value = parts[1]
    
    # If key has spaces or multiple parts
    if len(parts) > 2:
        key_value = " ".join(parts[1:])
    
    # Keep the exact case as sent by admin - NO UPPERCASE CONVERSION
    # Determine key type from command
    if command == "/addkey_3d":
        key_type = '3d'
    elif command == "/addkey_10d":
        key_type = '10d'
    elif command == "/addkey_30d":
        key_type = '30d'
    else:
        await update.message.reply_text("❌ Invalid command! Use /addkey_3d, /addkey_10d, or /addkey_30d")
        return
    
    conn = sqlite3.connect('atoplay_bot.db')
    cursor = conn.cursor()
    
    try:
        # Check if key already exists (case sensitive)
        cursor.execute('SELECT key_value FROM keys_stock WHERE key_value = ? COLLATE NOCASE', (key_value,))
        existing_key = cursor.fetchone()
        
        if existing_key:
            await update.message.reply_text(f"❌ Key '{key_value}' already exists as '{existing_key[0]}'!")
            conn.close()
            return
        
        # Add the key with exact case
        cursor.execute('INSERT INTO keys_stock (key_value, key_type) VALUES (?, ?)', 
                      (key_value, key_type))
        conn.commit()
        
        # Log admin action
        log_admin_action(admin_id, 'add_key', 0, f"{key_type} key: {key_value}")
        
        # Get updated stock
        stock_info = get_stock_info()
        
        await update.message.reply_text(
            f"""✅ Key Added Successfully!

🔑 Key: `{key_value}`
📦 Type: {key_type.upper()}-Day Key
💰 Price: ₹{PRODUCT_PRICES[key_type]}
👤 Added by: Admin

📊 Updated Stock:
• 3-Day Keys: {stock_info.get('3d', 0)} available
• 10-Day Keys: {stock_info.get('10d', 0)} available  
• 30-Day Keys: {stock_info.get('30d', 0)} available"""
        )
        
        logger.info(f"Admin {admin_id} added {key_type} key: {key_value} (exact case)")
        
    except Exception as e:
        await update.message.reply_text(f"❌ Error adding key: {str(e)}")
    finally:
        conn.close()

async def handle_delete_key(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle deleting keys by admin - CASE SENSITIVE"""
    admin_id = update.effective_user.id
    
    if not is_admin(admin_id):
        await update.message.reply_text("❌ Unauthorized!")
        return
    
    command_text = update.message.text
    parts = command_text.split()
    
    if len(parts) < 2:
        await update.message.reply_text("❌ Invalid format! Use: /delkey KEYVALUE")
        return
    
    # Extract key value exactly as admin sent it (including case)
    key_value = parts[1]
    
    # If key has spaces or multiple parts
    if len(parts) > 2:
        key_value = " ".join(parts[1:])
    
    conn = sqlite3.connect('atoplay_bot.db')
    cursor = conn.cursor()
    
    try:
        # Check if key exists (case insensitive search but delete exact match)
        cursor.execute('''SELECT key_id, key_type, status, key_value 
                          FROM keys_stock 
                          WHERE key_value = ? COLLATE NOCASE''', (key_value,))
        key_data = cursor.fetchone()
        
        if not key_data:
            await update.message.reply_text(f"❌ Key '{key_value}' not found!")
            conn.close()
            return
        
        key_id, key_type, status, actual_key_value = key_data
        
        # Delete the key using exact key value from database
        cursor.execute('DELETE FROM keys_stock WHERE key_id = ?', (key_id,))
        conn.commit()
        
        # Log admin action
        log_admin_action(admin_id, 'delete_key', 0, f"{key_type} key: {actual_key_value} (Status: {status})")
        
        # Get updated stock
        stock_info = get_stock_info()
        
        await update.message.reply_text(
            f"""✅ Key Deleted Successfully!

🔑 Key: `{actual_key_value}`
📦 Type: {key_type.upper()}-Day Key
📊 Status: {status}
👤 Deleted by: Admin

📊 Updated Stock:
• 3-Day Keys: {stock_info.get('3d', 0)} available
• 10-Day Keys: {stock_info.get('10d', 0)} available  
• 30-Day Keys: {stock_info.get('30d', 0)} available"""
        )
        
        logger.info(f"Admin {admin_id} deleted {key_type} key: {actual_key_value} (exact case)")
        
    except Exception as e:
        await update.message.reply_text(f"❌ Error deleting key: {str(e)}")
    finally:
        conn.close()

async def handle_price_change(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle price changes by admin"""
    admin_id = update.effective_user.id
    
    if not is_admin(admin_id):
        await update.message.reply_text("❌ Unauthorized!")
        return
    
    command_text = update.message.text
    parts = command_text.split()
    
    if len(parts) != 2:
        await update.message.reply_text("❌ Invalid format! Use: /price_3d NEW_PRICE")
        return
    
    command = parts[0]
    try:
        new_price = int(parts[1])
        if new_price <= 0:
            await update.message.reply_text("❌ Price must be greater than 0!")
            return
    except ValueError:
        await update.message.reply_text("❌ Invalid price! Please enter a valid number.")
        return
    
    # Determine product type from command
    if command == "/price_3d":
        product_type = '3d'
        product_name = '3-Day Key'
        old_price = PRODUCT_PRICES['3d']
        PRODUCT_PRICES['3d'] = new_price
    elif command == "/price_10d":
        product_type = '10d'
        product_name = '10-Day Key'
        old_price = PRODUCT_PRICES['10d']
        PRODUCT_PRICES['10d'] = new_price
    elif command == "/price_30d":
        product_type = '30d'
        product_name = '30-Day Key'
        old_price = PRODUCT_PRICES['30d']
        PRODUCT_PRICES['30d'] = new_price
    else:
        await update.message.reply_text("❌ Invalid command! Use /price_3d, /price_10d, or /price_30d")
        return
    
    # Save price to database
    conn = sqlite3.connect('atoplay_bot.db')
    cursor = conn.cursor()
    
    cursor.execute('''INSERT OR REPLACE INTO settings (setting_key, setting_value) 
                      VALUES (?, ?)''',
                   (f'price_{product_type}', str(new_price)))
    
    conn.commit()
    conn.close()
    
    # Log admin action
    log_admin_action(admin_id, 'change_price', 0, f"{product_name}: ₹{old_price} → ₹{new_price}")
    
    await update.message.reply_text(
        f"""✅ Price Updated Successfully!

📦 Product: {product_name}
💰 Old Price: ₹{old_price}
💰 New Price: ₹{new_price}
👤 Changed by: Admin

✅ Price has been updated for all users."""
    )
    
    logger.info(f"Admin {admin_id} changed {product_name} price: ₹{old_price} → ₹{new_price}")

async def show_stock(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show current stock"""
    admin_id = update.effective_user.id
    
    if not is_admin(admin_id):
        await update.message.reply_text("❌ Unauthorized!")
        return
    
    stock_info = get_stock_info()
    
    conn = sqlite3.connect('atoplay_bot.db')
    cursor = conn.cursor()
    
    # Get all keys with details
    cursor.execute('''SELECT key_type, key_value, status, 
                             strftime('%Y-%m-%d %H:%M', created_at) as created
                      FROM keys_stock 
                      ORDER BY key_type, created_at DESC''')
    
    all_keys = cursor.fetchall()
    conn.close()
    
    # Group keys by type
    keys_by_type = {'3d': [], '10d': [], '30d': []}
    
    for key_type, key_value, status, created in all_keys:
        keys_by_type[key_type].append(f"`{key_value}` - {status} ({created})")
    
    text = f"""📊 STOCK REPORT

📈 Available Keys:
• 3-Day Keys: {stock_info.get('3d', 0)} available - ₹{PRODUCT_PRICES['3d']}
• 10-Day Keys: {stock_info.get('10d', 0)} available - ₹{PRODUCT_PRICES['10d']}
• 30-Day Keys: {stock_info.get('30d', 0)} available - ₹{PRODUCT_PRICES['30d']}

🔑 All Keys:

📅 3-Day Keys:"""
    
    if keys_by_type['3d']:
        for key_info in keys_by_type['3d']:
            text += f"\n• {key_info}"
    else:
        text += "\n• No 3-day keys"
    
    text += "\n\n📅 10-Day Keys:"
    if keys_by_type['10d']:
        for key_info in keys_by_type['10d']:
            text += f"\n• {key_info}"
    else:
        text += "\n• No 10-day keys"
    
    text += "\n\n📅 30-Day Keys:"
    if keys_by_type['30d']:
        for key_info in keys_by_type['30d']:
            text += f"\n• {key_info}"
    else:
        text += "\n• No 30-day keys"
    
    await update.message.reply_text(text, parse_mode='Markdown')

async def show_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show bot statistics"""
    admin_id = update.effective_user.id
    
    if not is_admin(admin_id):
        await update.message.reply_text("❌ Unauthorized!")
        return
    
    conn = sqlite3.connect('atoplay_bot.db')
    cursor = conn.cursor()
    
    # Get total users
    cursor.execute('SELECT COUNT(*) FROM users')
    total_users = cursor.fetchone()[0]
    
    # Get total blocked users
    cursor.execute('SELECT COUNT(*) FROM users WHERE is_blocked = 1')
    blocked_users = cursor.fetchone()[0]
    
    # Get total admins
    cursor.execute('SELECT COUNT(*) FROM users WHERE is_admin = 1')
    total_admins = cursor.fetchone()[0]
    
    # Get total transactions
    cursor.execute('SELECT COUNT(*) FROM transactions')
    total_transactions = cursor.fetchone()[0]
    
    # Get total approved transactions amount
    cursor.execute('SELECT SUM(amount) FROM transactions WHERE status = "approved"')
    total_revenue = cursor.fetchone()[0] or 0
    
    # Get today's transactions
    cursor.execute('''SELECT COUNT(*), SUM(amount) FROM transactions 
                      WHERE DATE(created_at) = DATE('now') AND status = "approved"''')
    today_data = cursor.fetchone()
    today_transactions = today_data[0] or 0
    today_revenue = today_data[1] or 0
    
    # Get stock info
    stock_info = get_stock_info()
    
    conn.close()
    
    text = f"""📊 BOT STATISTICS

👥 Users:
• Total Users: {total_users}
• Blocked Users: {blocked_users}
• Total Admins: {total_admins}

💰 Revenue:
• Total Revenue: ₹{total_revenue}
• Today's Revenue: ₹{today_revenue}

💳 Transactions:
• Total Transactions: {total_transactions}
• Today's Transactions: {today_transactions}

📦 Stock Status:
• 3-Day Keys: {stock_info.get('3d', 0)} available
• 10-Day Keys: {stock_info.get('10d', 0)} available
• 30-Day Keys: {stock_info.get('30d', 0)} available

⏰ Last Updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"""
    
    await update.message.reply_text(text)

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle photo messages (payment screenshots)"""
    try:
        if not update.message or not update.message.photo:
            return
        
        user_id = update.message.from_user.id
        username = update.message.from_user.username or update.message.from_user.first_name
        
        logger.info(f"Photo received from user: {user_id}")
        
        # Check if user is blocked
        conn = sqlite3.connect('atoplay_bot.db')
        cursor = conn.cursor()
        cursor.execute('SELECT is_blocked FROM users WHERE telegram_id = ?', (user_id,))
        user_data = cursor.fetchone()
        conn.close()
        
        if user_data and user_data[0] == 1:
            await update.message.reply_text("❌ You are blocked from using this bot!")
            return
        
        # Check if we're expecting a screenshot
        if 'awaiting_screenshot' not in context.user_data or not context.user_data['awaiting_screenshot']:
            await update.message.reply_text("⚠️ I'm not expecting a screenshot right now. Please use /buy to start a purchase.")
            return
        
        # Check if this is for QR code setup
        if context.user_data.get('awaiting_qr_code'):
            await handle_qr_code_setup(update, context)
            return
        
        # Get the photo (largest size)
        photo = update.message.photo[-1]
        file_id = photo.file_id
        
        # Get user info
        conn = sqlite3.connect('atoplay_bot.db')
        cursor = conn.cursor()
        
        cursor.execute('SELECT user_id, unique_id FROM users WHERE telegram_id = ?', (user_id,))
        user_data = cursor.fetchone()
        
        if not user_data:
            await update.message.reply_text("❌ User not found! Please use /start first.")
            conn.close()
            return
        
        user_db_id, unique_id = user_data
        
        # Determine payment purpose and amount
        purpose = "Product Purchase" if 'selected_product' in context.user_data else "Add Balance"
        
        if 'selected_product' in context.user_data:
            product = context.user_data.get('selected_product')
            amount = product['price']
            product_name = product['name']
        elif 'amount' in context.user_data:
            amount = context.user_data.get('amount')
            product_name = "Balance Addition"
        else:
            amount = 0
            product_name = "Unknown"
        
        payment_method = context.user_data.get('payment_method', 'unknown')
        payment_method_name = PAYMENT_METHODS.get(payment_method, {}).get('name', 'Unknown')
        
        # Save transaction to database
        cursor.execute('''INSERT INTO transactions 
                          (user_id, amount, payment_method, screenshot, status) 
                          VALUES (?, ?, ?, ?, 'pending')''',
                       (user_db_id, amount, payment_method, file_id))
        conn.commit()
        transaction_id = cursor.lastrowid
        
        # Send confirmation to user
        await update.message.reply_text(
            f"""✅ Screenshot Received!

📋 Transaction Details:
• Transaction ID: {transaction_id}
• Purpose: {purpose}
• Amount: ₹{amount}
• Status: ⏳ Pending

✅ Your payment screenshot has been received and forwarded to admin for verification.

⏳ Please wait for admin approval. You will be notified once approved.

📞 Contact: @Aarifseller if you have any questions."""
        )
        
        # Forward screenshot to all admins with details
        caption = f"""🆕 Payment Request #{transaction_id}

👤 User: @{username} ({user_id})
🆔 Unique ID: {unique_id}
💰 Amount: ₹{amount}
🎯 Purpose: {purpose}
📦 Product: {product_name}
💳 Method: {payment_method_name}
⏰ Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
📊 Status: ⏳ Pending

Actions:
/approve_{transaction_id} - Approve payment
/reject_{transaction_id} - Reject payment"""
        
        # Forward to all admins
        admins = get_all_admins()
        for admin_id, admin_name, _ in admins:
            try:
                # Forward the photo
                await context.bot.forward_message(
                    chat_id=admin_id,
                    from_chat_id=user_id,
                    message_id=update.message.message_id
                )
                
                # Send details
                await context.bot.send_message(
                    chat_id=admin_id,
                    text=caption
                )
                logger.info(f"Screenshot forwarded to admin: {admin_id}")
            except Exception as e:
                logger.error(f"Failed to forward to admin {admin_id}: {e}")
        
        # Clear user data
        context.user_data.clear()
        
        conn.close()
        logger.info(f"Transaction #{transaction_id} created for user: {user_id}")
        
    except Exception as e:
        logger.error(f"Error in handle_photo: {e}")

async def approve_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Approve a payment transaction"""
    try:
        admin_id = update.effective_user.id
        
        # Check if user is admin
        if not is_admin(admin_id):
            await update.message.reply_text("❌ Unauthorized! Only admins can approve payments.")
            return
        
        # Get transaction ID from command
        command_text = update.message.text
        if not command_text.startswith('/approve_'):
            await update.message.reply_text("❌ Invalid command format!")
            return
        
        try:
            transaction_id = int(command_text.replace('/approve_', '').strip())
        except ValueError:
            await update.message.reply_text("❌ Invalid transaction ID!")
            return
        
        conn = sqlite3.connect('atoplay_bot.db')
        cursor = conn.cursor()
        
        # Get transaction details
        cursor.execute('''SELECT t.transaction_id, t.user_id, t.amount, t.status, 
                                 u.telegram_id, u.username, u.balance, u.unique_id
                          FROM transactions t
                          JOIN users u ON t.user_id = u.user_id
                          WHERE t.transaction_id = ?''', (transaction_id,))
        
        transaction_data = cursor.fetchone()
        
        if not transaction_data:
            await update.message.reply_text(f"❌ Transaction #{transaction_id} not found!")
            conn.close()
            return
        
        (trans_id, user_db_id, amount, status, user_telegram_id, 
         username, user_balance, unique_id) = transaction_data
        
        if status != 'pending':
            await update.message.reply_text(f"❌ Transaction #{transaction_id} is already {status}!")
            conn.close()
            return
        
        # Update transaction status
        cursor.execute('''UPDATE transactions 
                          SET status = 'approved', admin_id = ?
                          WHERE transaction_id = ?''',
                       (admin_id, transaction_id))
        
        # Update user balance
        new_balance = user_balance + amount
        cursor.execute('UPDATE users SET balance = ? WHERE user_id = ?',
                       (new_balance, user_db_id))
        
        conn.commit()
        
        # Log admin action
        log_admin_action(admin_id, 'approve_payment', user_db_id, f"Transaction #{transaction_id} - ₹{amount}")
        
        # Send notification to user
        try:
            await context.bot.send_message(
                chat_id=user_telegram_id,
                text=f"""✅ Payment Approved!

🎉 Congratulations! Your payment has been approved.

📋 Transaction Details:
• Transaction ID: #{transaction_id}
• Amount: ₹{amount}
• Status: ✅ Approved

💰 Your New Balance: ₹{new_balance}

💸 You can now use your balance to purchase keys!
Use /buy to get started.

📞 Contact: @Aarifseller for any queries."""
            )
        except Exception as e:
            logger.error(f"Failed to notify user {user_telegram_id}: {e}")
        
        # Send confirmation to admin
        await update.message.reply_text(
            f"""✅ Payment Approved Successfully!

📋 Transaction Details:
• Transaction ID: #{transaction_id}
• User: @{username} ({user_telegram_id})
• Amount: ₹{amount}
• Status: ✅ Approved
• Previous Balance: ₹{user_balance}
• New Balance: ₹{new_balance}

✅ User has been notified."""
        )
        
        conn.close()
        logger.info(f"Transaction #{transaction_id} approved by admin {admin_id}")
        
    except Exception as e:
        logger.error(f"Error in approve_payment: {e}")

async def reject_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Reject a payment transaction"""
    try:
        admin_id = update.effective_user.id
        
        # Check if user is admin
        if not is_admin(admin_id):
            await update.message.reply_text("❌ Unauthorized! Only admins can reject payments.")
            return
        
        # Get transaction ID from command
        command_text = update.message.text
        if not command_text.startswith('/reject_'):
            await update.message.reply_text("❌ Invalid command format!")
            return
        
        try:
            transaction_id = int(command_text.replace('/reject_', '').strip())
        except ValueError:
            await update.message.reply_text("❌ Invalid transaction ID!")
            return
        
        conn = sqlite3.connect('atoplay_bot.db')
        cursor = conn.cursor()
        
        # Get transaction details
        cursor.execute('''SELECT t.transaction_id, t.user_id, t.amount, t.status, 
                                 u.telegram_id, u.username
                          FROM transactions t
                          JOIN users u ON t.user_id = u.user_id
                          WHERE t.transaction_id = ?''', (transaction_id,))
        
        transaction_data = cursor.fetchone()
        
        if not transaction_data:
            await update.message.reply_text(f"❌ Transaction #{transaction_id} not found!")
            conn.close()
            return
        
        (trans_id, user_db_id, amount, status, user_telegram_id, username) = transaction_data
        
        if status != 'pending':
            await update.message.reply_text(f"❌ Transaction #{transaction_id} is already {status}!")
            conn.close()
            return
        
        # Ask for reason
        context.user_data['awaiting_reject_reason'] = True
        context.user_data['reject_transaction_id'] = transaction_id
        context.user_data['reject_user_id'] = user_telegram_id
        context.user_data['reject_amount'] = amount
        
        await update.message.reply_text(
            f"""❌ Reject Payment #{transaction_id}

User: @{username}
Amount: ₹{amount}

Please provide reason for rejection:"""
        )
        
        conn.close()
        
    except Exception as e:
        logger.error(f"Error in reject_payment: {e}")

async def handle_reject_reason(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle rejection reason"""
    try:
        admin_id = update.effective_user.id
        
        if not is_admin(admin_id):
            return
        
        if 'awaiting_reject_reason' not in context.user_data:
            return
        
        reason = update.message.text
        transaction_id = context.user_data.get('reject_transaction_id')
        user_telegram_id = context.user_data.get('reject_user_id')
        amount = context.user_data.get('reject_amount')
        
        conn = sqlite3.connect('atoplay_bot.db')
        cursor = conn.cursor()
        
        # Update transaction status
        cursor.execute('''UPDATE transactions 
                          SET status = 'rejected', admin_id = ?
                          WHERE transaction_id = ?''',
                       (admin_id, transaction_id))
        
        conn.commit()
        
        # Log admin action
        cursor.execute('SELECT user_id FROM users WHERE telegram_id = ?', (user_telegram_id,))
        user_data = cursor.fetchone()
        if user_data:
            log_admin_action(admin_id, 'reject_payment', user_data[0], 
                            f"Transaction #{transaction_id} - ₹{amount} - Reason: {reason}")
        
        # Send notification to user
        try:
            await context.bot.send_message(
                chat_id=user_telegram_id,
                text=f"""❌ Payment Rejected!

📋 Transaction Details:
• Transaction ID: #{transaction_id}
• Amount: ₹{amount}
• Status: ❌ Rejected
• Reason: {reason}

⚠️ If you believe this is a mistake, please contact @Aarifseller with your payment proof.

📞 Contact: @Aarifseller for assistance."""
            )
        except Exception as e:
            logger.error(f"Failed to notify user {user_telegram_id}: {e}")
        
        # Clear user data
        context.user_data.clear()
        
        # Send confirmation to admin
        await update.message.reply_text(
            f"""✅ Payment Rejected Successfully!

📋 Transaction Details:
• Transaction ID: #{transaction_id}
• Amount: ₹{amount}
• Reason: {reason}

✅ User has been notified."""
        )
        
        conn.close()
        logger.info(f"Transaction #{transaction_id} rejected by admin {admin_id}")
        
    except Exception as e:
        logger.error(f"Error in handle_reject_reason: {e}")

async def check_balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        await update.message.chat.send_action(action="typing")
        
        user_id = update.effective_user.id
        
        conn = sqlite3.connect('atoplay_bot.db')
        cursor = conn.cursor()
        
        cursor.execute('SELECT unique_id, balance, is_blocked FROM users WHERE telegram_id = ?', (user_id,))
        user_data = cursor.fetchone()
        conn.close()
        
        if user_data:
            unique_id, balance, is_blocked = user_data
            
            if is_blocked == 1:
                text = "❌ You are blocked from using this bot!"
            else:
                text = f"""💳 Your Account

🆔 ID: {unique_id}
💰 Balance: ₹{balance}

💸 Add Balance:
Use /buy → Add Balance

📞 Contact: @Aarifseller
📢 Channel: @SnakeEngine105

🛒 Use /buy to purchase keys!"""
        else:
            text = "❌ Account not found! Use /start"
        
        await update.message.reply_text(text)
        
    except Exception as e:
        logger.error(f"Error in check_balance: {e}")

async def my_keys(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        await update.message.chat.send_action(action="typing")
        
        user_id = update.effective_user.id
        
        conn = sqlite3.connect('atoplay_bot.db')
        cursor = conn.cursor()
        
        cursor.execute('SELECT user_id, unique_id, is_blocked FROM users WHERE telegram_id = ?', (user_id,))
        user_data = cursor.fetchone()
        
        if not user_data:
            await update.message.reply_text("❌ Account not found! Use /start")
            conn.close()
            return
        
        user_db_id, unique_id, is_blocked = user_data
        
        if is_blocked == 1:
            await update.message.reply_text("❌ You are blocked from using this bot!")
            conn.close()
            return
        
        # Get user's purchased keys
        cursor.execute('''SELECT key_value, key_type, 
                                 strftime('%Y-%m-%d %H:%M', purchased_at) as purchase_time,
                                 status
                          FROM user_keys 
                          WHERE user_id = ? 
                          ORDER BY purchased_at DESC''', (user_db_id,))
        
        keys = cursor.fetchall()
        conn.close()
        
        if not keys:
            text = f"""🔑 My Keys

🆔 Your ID: {unique_id}
📦 No keys purchased yet.

🛒 Use /buy to purchase your first key!"""
        else:
            text = f"""🔑 My Keys

🆔 Your ID: {unique_id}
📦 Total Keys: {len(keys)}

📋 Your Purchased Keys:"""
            
            for i, (key_value, key_type, purchase_time, status) in enumerate(keys, 1):
                days = 3 if key_type == '3d' else (10 if key_type == '10d' else 30)
                text += f"\n\n{i}. 🔑 Key: `{key_value}`"
                text += f"\n   📅 Type: {days}-Day"
                text += f"\n   🕒 Purchased: {purchase_time}"
                text += f"\n   📊 Status: {status}"
        
        await update.message.reply_text(text, parse_mode='Markdown')
        
    except Exception as e:
        logger.error(f"Error in my_keys: {e}")

async def block_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Block a user"""
    try:
        admin_id = update.effective_user.id
        
        if not is_admin(admin_id):
            await update.message.reply_text("❌ Unauthorized!")
            return
        
        command_text = update.message.text
        parts = command_text.split()
        
        if len(parts) < 3:
            await update.message.reply_text("❌ Invalid format! Use: /block USER_ID REASON")
            return
        
        try:
            target_user_id = int(parts[1])
        except ValueError:
            await update.message.reply_text("❌ Invalid user ID!")
            return
        
        reason = " ".join(parts[2:])
        
        conn = sqlite3.connect('atoplay_bot.db')
        cursor = conn.cursor()
        
        # Check if user exists
        cursor.execute('SELECT telegram_id, username FROM users WHERE telegram_id = ?', (target_user_id,))
        user_data = cursor.fetchone()
        
        if not user_data:
            await update.message.reply_text(f"❌ User with ID {target_user_id} not found!")
            conn.close()
            return
        
        target_telegram_id, username = user_data
        
        # Update user status
        cursor.execute('''UPDATE users 
                          SET is_blocked = 1, blocked_reason = ?, blocked_at = CURRENT_TIMESTAMP
                          WHERE telegram_id = ?''',
                       (reason, target_user_id))
        
        conn.commit()
        
        # Log admin action
        cursor.execute('SELECT user_id FROM users WHERE telegram_id = ?', (target_user_id,))
        target_db_id = cursor.fetchone()[0]
        log_admin_action(admin_id, 'block_user', target_db_id, f"Reason: {reason}")
        
        # Notify user
        try:
            await context.bot.send_message(
                chat_id=target_user_id,
                text=f"""❌ You have been blocked!

You have been blocked from using the Atoplay Shop bot.

📋 Block Details:
• Reason: {reason}
• Blocked by: Admin
• Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

⚠️ You can no longer use the bot commands or make purchases.

📞 Contact @Aarifseller for assistance."""
            )
        except Exception as e:
            logger.error(f"Failed to notify blocked user {target_user_id}: {e}")
        
        await update.message.reply_text(
            f"""✅ User Blocked Successfully!

👤 User: @{username} ({target_user_id})
📝 Reason: {reason}
⏰ Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

✅ User has been notified."""
        )
        
        conn.close()
        logger.info(f"User {target_user_id} blocked by admin {admin_id}")
        
    except Exception as e:
        logger.error(f"Error in block_user: {e}")

async def unblock_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Unblock a user"""
    try:
        admin_id = update.effective_user.id
        
        if not is_admin(admin_id):
            await update.message.reply_text("❌ Unauthorized!")
            return
        
        command_text = update.message.text
        parts = command_text.split()
        
        if len(parts) < 2:
            await update.message.reply_text("❌ Invalid format! Use: /unblock USER_ID")
            return
        
        try:
            target_user_id = int(parts[1])
        except ValueError:
            await update.message.reply_text("❌ Invalid user ID!")
            return
        
        conn = sqlite3.connect('atoplay_bot.db')
        cursor = conn.cursor()
        
        # Check if user exists
        cursor.execute('SELECT telegram_id, username FROM users WHERE telegram_id = ?', (target_user_id,))
        user_data = cursor.fetchone()
        
        if not user_data:
            await update.message.reply_text(f"❌ User with ID {target_user_id} not found!")
            conn.close()
            return
        
        target_telegram_id, username = user_data
        
        # Update user status
        cursor.execute('''UPDATE users 
                          SET is_blocked = 0, blocked_reason = NULL, blocked_at = NULL
                          WHERE telegram_id = ?''',
                       (target_user_id,))
        
        conn.commit()
        
        # Log admin action
        cursor.execute('SELECT user_id FROM users WHERE telegram_id = ?', (target_user_id,))
        target_db_id = cursor.fetchone()[0]
        log_admin_action(admin_id, 'unblock_user', target_db_id, "")
        
        # Notify user
        try:
            await context.bot.send_message(
                chat_id=target_user_id,
                text=f"""✅ You have been unblocked!

Your access to Atoplay Shop bot has been restored.

📋 Unblock Details:
• Unblocked by: Admin
• Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

✅ You can now use the bot commands and make purchases.

📞 Contact @Aarifseller for assistance."""
            )
        except Exception as e:
            logger.error(f"Failed to notify unblocked user {target_user_id}: {e}")
        
        await update.message.reply_text(
            f"""✅ User Unblocked Successfully!

👤 User: @{username} ({target_user_id})
⏰ Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

✅ User has been notified."""
        )
        
        conn.close()
        logger.info(f"User {target_user_id} unblocked by admin {admin_id}")
        
    except Exception as e:
        logger.error(f"Error in unblock_user: {e}")

async def user_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Get user information"""
    try:
        admin_id = update.effective_user.id
        
        if not is_admin(admin_id):
            await update.message.reply_text("❌ Unauthorized!")
            return
        
        command_text = update.message.text
        parts = command_text.split()
        
        if len(parts) < 2:
            await update.message.reply_text("❌ Invalid format! Use: /userinfo USER_ID")
            return
        
        try:
            target_user_id = int(parts[1])
        except ValueError:
            await update.message.reply_text("❌ Invalid user ID!")
            return
        
        conn = sqlite3.connect('atoplay_bot.db')
        cursor = conn.cursor()
        
        # Get user details
        cursor.execute('''SELECT telegram_id, username, unique_id, balance, 
                                 is_blocked, blocked_reason, blocked_at, is_admin,
                                 strftime('%Y-%m-%d %H:%M', blocked_at) as blocked_time
                          FROM users WHERE telegram_id = ?''', (target_user_id,))
        
        user_data = cursor.fetchone()
        
        if not user_data:
            await update.message.reply_text(f"❌ User with ID {target_user_id} not found!")
            conn.close()
            return
        
        (telegram_id, username, unique_id, balance, is_blocked, 
         blocked_reason, blocked_at, is_admin_user, blocked_time) = user_data
        
        # Get user's purchase history
        cursor.execute('''SELECT COUNT(*), SUM(amount) 
                          FROM transactions 
                          WHERE user_id = (SELECT user_id FROM users WHERE telegram_id = ?)
                          AND status = 'approved' ''', (target_user_id,))
        
        purchase_data = cursor.fetchone()
        total_purchases = purchase_data[0] or 0
        total_spent = purchase_data[1] or 0
        
        # Get user's keys
        cursor.execute('''SELECT COUNT(*) 
                          FROM user_keys 
                          WHERE user_id = (SELECT user_id FROM users WHERE telegram_id = ?)''', 
                       (target_user_id,))
        
        keys_count = cursor.fetchone()[0] or 0
        
        conn.close()
        
        text = f"""📋 USER INFORMATION

👤 Basic Info:
• User ID: {telegram_id}
• Username: @{username}
• Unique ID: {unique_id}
• Balance: ₹{balance}
• Is Admin: {'✅ Yes' if is_admin_user == 1 else '❌ No'}

📊 Statistics:
• Total Purchases: {total_purchases}
• Total Spent: ₹{total_spent}
• Keys Purchased: {keys_count}

🔒 Block Status: {'❌ BLOCKED' if is_blocked == 1 else '✅ ACTIVE'}"""
        
        if is_blocked == 1:
            text += f"\n• Block Reason: {blocked_reason}"
            text += f"\n• Blocked At: {blocked_time}"
        
        text += f"\n\n🛠️ Actions:"
        if is_blocked == 1:
            text += f"\n• /unblock_{telegram_id} - Unblock user"
        else:
            text += f"\n• /block_{telegram_id} REASON - Block user"
        
        await update.message.reply_text(text)
        
    except Exception as e:
        logger.error(f"Error in user_info: {e}")

async def setup_upi(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Change UPI number"""
    try:
        admin_id = update.effective_user.id
        
        if not is_admin(admin_id):
            await update.message.reply_text("❌ Unauthorized!")
            return
        
        command_text = update.message.text
        parts = command_text.split()
        
        if len(parts) < 2:
            await update.message.reply_text("❌ Invalid format! Use: /setupi NEW_UPI_NUMBER")
            return
        
        new_upi = parts[1].strip()
        
        # Update UPI number
        if 'upi' in PAYMENT_METHODS:
            old_upi = PAYMENT_METHODS['upi'].get('number', 'N/A')
            PAYMENT_METHODS['upi']['number'] = new_upi
        
        # Log admin action
        log_admin_action(admin_id, 'change_upi', 0, f"UPI: {old_upi} → {new_upi}")
        
        await update.message.reply_text(
            f"""✅ UPI Updated Successfully!

📱 Old UPI: {old_upi}
📱 New UPI: {new_upi}
👤 Changed by: Admin

✅ UPI number has been updated for all users."""
        )
        
        logger.info(f"Admin {admin_id} changed UPI: {old_upi} → {new_upi}")
        
    except Exception as e:
        logger.error(f"Error in setup_upi: {e}")

async def set_qr_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Set UPI QR code"""
    try:
        admin_id = update.effective_user.id
        
        if not is_admin(admin_id):
            await update.message.reply_text("❌ Unauthorized!")
            return
        
        # Set flag to await QR code photo
        context.user_data['awaiting_qr_code'] = True
        
        await update.message.reply_text(
            """📱 Set UPI QR Code

Please send the QR code image now.

⚠️ Requirements:
• Clear QR code image
• Good resolution
• Square aspect ratio

📸 Send the QR code photo now.

❌ Send /cancel to cancel."""
        )
        
    except Exception as e:
        logger.error(f"Error in set_qr_code: {e}")

async def handle_qr_code_setup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle QR code setup"""
    try:
        admin_id = update.effective_user.id
        
        if not update.message or not update.message.photo:
            return
        
        # Get the photo (largest size)
        photo = update.message.photo[-1]
        file_id = photo.file_id
        
        # Update QR code in PAYMENT_METHODS
        if 'upi' in PAYMENT_METHODS:
            old_qr = PAYMENT_METHODS['upi'].get('qr_code', 'None')
            PAYMENT_METHODS['upi']['qr_code'] = file_id
        
        # Clear the flag
        context.user_data.pop('awaiting_qr_code', None)
        
        # Log admin action
        log_admin_action(admin_id, 'change_qr', 0, "UPI QR code updated")
        
        await update.message.reply_text(
            f"""✅ QR Code Updated Successfully!

📱 UPI QR code has been updated.
👤 Changed by: Admin

✅ QR code is now available for users."""
        )
        
        logger.info(f"Admin {admin_id} updated UPI QR code")
        
    except Exception as e:
        logger.error(f"Error in handle_qr_code_setup: {e}")

async def add_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Add new admin (Super Admin only)"""
    try:
        admin_id = update.effective_user.id
        
        if not is_super_admin(admin_id):
            await update.message.reply_text("❌ Unauthorized! Only Super Admin can add admins.")
            return
        
        command_text = update.message.text
        parts = command_text.split()
        
        if len(parts) < 2:
            await update.message.reply_text("❌ Invalid format! Use: /addadmin USER_ID")
            return
        
        try:
            new_admin_id = int(parts[1])
        except ValueError:
            await update.message.reply_text("❌ Invalid user ID!")
            return
        
        conn = sqlite3.connect('atoplay_bot.db')
        cursor = conn.cursor()
        
        # Check if user exists
        cursor.execute('SELECT telegram_id, username FROM users WHERE telegram_id = ?', (new_admin_id,))
        user_data = cursor.fetchone()
        
        if not user_data:
            await update.message.reply_text(f"❌ User with ID {new_admin_id} not found!")
            conn.close()
            return
        
        target_telegram_id, username = user_data
        
        # Check if already admin
        cursor.execute('SELECT is_admin FROM users WHERE telegram_id = ?', (new_admin_id,))
        is_admin_user = cursor.fetchone()
        
        if is_admin_user and is_admin_user[0] == 1:
            await update.message.reply_text(f"❌ User @{username} is already an admin!")
            conn.close()
            return
        
        # Make user admin
        cursor.execute('UPDATE users SET is_admin = 1, added_by = ? WHERE telegram_id = ?',
                       (admin_id, new_admin_id))
        
        conn.commit()
        
        # Log admin action
        cursor.execute('SELECT user_id FROM users WHERE telegram_id = ?', (new_admin_id,))
        target_db_id = cursor.fetchone()[0]
        log_admin_action(admin_id, 'add_admin', target_db_id, f"Added new admin: {username}")
        
        # Notify new admin
        try:
            await context.bot.send_message(
                chat_id=new_admin_id,
                text=f"""🎉 Congratulations!

You have been promoted to Admin in Atoplay Shop bot.

🔧 Admin Privileges:
• Approve/Reject payments
• Add/Delete keys
• Change prices
• Block/Unblock users
• View statistics

📋 Admin Commands:
• /admin - Admin panel
• /stock - View stock
• /stats - View statistics

⚠️ Use your powers responsibly!

📞 Contact Super Admin for assistance."""
            )
        except Exception as e:
            logger.error(f"Failed to notify new admin {new_admin_id}: {e}")
        
        await update.message.reply_text(
            f"""✅ Admin Added Successfully!

👤 New Admin: @{username} ({new_admin_id})
👑 Added by: Super Admin
⏰ Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

✅ New admin has been notified."""
        )
        
        conn.close()
        logger.info(f"Admin {new_admin_id} added by Super Admin {admin_id}")
        
    except Exception as e:
        logger.error(f"Error in add_admin: {e}")

async def remove_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Remove admin (Super Admin only)"""
    try:
        admin_id = update.effective_user.id
        
        if not is_super_admin(admin_id):
            await update.message.reply_text("❌ Unauthorized! Only Super Admin can remove admins.")
            return
        
        command_text = update.message.text
        parts = command_text.split()
        
        if len(parts) < 2:
            await update.message.reply_text("❌ Invalid format! Use: /removeadmin USER_ID")
            return
        
        try:
            target_admin_id = int(parts[1])
        except ValueError:
            await update.message.reply_text("❌ Invalid user ID!")
            return
        
        # Prevent removing self
        if target_admin_id == admin_id:
            await update.message.reply_text("❌ You cannot remove yourself as admin!")
            return
        
        conn = sqlite3.connect('atoplay_bot.db')
        cursor = conn.cursor()
        
        # Check if user exists and is admin
        cursor.execute('SELECT telegram_id, username, is_admin FROM users WHERE telegram_id = ?', (target_admin_id,))
        user_data = cursor.fetchone()
        
        if not user_data:
            await update.message.reply_text(f"❌ User with ID {target_admin_id} not found!")
            conn.close()
            return
        
        target_telegram_id, username, is_admin_user = user_data
        
        if is_admin_user != 1:
            await update.message.reply_text(f"❌ User @{username} is not an admin!")
            conn.close()
            return
        
        # Remove admin privileges
        cursor.execute('UPDATE users SET is_admin = 0, added_by = NULL WHERE telegram_id = ?',
                       (target_admin_id,))
        
        conn.commit()
        
        # Log admin action
        cursor.execute('SELECT user_id FROM users WHERE telegram_id = ?', (target_admin_id,))
        target_db_id = cursor.fetchone()[0]
        log_admin_action(admin_id, 'remove_admin', target_db_id, f"Removed admin: {username}")
        
        # Notify removed admin
        try:
            await context.bot.send_message(
                chat_id=target_admin_id,
                text=f"""📢 Notice

Your admin privileges have been removed from Atoplay Shop bot.

📋 Details:
• Removed by: Super Admin
• Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

⚠️ You no longer have access to admin commands.

📞 Contact Super Admin for more information."""
            )
        except Exception as e:
            logger.error(f"Failed to notify removed admin {target_admin_id}: {e}")
        
        await update.message.reply_text(
            f"""✅ Admin Removed Successfully!

👤 Removed Admin: @{username} ({target_admin_id})
👑 Removed by: Super Admin
⏰ Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

✅ Admin has been notified."""
        )
        
        conn.close()
        logger.info(f"Admin {target_admin_id} removed by Super Admin {admin_id}")
        
    except Exception as e:
        logger.error(f"Error in remove_admin: {e}")

async def list_admins(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """List all admins"""
    try:
        admin_id = update.effective_user.id
        
        if not is_admin(admin_id):
            await update.message.reply_text("❌ Unauthorized!")
            return
        
        admins = get_all_admins()
        
        text = "👑 ADMIN LIST\n\n"
        
        for i, (admin_telegram_id, username, is_admin_user) in enumerate(admins, 1):
            status = "👑 Super Admin" if admin_telegram_id == 5911406948 else "🔧 Admin"
            text += f"{i}. @{username} ({admin_telegram_id}) - {status}\n"
        
        text += f"\n📊 Total Admins: {len(admins)}"
        
        if is_super_admin(admin_id):
            text += "\n\n🛠️ Super Admin Commands:"
            text += "\n• /addadmin USER_ID - Add new admin"
            text += "\n• /removeadmin USER_ID - Remove admin"
        
        await update.message.reply_text(text)
        
    except Exception as e:
        logger.error(f"Error in list_admins: {e}")

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Log errors"""
    logger.error(f"Update {update} caused error {context.error}")

def main():
    # First delete old database and create new one
    init_db()
    add_sample_keys()
    
    print("=" * 50)
    print("🤖 Bot starting...")
    print(f"📱 Token: {TOKEN[:10]}...")
    print("=" * 50)
    
    try:
        # Create application with build method
        application = Application.builder().token(TOKEN).build()
        
        # Add error handler
        application.add_error_handler(error_handler)
        
        # Basic command handlers
        application.add_handler(CommandHandler('start', start))
        application.add_handler(CommandHandler('buy', buy))
        application.add_handler(CommandHandler('balance', check_balance))
        application.add_handler(CommandHandler('mykeys', my_keys))
        application.add_handler(CommandHandler('admin', admin_panel))
        application.add_handler(CommandHandler('stats', show_stats))
        application.add_handler(CommandHandler('stock', show_stock))
        application.add_handler(CommandHandler('listadmins', list_admins))
        
        # Admin command handlers for adding keys
        application.add_handler(CommandHandler('addkey_3d', handle_add_key))
        application.add_handler(CommandHandler('addkey_10d', handle_add_key))
        application.add_handler(CommandHandler('addkey_30d', handle_add_key))
        
        # Admin command handlers for deleting keys
        application.add_handler(CommandHandler('delkey', handle_delete_key))
        
        # Admin command handlers for price changes
        application.add_handler(CommandHandler('price_3d', handle_price_change))
        application.add_handler(CommandHandler('price_10d', handle_price_change))
        application.add_handler(CommandHandler('price_30d', handle_price_change))
        
        # Admin user management commands
        application.add_handler(CommandHandler('block', block_user))
        application.add_handler(CommandHandler('unblock', unblock_user))
        application.add_handler(CommandHandler('userinfo', user_info))
        
        # Admin payment methods commands
        application.add_handler(CommandHandler('setupi', setup_upi))
        application.add_handler(CommandHandler('setqr', set_qr_code))
        
        # Super Admin commands
        application.add_handler(CommandHandler('addadmin', add_admin))
        application.add_handler(CommandHandler('removeadmin', remove_admin))
        
        # Admin payment approval handlers
        application.add_handler(MessageHandler(filters.Regex(r'^/approve_\d+$'), approve_payment))
        application.add_handler(MessageHandler(filters.Regex(r'^/reject_\d+$'), reject_payment))
        
        # Handle block/unblock via user info
        application.add_handler(MessageHandler(filters.Regex(r'^/block_\d+'), block_user))
        application.add_handler(MessageHandler(filters.Regex(r'^/unblock_\d+'), unblock_user))
        
        # Handle text messages for ALL users (including admin menu buttons)
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message))
        
        # SINGLE callback query handler for ALL callbacks
        application.add_handler(CallbackQueryHandler(callback_handler))
        
        # Photo handler for payment screenshots and QR codes
        application.add_handler(MessageHandler(filters.PHOTO, handle_photo))
        
        print("✅ All handlers registered successfully!")
        print("⏳ Starting polling...")
        
        # Start polling with simple parameters
        application.run_polling(allowed_updates=Update.ALL_TYPES)
        
    except Exception as e:
        print(f"❌ CRITICAL ERROR: {e}")
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    main()