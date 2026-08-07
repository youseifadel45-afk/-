import asyncio
import re
import logging
from urllib.parse import quote, unquote
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# إعداد نظام الـ Logging لمراقبة السيرفر وحفظ السجلات
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# إعدادات التوكن الخاص بك والدومين المستهدف
TOKEN = "8865248253:AAFbA0K0OJZz0n-mvVTnTD8j0oW4c1TnrcU"
BASE_URL = "https://fasel-hd.cam"

# دالة فرز وتصنيف جودات البث التكيفية المستخرجة من حزم البيانات
def categorize_streams(raw_links):
    categorized = {}
    for link in raw_links:
        if "mu=" in link:
            try:
                link = unquote(link.split("mu=")[1].split("&")[0])
            except:
                pass
        
        # فرز الروابط بناءً على تسمية الملفات في سيرفر scdns.io
        if "hd1080b" in link.lower() or "1080p" in link.lower():
            categorized["FHD 1080p"] = link
        elif "hd720b" in link.lower() or "720p" in link.lower():
            categorized["HD 720p"] = link
        elif "sd480b" in link.lower() or "480p" in link.lower():
            categorized["SD 480p"] = link
        elif "sd360b" in link.lower() or "360p" in link.lower():
            categorized["SD 360p"] = link
        elif "master.m3u8" in link.lower() and "التلقائي (Master)" not in categorized:
            categorized["التلقائي (Master)"] = link
            
    return categorized

# دالة اقتحام الموقع بالمتصفح الكامل واصطياد الروابط والتوكنات
async def search_and_sniff_movie(movie_name: str):
    video_links = set()
    page_title = movie_name
    poster_url = None
    
    async with async_playwright() as p:
        # تشغيل كروميوم بكامل طاقته المهيأة للعمل الصامت على السيرفرات الكبيرة
        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu"
            ]
        )
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:120.0) Gecko/20100101 Firefox/120.0",
            viewport={"width": 1280, "height": 720}
        )
        page = await context.new_page()

        # صائد اتصالات الشبكة لالتقاط الـ API والـ m3u8 ديناميكياً
        async def handle_request(request):
            url = request.url
            if any(k in url for k in ["master.m3u8", "scdns.io", "playlist.m3u8"]):
                # تصفية الروابط وإبعاد الإعلانات والتتبع لضمان سرعة تشغيل الميديا
                if not any(b in url for b in ["google", "analytics", "doubleclick", "facebook"]):
                    video_links.add(url)

        page.on("request", handle_request)

        try:
            # الخطوة 1: حقن الاسم في محرك بحث الموقع تلقائياً
            search_url = f"{BASE_URL}/?s={quote(movie_name)}"
            logger.info(f"جاري البحث عن العرض: {movie_name}")
            await page.goto(search_url, wait_until="domcontentloaded", timeout=50000)
            await asyncio.sleep(3)
            
            # قراءة كود البحث لاختيار أول فيلم ظاهر
            html = await page.content()
            soup = BeautifulSoup(html, 'html.parser')
            movie_tag = soup.find('a', href=re.compile(r'/movies/|/episodes/'))
            
            if movie_tag and movie_tag.get('href'):
                movie_page = movie_tag.get('href')
                logger.info(f"تم العثور على رابط صفحة العرض: {movie_page}")
                
                # الخطوة 2: الدخول لصفحة الفيلم وقراءة البوستر والعنوان الحقيقي
                await page.goto(movie_page, wait_until="domcontentloaded", timeout=50000)
                await asyncio.sleep(3)
                
                movie_html = await page.content()
                movie_soup = BeautifulSoup(movie_html, 'html.parser')
                
                if movie_soup.find('title'):
                    page_title = movie_soup.find('title').text.split('-')[0].strip()
                meta_img = movie_soup.find('meta', property='og:image') or movie_soup.find('meta', property='twitter:image')
                if meta_img:
                    poster_url = meta_img.get('content')

                # الخطوة 3: التوجه التلقائي لإطار المشغل (iframe) الداخلي وإرغامه على توليد التوكن
                iframes = await page.query_selector_all("iframe")
                for iframe in iframes:
                    src = await iframe.get_attribute("src")
                    if src and any(k in src for k in ["fashd", "scdns", "player", "stream"]):
                        logger.info(f"اقتحام سيرفر المشاهدة وتوليد التوكن التلقائي: {src}")
                        await page.goto(src, wait_until="networkidle", timeout=30000)
                        await asyncio.sleep(8) # مهلة لضمان تجميع كل الجودات من حزم البيانات
                        break
        except Exception as e:
            logger.error(f"حدث خطأ أثناء فحص وتتبع الشبكة: {e}")
        finally:
            await browser.close() # إغلاق المتصفح الآمن لتحرير رامات السيرفر
            
    return page_title, poster_url, categorize_streams(video_links)

# أمر الترحيب والبدء /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 أهلاً بك في النسخة الاحترافية الكاملة لبوت استخراج روابط البث!\n\n"
        "🔍 **طريقة الاستخدام الحالية:**\n"
        "فقط أرسل لي **اسم الفيلم أو المسلسل** (مثل: Avatar أو Dark)، وسأقوم بالبحث عنه ومحاكاة متصفح كامل لفك التشفير، وإرسال البوستر وكافة الجودات في رسالة واحدة صاروخية وجاهزة للنسخ!"
    )

# استقبال اسم الفيلم ومعالجته برمجياً بالكامل
async def handle_movie_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = update.message.text.strip()
    
    if user_text.startswith(("http://", "https://")):
        await update.message.reply_text("⚠️ يرجى إرسال اسم الفيلم فقط نصاً وليس الرابط؛ البوت يبحث تلقائياً بالاسم.")
        return

    status = await update.message.reply_text(f"⏳ جاري فتح المتصفح السحابي، تخطي الحماية واصطياد جودات «{user_text}»...")
    title, poster, streams = await search_and_sniff_movie(user_text)

    if streams:
        # صياغة نص الرسالة الشامل والمدمج المطابق لطلبك
        caption_text = f"🎬 **{title}**\n\n🎯 **روابط البث المباشر المستخرجة بنجاح:**\n\n"
        for quality, link in streams.items():
            caption_text += f"▶️ **جودة {quality}:**\n`{link}`\n\n"
        caption_text += "⚠️ **ملحوظة:** روابط البث مؤقتة وتعمل مباشرة على تطبيق VLC أو MX Player."
        
        await status.delete()
        
        if poster:
            try:
                await update.message.reply_photo(photo=poster, caption=caption_text, parse_mode="Markdown")
            except Exception as e:
                logger.error(f"فشل إرسال البوستر: {e}")
                await update.message.reply_text(caption_text, parse_mode="Markdown")
        else:
            await update.message.reply_text(caption_text, parse_mode="Markdown")
    else:
        await status.edit_text(f"❌ لم يتم العثور على جودات بث لـ «{user_text}». تأكد من كتابة الاسم صحيحاً أو جرب فيلماً آخر.")

def main():
    application = Application.builder().token(TOKEN).build()
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_movie_search))
    
    print("🤖 النسخة الشاملة والكاملة تعمل الآن على السيرفر الكبير بنجاح وثبات تام...")
    application.run_polling()

if __name__ == "__main__":
    main()
