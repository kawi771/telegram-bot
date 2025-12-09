#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
import subprocess

# تثبيت المكتبات المطلوبة تلقائياً
required_packages = ['requests', 'pyTelegramBotAPI']

for package in required_packages:
    try:
        if package == 'pyTelegramBotAPI':
            __import__('telebot')
        else:
            __import__(package)
    except ImportError:
        print(f"Installing {package}...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", package])

# الآن استيراد المكتبات
import telebot
from telebot import types
import os
import re
import sqlite3
import json
from datetime import datetime, timedelta
import threading
import shlex
import http.server
import socketserver
import py_compile
import base64
import marshal
import zlib
import lzma

# =========================================================
# إعدادات البوت - باستخدام متغيرات البيئة
# =========================================================

# استيراد التوكن من متغير البيئة
TOKEN = os.environ.get('6178473530:AAGdxVnprg_qE75e5wkKLlLD77euXigDTEs')
if not TOKEN:
    print("❌ خطأ: لم يتم تعيين TELEGRAM_BOT_TOKEN")
    print("🔧 يرجى تعيين متغير البيئة TELEGRAM_BOT_TOKEN")
    sys.exit(1)

bot = telebot.TeleBot(TOKEN)
ADMIN_ID = os.environ.get('ADMIN_ID', '1967046629')
DEVELOPER_USERNAME = '@YM_M1'
DEVELOPER_NAME = "وحش اليمن كاوي"

# قائمة قنوات الاشتراك الإجباري
CHANNELS = [
    '@YM_M1_1',
    '@YM_M1_KAWI',
    '@KAWI_711',
    '@K_S_lS',
    '@S_N_NS',
    '@YM_M0'
]

# مسار مجلدات حفظ ملفات المستخدمين
USER_FILES_DIR = 'user_files'
if not os.path.exists(USER_FILES_DIR):
    os.makedirs(USER_FILES_DIR)

# قائمة العمليات الجارية للملفات المرفوعة
running_processes = {}
# متغير مؤقت لحفظ حالة المشرف
admin_mode = {}

# إعداد خادم HTML
HTML_SERVER_PORT = os.environ.get('HTML_SERVER_PORT', '8000')

# =========================================================
# إعداد قاعدة البيانات
# =========================================================

def setup_database():
    """ينشئ جداول قاعدة البيانات إذا لم تكن موجودة."""
    conn = sqlite3.connect('bot_data.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            is_subscribed INTEGER DEFAULT 0,
            is_paid INTEGER DEFAULT 0,
            is_banned INTEGER DEFAULT 0,
            subscription_end_date TEXT
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            file_name TEXT,
            is_running INTEGER DEFAULT 0,
            FOREIGN KEY (user_id) REFERENCES users (user_id)
        )
    ''')
    # إضافة جدول المشرفين
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS admins (
            admin_id INTEGER PRIMARY KEY
        )
    ''')
    # إضافة المشرف الأساسي
    cursor.execute("INSERT OR IGNORE INTO admins (admin_id) VALUES (?)", (ADMIN_ID,))
    
    # إضافة جدول إعدادات الأزرار
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS button_settings (
            setting_name TEXT PRIMARY KEY,
            is_enabled_free INTEGER DEFAULT 1,
            is_enabled_paid INTEGER DEFAULT 1
        )
    ''')
    
    # إعدادات الأزرار الافتراضية
    default_buttons = {
        'upload_py': (1, 1),
        'upload_php': (1, 1),
        'upload_html': (1, 1),
        'my_files': (1, 1),
        'encrypt_file': (0, 1), # ميزة مدفوعة افتراضيا
        'decrypt_file': (0, 1), # ميزة مدفوعة افتراضيا
        'bot_features': (1, 1) # زر مميزات البوت
    }
    
    for name, (free, paid) in default_buttons.items():
        cursor.execute("INSERT OR IGNORE INTO button_settings (setting_name, is_enabled_free, is_enabled_paid) VALUES (?, ?, ?)", (name, free, paid))

    conn.commit()
    conn.close()
    print("✅ تم إعداد قاعدة البيانات بنجاح")

setup_database()

def get_button_settings():
    """يحصل على إعدادات الأزرار من قاعدة البيانات."""
    conn = sqlite3.connect('bot_data.db')
    cursor = conn.cursor()
    cursor.execute("SELECT setting_name, is_enabled_free, is_enabled_paid FROM button_settings")
    settings = {row[0]: {'free': row[1], 'paid': row[2]} for row in cursor.fetchall()}
    conn.close()
    return settings

# =========================================================
# وظائف مساعدة
# =========================================================

def is_admin(user_id):
    """يتحقق مما إذا كان المستخدم مشرفًا."""
    conn = sqlite3.connect('bot_data.db')
    cursor = conn.cursor()
    cursor.execute("SELECT 1 FROM admins WHERE admin_id = ?", (user_id,))
    is_adm = cursor.fetchone() is not None
    conn.close()
    return is_adm
    
def get_user_status(user_id):
    """يتحقق من حالة المستخدم (عادي، مدفوع، محظور)."""
    if is_admin(user_id):
        return 'admin'
    
    conn = sqlite3.connect('bot_data.db')
    cursor = conn.cursor()
    cursor.execute("SELECT is_paid, is_banned, subscription_end_date FROM users WHERE user_id = ?", (user_id,))
    user_data = cursor.fetchone()
    conn.close()
    
    if not user_data:
        return 'free'
    
    if user_data[1]:  # is_banned
        return 'banned'
    
    if user_data[0] and user_data[2]:  # is_paid and has subscription_end_date
        try:
            if datetime.strptime(user_data[2], '%Y-%m-%d') > datetime.now():
                return 'paid'
        except ValueError:
            pass
            
    return 'free'

def is_member(user_id):
    """يتحقق مما إذا كان المستخدم مشتركًا في جميع القنوات أو مشتركًا مدفوعًا."""
    user_status = get_user_status(user_id)
    if user_status in ['admin', 'paid']:
        return True
    
    for channel in CHANNELS:
        try:
            status = bot.get_chat_member(channel, user_id).status
            if status not in ['member', 'administrator', 'creator']:
                return False
        except Exception as e:
            print(f"⚠️ خطأ في التحقق من القناة {channel}: {e}")
            return False
    return True

def get_bot_token(file_path):
    """يستخرج التوكن من ملف بايثون."""
    try:
        with open(file_path, 'r', encoding='utf-8') as file:
            content = file.read()
            match = re.search(r'TOKEN\s*=\s*[\'"]([^\'"]*)[\'"]', content)
            return match.group(1) if match else "❌ تعذر العثور على التوكن"
    except Exception as e:
        return f"❌ خطأ في قراءة الملف: {e}"

def run_uploaded_file(file_path, db_file_id, file_type):
    """يشغل ملف بايثون أو PHP أو HTML مرفوع ويعرض الأخطاء."""
    global running_processes
    try:
        if file_type == 'py':
            cmd = [sys.executable, file_path]
            process = subprocess.Popen(cmd, stderr=subprocess.PIPE, stdout=subprocess.PIPE)
            running_processes[db_file_id] = process
            exit_code = process.poll()
            if exit_code is not None and exit_code != 0:
                stderr = process.stderr.read().decode('utf-8')
                return False, stderr
        elif file_type == 'php':
            cmd = ['php', file_path]
            process = subprocess.Popen(cmd, stderr=subprocess.PIPE, stdout=subprocess.PIPE)
            running_processes[db_file_id] = process
            exit_code = process.poll()
            if exit_code is not None and exit_code != 0:
                stderr = process.stderr.read().decode('utf-8')
                return False, stderr
        elif file_type == 'html':
            # تشغيل خادم ويب بسيط
            handler = http.server.SimpleHTTPRequestHandler
            httpd = socketserver.TCPServer(("", int(HTML_SERVER_PORT)), handler)
            thread = threading.Thread(target=httpd.serve_forever, daemon=True)
            thread.start()
            running_processes[db_file_id] = httpd
        else:
            return False, "❌ نوع ملف غير مدعوم."

        conn = sqlite3.connect('bot_data.db')
        cursor = conn.cursor()
        cursor.execute("UPDATE files SET is_running = 1 WHERE id = ?", (db_file_id,))
        conn.commit()
        conn.close()
        
        return True, "✅ تم التشغيل بنجاح."
    except Exception as e:
        print(f"❌ خطأ في تشغيل الملف {file_path}: {e}")
        return False, str(e)

def stop_process(db_file_id):
    """يوقف تشغيل ملف."""
    global running_processes
    if db_file_id in running_processes:
        process = running_processes.pop(db_file_id)
        try:
            if hasattr(process, 'shutdown'):  # إذا كان خادم ويب
                process.shutdown()
            else:  # إذا كان عملية عادية
                process.terminate()
                process.wait(timeout=5)
        except:
            try:
                if hasattr(process, 'kill'):
                    process.kill()
            except:
                pass
                
        conn = sqlite3.connect('bot_data.db')
        cursor = conn.cursor()
        cursor.execute("UPDATE files SET is_running = 0 WHERE id = ?", (db_file_id,))
        conn.commit()
        conn.close()
        return True
    return False

def restart_all_files():
    """يعيد تشغيل جميع الملفات المرفوعة عند إعادة تشغيل البوت."""
    conn = sqlite3.connect('bot_data.db')
    cursor = conn.cursor()
    cursor.execute("SELECT id, user_id, file_name FROM files WHERE is_running = 1")
    files_to_run = cursor.fetchall()
    conn.close()
    
    print(f"🔄 إعادة تشغيل {len(files_to_run)} ملف...")
    
    for db_file_id, user_id, file_name in files_to_run:
        file_path = os.path.join(USER_FILES_DIR, str(user_id), file_name)
        if os.path.exists(file_path):
            file_extension = file_name.split('.')[-1]
            success, message = run_uploaded_file(file_path, db_file_id, file_extension)
            if not success:
                print(f"❌ فشل إعادة تشغيل الملف {file_name}: {message}")

# =========================================================
# وظائف التشفير
# =========================================================

def encrypt_file_zlib(file_path):
    """يشفر ملف بايثون باستخدام zlib."""
    try:
        with open(file_path, 'rb') as f:
            content = f.read()
        
        compressed_content = zlib.compress(content)
        
        encrypted_code = f"""
import zlib
import marshal

compressed_code = {compressed_content}
decompressed_code = zlib.decompress(compressed_code)
exec(marshal.loads(decompressed_code))
"""
        encrypted_path = file_path.replace('.py', '_zlib_encrypted.py')
        with open(encrypted_path, 'w', encoding='utf-8') as f:
            f.write(encrypted_code)
        
        return encrypted_path
    except Exception as e:
        return f"❌ فشل تشفير Zlib: {e}"

def encrypt_file_lambda(file_path):
    """يشفر ملف بايثون باستخدام lambda (marshal)."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            code = f.read()
        
        compiled_code = compile(code, '<string>', 'exec')
        marshaled_code = marshal.dumps(compiled_code)
        
        encrypted_code = f"""
import marshal
marshaled_code = {marshaled_code}
exec(marshal.loads(marshaled_code))
"""
        encrypted_path = file_path.replace('.py', '_lambda_encrypted.py')
        with open(encrypted_path, 'w', encoding='utf-8') as f:
            f.write(encrypted_code)
        
        return encrypted_path
    except Exception as e:
        return f"❌ فشل تشفير Lambda: {e}"

def encrypt_file_marshal(file_path):
    """يشفر ملف بايثون باستخدام marshal."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            code = f.read()
        
        compiled_code = compile(code, '<string>', 'exec')
        marshaled_code = marshal.dumps(compiled_code)
        
        encrypted_code = f"""
import marshal
marshaled_code = {marshaled_code}
exec(marshal.loads(marshaled_code))
"""
        encrypted_path = file_path.replace('.py', '_marshal_encrypted.py')
        with open(encrypted_path, 'w', encoding='utf-8') as f:
            f.write(encrypted_code)
        
        return encrypted_path
    except Exception as e:
        return f"❌ فشل تشفير Marshal: {e}"

def encrypt_file_base64_variant(file_path, variant=16):
    """يشفر ملف بايثون باستخدام Base64 بمتغيرات مختلفة."""
    try:
        with open(file_path, 'rb') as f:
            content = f.read()
        
        encoded_content = base64.b64encode(content).decode('utf-8')
        
        # تقسيم المحتوى المشفر حسب المتغير
        if variant == 16:
            chunk_size = 16
        elif variant == 32:
            chunk_size = 32
        elif variant == 64:
            chunk_size = 64
        else:
            chunk_size = len(encoded_content)
        
        chunks = [encoded_content[i:i+chunk_size] for i in range(0, len(encoded_content), chunk_size)]
        
        encrypted_code = f"""
import base64

chunks = {chunks}
encoded_code = "".join(chunks)
decoded_code = base64.b64decode(encoded_code.encode('utf-8')).decode('utf-8')
exec(decoded_code)
"""
        encrypted_path = file_path.replace('.py', f'_base64_{variant}_encrypted.py')
        with open(encrypted_path, 'w', encoding='utf-8') as f:
            f.write(encrypted_code)
        
        return encrypted_path
    except Exception as e:
        return f"❌ فشل تشفير Base64 {variant}: {e}"

def encrypt_file_lzma(file_path):
    """يشفر ملف بايثون باستخدام LZMA."""
    try:
        with open(file_path, 'rb') as f:
            content = f.read()
        
        compressed_content = lzma.compress(content)
        
        encrypted_code = f"""
import lzma
import marshal

compressed_code = {compressed_content}
decompressed_code = lzma.decompress(compressed_code)
exec(marshal.loads(decompressed_code))
"""
        encrypted_path = file_path.replace('.py', '_lzma_encrypted.py')
        with open(encrypted_path, 'w', encoding='utf-8') as f:
            f.write(encrypted_code)
        
        return encrypted_path
    except Exception as e:
        return f"❌ فشل تشفير LZMA: {e}"

def encrypt_file_pyc(file_path):
    """يشفر ملف بايثون إلى pyc."""
    try:
        py_compile.compile(file_path, cfile=file_path + 'c', doraise=True)
        return file_path + 'c'
    except py_compile.PyCompileError as e:
        return f"❌ خطأ في التحويل: {e}"
    except Exception as e:
        return f"❌ خطأ غير معروف: {e}"

def encrypt_file_base64(file_path):
    """يشفر ملف بايثون باستخدام Base64."""
    try:
        with open(file_path, 'rb') as f:
            content = f.read()
        
        encoded_content = base64.b64encode(content).decode('utf-8')
        
        encrypted_code = f"""
import base64

encoded_code = "{encoded_content}"
decoded_code = base64.b64decode(encoded_code.encode('utf-8')).decode('utf-8')
exec(decoded_code)
"""
        encrypted_path = file_path.replace('.py', '_base64_encrypted.py')
        with open(encrypted_path, 'w', encoding='utf-8') as f:
            f.write(encrypted_code)
        
        return encrypted_path
    except Exception as e:
        return f"❌ فشل تشفير Base64: {e}"

# =========================================================
# وظائف فك التشفير
# =========================================================

def decrypt_file_zlib(file_path):
    """يفك تشفير ملف مشفر بـ zlib."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # استخراج الكود المضغوط
        match = re.search(r'compressed_code\s*=\s*([^\n]+)', content)
        if match:
            compressed_code = eval(match.group(1))
            decompressed_code = zlib.decompress(compressed_code)
            
            decrypted_path = file_path.replace('_zlib_encrypted.py', '_decrypted.py')
            with open(decrypted_path, 'wb') as f_out:
                f_out.write(decompressed_code)
            return decrypted_path
        else:
            return "❌ هذا الملف لا يبدو مشفراً بـ Zlib."
    except Exception as e:
        return f"❌ فشل فك تشفير Zlib: {e}"

def decrypt_file_lambda(file_path):
    """يفك تشفير ملف مشفر بـ lambda."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        match = re.search(r'marshaled_code\s*=\s*([^\n]+)', content)
        if match:
            marshaled_code = eval(match.group(1))
            compiled_code = marshal.loads(marshaled_code)
            
            # حفظ الكود المفكوك
            decrypted_path = file_path.replace('_lambda_encrypted.py', '_decrypted.py')
            with open(decrypted_path, 'w', encoding='utf-8') as f_out:
                f_out.write(compile(compiled_code, '<string>', 'exec').co_code)
            return decrypted_path
        else:
            return "❌ هذا الملف لا يبدو مشفراً بـ Lambda."
    except Exception as e:
        return f"❌ فشل فك تشفير Lambda: {e}"

def decrypt_file_marshal(file_path):
    """يفك تشفير ملف مشفر بـ marshal."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        match = re.search(r'marshaled_code\s*=\s*([^\n]+)', content)
        if match:
            marshaled_code = eval(match.group(1))
            compiled_code = marshal.loads(marshaled_code)
            
            decrypted_path = file_path.replace('_marshal_encrypted.py', '_decrypted.py')
            with open(decrypted_path, 'w', encoding='utf-8') as f_out:
                f_out.write(compile(compiled_code, '<string>', 'exec').co_code)
            return decrypted_path
        else:
            return "❌ هذا الملف لا يبدو مشفراً بـ Marshal."
    except Exception as e:
        return f"❌ فشل فك تشفير Marshal: {e}"

def decrypt_file_base64_variant(file_path):
    """يفك تشفير ملف مشفر بـ Base64 بمتغيرات مختلفة."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        match = re.search(r'chunks\s*=\s*([^\n]+)\s*\n.*encoded_code\s*=', content, re.DOTALL)
        if match:
            chunks = eval(match.group(1))
            encoded_code = "".join(chunks)
            decoded_data = base64.b64decode(encoded_code.encode('utf-8')).decode('utf-8')
            
            decrypted_path = file_path.replace('_base64_', '_base64_decrypted_').replace('_encrypted.py', '.py')
            with open(decrypted_path, 'w', encoding='utf-8') as f_out:
                f_out.write(decoded_data)
            return decrypted_path
        else:
            return "❌ هذا الملف لا يبدو مشفراً بـ Base64."
    except Exception as e:
        return f"❌ فشل فك تشفير Base64: {e}"

def decrypt_file_lzma(file_path):
    """يفك تشفير ملف مشفر بـ LZMA."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        match = re.search(r'compressed_code\s*=\s*([^\n]+)', content)
        if match:
            compressed_code = eval(match.group(1))
            decompressed_code = lzma.decompress(compressed_code)
            
            decrypted_path = file_path.replace('_lzma_encrypted.py', '_decrypted.py')
            with open(decrypted_path, 'wb') as f_out:
                f_out.write(decompressed_code)
            return decrypted_path
        else:
            return "❌ هذا الملف لا يبدو مشفراً بـ LZMA."
    except Exception as e:
        return f"❌ فشل فك تشفير LZMA: {e}"

def decrypt_file_base64(file_path):
    """يفك تشفير ملف مشفر بـ Base64."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        match = re.search(r'encoded_code\s*=\s*"([^\"]*)"', content)
        if match:
            encoded_code = match.group(1)
            decoded_data = base64.b64decode(encoded_code.encode('utf-8')).decode('utf-8')
            
            decrypted_path = file_path.replace('_base64_encrypted.py', '_decrypted.py')
            with open(decrypted_path, 'w', encoding='utf-8') as f_out:
                f_out.write(decoded_data)
            return decrypted_path
        else:
            return "❌ هذا الملف لا يبدو مشفراً بـ Base64."
    except Exception as e:
        return f"❌ فشل فك تشفير Base64: {e}"

def auto_detect_encryption(file_path):
    """يكتشف تلقائياً نوع التشفير المستخدم في الملف."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        if 'zlib.compress' in content and 'zlib.decompress' in content:
            return decrypt_file_zlib(file_path)
        elif 'lzma.compress' in content and 'lzma.decompress' in content:
            return decrypt_file_lzma(file_path)
        elif 'marshal.loads' in content and 'marshaled_code' in content:
            if 'lambda' in file_path:
                return decrypt_file_lambda(file_path)
            else:
                return decrypt_file_marshal(file_path)
        elif 'base64.b64decode' in content:
            if 'chunks' in content:
                return decrypt_file_base64_variant(file_path)
            else:
                return decrypt_file_base64(file_path)
        else:
            return "❌ تعذر اكتشاف نوع التشفير تلقائياً."
    except Exception as e:
        return f"❌ فشل الاكتشاف التلقائي: {e}"

# =========================================================
# معالجة الأوامر والرسائل
# =========================================================

@bot.message_handler(commands=['start'])
def start(message):
    """يعالج أمر /start."""
    user_id = message.chat.id
    username = message.from_user.first_name
    conn = sqlite3.connect('bot_data.db')
    cursor = conn.cursor()
    cursor.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (user_id,))
    conn.commit()
    conn.close()

    if not is_member(user_id):
        show_subscription_message(message)
    else:
        show_main_menu(message, username)

def show_subscription_message(message):
    """يرسل رسالة الاشتراك الإجباري."""
    markup = types.InlineKeyboardMarkup()
    for channel in CHANNELS:
        try:
            chat = bot.get_chat(channel)
            channel_link = chat.invite_link if chat.invite_link else f"https://t.me/{channel[1:]}"
            markup.add(types.InlineKeyboardButton(text=f"اشترك في {channel}", url=channel_link))
        except Exception as e:
            print(f"❌ خطأ في الحصول على القناة {channel}: {e}")
    markup.add(types.InlineKeyboardButton(text="تحقّق من الاشتراك ✅", callback_data='check_subscription'))
    bot.send_message(message.chat.id, "📢 للوصول إلى البوت، يجب عليك الاشتراك في القنوات التالية:", reply_markup=markup)

def show_main_menu(message, username=None):
    """يعرض القائمة الرئيسية للمستخدمين بناءً على حالتهم."""
    if username is None:
        username = message.from_user.first_name
    
    user_status = get_user_status(message.chat.id)
    settings = get_button_settings()
    markup = types.InlineKeyboardMarkup()
    
    # قائمة الأزرار وخصائصها
    buttons_info = {
        'upload_py': ("رفع ملف بايثون 🐍", 'upload_py'),
        'upload_php': ("رفع ملف PHP 🐘", 'upload_php'),
        'upload_html': ("رفع ملف HTML 🌐", 'upload_html'),
        'my_files': ("ملفاتي 📂", 'my_files'),
        'encrypt_file': ("تشفير ملف 🔐", 'encrypt_file'),
        'decrypt_file': ("فك تشفير ملف 🔓", 'decrypt_file'),
    }
    
    # رسالة ترحيب فخمة
    welcome_text = f"""
أهلاً بك يا **{username}** في بوت **{DEVELOPER_NAME}**! 👋

**مميزات البوت ✨:**
✅ يمكنك رفع وتشغيل ملفاتك الخاصة على مدار الساعة.
✅ تشفير وفك تشفير ملفات بايثون لحماية أكوادك.
✅ استمتع بتجربة سلسة وسريعة مع البوت.

تم تطوير البوت من قبل المطور **{DEVELOPER_NAME}** `{DEVELOPER_USERNAME}`
"""

    for name, (display_text, callback_data) in buttons_info.items():
        is_free_enabled = settings.get(name, {}).get('free', 0) == 1
        is_paid_enabled = settings.get(name, {}).get('paid', 0) == 1
        
        if is_free_enabled and user_status == 'free':
            markup.add(types.InlineKeyboardButton(display_text, callback_data=callback_data))
        elif is_paid_enabled and user_status in ['paid', 'admin']:
            markup.add(types.InlineKeyboardButton(display_text, callback_data=callback_data))
        elif not is_free_enabled and is_paid_enabled and user_status == 'free':
            markup.add(types.InlineKeyboardButton(f"{display_text} (مدفوع)", callback_data=f'paid_feature_{name}'))

    markup.add(types.InlineKeyboardButton("مميزات البوت ℹ️", callback_data='bot_features'))
    bot.send_message(message.chat.id, welcome_text, reply_markup=markup, parse_mode='Markdown')

@bot.message_handler(commands=['admin'])
def admin_panel(message):
    """يعرض لوحة تحكم المشرف."""
    if not is_admin(message.chat.id):
        bot.reply_to(message, "❌ ليس لديك صلاحية للوصول إلى لوحة التحكم.")
        return
    
    markup = types.InlineKeyboardMarkup()
    markup.row(types.InlineKeyboardButton(text="💰 وضع البوت", callback_data='bot_status'), types.InlineKeyboardButton(text="📊 عدد المستخدمين", callback_data='user_count'))
    markup.row(types.InlineKeyboardButton(text="📣 إذاعة للقنوات", callback_data='broadcast_to_channels'), types.InlineKeyboardButton(text="📢 إذاعة للمستخدمين", callback_data='broadcast_to_users'))
    markup.row(types.InlineKeyboardButton(text="➖ حذف مستخدم مدفوع", callback_data='remove_paid_user'), types.InlineKeyboardButton(text="➕ إضافة مستخدم مدفوع", callback_data='add_paid_user'))
    markup.row(types.InlineKeyboardButton(text="🔄 تجديد اشتراك مستخدم", callback_data='renew_subscription'))
    markup.row(types.InlineKeyboardButton(text="⛔ حظر مستخدم", callback_data='ban_user'), types.InlineKeyboardButton(text="✅ فك حظر مستخدم", callback_data='unban_user'))
    markup.row(types.InlineKeyboardButton(text="➕ إضافة مشرف", callback_data='add_admin'), types.InlineKeyboardButton(text="➖ حذف مشرف", callback_data='remove_admin'))
    markup.row(types.InlineKeyboardButton(text="📂 ملفات المستخدمين", callback_data='admin_files'))
    markup.row(types.InlineKeyboardButton(text="⚙️ إعدادات الأزرار", callback_data='button_settings'))
    markup.row(types.InlineKeyboardButton(text="📡 القنوات المشرف فيها", callback_data='admin_channels'))
    
    bot.send_message(message.chat.id, "👑 مرحباً بك في لوحة تحكم المشرف:", reply_markup=markup)

@bot.message_handler(content_types=['document'])
def handle_file(message):
    """يعالج الملفات المرفوعة من المستخدمين."""
    user_id = message.chat.id
    
    # معالجة وضع التشفير وفك التشفير أولاً
    if user_id in admin_mode:
        if admin_mode[user_id] == 'encrypt_file':
            if not message.document.file_name.endswith('.py'):
                bot.reply_to(message, "❌ يرجى إرسال ملف بايثون (.py) لتشفيره.")
                return
            
            # حفظ الملف
            file_info = bot.get_file(message.document.file_id)
            downloaded_file = bot.download_file(file_info.file_path)
            temp_path = os.path.join(USER_FILES_DIR, f"{user_id}_temp.py")
            with open(temp_path, 'wb') as f:
                f.write(downloaded_file)
            
            # إرسال خيارات التشفير
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("تشفير Pyc", callback_data=f'encrypt_pyc_{temp_path}'))
            markup.add(types.InlineKeyboardButton("تشفير Base64", callback_data=f'encrypt_base64_{temp_path}'))
            markup.add(types.InlineKeyboardButton("تشفير Base64 16", callback_data=f'encrypt_base64_16_{temp_path}'))
            markup.add(types.InlineKeyboardButton("تشفير Base64 32", callback_data=f'encrypt_base64_32_{temp_path}'))
            markup.add(types.InlineKeyboardButton("تشفير Base64 64", callback_data=f'encrypt_base64_64_{temp_path}'))
            markup.add(types.InlineKeyboardButton("تشفير Zlib", callback_data=f'encrypt_zlib_{temp_path}'))
            markup.add(types.InlineKeyboardButton("تشفير Lambda", callback_data=f'encrypt_lambda_{temp_path}'))
            markup.add(types.InlineKeyboardButton("تشفير Marshal", callback_data=f'encrypt_marshal_{temp_path}'))
            markup.add(types.InlineKeyboardButton("تشفير LZMA", callback_data=f'encrypt_lzma_{temp_path}'))
            
            bot.reply_to(message, "🔐 اختر نوع التشفير:", reply_markup=markup)
            del admin_mode[user_id]
            return
            
        elif admin_mode[user_id] == 'decrypt_file':
            # حفظ الملف المشفر
            file_info = bot.get_file(message.document.file_id)
            downloaded_file = bot.download_file(file_info.file_path)
            temp_path = os.path.join(USER_FILES_DIR, f"{user_id}_encrypted_temp.py")
            with open(temp_path, 'wb') as f:
                f.write(downloaded_file)
            
            # محاولة فك التشفير تلقائياً
            result = auto_detect_encryption(temp_path)
            if result.endswith('_decrypted.py'):
                with open(result, 'rb') as f:
                    bot.send_document(user_id, f, caption="✅ تم فك تشفير الملف بنجاح!")
                os.remove(temp_path)
                os.remove(result)
            else:
                bot.send_message(user_id, f"❌ فشل فك التشفير: {result}")
                os.remove(temp_path)
            
            del admin_mode[user_id]
            return

    # معالجة الرفع العادي للملف
    if not is_member(user_id):
        show_subscription_message(message)
        return

    file_name = message.document.file_name
    file_extension = file_name.split('.')[-1].lower()
    
    if file_extension not in ['py', 'php', 'html']:
        bot.reply_to(message, "❌ عذراً، يجب أن يكون الملف المرفوع من نوع بايثون (.py)، PHP (.php) أو HTML (.html).")
        return

    user_dir = os.path.join(USER_FILES_DIR, str(user_id))
    if not os.path.exists(user_dir):
        os.makedirs(user_dir)

    try:
        file_info = bot.get_file(message.document.file_id)
        downloaded_file = bot.download_file(file_info.file_path)
        
        file_path = os.path.join(user_dir, file_name)
        
        conn = sqlite3.connect('bot_data.db')
        cursor = conn.cursor()
        
        cursor.execute("SELECT id, is_running FROM files WHERE user_id = ? AND file_name = ?", (user_id, file_name))
        existing_file = cursor.fetchone()
        
        if existing_file:
            db_file_id, is_running = existing_file
            if is_running:
                stop_process(db_file_id)
            if os.path.exists(os.path.join(user_dir, file_name)):
                os.remove(os.path.join(user_dir, file_name))
            cursor.execute("DELETE FROM files WHERE id = ?", (db_file_id,))

        with open(file_path, 'wb') as new_file:
            new_file.write(downloaded_file)
        
        cursor.execute("INSERT INTO files (user_id, file_name) VALUES (?, ?)", (user_id, file_name))
        db_file_id = cursor.lastrowid
        conn.commit()
        conn.close()
        
        if file_extension == 'html':
            # تشغيل خادم ويب بسيط
            handler = http.server.SimpleHTTPRequestHandler
            httpd = socketserver.TCPServer(("", int(HTML_SERVER_PORT)), handler)
            thread = threading.Thread(target=httpd.serve_forever, daemon=True)
            thread.start()
            
            server_link = f"http://localhost:{HTML_SERVER_PORT}/{file_name}"
            bot.reply_to(message, f"✅ تم رفع ملفك بنجاح\n\n📄 اسم الملف: {file_name}\n🔗 رابط الصفحة: {server_link}\n\nتم تشغيل الملف على السيرفر.")
        else:
            success, error_message = run_uploaded_file(file_path, db_file_id, file_extension)
            
            if success:
                bot_token = get_bot_token(file_path) if file_extension == 'py' else "غير متوفر"
                bot.reply_to(message, f"✅ تم رفع ملفك بنجاح\n\n📄 اسم الملف: {file_name}\n🔑 توكن البوت: {bot_token}\n\nتم تشغيل الملف على السيرفر.")
            else:
                bot.reply_to(message, f"⚠️ تم رفع الملف بنجاح، لكن حدث خطأ أثناء تشغيله.\n\nالخطأ:\n```\n{error_message}\n```", parse_mode='Markdown')
        
    except Exception as e:
        bot.reply_to(message, f"❌ حدث خطأ: {e}")

# =========================================================
# معالجة الأزرار (Callback Queries)
# =========================================================

@bot.callback_query_handler(func=lambda call: call.data.startswith('paid_feature_'))
def handle_paid_feature(call):
    user_id = call.message.chat.id
    button_name = call.data.split('_')[-1]
    
    buttons_info = {
        'upload_py': "رفع ملف بايثون",
        'upload_php': "رفع ملف PHP",
        'upload_html': "رفع ملف HTML",
        'my_files': "ملفاتي",
        'encrypt_file': "تشفير ملف",
        'decrypt_file': "فك تشفير ملف",
    }
    
    button_display_name = buttons_info.get(button_name, "هذه الميزة")
    
    message_text = (
        f"🔒 عذراً، **{button_display_name}** هي ميزة مدفوعة.\n\n"
        f"للاشتراك والوصول إلى هذه الميزة، يرجى التواصل مع المطور: {DEVELOPER_USERNAME}"
    )
    
    bot.send_message(user_id, message_text, parse_mode='Markdown')

@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    user_id = call.message.chat.id
    
    if call.data == 'check_subscription':
        if is_member(user_id):
            bot.delete_message(call.message.chat.id, call.message.message_id)
            show_main_menu(call.message)
        else:
            bot.answer_callback_query(call.id, "❌ لم يتم التحقق من الاشتراك بعد. يرجى الاشتراك في القنوات ثم المحاولة مرة أخرى.", show_alert=True)
    
    elif call.data == 'go_back_to_main':
        bot.delete_message(call.message.chat.id, call.message.message_id)
        show_main_menu(call.message)
    
    elif call.data == 'bot_features':
        features_text = """
**🎯 مميزات البوت المتاحة:**

🔹 **📤 رفع وتشغيل الملفات:**
   - ملفات بايثون (.py)
   - ملفات PHP (.php) 
   - ملفات HTML (.html)

🔹 **🔐 تشفير الملفات (للمستخدمين المدفوعين):**
   - تشفير Pyc
   - تشفير Base64 (بمستويات 16، 32، 64)
   - تشفير Zlib
   - تشفير Lambda
   - تشفير Marshal
   - تشفير LZMA

🔹 **🔓 فك تشفير الملفات (للمستخدمين المدفوعين):**
   - فك جميع أنواع التشفير المذكورة أعلاه
   - كشف تلقائي لنوع التشفير

🔹 **📁 إدارة الملفات:**
   - عرض جميع الملفات
   - تشغيل/إيقاف الملفات
   - تحديث الملفات
   - حذف الملفات

🔹 **👑 مميزات المشرف:**
   - إدارة المستخدمين
   - البث للقنوات والمستخدمين
   - إعدادات الأزرار
   - إدارة الملفات
"""
        bot.send_message(user_id, features_text, parse_mode='Markdown')
        
    elif call.data == 'upload_py':
        if not is_member(user_id):
            show_subscription_message(call.message)
            return
        bot.send_message(user_id, "📤 أرسل لي ملف بايثون (.py) الذي تريد رفعه.")
    
    elif call.data == 'upload_php':
        if not is_member(user_id):
            show_subscription_message(call.message)
            return
        bot.send_message(user_id, "📤 أرسل لي ملف PHP (.php) الذي تريد رفعه.")
        
    elif call.data == 'upload_html':
        if not is_member(user_id):
            show_subscription_message(call.message)
            return
        bot.send_message(user_id, "📤 أرسل لي ملف HTML (.html) الذي تريد رفعه.")
        
    elif call.data == 'my_files':
        if not is_member(user_id):
            show_subscription_message(call.message)
            return
            
        conn = sqlite3.connect('bot_data.db')
        cursor = conn.cursor()
        cursor.execute("SELECT id, file_name, is_running FROM files WHERE user_id = ?", (user_id,))
        user_files = cursor.fetchall()
        conn.close()
        
        if not user_files:
            bot.send_message(user_id, "📭 لم تقم برفع أي ملفات حتى الآن.")
            return

        markup = types.InlineKeyboardMarkup()
        for db_file_id, file_name, is_running in user_files:
            status = "✅ يعمل" if is_running else "🔴 متوقف"
            markup.add(types.InlineKeyboardButton(text=f"{file_name} ({status})", callback_data=f'file_info_{db_file_id}'))
        
        markup.add(types.InlineKeyboardButton("🔙 العودة للقائمة الرئيسية", callback_data='go_back_to_main'))
        
        bot.send_message(user_id, "📂 ملفاتي المرفوعة:", reply_markup=markup)
    
    elif call.data.startswith('file_info_'):
        db_file_id = int(call.data.split('_')[2])
        conn = sqlite3.connect('bot_data.db')
        cursor = conn.cursor()
        cursor.execute("SELECT file_name, is_running FROM files WHERE id = ?", (db_file_id,))
        file_info = cursor.fetchone()
        conn.close()
        
        if not file_info:
            bot.answer_callback_query(call.id, "❌ الملف غير موجود.", show_alert=True)
            return
        
        file_name, is_running = file_info
        status = "يعمل" if is_running else "متوقف"
        
        markup = types.InlineKeyboardMarkup()
        markup.row(
            types.InlineKeyboardButton(text="⏯ إيقاف / تشغيل", callback_data=f'toggle_file_{db_file_id}'),
            types.InlineKeyboardButton(text="🗑 حذف الملف", callback_data=f'delete_file_{db_file_id}')
        )
        markup.row(types.InlineKeyboardButton(text="🔄 تحديث الملف", callback_data=f'update_file_prompt_{db_file_id}'))
        markup.row(types.InlineKeyboardButton("🔙 العودة للقائمة الرئيسية", callback_data='go_back_to_main'))
        
        bot.edit_message_text(f"📄 معلومات الملف: **{file_name}**\n📊 الحالة: **{status}**", call.message.chat.id, call.message.message_id, reply_markup=markup, parse_mode='Markdown')
        
    elif call.data.startswith('toggle_file_'):
        db_file_id = int(call.data.split('_')[2])
        if not is_member(user_id):
            show_subscription_message(call.message)
            return
            
        conn = sqlite3.connect('bot_data.db')
        cursor = conn.cursor()
        cursor.execute("SELECT file_name, is_running FROM files WHERE id = ? AND user_id = ?", (db_file_id, user_id))
        file_info = cursor.fetchone()
        conn.close()
        
        if not file_info:
            bot.answer_callback_query(call.id, "❌ الملف غير موجود.", show_alert=True)
            return

        file_name, is_running = file_info
        file_path = os.path.join(USER_FILES_DIR, str(user_id), file_name)
        file_extension = file_name.split('.')[-1]
        
        if is_running:
            if stop_process(db_file_id):
                bot.answer_callback_query(call.id, "⏹ تم إيقاف الملف بنجاح.", show_alert=True)
                bot.edit_message_text(f"📄 معلومات الملف: **{file_name}**\n📊 الحالة: **متوقف**", call.message.chat.id, call.message.message_id, parse_mode='Markdown', reply_markup=call.message.reply_markup)
        else:
            if os.path.exists(file_path):
                success, error_message = run_uploaded_file(file_path, db_file_id, file_extension)
                if success:
                    bot.answer_callback_query(call.id, "▶️ تم تشغيل الملف بنجاح.", show_alert=True)
                    bot.edit_message_text(f"📄 معلومات الملف: **{file_name}**\n📊 الحالة: **يعمل**", call.message.chat.id, call.message.message_id, parse_mode='Markdown', reply_markup=call.message.reply_markup)
                else:
                    bot.answer_callback_query(call.id, f"❌ حدث خطأ أثناء تشغيل الملف: {error_message}", show_alert=True)
            else:
                bot.answer_callback_query(call.id, "❌ لم يتم العثور على ملفك المحلي، يرجى إعادة رفعه.", show_alert=True)

    elif call.data.startswith('delete_file_'):
        db_file_id = int(call.data.split('_')[2])
        if not is_member(user_id):
            show_subscription_message(call.message)
            return

        conn = sqlite3.connect('bot_data.db')
        cursor = conn.cursor()
        cursor.execute("SELECT file_name, is_running, user_id FROM files WHERE id = ?", (db_file_id,))
        file_info = cursor.fetchone()
        
        if not file_info:
            conn.close()
            bot.answer_callback_query(call.id, "❌ الملف غير موجود.", show_alert=True)
            return
            
        file_name, is_running, file_user_id = file_info
        
        if file_user_id != user_id and not is_admin(user_id):
            bot.answer_callback_query(call.id, "❌ ليس لديك الصلاحية لحذف هذا الملف.", show_alert=True)
            conn.close()
            return
            
        file_path = os.path.join(USER_FILES_DIR, str(file_user_id), file_name)
        
        if is_running:
            stop_process(db_file_id)

        if os.path.exists(file_path):
            os.remove(file_path)

        cursor.execute("DELETE FROM files WHERE id = ?", (db_file_id,))
        conn.commit()
        conn.close()
        
        bot.answer_callback_query(call.id, "🗑 تم حذف الملف بنجاح.", show_alert=True)
        bot.edit_message_text(f"✅ تم حذف الملف: **{file_name}**.", call.message.chat.id, call.message.message_id, parse_mode='Markdown')

    elif call.data.startswith('update_file_prompt_'):
        db_file_id = int(call.data.split('_')[3])
        if not is_member(user_id):
            show_subscription_message(call.message)
            return

        bot.send_message(user_id, "📤 أرسل الملف الجديد الذي تريد استخدامه لتحديث الملف السابق.")
    
    elif call.data == 'encrypt_file':
        if get_user_status(user_id) not in ['paid', 'admin']:
            handle_paid_feature(call)
            return
        bot.send_message(user_id, "🔐 أرسل لي ملف بايثون (.py) الذي تريد تشفيره.")
        admin_mode[user_id] = 'encrypt_file'
    
    elif call.data == 'decrypt_file':
        if get_user_status(user_id) not in ['paid', 'admin']:
            handle_paid_feature(call)
            return
        bot.send_message(user_id, "🔓 أرسل لي ملف بايثون المشفر الذي تريد فك تشفيره.")
        admin_mode[user_id] = 'decrypt_file'

    # معالجة أنواع التشفير المختلفة
    elif call.data.startswith('encrypt_'):
        parts = call.data.split('_')
        encryption_type = parts[1]
        file_path = '_'.join(parts[2:])
        
        if not os.path.exists(file_path):
            bot.answer_callback_query(call.id, "❌ الملف غير موجود.", show_alert=True)
            return
        
        encryption_functions = {
            'pyc': encrypt_file_pyc,
            'base64': encrypt_file_base64,
            'base64_16': lambda path: encrypt_file_base64_variant(path, 16),
            'base64_32': lambda path: encrypt_file_base64_variant(path, 32),
            'base64_64': lambda path: encrypt_file_base64_variant(path, 64),
            'zlib': encrypt_file_zlib,
            'lambda': encrypt_file_lambda,
            'marshal': encrypt_file_marshal,
            'lzma': encrypt_file_lzma
        }
        
        if encryption_type in encryption_functions:
            result_path = encryption_functions[encryption_type](file_path)
            if result_path.endswith(('.pyc', '.py')):
                with open(result_path, 'rb') as f:
                    bot.send_document(user_id, f, caption=f"✅ تم تشفير الملف بنجاح باستخدام {encryption_type}.")
                os.remove(file_path)
                os.remove(result_path)
            else:
                bot.send_message(user_id, f"❌ فشل التشفير: {result_path}")
                os.remove(file_path)
        else:
            bot.send_message(user_id, "❌ نوع التشفير غير مدعوم.")
            os.remove(file_path)
    
    # =========================================================
    # معالجة أزرار لوحة تحكم المشرف
    # =========================================================

    elif is_admin(user_id):
        if call.data == 'button_settings':
            show_button_settings_menu(user_id)
        
        elif call.data.startswith('toggle_button_'):
            parts = call.data.split('_')
            button_name = parts[2]
            user_type = parts[3]
            toggle_button_setting(user_id, button_name, user_type)

        elif call.data.startswith('back_to_admin_panel'):
            bot.delete_message(call.message.chat.id, call.message.message_id)
            admin_panel(call.message)
            
        elif call.data == 'bot_status':
            conn = sqlite3.connect('bot_data.db')
            cursor = conn.cursor()
            
            # إحصائيات البوت
            cursor.execute("SELECT COUNT(*) FROM users")
            total_users = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM users WHERE is_paid = 1")
            paid_users = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM files")
            total_files = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM files WHERE is_running = 1")
            running_files = cursor.fetchone()[0]
            
            conn.close()
            
            status_text = f"""
**📊 إحصائيات البوت:**

👥 **المستخدمين:**
   - إجمالي المستخدمين: {total_users}
   - المستخدمين المدفوعين: {paid_users}

📁 **الملفات:**
   - إجمالي الملفات: {total_files}
   - الملفات قيد التشغيل: {running_files}

⚙️ **الحالة:** البوت يعمل بشكل طبيعي ✅
"""
            bot.send_message(user_id, status_text, parse_mode='Markdown')

        elif call.data == 'user_count':
            conn = sqlite3.connect('bot_data.db')
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(user_id) FROM users")
            count = cursor.fetchone()[0]
            conn.close()
            bot.send_message(user_id, f"👥 عدد المستخدمين الكلي: {count}")
            
        elif call.data == 'broadcast_to_channels':
            bot.send_message(user_id, "📣 أرسل لي الرسالة التي تريد بثها للقنوات.")
            admin_mode[user_id] = 'broadcast_to_channels'
        
        elif call.data == 'broadcast_to_users':
            bot.send_message(user_id, "📢 أرسل لي الرسالة التي تريد بثها للمستخدمين.")
            admin_mode[user_id] = 'broadcast_to_users'
        
        elif call.data == 'ban_user':
            bot.send_message(user_id, "⛔ أرسل لي معرف المستخدم (ID) الذي تريد حظره.")
            admin_mode[user_id] = 'ban'

        elif call.data == 'unban_user':
            bot.send_message(user_id, "✅ أرسل لي معرف المستخدم (ID) الذي تريد إلغاء حظره.")
            admin_mode[user_id] = 'unban'
            
        elif call.data == 'add_paid_user':
            bot.send_message(user_id, "➕ أرسل لي معرف المستخدم (ID) ومدة الاشتراك (بالأيام) مفصولة بمسافة (مثال: 123456789 30).")
            admin_mode[user_id] = 'add_paid'
            
        elif call.data == 'remove_paid_user':
            bot.send_message(user_id, "➖ أرسل لي معرف المستخدم (ID) الذي تريد إزالة اشتراكه المدفوع.")
            admin_mode[user_id] = 'remove_paid'

        elif call.data == 'renew_subscription':
            bot.send_message(user_id, "🔄 أرسل لي معرف المستخدم (ID) ومدة الاشتراك الجديدة (بالأيام) مفصولة بمسافة (مثال: 123456789 60).")
            admin_mode[user_id] = 'renew_sub'
            
        elif call.data == 'add_admin':
            bot.send_message(user_id, "👑 أرسل لي معرف المستخدم (ID) الذي تريد إضافته كمشرف.")
            admin_mode[user_id] = 'add_admin'

        elif call.data == 'remove_admin':
            bot.send_message(user_id, "👥 أرسل لي معرف المستخدم (ID) الذي تريد إزالته كمشرف.")
            admin_mode[user_id] = 'remove_admin'

        elif call.data == 'admin_files':
            conn = sqlite3.connect('bot_data.db')
            cursor = conn.cursor()
            cursor.execute("SELECT id, user_id, file_name, is_running FROM files")
            all_files = cursor.fetchall()
            conn.close()
            
            if not all_files:
                bot.send_message(user_id, "📭 لا توجد ملفات مرفوعة حاليًا.")
                return

            markup = types.InlineKeyboardMarkup()
            for db_file_id, file_user_id, file_name, is_running in all_files:
                status = "✅ يعمل" if is_running else "🔴 متوقف"
                markup.add(types.InlineKeyboardButton(text=f"👤 ID: {file_user_id} | 📄 {file_name} ({status})", callback_data=f'admin_file_info_{db_file_id}'))
            
            markup.add(types.InlineKeyboardButton("🔙 العودة إلى لوحة المشرف", callback_data='back_to_admin_panel'))
            bot.send_message(user_id, "📁 قائمة بجميع الملفات المرفوعة:", reply_markup=markup)
            
        elif call.data == 'admin_channels':
            channels_text = "**📡 القنوات التي يشرف عليها البوت:**\n\n" + "\n".join([f"• {channel}" for channel in CHANNELS])
            bot.send_message(user_id, channels_text, parse_mode='Markdown')

def show_button_settings_menu(user_id):
    """يعرض قائمة إعدادات الأزرار للمشرف."""
    settings = get_button_settings()
    markup = types.InlineKeyboardMarkup()
    
    button_map = {
        'upload_py': "رفع ملف بايثون",
        'upload_php': "رفع ملف PHP",
        'upload_html': "رفع ملف HTML",
        'my_files': "ملفاتي",
        'encrypt_file': "تشفير ملف",
        'decrypt_file': "فك تشفير ملف",
    }

    for name, display_name in button_map.items():
        free_status = "✅" if settings[name]['free'] else "❌"
        paid_status = "✅" if settings[name]['paid'] else "❌"
        
        markup.add(types.InlineKeyboardButton(f"{display_name} (عادي {free_status})", callback_data=f'toggle_button_{name}_free'))
        markup.add(types.InlineKeyboardButton(f"{display_name} (مدفوع {paid_status})", callback_data=f'toggle_button_{name}_paid'))

    markup.add(types.InlineKeyboardButton("🔙 العودة إلى لوحة المشرف", callback_data='back_to_admin_panel'))
    
    bot.send_message(user_id, "⚙️ إعدادات الأزرار (اضغط لتغيير الحالة):", reply_markup=markup)

def toggle_button_setting(user_id, button_name, user_type):
    """يغير حالة زر معين لنوع مستخدم معين."""
    conn = sqlite3.connect('bot_data.db')
    cursor = conn.cursor()
    
    cursor.execute(f"UPDATE button_settings SET is_enabled_{user_type} = NOT is_enabled_{user_type} WHERE setting_name = ?", (button_name,))
    conn.commit()
    conn.close()
    
    bot.answer_callback_query(user_id, "✅ تم تحديث الإعداد بنجاح.", show_alert=True)
    show_button_settings_menu(user_id)

@bot.message_handler(func=lambda message: True)
def handle_text_messages(message):
    user_id = message.chat.id
    text = message.text
    
    if user_id in admin_mode:
        mode = admin_mode[user_id]
        
        if mode == 'broadcast_to_channels':
            success_count = 0
            fail_count = 0
            
            for channel in CHANNELS:
                try:
                    bot.send_message(channel, text)
                    success_count += 1
                except Exception as e:
                    print(f"❌ فشل إرسال الرسالة إلى {channel}: {e}")
                    fail_count += 1
                    
            bot.send_message(user_id, f"✅ تم بث الرسالة للقنوات.\n\n✅ تم الإرسال لـ: {success_count} قناة\n❌ فشل الإرسال لـ: {fail_count} قناة")
            del admin_mode[user_id]

        elif mode == 'broadcast_to_users':
            conn = sqlite3.connect('bot_data.db')
            cursor = conn.cursor()
            cursor.execute("SELECT user_id FROM users")
            users = [row[0] for row in cursor.fetchall()]
            conn.close()
            
            success_count = 0
            fail_count = 0
            
            for user in users:
                try:
                    bot.send_message(user, text)
                    success_count += 1
                except Exception as e:
                    print(f"❌ فشل إرسال الرسالة إلى المستخدم {user}: {e}")
                    fail_count += 1
                    
            bot.send_message(user_id, f"✅ تم بث الرسالة للمستخدمين.\n\n✅ تم الإرسال لـ: {success_count} مستخدم\n❌ فشل الإرسال لـ: {fail_count} مستخدم")
            del admin_mode[user_id]
        
        elif mode == 'add_paid':
            try:
                parts = text.split()
                if len(parts) != 2:
                    bot.send_message(user_id, "❌ صيغة خاطئة. يرجى إدخال معرف المستخدم والمدة بالأيام مفصولة بمسافة.")
                    del admin_mode[user_id]
                    return
                    
                target_id = int(parts[0])
                duration_days = int(parts[1])
                
                conn = sqlite3.connect('bot_data.db')
                cursor = conn.cursor()
                cursor.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (target_id,))
                
                end_date = datetime.now() + timedelta(days=duration_days)
                cursor.execute("UPDATE users SET is_paid = 1, subscription_end_date = ? WHERE user_id = ?", (end_date.strftime('%Y-%m-%d'), target_id))
                conn.commit()
                conn.close()
                bot.send_message(user_id, f"✅ تم إضافة المستخدم {target_id} كمدفوع لمدة {duration_days} يوماً.")
            except ValueError:
                bot.send_message(user_id, "❌ صيغة خاطئة. يرجى إدخال أرقام صحيحة.")
            except Exception as e:
                bot.send_message(user_id, f"❌ حدث خطأ: {e}")
            finally:
                del admin_mode[user_id]

        elif mode == 'remove_paid':
            try:
                target_id = int(text)
                conn = sqlite3.connect('bot_data.db')
                cursor = conn.cursor()
                cursor.execute("UPDATE users SET is_paid = 0, subscription_end_date = NULL WHERE user_id = ?", (target_id,))
                conn.commit()
                conn.close()
                bot.send_message(user_id, f"✅ تم إزالة الاشتراك المدفوع من المستخدم {target_id}.")
            except ValueError:
                bot.send_message(user_id, "❌ صيغة خاطئة. يرجى إدخال معرف المستخدم فقط.")
            finally:
                del admin_mode[user_id]

        elif mode == 'renew_sub':
            try:
                parts = text.split()
                if len(parts) != 2:
                    bot.send_message(user_id, "❌ صيغة خاطئة. يرجى إدخال معرف المستخدم والمدة بالأيام مفصولة بمسافة.")
                    del admin_mode[user_id]
                    return
                    
                target_id = int(parts[0])
                duration_days = int(parts[1])
                
                conn = sqlite3.connect('bot_data.db')
                cursor = conn.cursor()
                cursor.execute("SELECT subscription_end_date FROM users WHERE user_id = ?", (target_id,))
                result = cursor.fetchone()
                
                if result and result[0]:
                    try:
                        end_date = datetime.strptime(result[0], '%Y-%m-%d')
                        if end_date < datetime.now():
                            end_date = datetime.now()
                    except ValueError:
                        end_date = datetime.now()
                else:
                    end_date = datetime.now()
                
                new_end_date = end_date + timedelta(days=duration_days)
                cursor.execute("UPDATE users SET is_paid = 1, subscription_end_date = ? WHERE user_id = ?", (new_end_date.strftime('%Y-%m-%d'), target_id))
                conn.commit()
                conn.close()
                bot.send_message(user_id, f"✅ تم تجديد اشتراك المستخدم {target_id} لمدة {duration_days} يوماً. سينتهي في {new_end_date.strftime('%Y-%m-%d')}.")
            except ValueError:
                bot.send_message(user_id, "❌ صيغة خاطئة. يرجى إدخال أرقام صحيحة.")
            except Exception as e:
                bot.send_message(user_id, f"❌ حدث خطأ: {e}")
            finally:
                del admin_mode[user_id]

        elif mode == 'ban':
            try:
                target_id = int(text)
                conn = sqlite3.connect('bot_data.db')
                cursor = conn.cursor()
                cursor.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (target_id,))
                cursor.execute("UPDATE users SET is_banned = 1 WHERE user_id = ?", (target_id,))
                conn.commit()
                conn.close()
                bot.send_message(user_id, f"✅ تم حظر المستخدم {target_id}.")
            except ValueError:
                bot.send_message(user_id, "❌ صيغة خاطئة. يرجى إدخال معرف المستخدم فقط.")
            finally:
                del admin_mode[user_id]

        elif mode == 'unban':
            try:
                target_id = int(text)
                conn = sqlite3.connect('bot_data.db')
                cursor = conn.cursor()
                cursor.execute("UPDATE users SET is_banned = 0 WHERE user_id = ?", (target_id,))
                conn.commit()
                conn.close()
                bot.send_message(user_id, f"✅ تم فك حظر المستخدم {target_id}.")
            except ValueError:
                bot.send_message(user_id, "❌ صيغة خاطئة. يرجى إدخال معرف المستخدم فقط.")
            finally:
                del admin_mode[user_id]
        
        elif mode == 'add_admin':
            try:
                target_id = int(text)
                conn = sqlite3.connect('bot_data.db')
                cursor = conn.cursor()
                cursor.execute("INSERT OR IGNORE INTO admins (admin_id) VALUES (?)", (target_id,))
                conn.commit()
                conn.close()
                bot.send_message(user_id, f"✅ تم إضافة المستخدم {target_id} كمشرف.")
            except ValueError:
                bot.send_message(user_id, "❌ صيغة خاطئة. يرجى إدخال معرف المستخدم فقط.")
            finally:
                del admin_mode[user_id]
        
        elif mode == 'remove_admin':
            try:
                target_id = int(text)
                if str(target_id) == str(ADMIN_ID):
                    bot.send_message(user_id, "❌ لا يمكنك إزالة المشرف الأساسي.")
                else:
                    conn = sqlite3.connect('bot_data.db')
                    cursor = conn.cursor()
                    cursor.execute("DELETE FROM admins WHERE admin_id = ?", (target_id,))
                    conn.commit()
                    conn.close()
                    bot.send_message(user_id, f"✅ تم إزالة المستخدم {target_id} من قائمة المشرفين.")
            except ValueError:
                bot.send_message(user_id, "❌ صيغة خاطئة. يرجى إدخال معرف المستخدم فقط.")
            finally:
                del admin_mode[user_id]

# =========================================================
# تشغيل البوت
# =========================================================

if __name__ == "__main__":
    print("=" * 50)
    print("🤖 بوت تيليجرام يعمل...")
    print(f"📅 التاريخ: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"🐍 إصدار Python: {sys.version}")
    print(f"🔑 التوكن مضبوط: {'نعم' if TOKEN else 'لا'}")
    print("=" * 50)
    
    restart_all_files()
    
    while True:
        try:
            bot.polling(none_stop=True, interval=1, timeout=60)
        except Exception as e:
            print(f"❌ خطأ في البوت: {e}")
            print("🔄 إعادة التشغيل خلال 5 ثواني...")
            import time
            time.sleep(5)