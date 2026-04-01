import logging
import asyncio
import os
import json
import time
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# --- КОНФИГУРАЦИЯ ---
API_TOKEN = '8286778160:AAHftyjLgM4cgjXovY2LMCwPbpfeHW0-vig'
ADMIN_IDS = [8141992001, 1825486156, 5639348899]
SUPPORT_URL = "tg://resolve?domain=sellerblume"

# Настройки по умолчанию
settings = {
    "uah_rate": 45.0, "rub_rate": 105.0,
    "uah_margin": 10.0, "rub_margin": 15.0,
    "uah_card": "0000 0000 0000 0000", "uah_bank": "Monobank", "uah_name": "Ivan I.", "uah_comm": "На річницю",
    "rub_phone": "+79000000000", "rub_bank": "Sberbank (SBP)", "rub_name": "Ivan I.", "rub_comm": "На годовщину"
}

last_order_time = {}
bot = Bot(token=API_TOKEN)
dp = Dispatcher()

# --- СТАТИСТИКА ---
def get_stats():
    if not os.path.exists("stats.json"):
        with open("stats.json", "w") as f:
            json.dump({"UAH_TON": 0.0, "RUB_TON": 0.0, "total_orders": 0}, f)
    try:
        with open("stats.json", "r") as f: return json.load(f)
    except: return {"UAH_TON": 0.0, "RUB_TON": 0.0, "total_orders": 0}

def update_stats(currency, amount):
    stats = get_stats()
    key = f"{currency}_TON"
    stats[key] = stats.get(key, 0.0) + float(amount)
    stats["total_orders"] += 1
    with open("stats.json", "w") as f: json.dump(stats, f)

# --- СОСТОЯНИЯ ---
class Order(StatesGroup):
    entering_amount = State()
    entering_wallet = State()
    waiting_confirm = State()
    waiting_for_pdf = State()

class AdminStates(StatesGroup):
    waiting_for_reqs = State()
    waiting_for_broadcast = State()

# --- ЛОГИРОВАНИЕ ЮЗЕРОВ ---
def log_user(user_id):
    if not os.path.exists("users.txt"):
        with open("users.txt", "a") as f: f.write(str(user_id) + "\n")
    else:
        with open("users.txt", "r+") as f:
            users = f.read().splitlines()
            if str(user_id) not in users: f.write(str(user_id) + "\n")

# --- КЛИЕНТСКАЯ ЧАСТЬ ---

@dp.message(Command("start"))
@dp.callback_query(F.data == "start")
async def cmd_start(event: types.Message | types.CallbackQuery, state: FSMContext):
    await state.clear()
    user_id = event.from_user.id if isinstance(event, types.Message) else event.message.chat.id
    log_user(user_id)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🇺🇦 Купить за UAH", callback_data="buy_UAH")],
        [InlineKeyboardButton(text="🇷🇺 Купить за RUB", callback_data="buy_RUB")],
        [InlineKeyboardButton(text="👨‍💻 Поддержка", url=SUPPORT_URL)]
    ])
    text = "👋 Добро пожаловать в **Seller TON**!\n\nВыберите валюту оплаты ниже: 👇"
    if isinstance(event, types.Message): 
        await event.answer(text, reply_markup=kb, parse_mode="Markdown")
    else: 
        await event.message.edit_text(text, reply_markup=kb, parse_mode="Markdown")

@dp.callback_query(F.data.startswith("buy_"))
async def process_buy(callback: types.CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    curr = callback.data.split("_")[1] # Исправлено: берем UAH или RUB
    
    # Антиспам 60 сек
    curr_t = time.time()
    if user_id in last_order_time and curr_t - last_order_time[user_id] < 60:
        return await callback.answer(f"⏳ Подождите минуту перед новой заявкой", show_alert=True)
    
    rate_key = 'uah_rate' if curr == "UAH" else 'rub_rate'
    margin = settings['uah_margin'] if curr == "UAH" else settings['rub_margin']
    final_rate = settings[rate_key] + margin
    
    await state.update_data(currency=curr, final_rate=final_rate)
    last_order_time[user_id] = curr_t
    
    await callback.message.edit_text(
        f"💎 Покупка TON за {curr}\n📊 Курс: {final_rate} {curr}/TON\n\nВведите кол-во TON:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅️ Назад", callback_data="start")]])
    )
    await state.set_state(Order.entering_amount)

@dp.message(Order.entering_amount)
async def amount_step(message: types.Message, state: FSMContext):
    try:
        amount = float(message.text.replace(',', '.'))
        data = await state.get_data()
        total = round(amount * data['final_rate'], 2)
        await state.update_data(amount=amount, total_cost=total)
        await message.answer(f"💰 К оплате: {total} {data['currency']}\nВведите ваш TON кошелек:", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅️ Назад", callback_data="start")]]))
        await state.set_state(Order.entering_wallet)
    except: await message.answer("⚠️ Введите число.")

@dp.message(Order.entering_wallet)
async def wallet_step(message: types.Message, state: FSMContext):
    await state.update_data(wallet=message.text)
    data = await state.get_data()
    
    if data['currency'] == "UAH":
        reqs = f"💳 Карта: `{settings['uah_card']}`\n🏦 Банк: {settings['uah_bank']}\n👤 Получатель: {settings['uah_name']}"
        comment = settings['uah_comm']
    else:
        reqs = f"📱 Номер (СБП): `{settings['rub_phone']}`\n🏦 Банк: {settings['rub_bank']}\n👤 Получатель: {settings['rub_name']}"
        comment = settings['rub_comm']
    
    text = (
        f"🚀 **ЗАЯВКА СФОРМИРОВАНА**\n\n"
        f"Сумма: `{data['total_cost']} {data['currency']}`\n\n{reqs}\n\n"
        f"💬 **КОММЕНТАРИЙ:** `{comment}`\n\n"
        f"⚠️ **БЕЗ КОММЕНТАРИЯ TON НЕ ПРИДУТ!**\n\n"
        f"Нажмите кнопку после оплаты: 👇"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Я ОПЛАТИЛ", callback_data="i_paid")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="start")]
    ])
    await message.answer(text, reply_markup=kb, parse_mode="Markdown")
    await state.set_state(Order.waiting_confirm)

@dp.callback_query(F.data == "i_paid", Order.waiting_confirm)
async def confirm_payment_btn(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text("📥 Отправьте чек (фото/PDF) боту.\n⏱ Время выплаты: от 1 мин до 1 часа.")
    await state.set_state(Order.waiting_for_pdf)

@dp.message(Order.waiting_for_pdf, F.document | F.photo)
async def payment_received(message: types.Message, state: FSMContext):
    data = await state.get_data()
    log = (f"🎁 **ЗАКАЗ**\nКлиент: @{message.from_user.username or 'NoUser'}\n"
           f"Сумма: `{data['amount']} TON` ({data['total_cost']} {data['currency']})\n"
           f"Кошелек: `{data['wallet']}`")
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ ВЫПОЛНЕНО", callback_data=f"done_{message.from_user.id}_{data['currency']}_{data['amount']}")]])
    
    for admin_id in ADMIN_IDS:
        try:
            if message.document: await bot.send_document(admin_id, message.document.file_id, caption=log, reply_markup=kb, parse_mode="Markdown")
            else: await bot.send_photo(admin_id, message.photo[-1].file_id, caption=log, reply_markup=kb, parse_mode="Markdown")
        except: pass
    
    await message.answer("📡 Чек принят! Ожидайте уведомления.\n⏱ Время выплаты: от 1 минуты до 1 часа.")
    await state.clear()

# --- АДМИН ПАНЕЛЬ ---

@dp.message(Command("admin_panel"), F.from_user.id.in_(ADMIN_IDS))
async def admin_panel(message: types.Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📈 Курсы", callback_data="adm_rates"), InlineKeyboardButton(text="💳 Реквизиты", callback_data="adm_reqs")],
        [InlineKeyboardButton(text="💬 Комменты", callback_data="adm_comm"), InlineKeyboardButton(text="📊 Статистика", callback_data="adm_stats")],
        [InlineKeyboardButton(text="📢 Рассылка", callback_data="adm_push")]
    ])
    await message.answer("🛠 **МЕНЮ АДМИНИСТРАТОРА**", reply_markup=kb, parse_mode="Markdown")

@dp.callback_query(F.data == "adm_stats", F.from_user.id.in_(ADMIN_IDS))
async def adm_stats(callback: types.CallbackQuery):
    s = get_stats()
    text = (f"📊 **СТАТИСТИКА ПРОДАЖ**\n\n🇺🇦 UAH: `{round(s['UAH_TON'], 2)} TON`\n🇷🇺 RUB: `{round(s['RUB_TON'], 2)} TON`"
            f"\n\n✅ Успешных сделок: `{s['total_orders']}`")
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Назад", callback_data="admin_back")]]), parse_mode="Markdown")

@dp.callback_query(F.data.startswith("done_"), F.from_user.id.in_(ADMIN_IDS))
async def complete_order(callback: types.CallbackQuery):
    params = callback.data.split("_")
    uid, curr, amt = params[1], params[2], params[3]
    update_stats(curr, amt)
    try:
        await bot.send_message(int(uid), f"💎 **ЗАКАЗ ВЫПОЛНЕН!**\nTON отправлены.\n\n⏱ Время обработки составило менее часа.\nПоддержка: {SUPPORT_URL}", parse_mode="Markdown")
        await callback.message.edit_caption(caption=(callback.message.caption or "") + "\n\n✅ **ВЫПОЛНЕНО (СТАТИСТИКА+)**", parse_mode="Markdown")
    except: await callback.answer("Ошибка связи.")

@dp.callback_query(F.data == "admin_back", F.from_user.id.in_(ADMIN_IDS))
async def adm_back(callback: types.CallbackQuery): await admin_panel(callback.message)

@dp.callback_query(F.data == "adm_rates", F.from_user.id.in_(ADMIN_IDS))
async def adm_rates(callback: types.CallbackQuery):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="UAH база", callback_data="set_uah_rate"), InlineKeyboardButton(text="RUB база", callback_data="set_rub_rate")],
        [InlineKeyboardButton(text="Назад", callback_data="admin_back")]
    ])
    await callback.message.edit_text(f"Курсы:\nUAH: {settings['uah_rate']}\nRUB: {settings['rub_rate']}", reply_markup=kb)

@dp.callback_query(F.data == "adm_reqs", F.from_user.id.in_(ADMIN_IDS))
async def adm_reqs(callback: types.CallbackQuery):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="UA: Карта", callback_data="set_uah_card"), InlineKeyboardButton(text="UA: Имя", callback_data="set_uah_name")],
        [InlineKeyboardButton(text="RU: Тел", callback_data="set_rub_phone"), InlineKeyboardButton(text="RU: Имя", callback_data="set_rub_name")],
        [InlineKeyboardButton(text="RU: Банк", callback_data="set_rub_bank"), InlineKeyboardButton(text="Назад", callback_data="admin_back")]
    ])
    await callback.message.edit_text("Реквизиты:", reply_markup=kb)

@dp.callback_query(F.data == "adm_comm", F.from_user.id.in_(ADMIN_IDS))
async def adm_comm(callback: types.CallbackQuery):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Коммент UA", callback_data="set_uah_comm"), InlineKeyboardButton(text="Коммент RU", callback_data="set_rub_comm")],
        [InlineKeyboardButton(text="Назад", callback_data="admin_back")]
    ])
    await callback.message.edit_text(f"UA: {settings['uah_comm']}\nRU: {settings['rub_comm']}", reply_markup=kb)

@dp.callback_query(F.data.startswith("set_"), F.from_user.id.in_(ADMIN_IDS))
async def set_value(callback: types.CallbackQuery, state: FSMContext):
    key = callback.data.replace("set_", "")
    await state.update_data(changing=key)
    await callback.message.answer(f"Введите новое значение для {key}:")
    await state.set_state(AdminStates.waiting_for_reqs)

@dp.message(AdminStates.waiting_for_reqs, F.from_user.id.in_(ADMIN_IDS))
async def save_value(message: types.Message, state: FSMContext):
    data = await state.get_data(); key = data['changing']
    if "rate" in key:
        try: settings[key] = float(message.text.replace(',','.'))
        except: return await message.answer("Введите число.")
    else: settings[key] = message.text
    await message.answer("✅ Успешно обновлено!"); await state.clear()

@dp.callback_query(F.data == "adm_push", F.from_user.id.in_(ADMIN_IDS))
async def push_start(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("Введите текст рассылки:"); await state.set_state(AdminStates.waiting_for_broadcast)

@dp.message(AdminStates.waiting_for_broadcast, F.from_user.id.in_(ADMIN_IDS))
async def push_finish(message: types.Message, state: FSMContext):
    if not os.path.exists("users.txt"): return await message.answer("Нет пользователей.")
    with open("users.txt", "r") as f: users = f.read().splitlines()
    count = 0
    for u_id in users:
        try:
            await bot.send_message(u_id, f"🔔 **УВЕДОМЛЕНИЕ**\n\n{message.text}", parse_mode="Markdown")
            count += 1
            await asyncio.sleep(0.05)
        except: pass
    await message.answer(f"✅ Готово! Отправлено: {count}"); await state.clear()

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(dp.start_polling(bot))
