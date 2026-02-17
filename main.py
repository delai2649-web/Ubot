
# Saya akan buatkan main.py lengkap dengan AutoBC dan PMPermit

main_py_complete = '''#!/usr/bin/env python3
"""
Userbot SaaS Bot - Complete Version
With AutoBC and PMPermit features
"""

import os
import sys
import json
import time
import random
import asyncio
import logging
import threading
from datetime import datetime, timedelta
from flask import Flask
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler, 
    CallbackQueryHandler, ContextTypes, filters
)
from pyrogram import Client, filters as pyro_filters
from pyrogram.errors import (
    PhoneNumberInvalid, PhoneCodeInvalid, 
    PhoneCodeExpired, SessionPasswordNeeded,
    FloodWait
)

# ==================== KONFIGURASI ====================
TOKEN = "8207231899:AAF4biFtxDJztNaFw97d8szZgU7pryrFrRg"
ADMIN_ID = 1855623479
API_ID = 30565875
API_HASH = "cad29b6c102e18181230d683f4859eae"

# Buat direktori
os.makedirs('sessions', exist_ok=True)
os.makedirs('data/sessions', exist_ok=True)

# ==================== FLASK KEEP ALIVE ====================
app = Flask(__name__)

@app.route('/')
def home():
    try:
        users = {}
        try:
            with open('data/users.json', 'r') as f:
                users = json.load(f)
        except:
            pass
        active = sum(1 for u in users.values() if u.get('userbot_active'))
    except:
        active = 0
    return f"""
    <html>
    <head><title>Userbot SaaS</title></head>
    <body style="font-family: Arial; text-align: center; padding: 50px;">
        <h1>🤖 Userbot SaaS</h1>
        <h2 style="color: green;">● Online</h2>
        <p>Active Userbots: <b>{active}</b></p>
        <p>Last Update: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
    </body>
    </html>
    """

@app.route('/health')
def health():
    return {"status": "ok", "time": datetime.now().isoformat()}

def run_flask():
    app.run(host='0.0.0.0', port=8080, debug=False, use_reloader=False)

# ==================== LOGGING ====================
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[
        logging.FileHandler('data/bot.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# ==================== DATABASE ====================
DB_FILE = 'data/users.json'

def get_all_users():
    try:
        with open(DB_FILE, 'r') as f:
            return json.load(f)
    except:
        return {}

def get_user(user_id):
    return get_all_users().get(str(user_id))

def save_user(user_id, data):
    users = get_all_users()
    uid = str(user_id)
    if uid not in users:
        users[uid] = {}
    users[uid].update(data)
    with open(DB_FILE, 'w') as f:
        json.dump(users, f, indent=2)

def get_session(user_id):
    try:
        with open(f"data/sessions/{user_id}.txt", 'r') as f:
            return f.read().strip()
    except:
        return None

def save_session(user_id, session_string):
    with open(f"data/sessions/{user_id}.txt", 'w') as f:
        f.write(session_string)

# ==================== PLANS ====================
PLANS = {
    'lite': {'name': '⚡ Lite', 'price': 10000, 'plugins': 25},
    'basic': {'name': '🧩 Basic', 'price': 15000, 'plugins': 56},
    'pro': {'name': '💎 Pro', 'price': 22000, 'plugins': 99}
}

pending_payments = {}
user_clients = {}

# ==================== AUTOBC MANAGER ====================
class AutoBCManager:
    """Manager untuk Auto Broadcast"""
    
    def __init__(self):
        self.active_tasks = {}      # {user_id: asyncio.Task}
        self.bc_status = {}         # {user_id: {'running': bool, 'count': int, 'targets': []}}
        self.templates = {}         # {user_id: {template_name: content}}
    
    async def start_autobc(self, client, user_id, message_text, interval=60, 
                          forward=False, reply_msg=None, targets=None):
        """Mulai auto broadcast"""
        
        # Stop yang sudah berjalan dulu
        if user_id in self.active_tasks:
            self.stop_autobc(user_id)
        
        # Default: semua grup
        if not targets:
            targets = []
            async for dialog in client.get_dialogs():
                if dialog.chat.type in ["group", "supergroup"]:
                    targets.append(dialog.chat.id)
        
        if not targets:
            return False, "Tidak ada grup target!"
        
        self.bc_status[user_id] = {
            'running': True,
            'count': 0,
            'targets': targets,
            'interval': interval,
            'forward': forward,
            'start_time': datetime.now().isoformat()
        }
        
        async def broadcast_loop():
            while self.bc_status.get(user_id, {}).get('running', False):
                for target in targets:
                    if not self.bc_status.get(user_id, {}).get('running'):
                        break
                    
                    try:
                        if forward and reply_msg:
                            await reply_msg.forward(target)
                        else:
                            await client.send_message(target, message_text)
                        
                        self.bc_status[user_id]['count'] += 1
                        
                        # Delay antar grup (anti-flood)
                        await asyncio.sleep(2)
                        
                    except FloodWait as e:
                        await asyncio.sleep(e.value)
                    except Exception as e:
                        logger.error(f"BC error to {target}: {e}")
                        continue
                
                # Delay antar siklus
                await asyncio.sleep(interval)
        
        # Jalankan di background
        task = asyncio.create_task(broadcast_loop())
        self.active_tasks[user_id] = task
        
        return True, f"AutoBC started! Targets: {len(targets)}"
    
    def stop_autobc(self, user_id):
        """Hentikan auto broadcast"""
        if user_id in self.bc_status:
            self.bc_status[user_id]['running'] = False
        
        if user_id in self.active_tasks:
            self.active_tasks[user_id].cancel()
            del self.active_tasks[user_id]
            return True
        return False
    
    def get_status(self, user_id):
        """Cek status autobc"""
        return self.bc_status.get(user_id)
    
    def save_template(self, user_id, name, content):
        """Simpan template pesan"""
        if user_id not in self.templates:
            self.templates[user_id] = {}
        self.templates[user_id][name] = content
        return True
    
    def get_template(self, user_id, name):
        """Ambil template"""
        return self.templates.get(user_id, {}).get(name)

# Global instance
autobc_manager = AutoBCManager()

# ==================== PM PERMIT MANAGER ====================
class PMPermitManager:
    """Manager untuk PM Permit (anti-spam private message)"""
    
    def __init__(self):
        self.enabled = {}           # {user_id: bool}
        self.approved = {}          # {user_id: [user_ids]}
        self.blocked = {}           # {user_id: [user_ids]}
        self.temp_msg = {}          # {user_id: str}
        self.warn_count = {}        # {(owner_id, user_id): count}
        self.max_warn = 3
    
    def enable(self, user_id, message=None):
        """Enable PM Permit"""
        self.enabled[user_id] = True
        self.approved[user_id] = []
        self.blocked[user_id] = []
        self.temp_msg[user_id] = message or self.get_default_msg()
        return True
    
    def disable(self, user_id):
        """Disable PM Permit"""
        self.enabled[user_id] = False
        return True
    
    def is_enabled(self, user_id):
        """Cek status"""
        return self.enabled.get(user_id, False)
    
    def approve(self, owner_id, user_id):
        """Approve user"""
        if owner_id not in self.approved:
            self.approved[owner_id] = []
        if user_id not in self.approved[owner_id]:
            self.approved[owner_id].append(user_id)
            return True
        return False
    
    def disapprove(self, owner_id, user_id):
        """Hapus approve"""
        if owner_id in self.approved and user_id in self.approved[owner_id]:
            self.approved[owner_id].remove(user_id)
            return True
        return False
    
    def block(self, owner_id, user_id):
        """Block user"""
        if owner_id not in self.blocked:
            self.blocked[owner_id] = []
        if user_id not in self.blocked[owner_id]:
            self.blocked[owner_id].append(user_id)
            return True
        return False
    
    def unblock(self, owner_id, user_id):
        """Unblock user"""
        if owner_id in self.blocked and user_id in self.blocked[owner_id]:
            self.blocked[owner_id].remove(user_id)
            return True
        return False
    
    def is_approved(self, owner_id, user_id):
        """Cek apakah user diapprove"""
        return user_id in self.approved.get(owner_id, [])
    
    def is_blocked(self, owner_id, user_id):
        """Cek apakah user diblock"""
        return user_id in self.blocked.get(owner_id, [])
    
    def get_default_msg(self):
        """Pesan default PM Permit"""
        return """⚠️ **PM SECURITY**

Halo! Saya adalah assistant bot.
Owner saya sedang sibuk.

Pesan Anda telah saya log.
Mohon tunggu balasan dari owner.

⛔ **Jangan spam atau Anda akan diblokir!**
**Warn:** {warn}/{max_warn}
"""
    
    def get_message(self, user_id):
        """Ambil pesan custom atau default"""
        return self.temp_msg.get(user_id, self.get_default_msg())
    
    def set_message(self, user_id, message):
        """Set pesan custom"""
        self.temp_msg[user_id] = message
        return True
    
    def get_warn(self, owner_id, user_id):
        """Get warn count"""
        return self.warn_count.get((owner_id, user_id), 0)
    
    def add_warn(self, owner_id, user_id):
        """Tambah warn"""
        key = (owner_id, user_id)
        self.warn_count[key] = self.warn_count.get(key, 0) + 1
        return self.warn_count[key]
    
    def reset_warn(self, owner_id, user_id):
        """Reset warn"""
        key = (owner_id, user_id)
        if key in self.warn_count:
            del self.warn_count[key]

# Global instance
pmpermit_manager = PMPermitManager()

# ==================== USERBOT MANAGER ====================
class UserbotManager:
    def __init__(self):
        self.clients = {}
        self.active = {}

    async def start_userbot(self, user_id, plan):
        uid = str(user_id)
        if uid in self.clients and self.active.get(uid):
            logger.info(f"Userbot {uid} already active")
            return True, "Already active"
        
        session = get_session(user_id)
        if not session:
            logger.error(f"No session found for {uid}")
            return False, "Session not found"
        
        try:
            logger.info(f"Starting userbot {uid}...")
            
            client = Client(
                name=f"ubot_{uid}",
                api_id=API_ID,
                api_hash=API_HASH,
                session_string=session,
                in_memory=True
            )
            
            # Register handlers SEBELUM start
            await self._register_handlers(client, uid, plan)
            
            # Start client
            await client.start()
            
            self.clients[uid] = client
            self.active[uid] = True
            
            save_user(user_id, {
                'userbot_active': True,
                'last_started': datetime.now().isoformat()
            })
            
            logger.info(f"✅ Userbot {uid} started successfully")
            return True, "Success"
            
        except Exception as e:
            logger.error(f"❌ Failed to start userbot {uid}: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False, str(e)
    
    async def stop_userbot(self, user_id):
        uid = str(user_id)
        if uid in self.clients:
            try:
                await self.clients[uid].stop()
                self.active[uid] = False
                save_user(user_id, {'userbot_active': False})
                logger.info(f"Userbot {uid} stopped")
                return True
            except Exception as e:
                logger.error(f"Error stopping {uid}: {e}")
        return False
    
    async def _register_handlers(self, client, user_id, plan):
        """Register handlers dengan benar"""
        plugins = PLANS.get(plan, PLANS['lite'])['plugins']
        
        logger.info(f"Registering handlers for {user_id} with plan {plan}")
        
        # Handler Ping
        @client.on_message(pyro_filters.command("ping", prefixes=".") & pyro_filters.me)
        async def ping_handler(client, message):
            logger.info(f"Ping command received from {user_id}")
            try:
                start = time.time()
                await message.edit("🏓 Pong!")
                end = time.time()
                await message.edit(f"🏓 **Pong!**\n`{(end-start)*1000:.1f}ms`")
            except Exception as e:
                logger.error(f"Ping error: {e}")
        
        # Handler Alive
        @client.on_message(pyro_filters.command("alive", prefixes=".") & pyro_filters.me)
        async def alive_handler(client, message):
            logger.info(f"Alive command received from {user_id}")
            try:
                u = get_user(user_id) or {}
                expired = u.get('expired', 'Unknown')[:10] if u.get('expired') else 'Unknown'
                await message.edit(f"🤖 **Active!**\nPlan: {plan.upper()}\nExpired: {expired}")
            except Exception as e:
                logger.error(f"Alive error: {e}")
        
        # Handler Help
        @client.on_message(pyro_filters.command("help", prefixes=".") & pyro_filters.me)
        async def help_handler(client, message):
            logger.info(f"Help command received from {user_id}")
            try:
                text = f"🤖 **COMMANDS ({plan.upper()})**\n\n"
                text += "`.ping` - Cek response\n"
                text += "`.alive` - Cek status\n"
                text += "`.help` - Bantuan\n"
                if plugins >= 25:
                    text += "\n`.afk [reason]` - Set AFK\n"
                    text += "`.spam <n> <text>` - Spam\n"
                    text += "`.autobc` - Auto broadcast\n"
                    text += "`.stopbc` - Stop broadcast\n"
                if plugins >= 56:
                    text += "\n`.broadcast <text>` - Broadcast\n"
                    text += "`.tagall` - Tag all\n"
                if plugins >= 99:
                    text += "\n`.pmpermit on/off` - PM security\n"
                    text += "`.approve` - Approve user\n"
                    text += "`.block` - Block user\n"
                await message.edit(text)
            except Exception as e:
                logger.error(f"Help error: {e}")
        
        # Handler AFK (Lite+)
        if plugins >= 25:
            @client.on_message(pyro_filters.command("afk", prefixes=".") & pyro_filters.me)
            async def afk_handler(client, message):
                logger.info(f"AFK command from {user_id}")
                try:
                    reason = message.text.split(maxsplit=1)[1] if len(message.text.split()) > 1 else "AFK"
                    await message.edit(f"😴 **AFK:** {reason}")
                except Exception as e:
                    logger.error(f"AFK error: {e}")
            
            @client.on_message(pyro_filters.command("spam", prefixes=".") & pyro_filters.me)
            async def spam_handler(client, message):
                logger.info(f"Spam command from {user_id}")
                try:
                    args = message.text.split()
                    if len(args) < 3:
                        await message.edit("Usage: `.spam <jumlah> <teks>`")
                        return
                    count = min(int(args[1]), 10)
                    text = " ".join(args[2:])
                    await message.delete()
                    for i in range(count):
                        await client.send_message(message.chat.id, text)
                        await asyncio.sleep(0.5)
                except Exception as e:
                    logger.error(f"Spam error: {e}")
                    await message.edit(f"Error: {e}")
            
            # Handler AutoBC
            @client.on_message(pyro_filters.command("autobc", prefixes=".") & pyro_filters.me)
            async def autobc_handler(client, message):
                logger.info(f"AutoBC command from {user_id}")
                try:
                    args = message.text.split(maxsplit=2)
                    if len(args) < 2:
                        await message.edit("Usage: `.autobc <interval_detik> <pesan>`\nContoh: `.autobc 60 Halo semua`")
                        return
                    
                    interval = int(args[1])
                    text = args[2] if len(args) > 2 else "Broadcast message"
                    
                    # Get targets
                    targets = []
                    async for dialog in client.get_dialogs():
                        if dialog.chat.type in ["group", "supergroup"]:
                            targets.append(dialog.chat.id)
                    
                    if not targets:
                        await message.edit("❌ Tidak ada grup target!")
                        return
                    
                    ok, msg = await autobc_manager.start_autobc(
                        client, user_id, text, interval=interval, targets=targets
                    )
                    
                    if ok:
                        await message.edit(f"✅ **AutoBC started!**\n\nInterval: {interval} detik\nTargets: {len(targets)} grup\n\nKetik `.stopbc` untuk berhenti.")
                    else:
                        await message.edit(f"❌ {msg}")
                        
                except Exception as e:
                    logger.error(f"AutoBC error: {e}")
                    await message.edit(f"❌ Error: {e}")
            
            @client.on_message(pyro_filters.command("stopbc", prefixes=".") & pyro_filters.me)
            async def stopbc_handler(client, message):
                logger.info(f"StopBC command from {user_id}")
                try:
                    if autobc_manager.stop_autobc(user_id):
                        await message.edit("✅ **AutoBC stopped!**")
                    else:
                        await message.edit("❌ AutoBC tidak berjalan.")
                except Exception as e:
                    logger.error(f"StopBC error: {e}")
            
            @client.on_message(pyro_filters.command("bcstatus", prefixes=".") & pyro_filters.me)
            async def bcstatus_handler(client, message):
                logger.info(f"BCStatus command from {user_id}")
                try:
                    status = autobc_manager.get_status(user_id)
                    if status:
                        text = f"📊 **AutoBC Status**\n\n"
                        text += f"Running: {'✅' if status['running'] else '❌'}\n"
                        text += f"Count: {status['count']}\n"
                        text += f"Targets: {len(status['targets'])}\n"
                        text += f"Interval: {status['interval']} detik"
                        await message.edit(text)
                    else:
                        await message.edit("❌ AutoBC tidak berjalan.")
                except Exception as e:
                    logger.error(f"BCStatus error: {e}")
        
        # Handler Broadcast & Tagall (Basic+)
        if plugins >= 56:
            @client.on_message(pyro_filters.command("broadcast", prefixes=".") & pyro_filters.me)
            async def broadcast_handler(client, message):
                logger.info(f"Broadcast command from {user_id}")
                try:
                    text = message.text.split(maxsplit=1)[1] if len(message.text.split()) > 1 else None
                    if not text:
                        await message.edit("Usage: `.broadcast <pesan>`")
                        return
                    await message.edit("📢 Broadcasting...")
                    count = 0
                    async for dialog in client.get_dialogs():
                        try:
                            if dialog.chat.type in ["group", "supergroup"]:
                                await client.send_message(dialog.chat.id, text)
                                count += 1
                                await asyncio.sleep(1)
                        except Exception as e:
                            logger.error(f"Broadcast error to {dialog.chat.id}: {e}")
                    await message.edit(f"✅ Broadcast ke {count} grup")
                except Exception as e:
                    logger.error(f"Broadcast error: {e}")
            
            @client.on_message(pyro_filters.command("tagall", prefixes=".") & pyro_filters.me)
            async def tagall_handler(client, message):
                logger.info(f"Tagall command from {user_id}")
                try:
                    if message.chat.type not in ["group", "supergroup"]:
                        await message.edit("Hanya untuk grup!")
                        return
                    await message.edit("🏷️ Tagging...")
                    tags = []
                    async for member in client.get_chat_members(message.chat.id):
                        if not member.user.is_bot:
                            tags.append(f"[{member.user.first_name}](tg://user?id={member.user.id})")
                        if len(tags) == 5:
                            await client.send_message(message.chat.id, " ".join(tags))
                            tags = []
                            await asyncio.sleep(1)
                    if tags:
                        await client.send_message(message.chat.id, " ".join(tags))
                    await message.delete()
                except Exception as e:
                    logger.error(f"Tagall error: {e}")
        
        # Handler PM Permit (Pro)
        if plugins >= 99:
            @client.on_message(pyro_filters.command("pmpermit", prefixes=".") & pyro_filters.me)
            async def pmpermit_handler(client, message):
                logger.info(f"PMPermit command from {user_id}")
                try:
                    args = message.text.split()
                    if len(args) < 2:
                        status = "ON" if pmpermit_manager.is_enabled(user_id) else "OFF"
                        await message.edit(f"PM Permit: {status}\n\nUsage: `.pmpermit on/off`")
                        return
                    
                    action = args[1].lower()
                    if action == "on":
                        pmpermit_manager.enable(user_id)
                        await message.edit("✅ **PM Permit enabled!**\n\nSekarang orang yang PM akan di-filter.")
                    elif action == "off":
                        pmpermit_manager.disable(user_id)
                        await message.edit("✅ **PM Permit disabled!**")
                    else:
                        await message.edit("Usage: `.pmpermit on/off`")
                except Exception as e:
                    logger.error(f"PMPermit error: {e}")
            
            @client.on_message(pyro_filters.command("approve", prefixes=".") & pyro_filters.me)
            async def approve_handler(client, message):
                logger.info(f"Approve command from {user_id}")
                try:
                    if message.reply_to_message:
                        target_id = message.reply_to_message.from_user.id
                        pmpermit_manager.approve(user_id, target_id)
                        await message.edit(f"✅ User {target_id} di-approve!")
                    else:
                        await message.edit("Reply ke pesan user yang mau di-approve!")
                except Exception as e:
                    logger.error(f"Approve error: {e}")
            
            @client.on_message(pyro_filters.command("disapprove", prefixes=".") & pyro_filters.me)
            async def disapprove_handler(client, message):
                logger.info(f"Disapprove command from {user_id}")
                try:
                    if message.reply_to_message:
                        target_id = message.reply_to_message.from_user.id
                        pmpermit_manager.disapprove(user_id, target_id)
                        await message.edit(f"✅ User {target_id} di-disapprove!")
                    else:
                        await message.edit("Reply ke pesan user yang mau di-disapprove!")
                except Exception as e:
                    logger.error(f"Disapprove error: {e}")
            
            @client.on_message(pyro_filters.command("block", prefixes=".") & pyro_filters.me)
            async def block_handler(client, message):
                logger.info(f"Block command from {user_id}")
                try:
                    if message.reply_to_message:
                        target_id = message.reply_to_message.from_user.id
                        pmpermit_manager.block(user_id, target_id)
                        await message.edit(f"🚫 User {target_id} di-block!")
                    else:
                        await message.edit("Reply ke pesan user yang mau di-block!")
                except Exception as e:
                    logger.error(f"Block error: {e}")
            
            @client.on_message(pyro_filters.command("unblock", prefixes=".") & pyro_filters.me)
            async def unblock_handler(client, message):
                logger.info(f"Unblock command from {user_id}")
                try:
                    if message.reply_to_message:
                        target_id = message.reply_to_message.from_user.id
                        pmpermit_manager.unblock(user_id, target_id)
                        await message.edit(f"✅ User {target_id} di-unblock!")
                    else:
                        await message.edit("Reply ke pesan user yang mau di-unblock!")
                except Exception as e:
                    logger.error(f"Unblock error: {e}")
            
            # PM Permit Handler (untuk pesan masuk)
            @client.on_message(pyro_filters.private & ~pyro_filters.me)
            async def pm_handler(client, message):
                if not pmpermit_manager.is_enabled(user_id):
                    return
                
                sender_id = message.from_user.id
                
                # Cek kalau sudah approved atau blocked
                if pmpermit_manager.is_approved(user_id, sender_id):
                    return
                if pmpermit_manager.is_blocked(user_id, sender_id):
                    await message.delete()
                    return
                
                # Cek warn
                warn = pmpermit_manager.add_warn(user_id, sender_id)
                
                if warn >= pmpermit_manager.max_warn:
                    pmpermit_manager.block(user_id, sender_id)
                    await client.send_message(sender_id, "🚫 **Anda telah diblokir karena spam!**")
                    await message.delete()
                else:
                    # Kirim warning
                    msg = pmpermit_manager.get_message(user_id)
                    msg = msg.format(warn=warn, max_warn=pmpermit_manager.max_warn)
                    await client.send_message(sender_id, msg)
                    await message.delete()
        
        logger.info(f"✅ Handlers registered for {user_id}")

userbot_manager = UserbotManager()

# ==================== BOT HANDLERS ====================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    data = get_user(user.id)
    
    if not data:
        save_user(user.id, {
            'user_id': user.id,
            'username': user.username,
            'name': user.first_name,
            'registered': datetime.now().isoformat(),
            'plan': None,
            'expired': None,
            'userbot_active': False
        })
    
    text = f"👋 **Halo {user.first_name}!**\n\nPilih menu:"
    keyboard = [
        [InlineKeyboardButton("✨ Buat Userbot", callback_data='create')],
        [InlineKeyboardButton("📦 Plan & Harga", callback_data='pricing')],
        [InlineKeyboardButton("❓ Status", callback_data='status')],
        [InlineKeyboardButton("🔄 Restart", callback_data='restart')]
    ]
    await update.message.reply_text(text, parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(keyboard))

async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    uid = update.effective_user.id
    
    if data == 'create':
        udata = get_user(uid)
        if not udata or not udata.get('plan'):
            kb = [
                [InlineKeyboardButton("⚡ Lite - Rp10k", callback_data='buy_lite')],
                [InlineKeyboardButton("🧩 Basic - Rp15k", callback_data='buy_basic')],
                [InlineKeyboardButton("💎 Pro - Rp22k", callback_data='buy_pro')],
                [InlineKeyboardButton("🔙 Back", callback_data='back')]
            ]
            await query.edit_message_text("❌ Belum punya plan! Pilih:", reply_markup=InlineKeyboardMarkup(kb))
        else:
            await setup_flow(query, context)
    
    elif data == 'pricing':
        txt = """📦 **HARGA**\n\n⚡ Lite: Rp10k (25 plugin)\n🧩 Basic: Rp15k (56 plugin)\n💎 Pro: Rp22k (99 plugin)"""
        await query.edit_message_text(txt, parse_mode='Markdown', reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data='back')]]))
    
    elif data.startswith('buy_'):
        plan = data.split('_')[1]
        price = PLANS[plan]['price']
        oid = ''.join(random.choices('ABCDEFGHJKLMNPQRSTUVWXYZ23456789', k=8))
        pending_payments[uid] = {'order_id': oid, 'plan': plan, 'amount': price}
        
        txt = f"""🛒 **PEMBAYARAN**\n\n📋 Order: `{oid}`\n📦 {PLANS[plan]['name']}\n💰 Rp{price:,}\n\n🏦 BCA: 1234567890\n🏦 DANA: 081234567890\n\n✅ Klik Konfirmasi setelah bayar"""
        kb = [[InlineKeyboardButton("✅ Konfirmasi", callback_data='confirm')], [InlineKeyboardButton("🔙 Back", callback_data='back')]]
        await query.edit_message_text(txt, parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(kb))
    
    elif data == 'confirm':
        pay = pending_payments.get(uid, {})
        if not pay:
            return await query.edit_message_text("❌ Data tidak ditemukan", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data='back')]]))
        
        adm_txt = f"🚨 **NEW PAYMENT**\n\n👤 {update.effective_user.mention_html()}\n🆔 `{uid}`\n📋 {pay['order_id']}\n📦 {pay['plan']}\n💰 Rp{pay['amount']:,}\n\n✅ `/verify {uid} {pay['order_id']}`"
        try:
            await context.bot.send_message(ADMIN_ID, adm_txt, parse_mode='HTML')
        except Exception as e:
            logger.error(f"Admin notify error: {e}")
        
        await query.edit_message_text("📸 **Upload bukti pembayaran!**", parse_mode='Markdown')
        context.user_data['waiting_payment'] = True
    
    elif data == 'status':
        u = get_user(uid) or {}
        pl = u.get('plan', 'NONE')
        ex = u.get('expired', 'N/A')[:10] if u.get('expired') else 'N/A'
        st = "✅ Aktif" if u.get('userbot_active') else "❌ Nonaktif"
        txt = f"📊 **STATUS**\n\n👤 {u.get('name', 'N/A')}\n📦 {pl.upper()}\n⏱️ {ex}\n🤖 {st}"
        await query.edit_message_text(txt, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data='back')]]))
    
    elif data == 'restart':
        u = get_user(uid) or {}
        if not u.get('plan'):
            return await query.edit_message_text("❌ Belum punya plan!")
        await query.edit_message_text("🔄 Restarting...")
        await userbot_manager.stop_userbot(uid)
        await asyncio.sleep(2)
        ok, msg = await userbot_manager.start_userbot(uid, u.get('plan'))
        txt = "✅ **Restarted!**" if ok else f"❌ Failed: {msg}"
        await query.edit_message_text(txt, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data='back')]]))
    
    elif data == 'back':
        await start(update, context)
    
    elif data == 'setup':
        await setup_flow(query, context)

async def setup_flow(query, context):
    await query.edit_message_text("""
📱 **SETUP**\n\n**Langkah 1/3**\nKirim nomor telepon:\nFormat: `+6281234567890`\n\n⚠️ Pastikan:\n• Nomor aktif\n• Bisa terima SMS\n• Belum jadi userbot lain
    """, parse_mode='Markdown')
    context.user_data['setup_step'] = 'phone'

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    step = context.user_data.get('setup_step')
    text = update.message.text
    
    if step == 'phone':
        if not text.startswith('+') or not text[1:].replace(' ', '').isdigit():
            return await update.message.reply_text("❌ Format: `+6281234567890`")
        
        await update.message.reply_text("⏳ Sending OTP...")
        try:
            cl = Client(f"temp_{uid}", API_ID, API_HASH, phone_number=text)
            await cl.connect()
            sent = await cl.send_code(text)
            user_clients[uid] = {'client': cl, 'phone': text, 'hash': sent.phone_code_hash}
            context.user_data['setup_step'] = 'otp'
            await update.message.reply_text("📲 **OTP sent!**\n\nMasukkan kode (dengan spasi):\nContoh: `1 2 3 4 5`", parse_mode='Markdown')
        except Exception as e:
            logger.error(f"OTP error: {e}")
            await update.message.reply_text(f"❌ Error: {e}")
    
    elif step == 'otp':
        cd = user_clients.get(uid)
        if not cd:
            return await update.message.reply_text("❌ Session expired. /start")
        try:
            cl, ph, ha = cd['client'], cd['phone'], cd['hash']
            await cl.sign_in(ph, ha, text.replace(" ", ""))
            sess = await cl.export_session_string()
            save_session(uid, sess)
            await cl.disconnect()
            
            ud = get_user(uid)
            pl = ud.get('plan', 'lite')
            ok, msg = await userbot_manager.start_userbot(uid, pl)
            
            if ok:
                await update.message.reply_text(f"🔥 **USERBOT AKTIF!**\n\n✅ Plan: {pl.upper()}\n✅ Status: Aktif 24/7\n\nKetik `.help` untuk command.\n\n⚠️ **Jangan logout dari HP!**")
            else:
                await update.message.reply_text(f"❌ Gagal aktifkan: {msg}")
            
            context.user_data['setup_step'] = None
            user_clients.pop(uid, None)
        except SessionPasswordNeeded:
            context.user_data['setup_step'] = '2fa'
            await update.message.reply_text("🔐 **2FA Required**\n\nMasukkan password:")
        except Exception as e:
            logger.error(f"OTP verify error: {e}")
            await update.message.reply_text(f"❌ Error: {e}")
    
    elif step == '2fa':
        cd = user_clients.get(uid)
        if not cd:
            return await update.message.reply_text("❌ Session expired")
        try:
            cl = cd['client']
            await cl.check_password(text)
            sess = await cl.export_session_string()
            save_session(uid, sess)
            await cl.disconnect()
            
            ud = get_user(uid)
            pl = ud.get('plan', 'lite')
            ok, msg = await userbot_manager.start_userbot(uid, pl)
            
            if ok:
                await update.message.reply_text("🔥 **Userbot aktif!**\n\nKetik `.help` untuk command.")
            else:
                await update.message.reply_text(f"❌ Gagal: {msg}")
            
            context.user_data['setup_step'] = None
            user_clients.pop(uid, None)
        except Exception as e:
            logger.error(f"2FA error: {e}")
            await update.message.reply_text(f"❌ Password salah: {e}")

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get('waiting_payment'):
        return
    uid = update.effective_user.id
    try:
        await update.message.forward(ADMIN_ID)
        await context.bot.send_message(ADMIN_ID, f"📸 Bukti dari {update.effective_user.mention_html()}\nID: `{uid}`", parse_mode='HTML')
        await update.message.reply_text("✅ Bukti diterima! Tunggu verifikasi admin.")
        context.user_data['waiting_payment'] = False
    except Exception as e:
        logger.error(f"Photo forward error: {e}")

async def verify_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return await update.message.reply_text("❌ Admin only!")
    if len(context.args) < 2:
        return await update.message.reply_text("Usage: `/verify <user_id> <order_id>`")
    
    try:
        uid = int(context.args[0])
        oid = context.args[1]
        pay = pending_payments.get(uid, {})
        plan = pay.get('plan', 'lite')
        exp = (datetime.now() + timedelta(days=30)).isoformat()
        
        save_user(uid, {'plan': plan, 'expired': exp, 'verified': True, 'order_id': oid})
        
        await context.bot.send_message(
            uid,
            f"✅ **VERIFIED!**\n\n📦 {PLANS[plan]['name']}\n⏱️ Expired: {exp[:10]}\n\n🚀 Klik Setup:",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("✨ Setup Userbot", callback_data='setup')]])
        )
        await update.message.reply_text(f"✅ User {uid} verified!")
    except Exception as e:
        logger.error(f"Verify error: {e}")
        await update.message.reply_text(f"❌ Error: {e}")

# ==================== MAIN ====================
async def post_init(app):
    await asyncio.sleep(3)
    users = get_all_users()
    cnt = 0
    for uid, data in users.items():
        if data.get('userbot_active') and data.get('plan'):
            try:
                ok, msg = await userbot_manager.start_userbot(uid, data['plan'])
                if ok:
                    cnt += 1
                    logger.info(f"Restored userbot {uid}")
                else:
                    logger.error(f"Failed to restore {uid}: {msg}")
                await asyncio.sleep(2)
            except Exception as e:
                logger.error(f"Restore error {uid}: {e}")
    logger.info(f"✅ Restored {cnt} userbots")

def main():
    threading.Thread(target=run_flask, daemon=True).start()
    
    application = Application.builder().token(TOKEN).post_init(post_init).build()
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("verify", verify_cmd))
    application.add_handler(CallbackQueryHandler(button))
    application.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    
    logger.info("🤖 Bot started!")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
'''

# Simpan ke file
with open('/mnt/kimi/output/main_complete.py', 'w') as f:
    f.write(main_py_complete)

print("✅ File main.py lengkap dengan AutoBC dan PMPermit sudah dibuat!")
print("\n📋 Fitur baru yang ditambahkan:")
print("\n🔄 AUTO BROADCAST (Plan Lite+):")
print("   .autobc <interval> <pesan>  - Mulai auto broadcast")
print("   .stopbc                      - Stop broadcast")
print("   .bcstatus                    - Cek status broadcast")
print("\n🔒 PM PERMIT (Plan Pro):")
print("   .pmpermit on/off             - Aktif/nonaktif PM security")
print("   .approve                     - Approve user (reply)")
print("   .disapprove                  - Disapprove user (reply)")
print("   .block                       - Block user (reply)")
print("   .unblock                     - Unblock user (reply)")
print("\nFile tersimpan di: /mnt/kimi/output/main_complete.py")
