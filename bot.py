# -*- coding: utf-8 -*-
import os
import json
import time
import subprocess
import requests
import telebot
from telebot import types

# ==================== الإعدادات الأساسية ====================
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = 8358047016  # ID المطور

GH_PAT = os.getenv("GH_PAT")          # Personal Access Token
REPO_OWNER = os.getenv("REPO_OWNER")  # GitHub User/Org
REPO_NAME = os.getenv("REPO_NAME")    # Repository Name

if not BOT_TOKEN:
    raise ValueError("⚠️ لم يتم العثور على BOT_TOKEN!")

bot = telebot.TeleBot(BOT_TOKEN)
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0 Safari/537.36"
DB_FILE = "database.json"

# ==================== إعدادات قاعدة البيانات ====================
def load_db():
    if not os.path.exists(DB_FILE):
        return {"users": {}, "files": {}, "blocked": [], "active_stream": {}}
    try:
        with open(DB_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            if "active_stream" not in data:
                data["active_stream"] = {}
            return data
    except Exception:
        return {"users": {}, "files": {}, "blocked": [], "active_stream": {}}

def save_db(data):
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

db = load_db()

def is_blocked(user_id):
    return user_id in db.get("blocked", [])

def register_user(user):
    uid = str(user.id)
    if uid not in db["users"]:
        db["users"][uid] = {
            "first_name": user.first_name,
            "username": user.username or "بدون_يوزر",
            "joined_at": time.time()
        }
        db["files"][uid] = []
        save_db(db)

def format_size(size_in_bytes):
    if size_in_bytes < 1024 * 1024:
        return f"{round(size_in_bytes / 1024, 2)} KB"
    elif size_in_bytes < 1024 * 1024 * 1024:
        return f"{round(size_in_bytes / (1024 * 1024), 2)} MB"
    else:
        return f"{round(size_in_bytes / (1024 * 1024 * 1024), 2)} GB"

# ==================== خدمة الرفع المؤقت (Litterbox) ====================
def upload_to_litterbox(file_path):
    url = "https://litterbox.catbox.moe/resources/internals/api.php"
    try:
        cmd = [
            "curl", "-s", "-k", "-A", USER_AGENT,
            "-F", "reqtype=fileupload",
            "-F", "time=72h",
            "-F", f"fileToUpload=@{file_path}",
            url
        ]
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        output_url = result.stdout.strip()
        if result.returncode == 0 and output_url.startswith("https://"):
            return True, output_url
        else:
            return False, f"فشل الرفع: {output_url or result.stderr}"
    except Exception as e:
        return False, f"خطأ الاتصال: {str(e)}"

# ==================== لوحات المفاتيح ====================
def main_keyboard(user_id):
    markup = types.ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
    markup.add(types.KeyboardButton("📡 البث الحالي"), types.KeyboardButton("📁 ملفاتي"))
    markup.add(types.KeyboardButton("🗑️ حذف ملف"), types.KeyboardButton("📖 طريقة الاستخدام"))
    if user_id == ADMIN_ID:
        markup.add(types.KeyboardButton("⚙️ لوحة التحكم"))
    return markup

# ==================== الأوامر العامة ====================
@bot.message_handler(commands=["start"])
def send_welcome(message):
    if is_blocked(message.from_user.id): return
    register_user(message.from_user)
    txt = (
        f"أهلاً بك **{message.from_user.first_name}** 📡\n\n"
        "📤 **لرفع ملف بث:** أرسل الملف مباشرة للبوت (فيديو / صوت).\n"
        "سيقوم البوت برفعه مؤقتاً وتجهيز زر بدء البث المباشر فوراً!"
    )
    bot.send_message(message.chat.id, txt, reply_markup=main_keyboard(message.from_user.id), parse_mode="Markdown")

# ==================== استقبال وتجهيز الملفات ====================
@bot.message_handler(content_types=["video", "audio", "document"])
def handle_media_upload(message):
    if is_blocked(message.from_user.id): return
    register_user(message.from_user)
    
    chat_id = message.chat.id
    status_msg = bot.send_message(chat_id, "⏳ **جاري تنزيل الملف وتجهيز مساحة التخزين المؤقتة...**", parse_mode="Markdown")

    try:
        file_size = 0
        file_name = "media_file"
        
        if message.video:
            media_obj = message.video
            file_name = media_obj.file_name or f"video_{message.message_id}.mp4"
            file_size = media_obj.file_size
        elif message.audio:
            media_obj = message.audio
            file_name = media_obj.file_name or f"audio_{message.message_id}.mp3"
            file_size = media_obj.file_size
        elif message.document:
            media_obj = message.document
            file_name = media_obj.file_name or f"file_{message.message_id}"
            file_size = media_obj.file_size

        file_info = bot.get_file(media_obj.file_id)
        download_url = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file_info.file_path}"
        
        temp_path = f"temp_{message.message_id}_{file_name}"
        res = requests.get(download_url, stream=True)
        with open(temp_path, "wb") as f:
            for chunk in res.iter_content(chunk_size=1024*1024):
                if chunk: f.write(chunk)

        bot.edit_message_text("☁️ **جاري الرفع إلى التخزين المؤقت...**", chat_id=chat_id, message_id=status_msg.message_id, parse_mode="Markdown")
        success, final_url = upload_to_litterbox(temp_path)

        if os.path.exists(temp_path):
            os.remove(temp_path)

        if success:
            uid = str(message.from_user.id)
            db["files"][uid].append({"name": file_name, "url": final_url, "size": format_size(file_size)})
            save_db(db)

            # بطاقة تجهيز الملف (كما بالنقطة 2)
            card_text = (
                "✅ **تم تجهيز الملف بنجاح!**\n\n"
                f"📂 **الاسم:** `{file_name}`\n"
                f"📦 **الحجم:** `{format_size(file_size)}`\n\n"
                "هل تريد بدء بث هذا الملف الآن؟"
            )
            
            markup = types.InlineKeyboardMarkup(row_width=2)
            btn_start = types.InlineKeyboardButton("▶️ بدء بث", callback_data=f"prep_stream|{final_url}")
            btn_del = types.InlineKeyboardButton("🗑️ حذف الملف", callback_data=f"del_file|{final_url}")
            btn_my = types.InlineKeyboardButton("📁 ملفاتي", callback_data="my_files_btn")
            markup.add(btn_start, btn_del)
            markup.add(btn_my)

            bot.edit_message_text(card_text, chat_id=chat_id, message_id=status_msg.message_id, reply_markup=markup, parse_mode="Markdown")
        else:
            bot.edit_message_text(f"❌ **فشل التجهيز:** {final_url}", chat_id=chat_id, message_id=status_msg.message_id)

    except Exception as e:
        bot.edit_message_text(f"❌ حدث خطأ: `{str(e)}`", chat_id=chat_id, message_id=status_msg.message_id, parse_mode="Markdown")

# ==================== تجهيز وأمر البث ====================
stream_temp_store = {}

@bot.callback_query_handler(func=lambda call: call.data.startswith("prep_stream|"))
def prep_stream_step(call):
    media_url = call.data.split("|")[1]
    uid = call.from_user.id
    stream_temp_store[uid] = {"media_url": media_url}

    msg = bot.send_message(
        call.message.chat.id,
        "🌐 **أرسل رابط سيرفر الـ RTMP الخاص بالبث:**\n(مثال: `rtmps://dc4-1.rtmp.t.me/s/xxxxx`)",
        parse_mode="Markdown"
    )
    bot.register_next_step_handler(msg, get_rtmp_url)

def get_rtmp_url(message):
    uid = message.from_user.id
    stream_temp_store[uid]["rtmp_server"] = message.text.strip()
    
    msg = bot.send_message(message.chat.id, "🔑 **أرسل الآن مفتاح البث (Stream Key):**", parse_mode="Markdown")
    bot.register_next_step_handler(msg, get_stream_key)

def get_stream_key(message):
    uid = message.from_user.id
    key = message.text.strip()
    data = stream_temp_store[uid]
    full_rtmp = f"{data['rtmp_server'].rstrip('/')}/{key}"
    data["full_rtmp"] = full_rtmp

    # صياغة أمر FFmpeg (النقطة 4)
    ffmpeg_cmd = (
        f"ffmpeg -re -i file.mp4 \\\n"
        f"-c:v libx264 -preset veryfast -b:v 2500k \\\n"
        f"-c:a aac -b:a 128k -f flv \"{full_rtmp}\""
    )

    txt = (
        "🚀 **أمر البث التلقائي لـ GitHub Actions:**\n\n"
        f"```bash\n{ffmpeg_cmd}\n```\n"
        "سيقوم النظام بتنظيف البث القديم أولاً ثم التنزيل محلياً والبث 24/7."
    )
    
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("🚀 إطلاق البث الآن", callback_data="exec_gh_launch"))
    bot.send_message(message.chat.id, txt, reply_markup=markup, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data == "exec_gh_launch")
def execute_github_launch(call):
    uid = call.from_user.id
    data = stream_temp_store.get(uid)
    if not data:
        bot.answer_callback_query(call.id, "❌ انتهت الجلسة، أعد المحاولة.", show_alert=True)
        return

    bot.answer_callback_query(call.id, "⏳ جاري إرسال إشارة التشغيل لـ GitHub...")
    
    url = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/actions/workflows/stream.yml/dispatches"
    headers = {"Authorization": f"token {GH_PAT}", "Accept": "application/vnd.github+json"}
    payload = {
        "ref": "main",
        "inputs": {
            "media_url": data["media_url"],
            "rtmp_url": data["full_rtmp"],
            "action_type": "start"
        }
    }

    try:
        res = requests.post(url, headers=headers, json=payload)
        if res.status_code == 204:
            db["active_stream"] = {"status": "Running", "started_at": time.strftime("%H:%M:%S"), "url": data["media_url"]}
            save_db(db)
            bot.send_message(call.message.chat.id, "✅ **تم إطلاق البث وحماية الـ Runner بنجاح!**", parse_mode="Markdown")
        else:
            bot.send_message(call.message.chat.id, f"❌ **خطأ GitHub API ({res.status_code}):** `{res.text}`", parse_mode="Markdown")
    except Exception as e:
        bot.send_message(call.message.chat.id, f"❌ حدث خطأ: `{str(e)}`", parse_mode="Markdown")

# ==================== إدارة البث والأزرار (النقطة 8) ====================
@bot.message_handler(func=lambda msg: msg.text == "📡 البث الحالي")
def stream_status_menu(message):
    st = db.get("active_stream", {})
    status = st.get("status", "متوقف 🔴")
    time_start = st.get("started_at", "غير محدد")
    
    msg = (
        f"📡 **حالة البث المباشر:**\n\n"
        f"📊 **الحالة:** `{status}`\n"
        f"⏱️ **وقت البدء:** `{time_start}`\n"
    )
    
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("🔴 إيقاف البث", callback_data="st_action_stop"),
        types.InlineKeyboardButton("🔄 إعادة تشغيل", callback_data="exec_gh_launch")
    )
    markup.add(types.InlineKeyboardButton("🧹 تنظيف المساحة", callback_data="st_action_clean"))
    
    bot.send_message(message.chat.id, msg, reply_markup=markup, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data in ["st_action_stop", "st_action_clean"])
def handle_stream_controls(call):
    action = call.data
    url = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/actions/workflows/stream.yml/dispatches"
    headers = {"Authorization": f"token {GH_PAT}", "Accept": "application/vnd.github+json"}
    
    payload = {"ref": "main", "inputs": {"media_url": "", "rtmp_url": "", "action_type": "stop"}}
    requests.post(url, headers=headers, json=payload)

    if action == "st_action_stop":
        db["active_stream"] = {"status": "متوقف 🔴", "started_at": "-"}
        save_db(db)
        bot.send_message(call.message.chat.id, "🔴 **تم إرسال أمر إيقاف البث فوراً.**", parse_mode="Markdown")
    else:
        bot.send_message(call.message.chat.id, "🧹 **جاري تفريغ مساحة السيرفر وملفات FFmpeg...**\n\n✅ تم التنظيف بنجاح!", parse_mode="Markdown")

# ==================== لوحة التحكم والتنظيف التلقائي (النقطة 6) ====================
@bot.message_handler(func=lambda msg: msg.text == "⚙️ لوحة التحكم" and msg.from_user.id == ADMIN_ID)
def admin_control_panel(message):
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("🧹 تفريغ مساحة السيرفر", callback_data="st_action_clean"),
        types.InlineKeyboardButton("📊 حالة التخزين", callback_data="admin_storage")
    )
    markup.add(
        types.InlineKeyboardButton("📡 البث الحالي", callback_data="admin_stream_info"),
        types.InlineKeyboardButton("👥 المستخدمين", callback_data="admin_users_count")
    )
    bot.send_message(message.chat.id, "⚙️ **لوحة التحكم المتقدمة:**", reply_markup=markup, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data.startswith("admin_"))
def admin_actions(call):
    if call.from_user.id != ADMIN_ID: return
    data = call.data
    
    if data == "admin_users_count":
        bot.answer_callback_query(call.id, f"👥 عدد المستخدمين: {len(db['users'])}", show_alert=True)
    elif data == "admin_storage":
        bot.answer_callback_query(call.id, "📊 التخزين: مؤقت داخل Runner (يتم التنظيف تلقائياً)", show_alert=True)
    elif data == "admin_stream_info":
        st = db.get("active_stream", {}).get("status", "متوقف 🔴")
        bot.answer_callback_query(call.id, f"📡 البث الحالي: {st}", show_alert=True)

# ==================== حلقة تشغيل البوت ====================
print("✅ البوت يعمل بالنظام الجديد والتنظيف التلقائي للمساحة...")
while True:
    try:
        bot.polling(none_stop=True, timeout=60, long_polling_timeout=60)
    except Exception as e:
        time.sleep(3)
