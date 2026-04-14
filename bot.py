import asyncio
from datetime import datetime, time, timedelta
import io
import csv

import matplotlib.pyplot as plt

from aiogram import Bot, Dispatcher, F
from aiogram.types import (
    Message,
    ReplyKeyboardMarkup,
    KeyboardButton,
    CallbackQuery,
    BufferedInputFile,
)
from aiogram.filters import Command
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.utils.keyboard import InlineKeyboardBuilder

from config import BOT_TOKEN
import db

bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)


# ---- Состояния ----

class AddHabitStates(StatesGroup):
    waiting_for_name = State()
    waiting_for_category = State()
    waiting_for_reminder_time = State()


# ---- Команда /start и Главное Меню ----

@dp.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    db.init_db()
    db.get_or_create_user(message.from_user.id)

    # Создаем удобное кнопочное меню
    kb = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="➕ Добавить привычку"), KeyboardButton(text="📋 Мои привычки")],
            [KeyboardButton(text="✅ Отметить выполнение"), KeyboardButton(text="📊 Статистика")],
            [KeyboardButton(text="📈 График"), KeyboardButton(text="📥 Экспорт")],
            [KeyboardButton(text="🗑 Удалить привычку")]
        ],
        resize_keyboard=True,
    )

    await message.answer(
        "Привет! Я персональный трекер привычек.\n"
        "Я помогу тебе отслеживать полезные действия каждый день 🌱\n\n"
        "Используй кнопки меню ниже:",
        reply_markup=kb,
    )


# ---- Обработчики кнопок главного меню ----

@dp.message(F.text == "➕ Добавить привычку")
async def button_add(message: Message, state: FSMContext):
    await cmd_add(message, state)

@dp.message(F.text == "📋 Мои привычки")
async def button_habits(message: Message):
    await cmd_habits(message)

@dp.message(F.text == "✅ Отметить выполнение")
async def button_done(message: Message):
    await cmd_done(message)

@dp.message(F.text == "📊 Статистика")
async def button_stats(message: Message):
    await cmd_stats(message)

@dp.message(F.text == "📈 График")
async def button_graph(message: Message):
    await cmd_graph(message)

@dp.message(F.text == "📥 Экспорт")
async def button_export(message: Message):
    await cmd_export(message)

@dp.message(F.text == "🗑 Удалить привычку")
async def button_delete(message: Message):
    await cmd_delete(message)


# ---- Добавление привычки ----

CATEGORIES = ["Здоровье", "Учёба", "Работа", "Привычки дня", "Другое"]

@dp.message(Command("add"))
async def cmd_add(message: Message, state: FSMContext):
    await message.answer("Напиши название новой привычки:")
    await state.set_state(AddHabitStates.waiting_for_name)

@dp.message(AddHabitStates.waiting_for_name)
async def process_habit_name(message: Message, state: FSMContext):
    habit_name = message.text.strip()
    if not habit_name:
        await message.answer("Название не может быть пустым. Попробуй ещё раз.")
        return

    await state.update_data(name=habit_name)
    kb = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=c)] for c in CATEGORIES],
        resize_keyboard=True,
        one_time_keyboard=True,
    )
    await message.answer("Выбери категорию:", reply_markup=kb)
    await state.set_state(AddHabitStates.waiting_for_category)

@dp.message(AddHabitStates.waiting_for_category)
async def process_habit_category(message: Message, state: FSMContext):
    category = message.text.strip()
    if category not in CATEGORIES:
        await message.answer("Выбери категорию из предложенных на клавиатуре.")
        return

    await state.update_data(category=category)
    await message.answer(
        "Введи время напоминания (ЧЧ:ММ) или напиши «нет»."
    )
    await state.set_state(AddHabitStates.waiting_for_reminder_time)

@dp.message(AddHabitStates.waiting_for_reminder_time)
async def process_habit_reminder_time(message: Message, state: FSMContext):
    text = message.text.strip().lower()
    reminder_time = None
    if text != "нет":
        try:
            dt = datetime.strptime(text, "%H:%M")
            reminder_time = dt.strftime("%H:%M")
        except ValueError:
            await message.answer("Неверный формат. Нужно ЧЧ:ММ, например 07:30.")
            return

    data = await state.get_data()
    user_id = db.get_or_create_user(message.from_user.id)
    db.add_habit(user_id, data["name"], data["category"], reminder_time)

    await message.answer(f"Привычка «{data['name']}» добавлена! ✅")
    await state.clear()
    
    # Вместо вызова cmd_start создаем только клавиатуру
    kb = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="➕ Добавить привычку"), KeyboardButton(text="📋 Мои привычки")],
            [KeyboardButton(text="✅ Отметить выполнение"), KeyboardButton(text="📊 Статистика")],
            [KeyboardButton(text="📈 График"), KeyboardButton(text="📥 Экспорт")],
            [KeyboardButton(text="🗑 Удалить привычку")]
        ],
        resize_keyboard=True,
    )
    
    await message.answer("Меню обновлено. Что сделаем теперь?", reply_markup=kb)


# ---- Список привычек ----

@dp.message(Command("habits"))
async def cmd_habits(message: Message):
    user_id = db.get_or_create_user(message.from_user.id)
    habits = db.get_habits(user_id)
    if not habits:
        await message.answer("У тебя пока нет привычек.")
        return

    lines = ["Твои привычки:"]
    for hid, name, category, reminder_time in habits:
        line = f"• {name} [{category}]"
        if reminder_time: line += f" ⏰ {reminder_time}"
        lines.append(line)
    await message.answer("\n".join(lines))


# ---- Отметка выполнения ----

@dp.message(Command("done"))
async def cmd_done(message: Message):
    user_id = db.get_or_create_user(message.from_user.id)
    habits = db.get_habits(user_id)
    if not habits:
        await message.answer("Сначала добавь привычку.")
        return

    kb = InlineKeyboardBuilder()
    for hid, name, category, _ in habits:
        kb.button(text=f"{name} [{category}]", callback_data=f"done:{hid}")
    kb.adjust(1)
    await message.answer("Что выполнил сегодня?", reply_markup=kb.as_markup())

@dp.callback_query(F.data.startswith("done:"))
async def process_done(callback: CallbackQuery):
    habit_id = int(callback.data.split(":")[1])
    is_added = db.add_completion(habit_id)
    
    await callback.answer()
    if is_added:
        await callback.message.edit_text("Отлично! Привычка выполнена сегодня 💪")
    else:
        await callback.message.edit_text("Ты уже отмечал эту привычку сегодня! 😊")


# ---- Удаление ----

@dp.message(Command("delete"))
async def cmd_delete(message: Message):
    user_id = db.get_or_create_user(message.from_user.id)
    habits = db.get_habits(user_id)
    if not habits:
        await message.answer("Нечего удалять.")
        return

    kb = InlineKeyboardBuilder()
    for hid, name, _, _ in habits:
        kb.button(text=name, callback_data=f"del:{hid}")
    kb.adjust(1)
    await message.answer("Что удалить?", reply_markup=kb.as_markup())

@dp.callback_query(F.data.startswith("del:"))
async def process_delete(callback: CallbackQuery):
    habit_id = int(callback.data.split(":")[1])
    habit = db.get_habit_by_id(habit_id)
    if habit:
        db.delete_habit(habit_id)
        await callback.message.edit_text(f"Привычка «{habit[2]}» удалена 🗑")
    await callback.answer()


# ---- Статистика и Графики ----

@dp.message(Command("stats"))
async def cmd_stats(message: Message):
    user_id = db.get_or_create_user(message.from_user.id)
    habits = db.get_habits(user_id)
    if not habits:
        await message.answer("Нет привычек для статистики.")
        return

    kb = InlineKeyboardBuilder()
    for hid, name, _, _ in habits:
        kb.button(text=name, callback_data=f"stats:{hid}")
    kb.adjust(1)
    await message.answer("Выбери привычку:", reply_markup=kb.as_markup())

@dp.callback_query(F.data.startswith("stats:"))
async def process_stats(callback: CallbackQuery):
    habit_id = int(callback.data.split(":")[1])
    total = db.get_stats_basic(habit_id)
    streak = db.get_streak(habit_id)
    await callback.message.edit_text(f"Всего выполнений: {total}\nСтрик: {streak} 🔥")
    await callback.answer()

@dp.message(Command("graph"))
async def cmd_graph(message: Message):
    user_id = db.get_or_create_user(message.from_user.id)
    habits = db.get_habits(user_id)
    if not habits:
        await message.answer("Нет данных для графика.")
        return

    kb = InlineKeyboardBuilder()
    for hid, name, _, _ in habits:
        kb.button(text=name, callback_data=f"graph:{hid}")
    kb.adjust(1)
    await message.answer("Построить график для:", reply_markup=kb.as_markup())

@dp.callback_query(F.data.startswith("graph:"))
async def process_graph(callback: CallbackQuery):
    habit_id = int(callback.data.split(":")[1])
    data = db.get_habit_daily_stats(habit_id)
    if not data:
        await callback.answer("Нет данных.")
        return

    dates, counts = [d for d, c in data], [c for d, c in data]
    plt.figure(figsize=(6, 4))
    plt.plot(dates, counts, marker="o")
    plt.title("Прогресс")
    plt.xticks(rotation=45)
    plt.tight_layout()

    buf = io.BytesIO()
    plt.savefig(buf, format="png")
    buf.seek(0)
    plt.close()

    await callback.message.answer_document(BufferedInputFile(buf.getvalue(), filename="graph.png"))
    await callback.answer()

@dp.message(Command("export"))
async def cmd_export(message: Message):
    user_id = db.get_or_create_user(message.from_user.id)
    rows = db.get_user_export_data(user_id)
    if not rows:
        await message.answer("Нет данных.")
        return

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["habit", "date"])
    writer.writerows(rows)
    
    file = BufferedInputFile(output.getvalue().encode(), filename="export.csv")
    await message.answer_document(file)


# ---- Фоновые задачи и запуск ----

async def reminder_worker():
    while True:
        now = datetime.now().strftime("%H:%M")
        rows = db.get_habits_to_remind(now)
        for tg_id, name in rows:
            try:
                await bot.send_message(tg_id, f"Пора выполнить: {name} 💡")
            except: pass
        await asyncio.sleep(60)

async def main():
    db.init_db()
    asyncio.create_task(reminder_worker())
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
