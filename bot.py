# bot.py
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


# ---- Команда /start ----

@dp.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    db.init_db()
    db.get_or_create_user(message.from_user.id)

    kb = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Добавить привычку")],
            [KeyboardButton(text="Мои привычки")],
            [KeyboardButton(text="Отметить выполнение")],
            [KeyboardButton(text="Статистика")],
            [KeyboardButton(text="Удалить привычку")],
        ],
        resize_keyboard=True,
    )

    await message.answer(
        "Привет! Я персональный трекер привычек.\n"
        "Я помогу тебе отслеживать полезные действия каждый день 🌱",
        reply_markup=kb,
    )


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
    await message.answer(
        "Выбери категорию для этой привычки:",
        reply_markup=kb,
    )
    await state.set_state(AddHabitStates.waiting_for_category)


@dp.message(AddHabitStates.waiting_for_category)
async def process_habit_category(message: Message, state: FSMContext):
    category = message.text.strip()
    if category not in CATEGORIES:
        await message.answer(
            "Я не знаю такую категорию 😅\n"
            "Выбери одну из предложенных на клавиатуре."
        )
        return

    await state.update_data(category=category)
    await message.answer(
        "Введи время напоминания в формате ЧЧ:ММ (например, 20:30)\n"
        "или напиши «нет», если напоминание не нужно."
    )
    await state.set_state(AddHabitStates.waiting_for_reminder_time)


@dp.message(AddHabitStates.waiting_for_reminder_time)
async def process_habit_reminder_time(message: Message, state: FSMContext):
    text = message.text.strip().lower()

    if text == "нет":
        reminder_time = None
    else:
        try:
            # Проверяем формат ЧЧ:ММ
            dt = datetime.strptime(text, "%H:%M")
            reminder_time = dt.strftime("%H:%M")
        except ValueError:
            await message.answer(
                "Неверный формат времени. Нужен формат ЧЧ:ММ, например 07:30 или 19:00.\n"
                "Или напиши «нет»."
            )
            return

    data = await state.get_data()
    name = data["name"]
    category = data["category"]

    user_id = db.get_or_create_user(message.from_user.id)
    db.add_habit(user_id, name, category, reminder_time)

    text_answer = f"Привычка «{name}» (категория: {category}) добавлена ✅"
    if reminder_time:
        text_answer += f"\nНапоминание каждый день в {reminder_time}."
    else:
        text_answer += "\nБез напоминаний."

    await message.answer(text_answer)
    await state.clear()


@dp.message(F.text.lower() == "добавить привычку")
async def button_add(message: Message, state: FSMContext):
    await cmd_add(message, state)


# ---- Список привычек ----

@dp.message(F.text.lower() == "мои привычки")
@dp.message(Command("habits"))
async def cmd_habits(message: Message):
    user_id = db.get_or_create_user(message.from_user.id)
    habits = db.get_habits(user_id)
    if not habits:
        await message.answer("У тебя пока нет привычек. Добавь первую через /add.")
        return

    lines = ["Твои привычки:"]
    for hid, name, category, reminder_time in habits:
        line = f"• {name}"
        if category:
            line += f" [{category}]"
        if reminder_time:
            line += f" ⏰ {reminder_time}"
        lines.append(line)

    await message.answer("\n".join(lines))


# ---- Отметка выполнения ----

@dp.message(F.text.lower() == "отметить выполнение")
@dp.message(Command("done"))
async def cmd_done(message: Message):
    user_id = db.get_or_create_user(message.from_user.id)
    habits = db.get_habits(user_id)
    if not habits:
        await message.answer("Сначала добавь хотя бы одну привычку.")
        return

    kb = InlineKeyboardBuilder()
    for hid, name, category, reminder_time in habits:
        btn_text = name
        if category:
            btn_text += f" [{category}]"
        kb.button(text=btn_text, callback_data=f"done:{hid}")
    kb.adjust(1)

    await message.answer(
        "Выбери привычку, которую ты выполнил сегодня:",
        reply_markup=kb.as_markup(),
    )


@dp.callback_query(F.data.startswith("done:"))
async def process_done(callback: CallbackQuery):
    _, habit_id_str = callback.data.split(":")
    habit_id = int(habit_id_str)
    db.add_completion(habit_id)
    await callback.answer("Отмечено!")
    await callback.message.answer("Отлично! Привычка выполнена сегодня 💪")

# ---- Удаление привычки ----

@dp.message(Command("delete"))
async def cmd_delete(message: Message):
    user_id = db.get_or_create_user(message.from_user.id)
    habits = db.get_habits(user_id)
    if not habits:
        await message.answer("У тебя нет привычек, нечего удалять.")
        return

    kb = InlineKeyboardBuilder()
    for hid, name, category, reminder_time in habits:
        btn_text = name
        if category:
            btn_text += f" [{category}]"
        kb.button(text=btn_text, callback_data=f"del:{hid}")
    kb.adjust(1)

    await message.answer(
        "Выбери привычку, которую хочешь удалить:",
        reply_markup=kb.as_markup(),
    )


@dp.message(F.text.lower() == "удалить привычку")
async def button_delete(message: Message):
    # просто переиспользуем логику /delete
    await cmd_delete(message)

@dp.callback_query(F.data.startswith("del:"))
async def process_delete(callback: CallbackQuery):
    _, habit_id_str = callback.data.split(":")
    habit_id = int(habit_id_str)

    habit = db.get_habit_by_id(habit_id)
    if habit is None:
        await callback.answer()
        await callback.message.answer("Эта привычка уже удалена или не найдена.")
        return

    _, user_id, name, category, reminder_time = habit

    # Удаляем из базы
    db.delete_habit(habit_id)

    await callback.answer()
    text = f"Привычка «{name}» удалена 🗑"
    await callback.message.answer(text)


# ---- Статистика ----

@dp.message(F.text.lower() == "статистика")
@dp.message(Command("stats"))
async def cmd_stats(message: Message):
    user_id = db.get_or_create_user(message.from_user.id)
    habits = db.get_habits(user_id)
    if not habits:
        await message.answer("У тебя нет привычек для статистики.")
        return

    kb = InlineKeyboardBuilder()
    for hid, name, category, reminder_time in habits:
        btn_text = name
        if category:
            btn_text += f" [{category}]"
        kb.button(text=btn_text, callback_data=f"stats:{hid}")
    kb.adjust(1)

    await message.answer(
        "Выбери привычку для просмотра статистики:",
        reply_markup=kb.as_markup(),
    )


@dp.callback_query(F.data.startswith("stats:"))
async def process_stats(callback: CallbackQuery):
    _, habit_id_str = callback.data.split(":")
    habit_id = int(habit_id_str)

    total = db.get_stats_basic(habit_id)
    streak = db.get_streak(habit_id)

    await callback.answer()
    text = (
        f"Всего выполнений этой привычки: {total} раз(а) 📊\n"
        f"Текущий стрик (подряд дней): {streak} 🔥"
    )
    await callback.message.answer(text)


# ---- Экспорт в CSV ----

@dp.message(Command("export"))
async def cmd_export(message: Message):
    user_id = db.get_or_create_user(message.from_user.id)
    rows = db.get_user_export_data(user_id)

    if not rows:
        await message.answer(
            "У тебя пока нет данных для экспорта (нет привычек или отметок)."
        )
        return

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["habit_name", "date"])
    for habit_name, dt in rows:
        writer.writerow([habit_name, dt if dt else ""])

    csv_data = output.getvalue().encode("utf-8")
    output.close()

    file = BufferedInputFile(csv_data, filename="habits_export.csv")
    await message.answer_document(file, caption="Вот твой экспорт привычек 📄")


# ---- График прогресса ----

@dp.message(Command("graph"))
async def cmd_graph(message: Message):
    user_id = db.get_or_create_user(message.from_user.id)
    habits = db.get_habits(user_id)
    if not habits:
        await message.answer("У тебя нет привычек для графика.")
        return

    kb = InlineKeyboardBuilder()
    for hid, name, category, reminder_time in habits:
        btn_text = name
        if category:
            btn_text += f" [{category}]"
        kb.button(text=btn_text, callback_data=f"graph:{hid}")
    kb.adjust(1)

    await message.answer(
        "Выбери привычку для построения графика:",
        reply_markup=kb.as_markup(),
    )


@dp.callback_query(F.data.startswith("graph:"))
async def process_graph(callback: CallbackQuery):
    _, habit_id_str = callback.data.split(":")
    habit_id = int(habit_id_str)

    data = db.get_habit_daily_stats(habit_id)
    if not data:
        await callback.answer()
        await callback.message.answer("Для этой привычки пока нет данных для графика.")
        return

    dates = [d for d, c in data]
    counts = [c for d, c in data]

    # Строим график
    plt.figure(figsize=(6, 4))
    plt.plot(dates, counts, marker="o")
    plt.xlabel("Дата")
    plt.ylabel("Количество выполнений")
    plt.title("Прогресс по привычке")
    plt.xticks(rotation=45)
    plt.tight_layout()

    buf = io.BytesIO()
    plt.savefig(buf, format="png")
    buf.seek(0)
    plt.close()

    file = BufferedInputFile(buf.getvalue(), filename="habit_graph.png")
    await callback.answer()
    await callback.message.answer_document(
        file, caption="График прогресса по привычке 📈"
    )


# ---- Фолбэк ----

@dp.message()
async def fallback(message: Message):
    await message.answer(
        "Я тебя не понял.\n"
        "Используй кнопки под клавиатурой или команды "
        "/start /add /habits /done /stats /export /graph."
    )


# ---- Напоминания ----

async def reminder_worker():
    """
    Фоновая задача: каждые 60 секунд проверяет, кому нужно отправить напоминания.
    """
    while True:
        now = datetime.now()
        current_time_str = now.strftime("%H:%M")

        rows = db.get_habits_to_remind(current_time_str)
        if rows:
            # rows: список (telegram_id, habit_name)
            # Сгруппируем по пользователям
            users: dict[int, list[str]] = {}
            for tg_id, habit_name in rows:
                users.setdefault(tg_id, []).append(habit_name)

            for tg_id, habits in users.items():
                text = "Напоминание 💡\nПора выполнить привычки:\n"
                for name in habits:
                    text += f"• {name}\n"
                try:
                    await bot.send_message(tg_id, text)
                except Exception as e:
                    print(f"Ошибка при отправке напоминания пользователю {tg_id}: {e}")

        # Ждём минуту до следующей проверки
        await asyncio.sleep(60)


async def main():
    db.init_db()
    asyncio.create_task(reminder_worker())
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
