# -*- coding: utf-8 -*-
import os
import json
import time
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
DB_FILE = "database.json"

# ==================== إدارة قاعدة البيانات ====================
def load_db():
    if not os.path.exists(DB_FILE):
        return {"users": {}, "files": {}, "blocked": [], "active_stream": {}}
    try:
        with open(DB_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            if "active_stream" not in data: data["active_stream"] = {}
            if "blocked" not in data: data["blocked"] = []
            if "users" not in data: data["users"] = {}
            if "files" not in data: data["files"] = {}
            return data
    except Exception:
        return {"users": {}, "files": {}, "blocked": [], "active_stream": {}}

def save_db(data):
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

db = load_db()

def register_user(user):
    uid = str(user.id)
    if uid not in db["users"]:
        db["users"][uid] = {
            "first_name": user.first_name,
            "username": user.username or "بدون_يوزر",
            "joined_at": time.strftime("%Y-%m-%d %H:%M:%S")
        }
        db["files"][uid] = []
        save_db(db)

def is_blocked(user_id):
    return str(user_id) in [str(i) for i in db.get("blocked", [])]

def format_size(size_in_bytes):
    if not size_in_bytes: return "غير معروف"
    if size_in_bytes < 1024 * 1024:
        return f"{round(size_in_bytes / 1024, 2)} KB"
    elif size_in_bytes < 1024 * 1024 * 1024:
        return f"{round(size_in_bytes / (1024 * 1024), 2)} MB"
    else:
        return f"{round(size_in_bytes / (1024 * 1024 * 1024), 2)} GB"

# ==================== خدمة تحويل رابط التلجرام لرابط بث ثابت ====================
def upload_to_permanent_link(file_info):
    """تحميل الملف من التلجرام ورفعه لـ Litterbox للحصول على رابط بث مباشر ثابت 100%"""
    try:
        tg_url = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file_info.file_path}"
        r = requests.get(tg_url, stream=True)
        files = {'fileToUpload': ('media_stream', r.raw)}
        data = {'reqtype': 'fileupload', 'time': '72h'}
        up = requests.post('https://litterbox.catbox.moe/resources/internals/api.php', files=files, data=data)
        if up.status_code == 200 and up.text.startswith("http"):
            return up.text.strip()
    except Exception:
        pass
    # في حال الفشل نستخدم رابط التلجرام الفوري
    return f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file_info.file_path}"

# ==================== إدارة GitHub API ====================
def send_github_dispatch(action_type="start", media_url="", rtmp_url=""):
    if not GH_PAT or not REPO_OWNER or not REPO_NAME:
        return False, "⚠️ بيانات GitHub غير مكتملة!"

    url = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/actions/workflows/stream.yml/dispatches"
    headers = {"Authorization": f"token {GH_PAT}", "Accept": "application/vnd.github+json"}
    payload = {"ref": "main", "inputs": {"action_type": action_type, "media_url": media_url, "rtmp_url": rtmp_url}}
    try:
        res = requests.post(url, headers=headers, json=payload)
        return (True, "Success") if res.status_code == 204 else (False, f"كود {res.status_code}")
    except Exception as e:
        return False, str(e)

def cancel_running_workflows():
    """إلغاء فوري لجميع الـ Runs النشطة حالياً لإيقاف البث بدلاً من الانتظار"""
    if not GH_PAT or not REPO_OWNER or not REPO_NAME: return False
    url = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/actions/runs?status=in_progress"
    headers = {"Authorization": f"token {GH_PAT}", "Accept": "application/vnd.github+json"}
    try:
        res = requests.get(url, headers=headers)
        if res.status_code == 200:
            runs = res.json().get("workflow_runs", [])
            for r in runs:
                cancel_url = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/actions/runs/{r['id']}/cancel"
                requests.post(cancel_url, headers=headers)
            return True
    except Exception:
        pass
    return False

def delete_old_github_runs():
    """حذف كافة سجلات الـ Workflow Runs والـ Logs القديمة عبر التصفح المترابط (Pagination)"""
    if not GH_PAT or not REPO_OWNER or not REPO_NAME:
        return False, "⚠️ بيانات GitHub غير مكتملة!"

    headers = {"Authorization": f"token {GH_PAT}", "Accept": "application/vnd.github+json"}
    total_deleted = 0
    page = 1
    try:
        while True:
            url = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/actions/runs?per_page=100&page={page}"
            res = requests.get(url, headers=headers)
            if res.status_code != 200: break
            runs = res.json().get("workflow_runs", [])
            if not runs: break

            deleted_in_page = 0
            for run in runs:
                if run.get("status") in ["completed", "cancelled", "failure"]:
                    del_url = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/actions/runs/{run['id']}"
                    requests.delete(del_url, headers=headers)
                    deleted_in_page += 1
                    total_deleted += 1

            if len(runs) < 100 or deleted_in_page == 0: break
            page += 1

        return True, f"تم مسح {total_deleted} سجل قديم بالكامل!"
    except Exception as e:
        return False, str(e)

# ==================== لوحات المفاتيح ====================
def main_keyboard(user_id):
    markup = types.ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
    markup.add(types.KeyboardButton("📡 البث الحالي"), types.KeyboardButton("📁 ملفاتي"))
    markup.add(types.KeyboardButton("🗑️ حذف ملف"), types.KeyboardButton("📖 طريقة الاستخدام"))
    if user_id == ADMIN_ID:
        markup.add(types.KeyboardButton("⚙️ لوحة التحكم"))
    return markup

# ==================== التعامل مع الأوامر وتصفية المحظورين ====================
@bot.message_handler(func=lambda msg: is_blocked(msg.from_user.id))
def blocked_user_reply(message):
    bot.send_message(message.chat.id, "🚫 **عذراً، لقد تم حظرك من استخدام هذا البوت.**", parse_mode="Markdown")

@bot.message_handler(commands=["start"])
def send_welcome(message):
    register_user(message.from_user)
    txt = (
        f"أهلاً بك **{message.from_user.first_name}** 📡\n\n"
        "📤 **للبث المباشر:** أرسل الملف (فيديو / صوت) وسيتم إنشاؤه كرابط بث مباشر ثابت!"
    )
    bot.send_message(message.chat.id, txt, reply_markup=main_keyboard(message.from_user.id), parse_mode="Markdown")

@bot.message_handler(commands=["help"])
@bot.message_handler(func=lambda msg: msg.text == "📖 طريقة الاستخدام")
def show_help(message):
    help_text = (
        "📖 **طريقة الاستخدام:**\n\n"
        "1️⃣ أرسل ملف الفيديو أو الصوت البوت.\n"
        "2️⃣ سينشئ البوت رابط بث مباشر ثابت دون استهلاك الـ Runner.\n"
        "3️⃣ اضغط **▶️ بدء بث** وتضمين الـ RTMP والـ Key."
    )
    bot.send_message(message.chat.id, help_text, parse_mode="Markdown")

# ==================== استقبال واستخراج روابط البث ====================
@bot.message_handler(content_types=["video", "audio", "document"])
def handle_media_upload(message):
    register_user(message.from_user)
    chat_id = message.chat.id
    status_msg = bot.send_message(chat_id, "⏳ **جاري إنشاء رابط بث ثابت للملف...**", parse_mode="Markdown")

    try:
        file_size, file_name = 0, "media_file"
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
        # تحويل لـ Permanent Streaming Link
        direct_url = upload_to_permanent_link(file_info)
        
        uid = str(message.from_user.id)
        if uid not in db["files"]: db["files"][uid] = []
        db["files"][uid].append({"name": file_name, "url": direct_url, "size": format_size(file_size)})
        save_db(db)

        card_text = (
            "✅ **تم تجهيز الملف ورابط البث المباشر!**\n\n"
            f"📂 **الاسم:** `{file_name}`\n"
            f"📦 **الحجم:** `{format_size(file_size)}`\n\n"
            "هل تريد بدء البث؟"
        )
        
        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.add(
            types.InlineKeyboardButton("▶️ بدء بث", callback_data=f"prep_stream|{direct_url}"),
            types.InlineKeyboardButton("🗑️ حذف الملف", callback_data=f"del_file|{direct_url}")
        )
        markup.add(types.InlineKeyboardButton("📁 ملفاتي", callback_data="my_files_btn"))

        bot.edit_message_text(card_text, chat_id=chat_id, message_id=status_msg.message_id, reply_markup=markup, parse_mode="Markdown")
    except Exception as e:
        bot.edit_message_text(f"❌ حدث خطأ: `{str(e)}`", chat_id=chat_id, message_id=status_msg.message_id, parse_mode="Markdown")

# ==================== تجهيز وتنفيذ البث ====================
stream_temp_store = {}

@bot.callback_query_handler(func=lambda call: call.data.startswith("prep_stream|"))
def prep_stream_step(call):
    media_url = call.data.split("|")[1]
    uid = call.from_user.id
    stream_temp_store[uid] = {"media_url": media_url}

    msg = bot.send_message(call.message.chat.id, "🌐 **أرسل رابط سيرفر الـ RTMP:**", parse_mode="Markdown")
    bot.register_next_step_handler(msg, get_rtmp_url)

def get_rtmp_url(message):
    uid = message.from_user.id
    stream_temp_store[uid]["rtmp_server"] = message.text.strip()
    msg = bot.send_message(message.chat.id, "🔑 **أرسل الآن مفتاح البث (Stream Key):**", parse_mode="Markdown")
    bot.register_next_step_handler(msg, get_stream_key)

def get_stream_key(message):
    uid = message.from_user.id
    key = message.text.strip()
    data = stream_temp_store.get(uid, {})
    full_rtmp = f"{data['rtmp_server'].rstrip('/')}/{key}"
    data["full_rtmp"] = full_rtmp

    ffmpeg_cmd = (
        f"ffmpeg -re -reconnect 1 -reconnect_at_eof 1 -reconnect_streamed 1 -reconnect_delay_max 10 \\\n"
        f"  -i \"{data['media_url']}\" \\\n"
        f"  -c:v libx264 -preset veryfast -b:v 2500k -c:a aac -b:a 128k -f flv \"{full_rtmp}\""
    )

    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("🚀 إطلاق البث الآن", callback_data="exec_gh_launch"))
    bot.send_message(message.chat.id, f"🚀 **جاهز للبث المباشر:**\n\n```bash\n{ffmpeg_cmd}\n```", reply_markup=markup, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data == "exec_gh_launch")
def execute_github_launch(call):
    uid = call.from_user.id
    data = stream_temp_store.get(uid)
    
    if not data or "media_url" not in data:
        active_st = db.get("active_stream", {})
        if active_st.get("media_url") and active_st.get("rtmp_url"):
            data = {"media_url": active_st["media_url"], "full_rtmp": active_st["rtmp_url"]}
        else:
            bot.answer_callback_query(call.id, "❌ لا توجد بيانات بث سابقة!", show_alert=True)
            return

    bot.answer_callback_query(call.id, "⏳ جاري بدء البث في GitHub Actions...")
    success, msg = send_github_dispatch("start", media_url=data["media_url"], rtmp_url=data["full_rtmp"])

    if success:
        db["active_stream"] = {
            "status": "Running 🟢",
            "started_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "media_url": data["media_url"],
            "rtmp_url": data["full_rtmp"]
        }
        save_db(db)
        bot.send_message(call.message.chat.id, "✅ **تم إطلاق البث المباشر بنجاح!**", parse_mode="Markdown")
    else:
        bot.send_message(call.message.chat.id, f"❌ **فشل التشغيل:** `{msg}`", parse_mode="Markdown")

# ==================== قسم الملفات ====================
@bot.message_handler(func=lambda msg: msg.text == "📁 ملفاتي")
@bot.callback_query_handler(func=lambda call: call.data == "my_files_btn")
def show_my_files(event):
    chat_id = event.chat.id if isinstance(event, types.Message) else event.message.chat.id
    uid = str(event.from_user.id if isinstance(event, types.Message) else event.from_user.id)
    
    user_files = db["files"].get(uid, [])
    if not user_files:
        txt = "📂 **لا توجد ملفات محفوظة حالياً.**"
        if isinstance(event, types.CallbackQuery): bot.answer_callback_query(event.id, txt, show_alert=True)
        else: bot.send_message(chat_id, txt, parse_mode="Markdown")
        return

    msg = "📋 **ملفاتك المحفوظة:**\n\n"
    markup = types.InlineKeyboardMarkup(row_width=1)
    for idx, f in enumerate(user_files, 1):
        msg += f"{idx}. [{f['name']}]({f['url']}) - `{f.get('size', 'N/A')}`\n"
        markup.add(types.InlineKeyboardButton(f"▶️ بث: {f['name']}", callback_data=f"prep_stream|{f['url']}"))

    bot.send_message(chat_id, msg, reply_markup=markup, parse_mode="Markdown", disable_web_page_preview=True)

@bot.message_handler(func=lambda msg: msg.text == "🗑️ حذف ملف")
@bot.callback_query_handler(func=lambda call: call.data.startswith("del_file|"))
def delete_file_handler(event):
    if isinstance(event, types.CallbackQuery):
        file_url = event.data.split("|")[1]
        uid = str(event.from_user.id)
        if uid in db["files"]:
            db["files"][uid] = [f for f in db["files"][uid] if f["url"] != file_url]
            save_db(db)
            bot.answer_callback_query(event.id, "✅ تم حذف الملف.", show_alert=True)
            bot.edit_message_text("🗑️ **تم حذف الملف بنجاح.**", chat_id=event.message.chat.id, message_id=event.message.message_id)
    else:
        show_my_files(event)

# ==================== إدارة البث والأزرار التفاعلية ====================
@bot.message_handler(func=lambda msg: msg.text == "📡 البث الحالي")
def stream_status_menu(message):
    st = db.get("active_stream", {})
    status = st.get("status", "متوقف 🔴")
    time_start = st.get("started_at", "غير محدد")
    
    msg_text = (
        f"📡 **حالة البث المباشر:**\n\n"
        f"📊 **الحالة:** `{status}`\n"
        f"⏱️ **وقت البدء:** `{time_start}`\n"
    )
    
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("🔴 إيقاف فوري", callback_data="st_action_stop"),
        types.InlineKeyboardButton("🔄 إعادة تشغيل آخر بث", callback_data="exec_gh_launch")
    )
    markup.add(
        types.InlineKeyboardButton("🧹 تنظيف Runner", callback_data="st_action_clean"),
        types.InlineKeyboardButton("🗑️ حذف Runs القديمة", callback_data="st_action_del_runs")
    )
    
    bot.send_message(message.chat.id, msg_text, reply_markup=markup, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data in ["st_action_stop", "st_action_clean", "st_action_del_runs"])
def handle_stream_controls(call):
    action = call.data
    
    if action == "st_action_stop":
        bot.answer_callback_query(call.id, "⏳ جاري إيقاف البث فوراً عبر إلغاء الـ Workflow...")
        # ⚡ إلغاء الـ Run شغال فوراً + إرسال أمر stop
        cancel_running_workflows()
        send_github_dispatch("stop")
        
        db["active_stream"]["status"] = "متوقف 🔴"
        save_db(db)
        bot.send_message(call.message.chat.id, "🔴 **تم إيقاف البث فوراً وتفريغ العمليات!**", parse_mode="Markdown")
            
    elif action == "st_action_clean":
        bot.answer_callback_query(call.id, "⏳ جاري التنظيف...")
        success, msg = send_github_dispatch("clean")
        bot.send_message(call.message.chat.id, "🧹 **تم تفريغ مساحة السيرفر بنجاح!**", parse_mode="Markdown")

    elif action == "st_action_del_runs":
        bot.answer_callback_query(call.id, "⏳ جاري حذف كافة سجلات GitHub القديمة...")
        success, msg = delete_old_github_runs()
        bot.send_message(call.message.chat.id, f"🗑️ **تنظيف GitHub Complete:**\n{msg}", parse_mode="Markdown")

# ==================== 🔥 لوحة التحكم المتقدمة للأدمن والتحكم بالأعضاء 🔥 ====================
@bot.message_handler(func=lambda msg: msg.text == "⚙️ لوحة التحكم" and msg.from_user.id == ADMIN_ID)
def admin_control_panel(message):
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("📊 الإحصائيات العامة", callback_data="adm_stats"),
        types.InlineKeyboardButton("👥 عرض قائمة الأعضاء", callback_data="adm_list_users")
    )
    markup.add(
        types.InlineKeyboardButton("🚫 حظر عضو", callback_data="adm_ban_user"),
        types.InlineKeyboardButton("✅ فك حظر عضو", callback_data="adm_unban_user")
    )
    markup.add(
        types.InlineKeyboardButton("🧹 تنظيف Runner", callback_data="st_action_clean"),
        types.InlineKeyboardButton("🗑️ حذف Runs القديمة", callback_data="st_action_del_runs")
    )
    bot.send_message(message.chat.id, "⚙️ **لوحة تحكم المشرف:**", reply_markup=markup, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data.startswith("adm_") and call.from_user.id == ADMIN_ID)
def admin_actions(call):
    data = call.data
    
    # 1️⃣ الإحصائيات العامة
    if data == "adm_stats":
        total_users = len(db.get("users", {}))
        total_blocked = len(db.get("blocked", []))
        total_files = sum(len(files) for files in db.get("files", {}).values())
        st_status = db.get("active_stream", {}).get("status", "متوقف 🔴")

        stats_text = (
            "📊 **الإحصائيات الشاملة للبوت:**\n\n"
            f"👤 **إجمالي المستخدمين:** `{total_users}`\n"
            f"🚫 **الأعضاء المحظورين:** `{total_blocked}`\n"
            f"📁 **إجمالي الملفات المحفوظة:** `{total_files}`\n"
            f"📡 **حالة البث الحالي:** `{st_status}`"
        )
        bot.send_message(call.message.chat.id, stats_text, parse_mode="Markdown")

    # 2️⃣ عرض قائمة الأعضاء كاملة
    elif data == "adm_list_users":
        users = db.get("users", {})
        if not users:
            bot.send_message(call.message.chat.id, "👥 **لا يوجد مستخدمون حالياً.**")
            return

        user_list_text = "👥 **قائمة أعضاء البوت:**\n\n"
        for uid, info in users.items():
            u_name = info.get("first_name", "بدون اسم")
            username = f"@{info['username']}" if info.get("username") != "بدون_يوزر" else "لا يوجد"
            status_b = " (🚫 محظور)" if uid in [str(i) for i in db.get("blocked", [])] else ""
            user_list_text += f"🔹 **الاسم:** `{u_name}`{status_b}\n🆔 **ID:** `{uid}`\n👤 **اليوزر:** {username}\n🗓️ **انضم:** `{info.get('joined_at', '-')}`\n------------------------\n"

        # إرسال النص مقسماً إن كان طويلاً
        if len(user_list_text) > 4000:
            for chunk in [user_list_text[i:i+4000] for i in range(0, len(user_list_text), 4000)]:
                bot.send_message(call.message.chat.id, chunk, parse_mode="Markdown")
        else:
            bot.send_message(call.message.chat.id, user_list_text, parse_mode="Markdown")

    # 3️⃣ طلب حظر عضو
    elif data == "adm_ban_user":
        msg = bot.send_message(call.message.chat.id, "🚫 **أرسل الآن الـ ID الخاص بالعضو المراد حظره:**", parse_mode="Markdown")
        bot.register_next_step_handler(msg, process_ban_step)

    # 4️⃣ طلب فك حظر عضو
    elif data == "adm_unban_user":
        msg = bot.send_message(call.message.chat.id, "✅ **أرسل الآن الـ ID الخاص بالعضو المراد فك حظره:**", parse_mode="Markdown")
        bot.register_next_step_handler(msg, process_unban_step)

def process_ban_step(message):
    target_id = message.text.strip()
    if not target_id.isdigit():
        bot.send_message(message.chat.id, "❌ **ID غير صالح!**")
        return
    
    if target_id not in db["blocked"]:
        db["blocked"].append(target_id)
        save_db(db)
        bot.send_message(message.chat.id, f"🚫 **تم حظر المستخدم صاحب الـ ID (`{target_id}`) بنجاح.**", parse_mode="Markdown")
    else:
        bot.send_message(message.chat.id, "⚠️ **هذا المستخدم محظور بالفعل.**")

def process_unban_step(message):
    target_id = message.text.strip()
    if target_id in db["blocked"]:
        db["blocked"].remove(target_id)
        save_db(db)
        bot.send_message(message.chat.id, f"✅ **تم فك الحظر عن المستخدم (`{target_id}`) بنجاح.**", parse_mode="Markdown")
    else:
        bot.send_message(message.chat.id, "⚠️ **هذا المستخدم غير موجود في قائمة الحظر.**")

# ==================== تشغيل البوت ====================
print("✅ تم تشغيل البوت النهائي مع النظام الكامل المتقدم...")
while True:
    try:
        bot.polling(none_stop=True, timeout=60, long_polling_timeout=60)
    except Exception as e:
        time.sleep(3)
