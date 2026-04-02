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
API_TOKEN = '8732609892:AAEre0vM4ktZGTMejTuhcWIy6cGmGvjqn34'
ADMIN_IDS = [8141992001, 1825486156, 5639348899]
SUPPORT_URL = "tg://resolve?domain=sellerblume"

EMOJI_IDS = {
    "buy_uah": "5445118241758257251",
    "buy_rub": "5398017006165305287",
    "support": "5818967120213445821",

    "back": "5316660455744223443",
    "paid": "5316827280863934685",
    "done": "5316827280863934685",

    "adm_rates": "5244837092042750681",
    "adm_reqs": "5445353829304387411",
    "adm_comm": "5426839801544338121",
    "adm_min": "5258134813302332906",
    "adm_stats": "5231200819986047254",
    "adm_push": "5825586339126452204",

    "set_uah_rate": "",
    "set_rub_rate": "",
    "set_uah_card": "",
    "set_uah_name": "",
    "set_rub_phone": "",
    "set_rub_name": "",
    "set_rub_bank": "",
    "set_uah_comm": "",
    "set_rub_comm": "",
}

# Глобальные настройки
settings = {
    "uah_rate": 45.0, "rub_rate": 105.0,
    "uah_margin": 10.0, "rub_margin": 15.0,
    "min_buy": 1.5,  # Твоя минималка по умолчанию
    "uah_card": "0000 0000 0000 0000", "uah_bank": "Monobank", "uah_name": "Ivan I.", "uah_comm": "На річницю",
    "rub_phone": "+79000000000", "rub_bank": "Sberbank (SBP)", "rub_name": "Ivan I.", "rub_comm": "На годовщину"
}

last_order_time = {}
bot = Bot(token=API_TOKEN)
dp = Dispatcher()


def ikb_button(text, *, callback_data=None, url=None, emoji_key=None):
    kwargs = {"text": text}

    if callback_data is not None:
        kwargs["callback_data"] = callback_data
    if url is not None:
        kwargs["url"] = url

    emoji_id = EMOJI_IDS.get(emoji_key, "") if emoji_key else ""
    if emoji_id:
        kwargs["icon_custom_emoji_id"] = emoji_id

    return InlineKeyboardButton(**kwargs)


# --- СТАТИСТИКА ---
def get_stats():
    if not os.path.exists("stats.json"):
        with open("stats.json", "w", encoding="utf-8") as f:
            json.dump({"UAH_TON": 0.0, "RUB_TON": 0.0, "total_orders": 0}, f)
    try:
        with open("stats.json", "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"UAH_TON": 0.0, "RUB_TON": 0.0, "total_orders": 0}


def update_stats(currency, amount):
    stats = get_stats()
    key = f"{currency}_TON"
    stats[key] = stats.get(key, 0.0) + float(amount)
    stats["total_orders"] += 1
    with open("stats.json", "w", encoding="utf-8") as f:
        json.dump(stats, f)


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
        with open("users.txt", "a", encoding="utf-8") as f:
            f.write(str(user_id) + "\n")
    else:
        with open("users.txt", "r+", encoding="utf-8") as f:
            users = f.read().splitlines()
            if str(user_id) not in users:
                f.write(str(user_id) + "\n")


# --- КЛИЕНТСКАЯ ЧАСТЬ ---
@dp.message(Command("start"))
@dp.callback_query(F.data == "start")
async def cmd_start(event: types.Message | types.CallbackQuery, state: FSMContext):
    await state.clear()
    user_id = event.from_user.id if isinstance(event, types.Message) else event.message.chat.id
    log_user(user_id)

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [ikb_button("Купить за UAH", callback_data="buy_UAH", emoji_key="buy_uah")],
        [ikb_button("Купить за RUB", callback_data="buy_RUB", emoji_key="buy_rub")],
        [ikb_button("Поддержка", url=SUPPORT_URL, emoji_key="support")]
    ])

    text = "👋 Добро пожаловать в **Seller TON**!\n\nВыберите валюту оплаты ниже: 👇"
    if isinstance(event, types.Message):
        await event.answer(text, reply_markup=kb, parse_mode="Markdown")
    else:
        await event.message.edit_text(text, reply_markup=kb, parse_mode="Markdown")


@dp.callback_query(F.data.startswith("buy_"))
async def process_buy(callback: types.CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    curr = callback.data.split("_")[1]

    curr_t = time.time()
    if user_id in last_order_time and curr_t - last_order_time[user_id] < 60:
        return await callback.answer("⏳ Подождите минуту перед новой заявкой", show_alert=True)

    rate_key = "uah_rate" if curr == "UAH" else "rub_rate"
    margin = settings["uah_margin"] if curr == "UAH" else settings["rub_margin"]
    final_rate = settings[rate_key] + margin

    await state.update_data(currency=curr, final_rate=final_rate)
    last_order_time[user_id] = curr_t

    await callback.message.edit_text(
        f"💎 Покупка TON за {curr}\n📊 Курс: {final_rate} {curr}/TON\n\n"
        f"⚠️ Минимальная покупка: **{settings['min_buy']} TON**\n\n"
        f"Введите количество TON:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [ikb_button("Назад", callback_data="start", emoji_key="back")]
        ]),
        parse_mode="Markdown"
    )
    await state.set_state(Order.entering_amount)


@dp.message(Order.entering_amount)
async def amount_step(message: types.Message, state: FSMContext):
    try:
        amount = float(message.text.replace(",", "."))
        if amount < settings["min_buy"]:
            return await message.answer(
                f"❌ Минимальная сумма покупки — **{settings['min_buy']} TON**.\nВведите сумму побольше:",
                parse_mode="Markdown"
            )

        data = await state.get_data()
        total = round(amount * data["final_rate"], 2)
        await state.update_data(amount=amount, total_cost=total)

        await message.answer(
            f"💰 К оплате: {total} {data['currency']}\nВведите ваш TON кошелек:",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [ikb_button("Назад", callback_data="start", emoji_key="back")]
            ])
        )
        await state.set_state(Order.entering_wallet)
    except Exception:
        await message.answer("⚠️ Введите число.")


@dp.message(Order.entering_wallet)
async def wallet_step(message: types.Message, state: FSMContext):
    await state.update_data(wallet=message.text)
    data = await state.get_data()

    if data["currency"] == "UAH":
        reqs = f"💳 Карта: `{settings['uah_card']}`\n🏦 Банк: {settings['uah_bank']}\n👤 Получатель: {settings['uah_name']}"
        comment = settings["uah_comm"]
    else:
        reqs = f"📱 Номер (СБП): `{settings['rub_phone']}`\n🏦 Банк: {settings['rub_bank']}\n👤 Получатель: {settings['rub_name']}"
        comment = settings["rub_comm"]

    text = (
        f"🚀 **ЗАЯВКА СФОРМИРОВАНА**\n\n"
        f"Сумма: `{data['total_cost']} {data['currency']}`\n\n{reqs}\n\n"
        f"💬 **КОММЕНТАРИЙ:** `{comment}`\n\n"
        f"⚠️ **БЕЗ КОММЕНТАРИЯ TON НЕ ПРИДУТ!**\n\n"
        f"Нажмите кнопку после оплаты: 👇"
    )

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [ikb_button("Я ОПЛАТИЛ", callback_data="i_paid", emoji_key="paid")],
        [ikb_button("Назад", callback_data="start", emoji_key="back")]
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
    log = (
        f"🎁 **ЗАКАЗ**\nКлиент: @{message.from_user.username or 'NoUser'}\n"
        f"Сумма: `{data['amount']} TON` ({data['total_cost']} {data['currency']})\n"
        f"Кошелек: `{data['wallet']}`"
    )

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [ikb_button(
            "ВЫПОЛНЕНО",
            callback_data=f"done_{message.from_user.id}_{data['currency']}_{data['amount']}",
            emoji_key="done"
        )]
    ])

    for admin_id in ADMIN_IDS:
        try:
            if message.document:
                await bot.send_document(admin_id, message.document.file_id, caption=log, reply_markup=kb, parse_mode="Markdown")
            else:
                await bot.send_photo(admin_id, message.photo[-1].file_id, caption=log, reply_markup=kb, parse_mode="Markdown")
        except Exception:
            pass

    await message.answer("📡 Чек принят! Ожидайте уведомления.\n⏱ Время выплаты: от 1 минуты до 1 часа.")
    await state.clear()


# --- АДМИН ПАНЕЛЬ ---
@dp.message(Command("admin_panel"), F.from_user.id.in_(ADMIN_IDS))
async def admin_panel(message: types.Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            ikb_button("Курсы", callback_data="adm_rates", emoji_key="adm_rates"),
            ikb_button("Реквизиты", callback_data="adm_reqs", emoji_key="adm_reqs")
        ],
        [
            ikb_button("Комменты", callback_data="adm_comm", emoji_key="adm_comm"),
            ikb_button("Мин. покупка", callback_data="adm_min", emoji_key="adm_min")
        ],
        [
            ikb_button("Статистика", callback_data="adm_stats", emoji_key="adm_stats"),
            ikb_button("Рассылка", callback_data="adm_push", emoji_key="adm_push")
        ]
    ])
    await message.answer("🛠 **МЕНЮ АДМИНИСТРАТОРА**", reply_markup=kb, parse_mode="Markdown")


@dp.callback_query(F.data == "adm_min", F.from_user.id.in_(ADMIN_IDS))
async def adm_min(callback: types.CallbackQuery, state: FSMContext):
    await state.update_data(changing="min_buy")
    await callback.message.answer(
        f"Текущая минималка: **{settings['min_buy']} TON**\nВведите новое значение:",
        parse_mode="Markdown"
    )
    await state.set_state(AdminStates.waiting_for_reqs)


@dp.callback_query(F.data.startswith("done_"), F.from_user.id.in_(ADMIN_IDS))
async def complete_order(callback: types.CallbackQuery):
    params = callback.data.split("_")
    uid, curr, amt = params[1], params[2], params[3]
    update_stats(curr, amt)
    try:
        await bot.send_message(
            int(uid),
            f"💎 **ЗАКАЗ ВЫПОЛНЕН!**\nTON отправлены.\n\n⏱ Время обработки составило менее часа.\nПоддержка: {SUPPORT_URL}",
            parse_mode="Markdown"
        )
        await callback.message.edit_caption(
            caption=(callback.message.caption or "") + "\n\n✅ **ВЫПОЛНЕНО (СТАТИСТИКА+)**",
            parse_mode="Markdown"
        )
    except Exception:
        await callback.answer("Ошибка связи.")


@dp.callback_query(F.data == "admin_back", F.from_user.id.in_(ADMIN_IDS))
async def adm_back(callback: types.CallbackQuery):
    await admin_panel(callback.message)


@dp.callback_query(F.data == "adm_stats", F.from_user.id.in_(ADMIN_IDS))
async def adm_stats(callback: types.CallbackQuery):
    s = get_stats()
    text = (
        f"📊 **СТАТИСТИКА ПРОДАЖ**\n\n🇺🇦 UAH: `{round(s['UAH_TON'], 2)} TON`\n🇷🇺 RUB: `{round(s['RUB_TON'], 2)} TON`"
        f"\n\n✅ Успешных сделок: `{s['total_orders']}`"
    )
    await callback.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [ikb_button("Назад", callback_data="admin_back", emoji_key="back")]
        ]),
        parse_mode="Markdown"
    )


@dp.callback_query(F.data == "adm_rates", F.from_user.id.in_(ADMIN_IDS))
async def adm_rates(callback: types.CallbackQuery):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            ikb_button("UAH база", callback_data="set_uah_rate", emoji_key="set_uah_rate"),
            ikb_button("RUB база", callback_data="set_rub_rate", emoji_key="set_rub_rate")
        ],
        [ikb_button("Назад", callback_data="admin_back", emoji_key="back")]
    ])
    await callback.message.edit_text(
        f"Курсы:\nUAH: {settings['uah_rate']}\nRUB: {settings['rub_rate']}",
        reply_markup=kb
    )


@dp.callback_query(F.data == "adm_reqs", F.from_user.id.in_(ADMIN_IDS))
async def adm_reqs(callback: types.CallbackQuery):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            ikb_button("UA: Карта", callback_data="set_uah_card", emoji_key="set_uah_card"),
            ikb_button("UA: Имя", callback_data="set_uah_name", emoji_key="set_uah_name")
        ],
        [
            ikb_button("RU: Тел", callback_data="set_rub_phone", emoji_key="set_rub_phone"),
            ikb_button("RU: Имя", callback_data="set_rub_name", emoji_key="set_rub_name")
        ],
        [
            ikb_button("RU: Банк", callback_data="set_rub_bank", emoji_key="set_rub_bank"),
            ikb_button("Назад", callback_data="admin_back", emoji_key="back")
        ]
    ])
    await callback.message.edit_text("Реквизиты:", reply_markup=kb)


@dp.callback_query(F.data == "adm_comm", F.from_user.id.in_(ADMIN_IDS))
async def adm_comm(callback: types.CallbackQuery):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            ikb_button("Коммент UA", callback_data="set_uah_comm", emoji_key="set_uah_comm"),
            ikb_button("Коммент RU", callback_data="set_rub_comm", emoji_key="set_rub_comm")
        ],
        [ikb_button("Назад", callback_data="admin_back", emoji_key="back")]
    ])
    await callback.message.edit_text(
        f"UA: {settings['uah_comm']}\nRU: {settings['rub_comm']}",
        reply_markup=kb
    )


@dp.callback_query(F.data.startswith("set_"), F.from_user.id.in_(ADMIN_IDS))
async def set_value(callback: types.CallbackQuery, state: FSMContext):
    key = callback.data.replace("set_", "")
    await state.update_data(changing=key)
    await callback.message.answer("Введите новое значение:")
    await state.set_state(AdminStates.waiting_for_reqs)


@dp.message(AdminStates.waiting_for_reqs, F.from_user.id.in_(ADMIN_IDS))
async def save_value(message: types.Message, state: FSMContext):
    data = await state.get_data()
    key = data["changing"]

    if key in ["uah_rate", "rub_rate", "min_buy"]:
        try:
            settings[key] = float(message.text.replace(",", "."))
        except Exception:
            return await message.answer("Введите число.")
    else:
        settings[key] = message.text

    await message.answer("✅ Успешно обновлено!")
    await state.clear()


@dp.callback_query(F.data == "adm_push", F.from_user.id.in_(ADMIN_IDS))
async def push_start(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("Введите текст рассылки:")
    await state.set_state(AdminStates.waiting_for_broadcast)


@dp.message(AdminStates.waiting_for_broadcast, F.from_user.id.in_(ADMIN_IDS))
async def push_finish(message: types.Message, state: FSMContext):
    if not os.path.exists("users.txt"):
        return await message.answer("Нет пользователей.")

    with open("users.txt", "r", encoding="utf-8") as f:
        users = f.read().splitlines()

    count = 0
    for u_id in users:
        try:
            await bot.send_message(u_id, f"🔔 **УВЕДОМЛЕНИЕ**\n\n{message.text}", parse_mode="Markdown")
            count += 1
            await asyncio.sleep(0.05)
        except Exception:
            pass

    await message.answer(f"✅ Готово! Отправлено: {count}")
    await state.clear()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(dp.start_polling(bot))
