import os
import telebot
from telebot import types
import requests
import sqlite3
from flask import Flask, request

# ----------------- تنظیمات اولیه ربات -----------------
BOT_TOKEN = '8609389890:AAFHNmgPSb6CXIG15gOtdWWnqBG4VC5375I'
ADMIN_ID = 7267007753  # آیدی عددی خودت (ادمین)

# ----------------- اطلاعات پنل نهان کلودفلر -----------------
NAHAN_API_URL = 'https://still-disk-40a6.ddvdfxfv.workers.dev' 
NAHAN_USER = 'admin'
NAHAN_PASS = 'admin'

bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(__name__)

# ----------------- بخش پایگاه داده -----------------
def init_db():
    conn = sqlite3.connect('shop_database.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            referred_by INTEGER DEFAULT 0,
            invite_count INTEGER DEFAULT 0,
            has_tested INTEGER DEFAULT 0
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS pending_orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            plan_name TEXT,
            days INTEGER,
            volume_gb INTEGER
        )
    ''')
    conn.commit()
    conn.close()

def add_user_if_not_exists(user_id, referred_by=0):
    conn = sqlite3.connect('shop_database.db')
    cursor = conn.cursor()
    cursor.execute('SELECT user_id FROM users WHERE user_id = ?', (user_id,))
    if not cursor.fetchone():
        cursor.execute('INSERT INTO users (user_id, referred_by) VALUES (?, ?)', (user_id, referred_by))
        if referred_by != 0 and referred_by != user_id:
            cursor.execute('UPDATE users SET invite_count = invite_count + 1 WHERE user_id = ?', (referred_by,))
    conn.commit()
    conn.close()

init_db()

# ----------------- توابع اتصال به API پنل نهان -----------------
def get_nahan_token():
    url = f"{NAHAN_API_URL}/sync/login" 
    payload = {"username": NAHAN_USER, "password": NAHAN_PASS}
    try:
        res = requests.post(url, json=payload, timeout=10)
        if res.status_code == 200:
            return res.json().get('token')
    except Exception as e:
        print(f"Panel login error: {e}")
    return None

def create_panel_config(username, days, volume_gb):
    token = get_nahan_token()
    url = f"{NAHAN_API_URL}/sync/add" 
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
        
    payload = {
        "username": username,
        "proxies": ["vless"], 
        "expire": days,
        "data_limit": volume_gb * 1024 * 1024 * 1024
    }
    try:
        res = requests.post(url, json=payload, headers=headers, timeout=10)
        if res.status_code in [200, 210]:
            return res.json().get('subscription_url') or res.json().get('link')
    except Exception as e:
        print(f"Panel create config error: {e}")
    return None

# ----------------- بخش دستورات ربات تلگرام -----------------
@bot.message_handler(commands=['start'])
def send_welcome(message):
    start_args = message.text.split()
    referred_by = 0
    if len(start_args) > 1:
        try: referred_by = int(start_args[1])
        except ValueError: referred_by = 0
            
    add_user_if_not_exists(message.chat.id, referred_by)

    welcome_text = f"👑 **سلام {message.from_user.first_name} عزیز، به فروشگاه وی‌پی‌ان ما خوش آمدی!**\n\nلطفاً از دکمه‌های زیر استفاده کن: 👇"
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add(types.KeyboardButton("🛍️ خرید سرویس جدید"))
    markup.add(types.KeyboardButton("🎁 تست رایگان ۱ روزه"), types.KeyboardButton("👥 زیرمجموعه‌گیری و هدیه"))
    bot.send_message(message.chat.id, welcome_text, reply_markup=markup, parse_mode="Markdown")

@bot.message_handler(func=lambda message: message.text == "🎁 تست رایگان ۱ روزه")
def request_free_test(message):
    conn = sqlite3.connect('shop_database.db')
    cursor = conn.cursor()
    cursor.execute('SELECT has_tested FROM users WHERE user_id = ?', (message.chat.id,))
    row = cursor.fetchone()
    has_tested = row[0] if row else 0
    
    if has_tested == 1:
        bot.reply_to(message, "❌ **خطا!** شما قبلاً یک‌بار اکانت تست رایگان دریافت کرده‌اید و هر کاربر فقط یک‌بار مجاز به تست است.")
        conn.close()
        return

    bot.reply_to(message, "⏳ **در حال ساخت کانفیگ تست شما...**\nلطفاً چند ثانیه صبور باشید...")
    username = f"test_{message.chat.id}"
    config_link = create_panel_config(username, days=1, volume_gb=1)
    
    if config_link:
        cursor.execute('UPDATE users SET has_tested = 1 WHERE user_id = ?', (message.chat.id,))
        conn.commit()
        bot.send_message(
            message.chat.id,
            f"🎁 **اکانت تست شما با موفقیت ساخته شد!**\n\n⏱️ اعتبار: ۱ روز | حجم: ۱ گیگابایت\n\n🔑 **لینک کانفیگ:**\n`{config_link}`",
            parse_mode="Markdown"
        )
    else:
        bot.send_message(message.chat.id, "❌ **ای وای!** در حال حاضر ارتباط با پنل برقرار نشد. لطفاً بعداً تلاش کنید.")
    conn.close()

@bot.message_handler(func=lambda message: message.text == "🛍️ خرید سرویس جدید")
def show_plans(message):
    text = "📅 **لطفاً پلان مد نظرت رو انتخاب کن رفیق:**"
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton("🚀 ۳۰ روزه - ۲۰ گیگ | ۱۰۰,۰۰۰ تومان", callback_data="buy_20gb_30_100000"),
        types.InlineKeyboardButton("🚀 ۳۰ روزه - ۴۰ گیگ | ۲۰۰,۰۰۰ تومان", callback_data="buy_40gb_30_200000"),
        types.InlineKeyboardButton("🚀 ۳۰ روزه - ۶۰ گیگ | ۳۰۰,۰۰۰ تومان", callback_data="buy_60gb_30_300000"),
        types.InlineKeyboardButton("🚀 ۳۰ روزه - ۱۰۰ گیگ | ۴۵۰,۰۰۰ تومان", callback_data="buy_100gb_30_450000"),
        types.InlineKeyboardButton("🔥 ۳۰ روزه - نامحدود | ۶۰۰,۰۰۰ تومان", callback_data="buy_9999gb_30_600000")
    )
    bot.send_message(message.chat.id, text, reply_markup=markup, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data.startswith('buy_'))
def process_plan_selection(call):
    parts = call.data.split('_')
    volume = int(parts[1].replace('gb', ''))
    days = int(parts[2])
    price = parts[3]
    
    plan_display = "نامحدود" if volume == 9999 else f"{volume} گیگ"
    
    conn = sqlite3.connect('shop_database.db')
    cursor = conn.cursor()
    cursor.execute('INSERT INTO pending_orders (user_id, plan_name, days, volume_gb) VALUES (?, ?, ?, ?)', 
                   (call.message.chat.id, f"{plan_display}-{days}Days", days, volume))
    order_id = cursor.lastrowid
    conn.commit()
    conn.close()
    
    formatted_price = "{:,}".format(int(price))
    
    text = f"💳 **درخواست خرید پلان {plan_display} ثبت شد**\n\n💰 مبلغ: {formatted_price} تومان\n📍 لطفاً مبلغ را به شماره کارت زیر واریز کنید و **فقط عکس رسید** را در پاسخ به این پیام فرستید:\n\n`6037997275603489`\nبه نام رایین ایمانی"
    msg = bot.send_message(call.message.chat.id, text, parse_mode="Markdown")
    bot.register_next_step_handler(msg, receive_receipt, order_id)

def receive_receipt(message, order_id):
    if not message.photo:
        bot.reply_to(message, "❌ لطفاً فقط عکس رسید واریزی رو بفرستید. دوباره دکمه خرید رو بزنید.")
        return

    photo_id = message.photo[-1].file_id
    markup = types.InlineKeyboardMarkup()
    markup.add(
        types.InlineKeyboardButton("✅ تایید و ساخت کانفیگ", callback_data=f"admin_approve_{order_id}_{message.chat.id}"),
        types.InlineKeyboardButton("❌ رد کردن رسید", callback_data=f"admin_reject_{message.chat.id}")
    )
    
    bot.send_photo(ADMIN_ID, photo_id, caption=f"🔔 **رسید جدید آمد!**\n👤 کاربر: `{message.chat.id}`\n📦 کد سفارش: `{order_id}`", reply_markup=markup, parse_mode="Markdown")
    bot.send_message(message.chat.id, "⏳ **رسید شما برای مدیریت ارسال شد.**\nپس از بررسی، کانفیگ به صورت خودکار همینجا براتون فرستاده میشه.")

@bot.callback_query_handler(func=lambda call: call.data.startswith('admin_'))
def process_admin_action(call):
    parts = call.data.split('_')
    action = parts[1]
    user_id = int(parts[-1])
    
    if action == "approve":
        order_id = int(parts[2])
        bot.edit_message_caption("✅ این رسید تایید شد و کانفیگ در حال ساخت است...", call.message.chat.id, call.message.message_id)
        
        conn = sqlite3.connect('shop_database.db')
        cursor = conn.cursor()
        cursor.execute('SELECT days, volume_gb FROM pending_orders WHERE id = ?', (order_id,))
        row = cursor.fetchone()
        
        if row:
            days, volume = row
            username = f"user_{user_id}_{order_id}"
            config_link = create_panel_config(username, days, volume)
            
            if config_link:
                bot.send_message(user_id, f"🎉 **خرید شما توسط مدیریت تایید شد!**\n\n🔑 **لینک کانفیگ اختصاصی شما:**\n`{config_link}`", parse_mode="Markdown")
                bot.send_message(ADMIN_ID, "✅ کانفیگ با موفقیت ساخته و به کاربر تحویل داده شد.")
            else:
                bot.send_message(user_id, "❌ خرید شما تایید شد اما خطایی در اتصال به پنل رخ داد. لطفا به پشتیبانی پیام دهید.")
                bot.send_message(ADMIN_ID, "❌ خطا: رسید تایید شد ولی پنل لینک رو نساخت.")
        conn.close()
        
    elif action == "reject":
        bot.edit_message_caption("❌ این رسید رد شد.", call.message.chat.id, call.message.message_id)
        bot.send_message(user_id, "❌ **رسید واریزی شما توسط مدیریت رد شد.**\nاگر اشتباهی رخ داده لطفا به پشتیبانی پیام دهید.")

@bot.message_handler(func=lambda message: message.text == "👥 زیرمجموعه‌گیری و هدیه")
def referral_menu(message):
    bot_info = bot.get_me()
    ref_link = f"https://t.me/{bot_info.username}?start={message.chat.id}"
    conn = sqlite3.connect('shop_database.db')
    cursor = conn.cursor()
    cursor.execute('SELECT invite_count FROM users WHERE user_id = ?', (message.chat.id,))
    row = cursor.fetchone()
    invite_count = row[0] if row else 0
    conn.close()
    text = f"🎁 **سیستم زیرمجموعه‌گیری**\n\n📊 تعداد دعوت‌های شما: `{invite_count}` نفر\n🔗 لینک اختصاصی شما:\n`{ref_link}`"
    bot.send_message(message.chat.id, text, parse_mode="Markdown")

# ----------------- تنظیمات وب‌هوک رندر -----------------
@app.route('/' + BOT_TOKEN, methods=['POST'])
def getMessage():
    json_string = request.get_data().decode('utf-8')
    update = telebot.types.Update.de_json(json_string)
    bot.process_new_updates([update])
    return "!", 200

@app.route("/")
def webhook():
    bot.remove_webhook()
    bot.set_webhook(url='https://https://my-fast-vpn-bot.onrender.com/' + BOT_TOKEN)
    return "Bot is active!", 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get('PORT', 5000)))
