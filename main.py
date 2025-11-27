# ============================
#        ASSASSIN BOT
# ============================

import os
import sqlite3
import random
import time
import asyncio

from aiogram import Bot, Dispatcher
from aiogram.types import Message, CallbackQuery, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton

# ====== TOKEN ======
TOKEN = os.getenv("TOKEN")
if not TOKEN:
    raise RuntimeError("TOKEN topilmadi! Render/Env ga TOKEN qo'y!")

# Aiogram 3
bot = Bot(token=TOKEN, parse_mode="HTML")
dp = Dispatcher()

# ====== DATABASE ======
DB_FILE = "guild_game.db"
conn = sqlite3.connect(DB_FILE, check_same_thread=False)
cur = conn.cursor()

# ====== TABLES ======
cur.execute('''
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    username TEXT,
    gold INTEGER,
    guild_xp INTEGER,
    guild_level INTEGER
)
''')

cur.execute('''
CREATE TABLE IF NOT EXISTS assassins (
    assassin_id TEXT PRIMARY KEY,
    user_id INTEGER,
    name TEXT,
    power INTEGER,
    level INTEGER,
    hp INTEGER,
    max_hp INTEGER,
    status TEXT,
    weapon TEXT,
    armor TEXT
)
''')

cur.execute('''
CREATE TABLE IF NOT EXISTS inventory (
    item_id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    name TEXT,
    type TEXT,
    power_mod INTEGER,
    rarity TEXT
)
''')

conn.commit()

# ======================================================
#                  DATABASE FUNKSIYALAR
# ======================================================
def ensure_user(uid: int, username: str = None):
    cur.execute("SELECT * FROM users WHERE user_id=?", (uid,))
    if not cur.fetchone():
        cur.execute(
            "INSERT INTO users (user_id, username, gold, guild_xp, guild_level) VALUES (?,?,?,?,?)",
            (uid, username or "", 50, 0, 1)
        )
        conn.commit()

def get_user(user_id: int):
    cur.execute("SELECT * FROM users WHERE user_id=?", (user_id,))
    return cur.fetchone()

def update_user_gold(user_id: int, new_gold: int):
    cur.execute("UPDATE users SET gold=? WHERE user_id=?", (new_gold, user_id))
    conn.commit()

def guild_xp_needed(lvl: int):
    return 100 + (lvl - 1) * 75

def update_user_xp_and_level(user_id: int, add_xp: int):
    u = list(get_user(user_id))
    current_xp = u[3] + add_xp
    lvl = u[4]
    leveled = False

    while current_xp >= guild_xp_needed(lvl):
        current_xp -= guild_xp_needed(lvl)
        lvl += 1
        leveled = True

    cur.execute("UPDATE users SET guild_xp=?, guild_level=? WHERE user_id=?",
                (current_xp, lvl, user_id))
    conn.commit()
    return leveled, lvl

def create_assassin(user_id: int):
    name = random.choice(["Ara","Boran","Cyrus","Dara","Eron","Fael","Galen","Horo","Ira","Jax"]) + str(random.randint(1,99))
    power = random.randint(3, 8)
    assassin_id = str(int(time.time()*1000)) + str(random.randint(0,999))

    cur.execute('''
        INSERT INTO assassins (assassin_id,user_id,name,power,level,hp,max_hp,status,weapon,armor)
        VALUES (?,?,?,?,?,?,?,?,?,?)
    ''', (assassin_id, user_id, name, power, 1, 100, 100, "ready", None, None))

    conn.commit()
    return assassin_id, name, power

def list_assassins(user_id: int):
    cur.execute("SELECT * FROM assassins WHERE user_id=?", (user_id,))
    return cur.fetchall()

def get_assassin(assassin_id: str):
    cur.execute("SELECT * FROM assassins WHERE assassin_id=?", (assassin_id,))
    return cur.fetchone()

def update_assassin_field(assassin_id: str, field: str, value):
    cur.execute(f"UPDATE assassins SET {field}=? WHERE assassin_id=?",
                (value, assassin_id))
    conn.commit()

def add_item(user_id: int, name: str, itype: str, power_mod: int, rarity: str):
    cur.execute('''INSERT INTO inventory (user_id,name,type,power_mod,rarity)
                   VALUES (?,?,?,?,?)''',
                (user_id, name, itype, power_mod, rarity))
    conn.commit()

def list_inventory(user_id: int):
    cur.execute("SELECT * FROM inventory WHERE user_id=?", (user_id,))
    return cur.fetchall()

# ======================================================
#                    POWER CALC
# ======================================================

def parse_eq_value(eq_str):
    if not eq_str:
        return 0
    try:
        return int(eq_str.split("+")[1])
    except:
        return 0

def calc_assassin_effective_power_from_row(row):
    base = row[3] + row[4]
    w = parse_eq_value(row[8])
    a = parse_eq_value(row[9])
    return base + w + a

# ======================================================
#                    KEYBOARDS
# ======================================================

main_menu = ReplyKeyboardMarkup(resize_keyboard=True)
main_menu.row(KeyboardButton("👤 Profil"), KeyboardButton("👥 Assassinlar"))
main_menu.row(KeyboardButton("🗡 Yollash"), KeyboardButton("🎯 Missiyalar"))
main_menu.row(KeyboardButton("🎒 Inventar"), KeyboardButton("🏛 Guild"))
main_menu.row(KeyboardButton("⚔️ PVP"))

missions_inline = InlineKeyboardMarkup()
missions_inline.row(
    InlineKeyboardButton("🔹 Oson", callback_data="mission_easy"),
    InlineKeyboardButton("🔸 O'rta", callback_data="mission_medium"),
    InlineKeyboardButton("🔺 Qiyin", callback_data="mission_hard")
)

# ======================================================
#                     MISSIYA LOGIKA
# ======================================================

def try_mission_row(ass_row, difficulty):
    base = {"easy": 60, "medium": 40, "hard": 25}[difficulty]
    p = calc_assassin_effective_power_from_row(ass_row)

    chance = max(5, min(base + p*4, 95))
    success = random.randint(1,100) <= chance

    gold_range = {"easy":(10,25), "medium":(25,50), "hard":(50,100)}[difficulty]
    xp_range = {"easy":(5,15), "medium":(15,35), "hard":(35,70)}[difficulty]

    gold = random.randint(*gold_range)
    xp = random.randint(*xp_range)

    death_chance = {"easy":0.01, "medium":0.05, "hard":0.15}[difficulty]
    if not success: death_chance *= 2
    died = random.random() < death_chance

    found = None
    if success and random.random() < 0.15:
        itype = random.choice(["weapon","armor"])
        name = f"{'Klassik' if itype=='weapon' else 'Qalin'} {random.choice(['qilich','kama','zirh','bolta'])}"
        found = {"name":name, "type":itype, "power_mod":random.randint(1,6),
                 "rarity":random.choice(["common","uncommon","rare"])}

    return success, gold, xp, died, found

async def revive_after_delay(assassin_id):
    await asyncio.sleep(15)
    update_assassin_field(assassin_id, "status", "ready")

# ======================================================
#                       PVP
# ======================================================

def pvp_battle_rows(my_row, opp_row):
    mp = calc_assassin_effective_power_from_row(my_row) + random.randint(-3,3)
    op = calc_assassin_effective_power_from_row(opp_row) + random.randint(-3,3)

    if random.random() < 0.1: mp *= 1.5
    if random.random() < 0.1: op *= 1.5

    if mp >= op:
        return my_row, opp_row, random.randint(5,25)
    else:
        return opp_row, my_row, 0

# ======================================================
#                   HANDLERS
# ======================================================

@dp.message(commands=["start"])
async def cmd_start(m: Message):
    ensure_user(m.from_user.id, m.from_user.username)
    await m.answer("🕵️ Assassin's Guild ga xush kelibsiz!", reply_markup=main_menu)

@dp.message(F.text == "👤 Profil")
async def handle_profile(m: Message):
    ensure_user(m.from_user.id, m.from_user.username)
    u = get_user(m.from_user.id)
    await m.answer(
        f"👤 Profil: {u[1]}\n💰 Oltin: {u[2]}\n"
        f"🏛 Guild lvl: {u[4]} (XP: {u[3]}/{guild_xp_needed(u[4])})",
        reply_markup=main_menu,
    )

@dp.message(F.text == "👥 Assassinlar")
async def handle_assassins(m: Message):
    rows = list_assassins(m.from_user.id)
    if not rows:
        await m.answer("Sizda assassin yo‘q!", reply_markup=main_menu)
        return

    out = "👥 Assassinlar:\n"
    for r in rows:
        out += f"{r[2]} | Lv:{r[4]} | P:{r[3]} | Eff:{calc_assassin_effective_power_from_row(r)} | {r[7]}\n"

    await m.answer(out, reply_markup=main_menu)

@dp.message(F.text == "🗡 Yollash")
async def handle_hire(m: Message):
    u = get_user(m.from_user.id)
    price = 20 + u[4]*10
    if u[2] < price:
        await m.answer("Oltin yetarli emas!", reply_markup=main_menu)
        return

    update_user_gold(m.from_user.id, u[2] - price)
    ass_id, name, power = create_assassin(m.from_user.id)

    await m.answer(f"🗡 Yangi assassin: {name} (P:{power})", reply_markup=main_menu)

@dp.message(F.text == "🎯 Missiyalar")
async def handle_missions(m: Message):
    await m.answer("Missiya tanlang:", reply_markup=missions_inline)

@dp.callback_query()
async def cb_mission(c: CallbackQuery):
    if not c.data.startswith("mission_"):
        await c.answer()
        return

    diff = c.data.split("_")[1]
    rows = list_assassins(c.from_user.id)
    ready = [r for r in rows if r[7] == "ready"]

    if not ready:
        await c.message.answer("Tayyor assassin yo‘q!", reply_markup=main_menu)
        await c.answer()
        return

    ass = random.choice(ready)
    success, gold, xp, died, found = try_mission_row(ass, diff)

    msg = f"🎯 Missiya ({diff})\nAssassin: {ass[2]}\n"
    msg += "✅ Muvaffaqiyatli!\n" if success else "❌ Bajarilmadi!\n"
    msg += f"💰 Oltin: +{gold}\n🏛 XP: +{xp}\n"

    # gold + XP
    u = get_user(c.from_user.id)
    update_user_gold(c.from_user.id, u[2] + gold)
    lvlup, newlvl = update_user_xp_and_level(c.from_user.id, xp)
    if lvlup:
        msg += f"🎉 Guild Level oshdi → {newlvl}\n"

    if died:
        update_assassin_field(ass[0], "status", "dead")
        msg += "☠ Assassin halok bo‘ldi.\n"
    else:
        update_assassin_field(ass[0], "status", "busy")
        asyncio.create_task(revive_after_delay(ass[0]))

    if found:
        add_item(c.from_user.id, found["name"], found["type"], found["power_mod"], found["rarity"])
        msg += f"🎁 Loot: {found['name']} (+{found['power_mod']})\n"

    await c.message.answer(msg, reply_markup=main_menu)
    await c.answer()

@dp.message(F.text == "🎒 Inventar")
async def handle_inventory(m: Message):
    items = list_inventory(m.from_user.id)
    if not items:
        await m.answer("Inventar bo‘sh!", reply_markup=main_menu)
        return

    out = "🎒 Inventar:\n"
    for i in items:
        out += f"{i[2]} | {i[3]} | +{i[4]} | {i[5]}\n"

    await m.answer(out, reply_markup=main_menu)

@dp.message(F.text == "🏛 Guild")
async def handle_guild(m: Message):
    u = get_user(m.from_user.id)
    await m.answer(
        f"🏛 Guild Level: {u[4]}\nXP: {u[3]}/{guild_xp_needed(u[4])}",
        reply_markup=main_menu
    )

@dp.message(F.text == "⚔️ PVP")
async def handle_pvp(m: Message):
    my = list_assassins(m.from_user.id)
    if not my:
        await m.answer("Sizda assassin yo‘q!", reply_markup=main_menu)
        return

    opp_ids = cur.execute("SELECT user_id FROM users WHERE user_id != ?", (m.from_user.id,)).fetchall()
    if not opp_ids:
        await m.answer("Raqib topilmadi.", reply_markup=main_menu)
        return

    opp_id = random.choice(opp_ids)[0]
    opp_ass = list_assassins(opp_id)
    if not opp_ass:
        await m.answer("Raqibda assassin yo‘q.", reply_markup=main_menu)
        return

    result = pvp_battle_rows(random.choice(my), random.choice(opp_ass))
    winner, loser, gold = result

    msg = (
        f"⚔️ PVP Jang!\n"
        f"G‘olib: {winner[2]}\n"
        f"Yutgan oltin: {gold}"
    )

    if gold > 0:
        u = get_user(m.from_user.id)
        update_user_gold(m.from_user.id, u[2] + gold)

    await m.answer(msg, reply_markup=main_menu)

# ======================================================
#                   START BOT
# ======================================================

import asyncio
async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
