"""
╔══════════════════════════════════════════════╗
║         🎬  VideoBot Configuration          ║
║    يقرأ المتغيرات من Railway Environment    ║
╚══════════════════════════════════════════════╝
"""

import os

# ══════════════════════════════════════════
#  إعدادات البوت — تُقرأ من Environment Variables
# ══════════════════════════════════════════
BOT_TOKEN = os.environ.get("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")

# ADMIN_IDS: ضعها في Railway هكذا:  123456789,987654321
_admin_env = os.environ.get("ADMIN_IDS", "")
ADMIN_IDS  = [int(x.strip()) for x in _admin_env.split(",") if x.strip().isdigit()]

# ══════════════════════════════════════════
#  إعدادات الاشتراك الإجباري
# ══════════════════════════════════════════
_channels_env      = os.environ.get("REQUIRED_CHANNELS", "")
REQUIRED_CHANNELS  = [c.strip() for c in _channels_env.split(",") if c.strip()]
CHECK_SUBSCRIPTION = os.environ.get("CHECK_SUBSCRIPTION", "false").lower() == "true"

# ══════════════════════════════════════════
#  إعدادات التنزيل
# ══════════════════════════════════════════
MAX_FILE_SIZE_MB        = int(os.environ.get("MAX_FILE_SIZE_MB", "50"))
DOWNLOAD_PATH           = os.environ.get("DOWNLOAD_PATH", "/tmp/videobot_downloads")
MAX_DOWNLOADS_PER_USER  = int(os.environ.get("MAX_DOWNLOADS_PER_USER", "0"))

# ══════════════════════════════════════════
#  قاعدة البيانات — /tmp على Railway
# ══════════════════════════════════════════
DATABASE_PATH = os.environ.get("DATABASE_PATH", "/tmp/videobot.db")

# ══════════════════════════════════════════
#  نصوص الرسائل
# ══════════════════════════════════════════
MESSAGES = {
    "welcome": (
        "🎬 <b>أهلاً وسهلاً في بوت التنزيل!</b>\n\n"
        "أرسل لي أي رابط من:\n"
        "▸ 🎵 <b>TikTok</b> — فيديوهات تيك توك\n"
        "▸ 📸 <b>Instagram</b> — ريلز ومنشورات\n"
        "▸ ▶️ <b>YouTube</b> — فيديوهات ويوتيوب شورتس\n\n"
        "وأنا أتكفل بالباقي! 🚀"
    ),
    "help": (
        "📌 <b>طريقة الاستخدام</b>\n\n"
        "1️⃣ انسخ رابط الفيديو من التطبيق\n"
        "2️⃣ أرسله مباشرة هنا\n"
        "3️⃣ انتظر لحظة وسيصلك الفيديو\n\n"
        "<b>المنصات المدعومة:</b>\n"
        "• TikTok.com / vm.tiktok.com\n"
        "• Instagram.com/reel\n"
        "• YouTube.com / youtu.be\n"
        "• YouTube Shorts\n\n"
        "⚡ <b>نصيحة:</b> أرسل الرابط كما هو بدون أي تعديل"
    ),
    "downloading":        "⏳ جارٍ التنزيل... انتظر لحظة 🔄",
    "sending":            "📤 جارٍ الإرسال...",
    "success":            "✅ تم بنجاح! استمتع بالفيديو 🎉",
    "error_invalid_link": "❌ الرابط غير صحيح أو المحتوى غير مدعوم\n\nتأكد من نسخ الرابط كاملاً",
    "error_too_large":    "⚠️ الفيديو أكبر من {size}MB\nجرب فيديو أصغر حجماً",
    "error_private":      "🔒 هذا المحتوى خاص ولا يمكن تنزيله",
    "error_general":      "❌ حدث خطأ أثناء التنزيل\nحاول مرة أخرى أو أرسل رابطاً مختلفاً",
    "not_subscribed": (
        "⚠️ <b>عذراً، يجب الاشتراك أولاً</b>\n\n"
        "لاستخدام البوت، اشترك في القنوات التالية:\n"
        "{channels}\n\n"
        "بعد الاشتراك اضغط ✅ <b>تحققت من الاشتراك</b>"
    ),
    "daily_limit": (
        "⏰ <b>وصلت للحد اليومي</b>\n\n"
        "يمكنك تنزيل {max} فيديوهات يومياً فقط\n"
        "عد غداً أو تواصل مع الأدمن للحصول على صلاحيات مميزة"
    ),
    "broadcast_confirm": "📢 تم إرسال الرسالة لـ <b>{count}</b> مستخدم ✅",
}
