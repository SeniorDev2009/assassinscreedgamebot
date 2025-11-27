# main.py
import json
import random
import os
import time
from threading import Lock
from aiogram import Bot, Dispatcher, executor, types
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton

# ========== SOZLAMALAR ==========
TOKEN = "8535791222:AAFnHkaeYmoDS32QYOafpZlDO_wl3nd6K1U"  # <-- bu yerga token qo'ying

DATA_FILE = "data.json"    # foydalanuvchi ma'lumotlari bu faylda saqlanadi
AUTOSAVE_INTERVAL = 30     # soniyada avtomatik saqlash (oddiy)
# =================================

bot = Bot(token=TOKEN)
dp = Dispatcher(bot)

data_lock = Lock()

# Foydalanuvchi ma'lumotlari (yuklanadi)
if os.path.exists(DATA_FILE):
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            users = json.load(f)
    except Exception:
        users = {}
else:
    users = {}

# ====== Yordamchi funksiyalar ======
def save_data():
    """Thread-safe save to JSON."""
    with data_lock:
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(users, f, ensure_ascii=False, indent=2)

def ensure_user(user_id, username=None):
    """Agar user mavjud bo'lmasa, yaratadi."""
    uid = str(user_id)
    if uid not in users:
        users[uid] = {
            "username": username or "",
            "gold": 50,
            "guild_xp": 0,
            "guild_level": 1,
            "assassins": [],  # list of dicts
            "inventory": [],  # list of items
            "last_saved": int(time.time())
        }
        save_data()

def generate_assassin_name():
    names = ["Ara", "Boran", "Cyrus", "Dara", "Eron", "Fael", "Galen", "Horo", "Ira", "Jax"]
    return random.choice(names) + str(random.randint(1, 99))

def create_assassin(seed=None):
    """Yangi assassin yaratadi — statistikalar va boshlang'ich asboblar."""
    if seed is None:
        seed = random.randint(0, 1000000)
    random.seed(seed)
    name = generate_assassin_name()
    base_power = random.randint(3, 8)
    assassin = {
        "id": str(int(time.time() * 1000)) + str(random.randint(0, 999)),
        "name": name,
        "power": base_power,        # asosiy kuch (qurol va level bilan oshadi)
        "level": 1,
        "hp": 100,
        "max_hp": 100,
        "equipment": {              # jihozlar (weapon modifies power)
            "weapon": None,
            "armor": None
        },
        "status": "ready"          # ready / on_mission / dead
    }
    return assassin

def calc_assassin_effective_power(assassin):
    """Assassinning real kuchini hisoblaydi — jihozlarga qarab."""
    p = assassin["power"] + assassin["level"]
    weap = assassin["equipment"].get("weapon")
    armor = assassin["equipment"].get("armor")
    if weap:
        p += weap.get("power_mod", 0)
    if armor:
        p += armor.get("power_mod", 0)
    return p

def guild_xp_needed(lvl):
    return 100 + (lvl - 1) * 75

def try_mission_result(ass_power, mission_difficulty):
    """
    mission_difficulty: 'easy'/'medium'/'hard'
    Returns tuple (success:bool, gold_reward:int, xp_gain:int, death_chance:float)
    """
    # difficulty multipliers
    diff = {
        "easy": {"base": 60, "gold": (8, 20), "xp": (8, 15), "death": 0.01},
        "medium": {"base": 40, "gold": (20, 45), "xp": (15, 30), "death": 0.05},
        "hard": {"base": 20, "gold": (40, 90), "xp": (30, 70), "death": 0.15}
    }[mission_difficulty]

    # success chance grows with ass_power
    chance = diff["base"] + (ass_power * 5)  # each power punkt adds 5%
    # limit chance
    chance = max(5, min(chance, 95))

    roll = random.randint(1, 100)
    success = roll <= chance

    gold = random.randint(diff["gold"][0], diff["gold"][1])
    xp = random.randint(diff["xp"][0], diff["xp"][1])
    death_base = diff["death"]

    # death chance higher if fail and difficulty high
    if success:
        death = death_base / 5  # very small chance on success
    else:
        death = min(0.9, death_base * 4)  # failing increases death chance

    return success, gold, xp, death

def find_assassin(user, assassin_id):
    for a in user["assassins"]:
        if a["id"] == assassin_id:
            return a
    return None

# ====== UI KEYBOARDS ======
main_menu = ReplyKeyboardMarkup(resize_keyboard=True)
main_menu.row(KeyboardButton("👤 Profil"), KeyboardButton("👥 Assassinlar"))
main_menu.row(KeyboardButton("🗡 Yollash"), KeyboardButton("🎯 Missiyalar"))
main_menu.row(KeyboardButton("🎒 Inventar"), KeyboardButton("🏛 Guild"))

# Inline keyboards for missions & inventory
def missions_inline_kb():
    kb = InlineKeyboardMarkup()
    kb.row(
        InlineKeyboardButton("🔹 Oson", callback_data="mission_easy"),
        InlineKeyboardButton("🔸 O'rta", callback_data="mission_medium"),
        InlineKeyboardButton("🔺 Qiyin", callback_data="mission_hard")
    )
    return kb

def assassin_action_kb(assassin_id):
    kb = InlineKeyboardMarkup()
    kb.row(InlineKeyboardButton("🔁 Yuiborish missiyaga", callback_data=f"send_{assassin_id}"))
    kb.row(InlineKeyboardButton("⚙️ Jihozlash", callback_data=f"equip_{assassin_id}"),
           InlineKeyboardButton("❌ O'chirish", callback_data=f"del_{assassin_id}"))
    return kb

def equip_choice_kb(user_id, assassin_id):
    uid = str(user_id)
    user = users[uid]
    kb = InlineKeyboardMarkup()
    # list inventory weapons and armors
    weapons = [ (idx, it) for idx, it in enumerate(user["inventory"]) if it["type"] == "weapon" ]
    armors = [ (idx, it) for idx, it in enumerate(user["inventory"]) if it["type"] == "armor" ]
    if not weapons and not armors:
        kb.add(InlineKeyboardButton("Inventar bo'sh", callback_data="no_inv"))
        return kb
    for idx, w in weapons:
        kb.add(InlineKeyboardButton(f"🔪 {w['name']} (P+{w.get('power_mod',0)})", callback_data=f"equip_w_{assassin_id}_{idx}"))
    for idx, a in armors:
        kb.add(InlineKeyboardButton(f"🛡 {a['name']} (P+{a.get('power_mod',0)})", callback_data=f"equip_a_{assassin_id}_{idx}"))
    kb.row(InlineKeyboardButton("⬅️ Orqaga", callback_data="equip_back"))
    return kb

def inventory_kb(user_id):
    uid = str(user_id)
    user = users[uid]
    kb = InlineKeyboardMarkup()
    if not user["inventory"]:
        kb.add(InlineKeyboardButton("Inventar bo'sh", callback_data="inv_empty"))
        return kb
    for idx, it in enumerate(user["inventory"]):
        kb.add(InlineKeyboardButton(f"{it['name']} ({it['type']})", callback_data=f"inv_use_{idx}"))
    kb.row(InlineKeyboardButton("⬅️ Orqaga", callback_data="inv_back"))
    return kb

# ====== BOT HANDLERS ======

@dp.message_handler(commands=["start", "help"])
async def cmd_start(message: types.Message):
    ensure_user(message.from_user.id, message.from_user.username)
    uid = str(message.from_user.id)
    user = users[uid]
    text = ("🕵️‍♂️ *Assassin's Guild* o'yin botiga xush kelibsiz!\n\n"
            "Siz guild boshlig'isiz — assassin yollang, ularni jihozlang, missiyalarga yuboring va guildni kuchaytiring.\n\n"
            "Asosiy buyruqlar: /start, /profile, /assassins, /hire, /missions, /inventory, /save")
    await message.reply(text, parse_mode="Markdown", reply_markup=main_menu)

@dp.message_handler(commands=["profile"])
async def cmd_profile(message: types.Message):
    ensure_user(message.from_user.id, message.from_user.username)
    uid = str(message.from_user.id)
    u = users[uid]
    profile_text = (f"👤 *Sizning Profil*: {u.get('username')}\n\n"
                    f"💰 Oltin: {u.get('gold')}\n"
                    f"🏛 Guild darajasi: {u.get('guild_level')} (XP: {u.get('guild_xp')}/{guild_xp_needed(u.get('guild_level'))})\n"
                    f"🗡 Assassinlar: {len(u.get('assassins'))}\n"
                    f"🎒 Inventar: {len(u.get('inventory'))} ta predmet")
    await message.answer(profile_text, parse_mode="Markdown", reply_markup=main_menu)

@dp.message_handler(lambda msg: msg.text == "👤 Profil")
async def profile_btn(msg: types.Message):
    await cmd_profile(msg)

@dp.message_handler(lambda msg: msg.text == "👥 Assassinlar")
async def cmd_assassins(msg: types.Message):
    ensure_user(msg.from_user.id, msg.from_user.username)
    uid = str(msg.from_user.id)
    u = users[uid]
    if not u["assassins"]:
        await msg.answer("Sizda hozircha assassinlar yo'q. 🗡 Yangi assassin yollash uchun '🗡 Yollash' tugmasini bosing.", reply_markup=main_menu)
        return
    text = "👥 *Sizning Assassinlaringiz:*\n\n"
    for a in u["assassins"]:
        text += (f"• {a['name']} (ID: {a['id'][:8]})\n"
                 f"  🔸 Level: {a['level']}  🔸 Power: {a['power']}  🔸 Status: {a['status']}\n"
                 f"  🔸 Equip: W:{a['equipment'].get('weapon')['name'] if a['equipment'].get('weapon') else 'Hech'} | A:{a['equipment'].get('armor')['name'] if a['equipment'].get('armor') else 'Hech'}\n\n")
    await msg.answer(text, parse_mode="Markdown", reply_markup=main_menu)

@dp.message_handler(lambda msg: msg.text == "🗡 Yollash" or msg.text == "/hire")
async def cmd_hire(msg: types.Message):
    ensure_user(msg.from_user.id, msg.from_user.username)
    uid = str(msg.from_user.id)
    user = users[uid]

    # yollash narxi guild level bilan oshadi
    price = 20 + user["guild_level"] * 10
    if user["gold"] < price:
        await msg.reply(f"Yollash uchun oltin yetarli emas. Narx: {price} oltin. Sizda: {user['gold']}")
        return

    # coinni yechamiz va assassin yaratiladi
    user["gold"] -= price
    new_a = create_assassin()
    user["assassins"].append(new_a)
    # yollashdan keyingi xp
    user["guild_xp"] += 10

    save_data()
    await msg.answer(f"🗡 Yangi assassin yollandi: *{new_a['name']}* (Power: {new_a['power']}, Level: {new_a['level']}).\n"
                     f"Yollash narxi: {price} oltin.\nGuild XP +10.",
                     parse_mode="Markdown", reply_markup=main_menu)

@dp.message_handler(lambda msg: msg.text == "🎯 Missiyalar")
async def cmd_missions(msg: types.Message):
    ensure_user(msg.from_user.id, msg.from_user.username)
    # Ko'rsatish: missiya tiplarini inline tugmalar bilan
    await msg.answer("🎯 Missiya tanlang — qaysi qiyinchilik?:", reply_markup=missions_inline_kb())

@dp.callback_query_handler(lambda c: c.data and c.data.startswith("mission_"))
async def process_mission_callback(callback_query: types.CallbackQuery):
    ensure_user(callback_query.from_user.id, callback_query.from_user.username)
    uid = str(callback_query.from_user.id)
    user = users[uid]
    difficulty = callback_query.data.split("_")[1]  # easy/medium/hard

    # tanlangan assassin (tasodifiy 'ready' holatidagi)
    ready_assassins = [a for a in user["assassins"] if a["status"] == "ready"]
    if not ready_assassins:
        await bot.answer_callback_query(callback_query.id, "Sizda missiyaga yuboriladigan tayyor assassin yo'q.")
        return

    assassin = random.choice(ready_assassins)
    assassin["status"] = "on_mission"
    save_data()

    # hisoblash
    eff_power = calc_assassin_effective_power(assassin)
    success, gold, xp, death_chance = try_mission_result(eff_power, difficulty)

    # mission natija — bu soddalashtirilgan; real o'yinda missiya vaqt oladi. Bu yerda darhol natija qaytadi.
    # natija
    if success:
        user["gold"] += gold
        user["guild_xp"] += xp
        assassin["level"] += 1
        assassin["status"] = "ready"
        # ozgina yangi qurol imkoniyati: kamdan-kam holda item topish
        found_item = None
        if random.random() < 0.12:
            # topilgan predmet
            itype = random.choice(["weapon", "armor"])
            item = {
                "name": f"{'Klassik' if itype=='weapon' else 'Qalin'} {random.choice(['qilich','bolta','kama','zirh','koylak'])}",
                "type": itype,
                "power_mod": random.randint(1, 6),
                "rarity": random.choice(["common", "uncommon", "rare"])
            }
            user["inventory"].append(item)
            found_item = item

        save_data()
        msg = (f"✅ Missiya muvaffaqiyatli!\n"
               f"Assassin: *{assassin['name']}* (Yangi level: {assassin['level']})\n"
               f"💰 Olingan oltin: {gold}\n"
               f"🏛 Guild XP: +{xp}")
        if found_item:
            msg += f"\n🎁 Topilgan predmet: {found_item['name']} (+{found_item['power_mod']})"
        await bot.send_message(callback_query.from_user.id, msg, parse_mode="Markdown")
    else:
        # muvaffaqiyatsiz — mumkin o'lim
        died = random.random() < death_chance
        assassin["status"] = "ready" if not died else "dead"
        if died:
            save_data()
            await bot.send_message(callback_query.from_user.id,
                                   f"❌ Missiya muvaffaqiyatsiz va afsuski *{assassin['name']}* o'ldirildi.", parse_mode="Markdown")
        else:
            # may be lose some gold as penalty
            lost = min(user["gold"], random.randint(2, 15))
            user["gold"] -= lost
            save_data()
            await bot.send_message(callback_query.from_user.id,
                                   f"❌ Missiya muvaffaqiyatsiz. Assassin qaytdi, lekin siz {lost} oltin yo'qotdingiz.", parse_mode="Markdown")

    # daraja tekshirish
    while user["guild_xp"] >= guild_xp_needed(user["guild_level"]):
        user["guild_xp"] -= guild_xp_needed(user["guild_level"])
        user["guild_level"] += 1
        save_data()
        await bot.send_message(callback_query.from_user.id,
                               f"🏛 *Tabriklaymiz!* Guild darajangiz oshdi: {user['guild_level']}", parse_mode="Markdown")

    await bot.answer_callback_query(callback_query.id, "")

@dp.message_handler(lambda msg: msg.text == "🎒 Inventar")
async def cmd_inventory(msg: types.Message):
    ensure_user(msg.from_user.id, msg.from_user.username)
    uid = str(msg.from_user.id)
    user = users[uid]
    if not user["inventory"]:
        await msg.answer("🎒 Inventaringiz hozircha bo'sh.", reply_markup=main_menu)
        return
    text = "🎒 *Inventar:*\n\n"
    for idx, it in enumerate(user["inventory"], 0):
        text += f"{idx+1}. {it['name']} ({it['type']}) — P+{it.get('power_mod',0)} | {it.get('rarity','common')}\n"
    text += "\nItemni jihozlash uchun /equip <index> (masalan: /equip 1)"
    await msg.answer(text, parse_mode="Markdown", reply_markup=main_menu)

@dp.message_handler(commands=["equip"])
async def cmd_equip(message: types.Message):
    ensure_user(message.from_user.id, message.from_user.username)
    uid = str(message.from_user.id)
    user = users[uid]
    args = message.get_args()
    if not args:
        await message.answer("Foydalanish: /equip <index> — inventardagi itemni jihozlash.")
        return
    try:
        idx = int(args.strip()) - 1
    except:
        await message.answer("Index raqam bo'lishi kerak.")
        return
    if idx < 0 or idx >= len(user["inventory"]):
        await message.answer("Noto'g'ri index.")
        return
    item = user["inventory"][idx]
    # jihozlash — itemni guild bossiga emas, assassinlarga berishimiz mumkin; shu yerda oddiy: birinchi assassin tanlab equip qiladi
    if not user["assassins"]:
        await message.answer("Sizda assassin yo'q, avval yollang.")
        return
    # birinchi tayyor assassin topamiz
    ass = user["assassins"][0]
    if item["type"] == "weapon":
        ass["equipment"]["weapon"] = item
    elif item["type"] == "armor":
        ass["equipment"]["armor"] = item
    else:
        await message.answer("Bu item jihozlash uchun mos emas.")
        return
    save_data()
    await message.answer(f"{item['name']} jihozlandi *{ass['name']}* ga.", parse_mode="Markdown")

@dp.message_handler(lambda msg: msg.text == "🏛 Guild")
async def cmd_guild(msg: types.Message):
    ensure_user(msg.from_user.id, msg.from_user.username)
    uid = str(msg.from_user.id)
    u = users[uid]
    text = (f"🏛 *Guild Ma'lumotlari*\n\n"
            f"Daraja: {u['guild_level']}\n"
            f"XP: {u['guild_xp']}/{guild_xp_needed(u['guild_level'])}\n"
            f"Oltin: {u['gold']}\n\n"
            f"Guild bilan nima qilsa bo'ladi:\n"
            f"- Yangi assassin yollash (🗡 Yollash)\n"
            f"- Inventar boshqarish (🎒 Inventar)\n"
            f"- Missiyalar (🎯 Missiyalar)")
    await msg.answer(text, parse_mode="Markdown", reply_markup=main_menu)

@dp.message_handler(commands=["save"])
async def cmd_save(msg: types.Message):
    ensure_user(msg.from_user.id, msg.from_user.username)
    uid = str(msg.from_user.id)
    users[uid]["last_saved"] = int(time.time())
    save_data()
    await msg.answer("Ma'lumotlar saqlandi ✅")

@dp.message_handler(commands=["load"])
async def cmd_load(msg: types.Message):
    global users
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            users = json.load(f)
        await msg.answer("Ma'lumotlar yuklandi ✅")
    else:
        await msg.answer("Saqlangan ma'lumot topilmadi.")

@dp.message_handler(commands=["reset"])
async def cmd_reset(msg: types.Message):
    uid = str(msg.from_user.id)
    users.pop(uid, None)
    save_data()
    await msg.answer("Sizning profildagi barcha ma'lumot o'chirildi. /start bilan qaytadan boshlang.")

# Oddiy text handlers for menu buttons
@dp.message_handler(lambda msg: msg.text == "🗡 Yollash")
async def hire_btn(msg: types.Message):
    await cmd_hire(msg)

@dp.message_handler(lambda msg: msg.text == "🎯 Missiyalar")
async def missions_btn(msg: types.Message):
    await cmd_missions(msg)

# Fallback: tekstli buyruqlar (agar user id bilan assassinni boshqarish istasa)
@dp.message_handler()
async def fallback(message: types.Message):
    text = ("Men tushunmadim. Quyidagi tugmalardan foydalaning yoki /help ga yozing.\n\n"
            "Asosiy buyruqlar: /start /profile /assassins /hire /missions /inventory /save")
    await message.reply(text, reply_markup=main_menu)

# ====== BOTni ishga tushirish ======
if __name__ == "__main__":
    # dastlab malumotlarni saqlab qo'yamiz
    save_data()
    print("Bot ishga tushmoqda... Ctrl+C bilan to'xtating.")
    executor.start_polling(dp, skip_updates=True)
