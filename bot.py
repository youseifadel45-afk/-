# -*- coding: utf-8 -*-
import os
import json
import time
import math
import subprocess
import requests
import telebot
from telebot import types

# ==================== الإعدادات الأساسية ====================
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = 8358047016  # ID المطور الخاص بك

# إعدادات GitHub API لتشغيل البث بنقرة زر
GH_PAT = os.getenv("GH_PAT")  # Personal Access Token
REPO_OWNER = os.getenv("REPO_OWNER")  # اسم مستخدم GitHub
REPO_NAME = os.getenv("REPO_NAME")    # اسم المستودع

if not BOT_TOKEN:
    raise ValueError("⚠️ خطأ: لم يتم العثور على BOT_TOKEN في متغيرات البيئة!")

bot = telebot.TeleBot(BOT_TOKEN)
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0 Safari/537.36"
DB_FILE = "database.json"

# ==================== إدارة قاعدة البيانات المحليّة ====================
def load_db():
    if not os.path.exists(DB_FILE):
        return {"users": {}, "files": {}, "blocked": []}
    try:
        with open(DB_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"users": {}, "files": {}, "blocked": []}

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
            "last_name": user.last_name or "",
            "username": user.username or "بدون_يوزر",
            "joined_at": time.time()
        }
        db["files"][uid] = []
        save_db(db)
        
        info = (
            f"🔔 **مستخدم جديد دخل البوت!**\n\n"
            f"👤 **الاسم:** {user.first_name} {user.last_name or ''}\n"
            f"🏷 **اليوزر:** @{user.username or 'بدون_يوزر'}\n"
            f"🆔 **ID:** `{user.id}`"
        )
        try:
            bot.send_message(ADMIN_ID, info, parse_mode="Markdown")
        except Exception as e:
            print(f"Notify Admin Error: {e}")

def save_user_file(user_id, file_url, file_type, file_name):
    uid = str(user_id)
    if uid not in db["files"]:
        db["files"][uid] = []
    
    file_entry = {
        "url": file_url,
        "type": file_type,
        "name": file_name,
        "date": time.strftime("%Y-%m-%d %H:%M")
    }
    db["files"][uid].append(file_entry)
    save_db(db)

def delete_user_file_by_url(user_id, file_url):
    uid = str(user_id)
    if uid in db["files"]:
        initial_len = len(db["files"][uid])
        db["files"][uid] = [f for f in db["files"][uid] if f["url"] != file_url]
        if len(db["files"][uid]) < initial_len:
            save_db(db)
            return True
    return False

# ==================== إعداد قائمة الأوامر (Menu) ====================
def setup_bot_commands():
    try:
        commands = [
            types.BotCommand("start", "تشغيل البوت والرجوع للقائمة الرئيسية"),
            types.BotCommand("help", "طريقة الاستخدام والتعليمات")
        ]
        bot.set_my_commands(commands)
    except Exception as e:
        print(f"Failed to set commands: {e}")

setup_bot_commands()

# ==================== الرفع على السحابة ====================
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
        return False, f"خطأ بالاتصال: {str(e)}"

# ==================== لوحات الأزرار ====================
def main_keyboard(user_id):
    markup = types.ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
    btn_stream = types.KeyboardButton("🎬 إنشاء بث جديد")
    btn_my_files = types.KeyboardButton("📁 ملفاتي")
    btn_delete = types.KeyboardButton("🗑️ حذف ملف")
    btn_help = types.KeyboardButton("📖 طريقة الاستخدام")
    
    markup.add(btn_stream, btn_my_files)
    markup.add(btn_delete, btn_help)
    
    if user_id == ADMIN_ID:
        btn_admin = types.KeyboardButton("⚙️ لوحة التحكم")
        markup.add(btn_admin)
        
    return markup

# ==================== الأوامر والتفاعلات ====================
@bot.message_handler(commands=["start"])
@bot.message_handler(func=lambda msg: msg.text in ["بداية البوت", "الرجوع للرئيسية 🔙"])
def send_welcome(message):
    if is_blocked(message.from_user.id):
        bot.send_message(message.chat.id, "🚫 تم حظرك من استخدام هذا البوت.")
        return

    register_user(message.from_user)
    welcome_txt = (
        f"أهلاً بك يا **{message.from_user.first_name}** في بوت إنشاء وتجهيز البث المباشر 📡\n\n"
        "📤 **لرفع ملف:** أرسل أي ملف (فيديو، صوت، موسيقى) وسيتم حفظه ورفعه تلقائياً.\n"
        "🎬 **لإنشاء بث:** اضغط على زر '🎬 إنشاء بث جديد'.\n"
        "📁 **لمعاينة ملفاتك:** اضغط على زر '📁 ملفاتي'.\n"
        "👇 استخدم الأزرار أسفله للتنقل:"
    )
    bot.send_message(message.chat.id, welcome_txt, reply_markup=main_keyboard(message.from_user.id), parse_mode="Markdown")

@bot.message_handler(commands=["help"])
@bot.message_handler(func=lambda msg: msg.text == "📖 طريقة الاستخدام")
def show_help(message):
    if is_blocked(message.from_user.id): return
    help_text = (
        "📖 **تعليمات الاستخدام:**\n\n"
        "1️⃣ أرسل أي فيديو أو ملف صوتي للبوت لرفعه على السحابة وحفظه في حسابك.\n"
        "2️⃣ اختر '🎬 إنشاء بث جديد' واتبع الخطوات لاختيار الجودة، الصوت، وإدخال سيرفر البث.\n"
        "3️⃣ سيعطيك البوت زر لتشغيل البث مباشرة على GitHub Actions أو أمر جاهز للـ CMD."
    )
    bot.send_message(message.chat.id, help_text, parse_mode="Markdown")

# ==================== قسم ملفاتي ====================
@bot.message_handler(func=lambda msg: msg.text == "📁 ملفاتي")
def my_files_menu(message):
    if is_blocked(message.from_user.id): return
    markup = types.InlineKeyboardMarkup(row_width=2)
    btn_audio = types.InlineKeyboardButton("🎵 ملفات صوتية", callback_data="files_audio")
    btn_video = types.InlineKeyboardButton("🎥 ملفات فيديو", callback_data="files_video")
    markup.add(btn_audio, btn_video)
    
    bot.send_message(message.chat.id, "📁 **اختر قسم الملفات التي ترغب بعرضها:**", reply_markup=markup, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data in ["files_audio", "files_video"])
def show_user_files_list(call):
    uid = str(call.from_user.id)
    file_type = "audio" if call.data == "files_audio" else "video"
    type_title = "الصوتية 🎵" if file_type == "audio" else "الفيديو 🎥"
    
    user_files = [f for f in db["files"].get(uid, []) if f["type"] == file_type]
    
    if not user_files:
        bot.answer_callback_query(call.id, f"لا توجد ملفات {type_title} محفوظة لديك!", show_alert=True)
        return
        
    msg = f"📋 **قائمة ملفات {type_title} الخاصة بك:**\n\n"
    for idx, f in enumerate(user_files, 1):
        msg += f"{idx}. [{f['name']}]({f['url']}) - 📅 {f['date']}\n"
        
    bot.edit_message_text(msg, chat_id=call.message.chat.id, message_id=call.message.message_id, parse_mode="Markdown", disable_web_page_preview=True)

# ==================== قسم حذف الملفات ====================
@bot.message_handler(func=lambda msg: msg.text == "🗑️ حذف ملف")
def ask_delete_file(message):
    if is_blocked(message.from_user.id): return
    msg = bot.send_message(message.chat.id, "🔗 **أرسل الآن رابط الملف الذي تريد حذفه من حسابك:**", parse_mode="Markdown")
    bot.register_next_step_handler(msg, process_delete_file)

def process_delete_file(message):
    url = message.text.strip()
    success = delete_user_file_by_url(message.from_user.id, url)
    if success:
        bot.send_message(message.chat.id, "✅ **تم حذف الملف بنجاح من قائمتك!**", parse_mode="Markdown")
    else:
        bot.send_message(message.chat.id, "❌ **لم يتم العثور على هذا الرابط في ملفاتك!**", parse_mode="Markdown")

# ==================== قسم لوحة التحكم ====================
@bot.message_handler(func=lambda msg: msg.text == "⚙️ لوحة التحكم" and msg.from_user.id == ADMIN_ID)
def admin_panel(message):
    markup = types.InlineKeyboardMarkup(row_width=2)
    btn_stats = types.InlineKeyboardButton("📊 الإحصائيات", callback_data="admin_stats")
    btn_bc = types.InlineKeyboardButton("📢 إذاعة للمستخدمين", callback_data="admin_broadcast")
    markup.add(btn_stats, btn_bc)
    bot.send_message(message.chat.id, "⚙️ **مرحباً بك في لوحة تحكم المطور:**", reply_markup=markup, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data.startswith("admin_"))
def handle_admin_actions(call):
    if call.from_user.id != ADMIN_ID: return
    
    if call.data == "admin_stats":
        total_users = len(db["users"])
        total_files = sum([len(files) for files in db["files"].values()])
        msg = f"📊 **إحصائيات البوت:**\n\n👥 عدد المستخدمين: `{total_users}`\n📁 إجمالي الملفات المرفوعة: `{total_files}`"
        bot.answer_callback_query(call.id)
        bot.send_message(call.message.chat.id, msg, parse_mode="Markdown")
        
    elif call.data == "admin_broadcast":
        msg = bot.send_message(call.message.chat.id, "📢 **أرسل الرسالة التي تريد إرسالها لجميع المستخدمين:**")
        bot.register_next_step_handler(msg, process_broadcast)

def process_broadcast(message):
    users = db["users"]
    count = 0
    for uid in users:
        try:
            bot.copy_message(chat_id=int(uid), from_chat_id=message.chat.id, message_id=message.message_id)
            count += 1
            time.sleep(0.05)
        except Exception:
            pass
    bot.send_message(ADMIN_ID, f"✅ تم إرسال الإذاعة بنجاح إلى `{count}` مستخدم.", parse_mode="Markdown")

# ==================== معالجة رفع الملفات ====================
@bot.message_handler(content_types=["audio", "video", "document", "voice"])
def handle_uploads(message):
    if is_blocked(message.from_user.id): return
    register_user(message.from_user)
    
    chat_id = message.chat.id
    status_msg = bot.send_message(chat_id, "⏳ **جاري تنزيل الملف وتجهيزه للرفع...**", parse_mode="Markdown")

    try:
        file_type = "video"
        file_name = "media_file"
        
        if message.video:
            media_obj = message.video
            file_name = media_obj.file_name or f"video_{message.message_id}.mp4"
        elif message.audio:
            media_obj = message.audio
            file_name = media_obj.file_name or f"audio_{message.message_id}.mp3"
            file_type = "audio"
        elif message.document:
            media_obj = message.document
            file_name = media_obj.file_name or f"doc_{message.message_id}"
            file_type = "video" if file_name.endswith(('.mp4', '.mkv', '.avi', '.mov')) else "audio"
        else:
            bot.edit_message_text("❌ نوع الملف غير مدعوم.", chat_id=chat_id, message_id=status_msg.message_id)
            return

        file_info = bot.get_file(media_obj.file_id)
        file_url = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file_info.file_path}"
        
        temp_path = f"temp_{message.message_id}_{file_name}"
        res = requests.get(file_url, stream=True)
        with open(temp_path, "wb") as f:
            for chunk in res.iter_content(chunk_size=1024*1024):
                if chunk: f.write(chunk)

        bot.edit_message_text("☁️ **جاري الرفع إلى السحابة...**", chat_id=chat_id, message_id=status_msg.message_id, parse_mode="Markdown")
        success, result_url = upload_to_litterbox(temp_path)

        if os.path.exists(temp_path):
            os.remove(temp_path)

        if success:
            save_user_file(message.from_user.id, result_url, file_type, file_name)
            msg_text = (
                f"✅ **تم رفع وحفظ الملف بنجاح!**\n\n"
                f"📂 **اسم الملف:** `{file_name}`\n"
                f"🔗 **الرابط المباشر:**\n`{result_url}`\n\n"
                f"💡 يمكنك استخدام هذا الرابط الآن عند **إنشاء بث جديد**."
            )
            bot.edit_message_text(msg_text, chat_id=chat_id, message_id=status_msg.message_id, parse_mode="Markdown")
        else:
            bot.edit_message_text(f"❌ **فشل الرفع:** {result_url}", chat_id=chat_id, message_id=status_msg.message_id)

    except Exception as e:
        bot.edit_message_text(f"❌ حدث خطأ أثناء المعالجة: `{str(e)}`", chat_id=chat_id, message_id=status_msg.message_id, parse_mode="Markdown")

# ==================== معالج إنشاء البث المباشر ====================
stream_sessions = {}

@bot.message_handler(func=lambda msg: msg.text == "🎬 إنشاء بث جديد")
def start_stream_wizard(message):
    if is_blocked(message.from_user.id): return
    uid = message.from_user.id
    stream_sessions[uid] = {}
    
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("🎬 بث فيديو", callback_data="st_type_video"),
        types.InlineKeyboardButton("🎧 بث صوتي", callback_data="st_type_audio")
    )
    bot.send_message(message.chat.id, "🎥 **اختر نوع البث الذي ترغب بإنشائه:**", reply_markup=markup, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data.startswith("st_type_"))
def step_stream_type(call):
    uid = call.from_user.id
    st_type = call.data.split("_")[-1]
    stream_sessions[uid]["type"] = st_type
    
    uid_str = str(uid)
    user_files = [f for f in db["files"].get(uid_str, []) if f["type"] == st_type]
    
    markup = types.InlineKeyboardMarkup(row_width=1)
    for f in user_files[:5]:
        markup.add(types.InlineKeyboardButton(f"📁 {f['name']}", callback_data=f"st_file_select"))
        
    bot.edit_message_text(
        "🔗 **أرسل رابط الملف الذي تريد بثه (فيديو/صوت):**\n"
        "(يمكنك إرسال رابط مباشر من السحابة أو استخدام ملف مرفوع سابقاً)",
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        reply_markup=markup if user_files else None,
        parse_mode="Markdown"
    )
    bot.register_next_step_handler(call.message, step_stream_url)

def step_stream_url(message):
    uid = message.from_user.id
    stream_sessions[uid]["url"] = message.text.strip()
    
    if stream_sessions[uid]["type"] == "video":
        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.add(
            types.InlineKeyboardButton("360p (منخفض)", callback_data="st_res_360p"),
            types.InlineKeyboardButton("480p (متوسط)", callback_data="st_res_480p"),
            types.InlineKeyboardButton("⭐ 720p (تليجرام موصى به)", callback_data="st_res_720p"),
            types.InlineKeyboardButton("1080p (FHD)", callback_data="st_res_1080p")
        )
        bot.send_message(message.chat.id, "📐 **اختر جودة عرض الفيديو البث:**", reply_markup=markup, parse_mode="Markdown")
    else:
        stream_sessions[uid]["res"] = "720p"
        ask_audio_bitrate(message.chat.id, uid)

@bot.callback_query_handler(func=lambda call: call.data.startswith("st_res_"))
def step_stream_res(call):
    uid = call.from_user.id
    res = call.data.replace("st_res_", "")
    stream_sessions[uid]["res"] = res
    ask_audio_bitrate(call.message.chat.id, uid)

def ask_audio_bitrate(chat_id, uid):
    markup = types.InlineKeyboardMarkup(row_width=3)
    markup.add(
        types.InlineKeyboardButton("64 kbps", callback_data="st_bitrate_64k"),
        types.InlineKeyboardButton("⭐ 128 kbps (موصى به)", callback_data="st_bitrate_128k"),
        types.InlineKeyboardButton("192 kbps", callback_data="st_bitrate_192k")
    )
    bot.send_message(chat_id, "🎵 **اختر جودة الصوت (Audio Bitrate):**", reply_markup=markup, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data.startswith("st_bitrate_"))
def step_stream_bitrate(call):
    uid = call.from_user.id
    bitrate = call.data.replace("st_bitrate_", "")
    stream_sessions[uid]["bitrate"] = bitrate
    
    markup = types.InlineKeyboardMarkup(row_width=3)
    markup.add(
        types.InlineKeyboardButton("100% (طبيعي)", callback_data="st_vol_1.0"),
        types.InlineKeyboardButton("150% (مرتفع)", callback_data="st_vol_1.5"),
        types.InlineKeyboardButton("200% (مضاعف)", callback_data="st_vol_2.0")
    )
    bot.send_message(call.message.chat.id, "🔊 **اختر مستوى صوت البث:**", reply_markup=markup, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data.startswith("st_vol_"))
def step_stream_vol(call):
    uid = call.from_user.id
    vol = call.data.replace("st_vol_", "")
    stream_sessions[uid]["vol"] = vol
    
    msg = bot.send_message(call.message.chat.id, "🌐 **أرسل الآن رابط سيرفر الـ RTMP الخاص بالبث:**\n(مثال: `rtmp://ingress.rmtp.youtube.com/live2` أو سيرفر التليجرام)", parse_mode="Markdown")
    bot.register_next_step_handler(msg, step_stream_rtmp)

def step_stream_rtmp(message):
    uid = message.from_user.id
    stream_sessions[uid]["rtmp"] = message.text.strip()
    
    msg = bot.send_message(message.chat.id, "🔑 **أرسل الآن مفتاح البث (Stream Key):**", parse_mode="Markdown")
    bot.register_next_step_handler(msg, step_stream_key)

def step_stream_key(message):
    uid = message.from_user.id
    stream_sessions[uid]["key"] = message.text.strip()
    
    data = stream_sessions[uid]
    full_rtmp = f"{data['rtmp'].rstrip('/')}/{data['key']}"
    
    if data["type"] == "video":
        ffmpeg_cmd = f'ffmpeg -re -stream_loop -1 -i "{data["url"]}" -c:v libx264 -preset veryfast -b:v 2500k -maxrate 2500k -bufsize 5000k -pix_fmt yuv420p -g 50 -af "volume={data["vol"]}" -c:a aac -b:a {data["bitrate"]} -ar 44100 -ac 2 -f flv "{full_rtmp}"'
    else:
        ffmpeg_cmd = f'ffmpeg -re -stream_loop -1 -i "{data["url"]}" -vn -af "volume={data["vol"]}" -c:a aac -b:a {data["bitrate"]} -ar 44100 -ac 2 -f flv "{full_rtmp}"'

    response_text = (
        "🎉 **تم تجهيز بيانات وإعدادات البث بنجاح!**\n\n"
        "💻 **أمر التشغيل عبر الـ CMD / Linux:**\n"
        f"```bash\n{ffmpeg_cmd}\n```\n\n"
        "🚀 **التشغيل عبر GitHub Actions (24/7):**\n"
        "اضغط على الزر أدناه لإرسال البث وإضافته إلى حالة (Running) على سيرفرات GitHub مباشرة!"
    )
    
    markup = types.InlineKeyboardMarkup()
    btn_run = types.InlineKeyboardButton("🚀 بدء البث الآن (Start Stream)", callback_data=f"run_gh_stream")
    markup.add(btn_run)
    
    bot.send_message(message.chat.id, response_text, reply_markup=markup, parse_mode="Markdown")

# ==================== تشغيل الـ Stream تلقائياً عبر GitHub API ====================
@bot.callback_query_handler(func=lambda call: call.data == "run_gh_stream")
def trigger_github_stream(call):
    uid = call.from_user.id
    if uid not in stream_sessions or "url" not in stream_sessions[uid]:
        bot.answer_callback_query(call.id, "❌ لم يتم العثور على جلسة بث نشطة!", show_alert=True)
        return

    # التحقق من وجود بيانات GitHub المطلوبة
    if not GH_PAT or not REPO_OWNER or not REPO_NAME:
        bot.send_message(
            call.message.chat.id,
            "❌ **خطأ في الإعدادات:**\nلم يتم التعرف على متغيّرات (GH_PAT أو REPO_OWNER أو REPO_NAME) داخل البوت.\n"
            "تأكد من إضافتها في قسم Secrets لملف `bot.yml`.",
            parse_mode="Markdown"
        )
        return

    data = stream_sessions[uid]
    full_rtmp = f"{data['rtmp'].rstrip('/')}/{data['key']}"
    
    bot.answer_callback_query(call.id, "⏳ جاري إرسال إشارة البث إلى GitHub Actions...")
    
    url = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/actions/workflows/stream.yml/dispatches"
    headers = {
        "Authorization": f"token {GH_PAT}",
        "Accept": "application/vnd.github+json"
    }
    payload = {
        "ref": "main",  # تأكد أنه اسم الفرع الرئيسي لديك (main أو master)
        "inputs": {
            "media_url": data["url"],
            "rtmp_url": full_rtmp,
            "volume": data["vol"],
            "bitrate": data["bitrate"]
        }
    }
    
    try:
        res = requests.post(url, headers=headers, json=payload)
        # تصحيح كود النجاح للـ GitHub API (204 No Content)
        if res.status_code == 204:
            bot.send_message(
                call.message.chat.id,
                "✅ **تم إطلاق البث بنجاح!**\n\n"
                "🟢 حالة البث الآن: `Running` على سيرفرات GitHub.\n"
                "📡 يمكنك التحقق من البث عبر قناتك أو منصتك الآن.",
                parse_mode="Markdown"
            )
        else:
            bot.send_message(
                call.message.chat.id,
                f"❌ **فشل إطلاق البث تلقائياً!**\n"
                f"كود الاستجابة: `{res.status_code}`\n"
                f"التفاصيل: `{res.text}`\n\n"
                f"💡 تأكد من صحة التوكن `GH_PAT` واسم الحساب والمستودع.",
                parse_mode="Markdown"
            )
    except Exception as e:
        bot.send_message(call.message.chat.id, f"❌ حدث خطأ أثناء الاتصال بـ GitHub API: `{str(e)}`", parse_mode="Markdown")

# ==================== حلقة تشغيل البوت ====================
print("✅ البوت يعمل بنجاح مع إضافة ميزة التشغيل التلقائي للبث...")

while True:
    try:
        bot.polling(none_stop=True, timeout=60, long_polling_timeout=60)
    except Exception as e:
        print(f"⚠️ خطأ بالاتصال، إعادة التوصيل: {e}")
        time.sleep(3)

