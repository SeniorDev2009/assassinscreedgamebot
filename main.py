# main.py
import sqlite3
import random
import time
from aiogram import Bot, Dispatcher, executor, types
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
import os

# ====== SOZLAMALAR ======
TOKEN = os.getenv("TOKEN")   # <-- BotFather tokeningizni shu yerga qo'ying
DB_FILE = "guild_game.db"

bot = Bot(token=os.getenv("TOKEN"))
dp = Dispatcher(bot)

# ====== SQLite ulanish ======
conn = sqlite3.connect(DB_FILE, check_same_thread=False)
cur = conn.cursor()

# ====== Jadval yaratish ======
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

# ====== Yordamchi funksiyalar ======
def ensure_user(uid: int, username: str = None):
    cur.execute("SELECT * FROM users WHERE user_id=?", (uid,))
    if not cur.fetchone():
        cur.execute(
            "INSERT INTO users (user_id, username, gold, guild_xp, guild_level) VALUES (?,?,?,?,?)",
            (uid, username or "", 50, 0, 1)
        )
        conn.commit()

def create_assassin(user_id: int):
    name = random.choice(["Ara","Boran","Cyrus","Dara","Eron","Fael","Galen","Horo","Ira","Jax"]) + str(random.randint(1,99))
    power = random.randint(3,8)
    assassin_id = str(int(time.time()*1000)) + str(random.randint(0,999))
    cur.execute('''
        INSERT INTO assassins (assassin_id,user_id,name,power,level,hp,max_hp,status,weapon,armor)
        VALUES (?,?,?,?,?,?,?,?,?,?)
    ''', (assassin_id,user_id,name,power,1,100,100,"ready",None,None))
    conn.commit()
    return assassin_id, name, power

def list_assassins(user_id: int):
    cur.execute("SELECT * FROM assassins WHERE user_id=?", (user_id,))
    return cur.fetchall()  # tuples

def get_user(user_id: int):
    cur.execute("SELECT * FROM users WHERE user_id=?", (user_id,))
    return cur.fetchone()

def update_user_gold(user_id: int, new_gold: int):
    cur.execute("UPDATE users SET gold=? WHERE user_id=?", (new_gold,user_id))
    conn.commit()

def update_user_xp_and_level(user_id: int, add_xp: int):
    user = list(get_user(user_id))
    current_xp = user[3] + add_xp
    lvl = user[4]
    leveled = False
    while current_xp >= guild_xp_needed(lvl):
        current_xp -= guild_xp_needed(lvl)
        lvl += 1
        leveled = True
    cur.execute("UPDATE users SET guild_xp=?, guild_level=? WHERE user_id=?", (current_xp, lvl, user_id))
    conn.commit()
    return leveled, lvl

def get_assassin(assassin_id: str):
    cur.execute("SELECT * FROM assassins WHERE assassin_id=?", (assassin_id,))
    return cur.fetchone()

def update_assassin_field(assassin_id: str, field: str, value):
    cur.execute(f"UPDATE assassins SET {field}=? WHERE assassin_id=?", (value,assassin_id))
    conn.commit()

def guild_xp_needed(lvl: int):
    return 100 + (lvl-1) * 75

def add_item(user_id: int, name: str, itype: str, power_mod: int, rarity: str):
    cur.execute("INSERT INTO inventory (user_id,name,type,power_mod,rarity) VALUES (?,?,?,?,?)",
                (user_id,name,itype,power_mod,rarity))
    conn.commit()

def list_inventory(user_id: int):
    cur.execute("SELECT * FROM inventory WHERE user_id=?", (user_id,))
    return cur.fetchall()

def parse_eq_value(eq_str):
    """eq_str format: 'Name+3' -> returns int 3; if None -> 0"""
    if not eq_str:
        return 0
    try:
        return int(eq_str.split("+")[1])
    except:
        return 0

def calc_assassin_effective_power_from_row(ass_row):
    """
    ass_row is tuple from DB: (assassin_id, user_id, name, power, level, hp, max_hp, status, weapon, armor)
    """
    base_power = ass_row[3] + ass_row[4]
    weap = parse_eq_value(ass_row[8])
    armor = parse_eq_value(ass_row[9])
    return base_power + weap + armor

# ====== Keyboards ======
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

# ====== Mission & PVP mechanics ======
def try_mission_row(ass_row, difficulty: str):
    """Return (success:bool, gold:int, xp:int, died:bool, found_item:dict or None)"""
    base = {"easy":60,"medium":40,"hard":25}[difficulty]
    power = calc_assassin_effective_power_from_row(ass_row)
    chance = max(5, min(base + power*4, 95))
    success = random.randint(1,100) <= chance

    gold_ranges = {"easy":(10,25),"medium":(25,50),"hard":(50,100)}
    xp_ranges = {"easy":(5,15),"medium":(15,35),"hard":(35,70)}
    death_base = {"easy":0.01,"medium":0.05,"hard":0.15}[difficulty]
    if not success:
        death_base *= 2

    gold = random.randint(*gold_ranges[difficulty])
    xp = random.randint(*xp_ranges[difficulty])
    died = random.random() < death_base

    found_item = None
    if success and random.random() < 0.15:
        itype = random.choice(["weapon","armor"])
        iname = f"{'Klassik' if itype=='weapon' else 'Qalin'} {random.choice(['qilich','bolta','kama','zirh'])}"
        found_item = {"name": iname, "type": itype, "power_mod": random.randint(1,6), "rarity": random.choice(["common","uncommon","rare"])}
    return success, gold, xp, died, found_item

def pvp_battle_rows(my_row, opp_row):
    """Return (winner_row, loser_row, gold_win:int, detail:dict)"""
    my_p = calc_assassin_effective_power_from_row(my_row) + random.randint(-3,3)
    opp_p = calc_assassin_effective_power_from_row(opp_row) + random.randint(-3,3)
    # criticals
    my_crit = random.random() < 0.10
    opp_crit = random.random() < 0.10
    if my_crit: my_p = int(my_p * 1.5)
    if opp_crit: opp_p = int(opp_p * 1.5)
    # winner
    if my_p >= opp_p:
        gold_win = random.randint(5,25)
        detail = {"my_power": my_p, "opp_power": opp_p, "my_crit": my_crit, "opp_crit": opp_crit}
        return my_row, opp_row, gold_win, detail
    else:
        gold_win = random.randint(0,0)  # loser gets nothing; winner will be other row's owner who receives gold
        detail = {"my_power": my_p, "opp_power": opp_p, "my_crit": my_crit, "opp_crit": opp_crit}
        return opp_row, my_row, gold_win, detail

# ====== Handlers ======
@dp.message_handler(commands=["start","help"])
async def cmd_start(message: types.Message):
    ensure_user(message.from_user.id, message.from_user.username)
    text = ("🕵️‍♂️ *Assassin's Guild* ga xush kelibsiz!\n"
            "Menyudan boshlang: 👤 Profil, 👥 Assassinlar, 🗡 Yollash, 🎯 Missiyalar, 🎒 Inventar, ⚔️ PVP")
    await message.reply(text, parse_mode="HTML", reply_markup=main_menu)

@dp.message_handler(lambda m: m.text and "Profil" in m.text)
async def handle_profile(m: types.Message):
    ensure_user(m.from_user.id, m.from_user.username)
    u = get_user(m.from_user.id)
    text = (f"👤 Profil: {u[1]}\n💰 Oltin: {u[2]}\n"
            f"🏛 Guild lvl: {u[4]} (XP: {u[3]}/{guild_xp_needed(u[4])})")
    await m.reply(text, reply_markup=main_menu)

@dp.message_handler(lambda m: m.text and "Assassinlar" in m.text)
async def handle_assassins(m: types.Message):
    ensure_user(m.from_user.id, m.from_user.username)
    ass = list_assassins(m.from_user.id)
    if not ass:
        await m.reply("Sizda assassinlar yo'q. 🗡 Yollash tugmasi bilan yangi assassin yollang.", reply_markup=main_menu)
        return
    lines = []
    for row in ass:
        # row: (assassin_id, user_id, name, power, level, hp, max_hp, status, weapon, armor)
        eff = calc_assassin_effective_power_from_row(row)
        lines.append(f"{row[2]} | Lv:{row[4]} | P:{row[3]} | Eff:{eff} | Status:{row[7]}")
    await m.reply("👥 Assassinlaringiz:\n" + "\n".join(lines), reply_markup=main_menu)

@dp.message_handler(lambda m: m.text and "Yollash" in m.text)
async def handle_hire(m: types.Message):
    ensure_user(m.from_user.id, m.from_user.username)
    u = get_user(m.from_user.id)
    price = 20 + u[4] * 10
    if u[2] < price:
        await m.reply(f"Oltin yetarli emas: Sizda {u[2]}, kerak: {price}", reply_markup=main_menu)
        return
    update_user_gold(m.from_user.id, u[2] - price)
    ass_id, name, power = create_assassin(m.from_user.id)
    # kamdan-kam inventar item berish
    if random.random() < 0.20:
        itype = random.choice(["weapon","armor"])
        iname = f"{'Klassik' if itype=='weapon' else 'Qalin'} {random.choice(['qilich','bolta','kama','zirh'])}"
        add_item(m.from_user.id, iname, itype, random.randint(1,5), random.choice(["common","uncommon","rare"]))
    await m.reply(f"🗡 Yangi assassin: {name} (P:{power}). Narx: {price} oltin.", reply_markup=main_menu)

@dp.message_handler(lambda m: m.text and "Missiyalar" in m.text)
async def handle_missions(m: types.Message):
    await m.reply("🎯 Missiya tanlang:", reply_markup=missions_inline)

@dp.callback_query_handler(lambda c: c.data and c.data.startswith("mission_"))
async def cb_mission(c: types.CallbackQuery):
    ensure_user(c.from_user.id, c.from_user.username)
    difficulty = c.data.split("_")[1]  # easy/medium/hard
    rows = list_assassins(c.from_user.id)
    ready = [r for r in rows if r[7] == "ready"]
    if not ready:
        await bot.answer_callback_query(c.id, "Tayyor assassin yo'q.")
        return
    ass_row = random.choice(ready)
    update_assassin_field(ass_row[0], "status", "on_mission")
    success, gold, xp, died, item = try_mission_row(ass_row, difficulty)
    resp_text = ""
    if success:
        # update gold and xp
        u = get_user(c.from_user.id)
        update_user_gold(c.from_user.id, u[2] + gold)
        leveled, new_lvl = update_user_xp_and_level(c.from_user.id, xp)
        # level up assassin locally: increase level in DB
        cur.execute("UPDATE assassins SET level=? WHERE assassin_id=?", (ass_row[4]+1, ass_row[0]))
        # set status ready
        update_assassin_field(ass_row[0], "status", "ready")
        if item:
            add_item(c.from_user.id, item["name"], item["type"], item["power_mod"], item["rarity"])
        resp_text = (f"✅ Missiya muvaffaqiyatli!\nAssassin: *{ass_row[2]}* Lv:+1\n"
                     f"💰 Gold +{gold}  XP +{xp}")
        if item:
            resp_text += f"\n🎁 Topildi: {item['name']} (+{item['power_mod']})"
        if leveled:
            resp_text += f"\n🏛 Guild darajangiz oshdi: {new_lvl}"
    else:
        # fail: maybe death
        if died:
            update_assassin_field(ass_row[0], "status", "dead")
            resp_text = f"❌ Missiya muvaffaqiyatsiz. Afsuski *{ass_row[2]}* o'ldirildi."
        else:
            # penalty gold
            u = get_user(c.from_user.id)
            lost = min(u[2], random.randint(2, 15))
            update_user_gold(c.from_user.id, u[2] - lost)
            update_assassin_field(ass_row[0], "status", "ready")
            resp_text = f"❌ Missiya muvaffaqiyatsiz. Assassin qaytdi, lekin siz {lost} gold yo'qotdingiz."
    await bot.send_message(c.from_user.id, resp_text, parse_mode="HTML", reply_markup=main_menu)
    await bot.answer_callback_query(c.id, "")

@dp.message_handler(lambda m: m.text and "Inventar" in m.text)
async def handle_inventory(m: types.Message):
    ensure_user(m.from_user.id, m.from_user.username)
    items = list_inventory(m.from_user.id)
    if not items:
        await m.reply("🎒 Inventar bo'sh.", reply_markup=main_menu)
        return
    lines = []
    for idx, it in enumerate(items, start=1):
        lines.append(f"{idx}. {it[2]} ({it[3]}) P+{it[4]} | {it[5]}")
    lines.append("\n/equip <index> — itemni birinchi assassin-ga jihozlash")
    await m.reply("🎒 Inventaringiz:\n" + "\n".join(lines), reply_markup=main_menu)

@dp.message_handler(commands=["equip"])
async def cmd_equip(m: types.Message):
    args = m.get_args().strip()
    if not args.isdigit():
        await m.reply("Foydalanish: /equip <index>", reply_markup=main_menu)
        return
    idx = int(args) - 1
    items = list_inventory(m.from_user.id)
    if idx < 0 or idx >= len(items):
        await m.reply("Noto'g'ri index.", reply_markup=main_menu)
        return
    item = items[idx]  # (item_id, user_id, name, type, power_mod, rarity)
    assassins = list_assassins(m.from_user.id)
    if not assassins:
        await m.reply("Assassin yo'q. Avval yollang.", reply_markup=main_menu)
        return
    # choose first assassin (simple)
    ass = assassins[0]
    field = "weapon" if item[3] == "weapon" else "armor"
    cur.execute(f"UPDATE assassins SET {field}=? WHERE assassin_id=?", (f"{item[2]}+{item[4]}", ass[0]))
    conn.commit()
    await m.reply(f"{item[2]} jihozlandi: {ass[2]}", reply_markup=main_menu)

@dp.message_handler(lambda m: m.text and "Guild" in m.text)
async def handle_guild(m: types.Message):
    ensure_user(m.from_user.id, m.from_user.username)
    u = get_user(m.from_user.id)
    text = (f"🏛 Guild ma'lumotlari\nDaraja: {u[4]}\nXP: {u[3]}/{guild_xp_needed(u[4])}\nOltin: {u[2]}")
    await m.reply(text, reply_markup=main_menu)

@dp.message_handler(lambda m: m.text and "Yollash" in m.text)
async def alias_hire(m: types.Message):
    # alias so that both "🗡 Yollash" and typed "Yollash" work
    await handle_hire(m)

@dp.message_handler(lambda m: m.text and "Missiyalar" in m.text)
async def alias_missions(m: types.Message):
    await handle_missions(m)

@dp.message_handler(lambda m: m.text and "Assassinlar" in m.text)
async def alias_assassins(m: types.Message):
    await handle_assassins(m)

@dp.message_handler(lambda m: m.text and "Profil" in m.text)
async def alias_profile(m: types.Message):
    await handle_profile(m)

@dp.message_handler(lambda m: m.text and "Inventar" in m.text)
async def alias_inventory(m: types.Message):
    await handle_inventory(m)

@dp.message_handler(lambda m: m.text and "⚔️ PVP" in m.text or (m.text and "PVP" in m.text))
async def handle_pvp(m: types.Message):
    ensure_user(m.from_user.id, m.from_user.username)
    # need at least 2 users with assassins
    cur.execute("SELECT user_id FROM users WHERE user_id!=?", (m.from_user.id,))
    opponents = [row[0] for row in cur.fetchall()]
    if not opponents:
        await m.reply("Hozircha raqib yo'q.", reply_markup=main_menu)
        return
    # pick opponent who has ready assassin
    random.shuffle(opponents)
    opponent_id = None
    opp_ass_row = None
    for op in opponents:
        rows = list_assassins(op)
        ready = [r for r in rows if r[7] == "ready"]
        if ready:
            opponent_id = op
            opp_ass_row = random.choice(ready)
            break
    if not opponent_id:
        await m.reply("Hozircha raqib topilmadi (tayyor assassin yo'q).", reply_markup=main_menu)
        return
    # pick my assassin
    my_rows = list_assassins(m.from_user.id)
    my_ready = [r for r in my_rows if r[7] == "ready"]
    if not my_ready:
        await m.reply("Sizda tayyor assassin yo'q.", reply_markup=main_menu)
        return
    my_ass = random.choice(my_ready)
    # run battle
    winner_row, loser_row, gold_win, detail = pvp_battle_rows(my_ass, opp_ass_row)
    # determine winner owner
    winner_owner = m.from_user.id if winner_row[1] == m.from_user.id else opponent_id
    loser_owner = m.from_user.id if loser_row[1] == m.from_user.id else opponent_id
    # credit gold to winner owner
    winner_user = get_user(winner_owner)
    update_user_gold(winner_owner, winner_user[2] + gold_win)
    # prepare message showing both players and assassins
    my_user = get_user(m.from_user.id)
    opp_user = get_user(opponent_id)
    result_msg = ("⚔️ PVP Natija\n\n"
                  f"🧑‍  {my_user[1]}  vs  {opp_user[1]}\n\n"
                  f"G'olib: *{winner_row[2]}* (Power: {detail['my_power'] if winner_row==my_ass else detail['opp_power']})\n"
                  f"Mag'lub: *{loser_row[2]}* (Power: {detail['opp_power'] if loser_row==opp_ass_row else detail['my_power']})\n")
    # show critical info
    crit_lines = []
    if detail.get("my_crit"):
        crit_lines.append(f"{my_ass[2]} qattiq zarba (kritikal) berdi.")
    if detail.get("opp_crit"):
        crit_lines.append(f"{opp_ass_row[2]} kritikal zarba berdi.")
    if crit_lines:
        result_msg += "\n" + "\n".join(crit_lines)
    result_msg += f"\n\n🏅 G'olibga +{gold_win} oltin"
    await m.reply(result_msg, parse_mode="HTML", reply_markup=main_menu)

@dp.message_handler(commands=["save"])
async def cmd_save(m: types.Message):
    # SQLite commits automatically; provide a small confirmation
    conn.commit()
    await m.reply("Ma'lumotlar saqlandi ✅", reply_markup=main_menu)

@dp.message_handler()
async def fallback(m: types.Message):
    await m.reply("Buyruqni tushunmadim. Tugmalardan foydalaning.", reply_markup=main_menu)

# ====== Start bot ======
if __name__ == "__main__":
    executor.start_polling(dp, skip_updates=True)
