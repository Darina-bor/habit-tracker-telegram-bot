import sqlite3
from datetime import date, timedelta

DB_NAME = "habit_tracker.db"


def get_connection():
    return sqlite3.connect(DB_NAME)


def init_db():
    conn = get_connection()
    cur = conn.cursor()

    # Таблица пользователей
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            telegram_id INTEGER UNIQUE
        );
        """
    )

    # Таблица привычек
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS habits (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            name TEXT,
            category TEXT,
            reminder_time TEXT,
            created_at DATE,
            FOREIGN KEY (user_id) REFERENCES users(id)
        );
        """
    )

    # Таблица отметок выполнения
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS completions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            habit_id INTEGER,
            date DATE,
            FOREIGN KEY (habit_id) REFERENCES habits(id)
        );
        """
    )

    conn.commit()
    conn.close()


def get_or_create_user(telegram_id: int) -> int:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT id FROM users WHERE telegram_id = ?", (telegram_id,))
    row = cur.fetchone()
    if row:
        user_id = row[0]
    else:
        cur.execute(
            "INSERT INTO users (telegram_id) VALUES (?)",
            (telegram_id,),
        )
        conn.commit()
        user_id = cur.lastrowid
    conn.close()
    return user_id


def add_habit(
    user_id: int,
    name: str,
    category: str | None = None,
    reminder_time: str | None = None,
) -> int:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO habits (user_id, name, category, reminder_time, created_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (user_id, name, category, reminder_time, date.today().isoformat()),
    )
    conn.commit()
    habit_id = cur.lastrowid
    conn.close()
    return habit_id


def get_habits(user_id: int):
    """
    Возвращает список привычек пользователя:
    (id, name, category, reminder_time)
    """
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT id, name, category, reminder_time FROM habits WHERE user_id = ?",
        (user_id,),
    )
    rows = cur.fetchall()
    conn.close()
    return rows

def get_habit_by_id(habit_id: int):
    """
    Возвращает одну привычку по id:
    (id, user_id, name, category, reminder_time)
    """
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT id, user_id, name, category, reminder_time FROM habits WHERE id = ?",
        (habit_id,),
    )
    row = cur.fetchone()
    conn.close()
    return row

def delete_habit(habit_id: int):
    """
    Удаляет привычку и все её отметки выполнения.
    """
    conn = get_connection()
    cur = conn.cursor()

    # Сначала удаляем все completions, которые ссылаются на эту привычку
    cur.execute(
        "DELETE FROM completions WHERE habit_id = ?",
        (habit_id,),
    )

    # Потом удаляем саму привычку
    cur.execute(
        "DELETE FROM habits WHERE id = ?",
        (habit_id,),
    )

    conn.commit()
    conn.close()


def add_completion(habit_id: int, d: date | None = None):
    if d is None:
        d = date.today()
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO completions (habit_id, date) VALUES (?, ?)",
        (habit_id, d.isoformat()),
    )
    conn.commit()
    conn.close()


def get_stats_basic(habit_id: int):
    """Простая статистика: общее количество выполнений."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT COUNT(*) FROM completions WHERE habit_id = ?",
        (habit_id,),
    )
    count = cur.fetchone()[0]
    conn.close()
    return count


def get_streak(habit_id: int) -> int:
    """
    Считает текущий стрик (сколько дней подряд привычка выполнялась до сегодня включительно).
    """
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT date FROM completions WHERE habit_id = ? ORDER BY date DESC",
        (habit_id,),
    )
    rows = cur.fetchall()
    conn.close()

    if not rows:
        return 0

    dates = [date.fromisoformat(r[0]) for r in rows]
    today = date.today()

    # Если сегодня нет выполнения — стрик = 0
    if today not in dates:
        return 0

    streak = 0
    current_day = today
    while current_day in dates:
        streak += 1
        current_day = current_day - timedelta(days=1)

    return streak


def get_all_users():
    """Возвращает список всех telegram_id пользователей."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT telegram_id FROM users")
    rows = cur.fetchall()
    conn.close()
    return [r[0] for r in rows]


def get_habits_to_remind(time_str: str):
    """
    Возвращает список (telegram_id, habit_name) для всех привычек,
    у которых время напоминания = time_str (в формате 'HH:MM').
    """
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT u.telegram_id, h.name
        FROM habits h
        JOIN users u ON h.user_id = u.id
        WHERE h.reminder_time = ?
        """,
        (time_str,),
    )
    rows = cur.fetchall()
    conn.close()
    return rows


def get_user_export_data(user_id: int):
    """
    Возвращает данные для экспорта:
    список записей (название привычки, дата выполнения).
    """
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT h.name, c.date
        FROM habits h
        LEFT JOIN completions c ON h.id = c.habit_id
        WHERE h.user_id = ?
        ORDER BY h.name, c.date
        """,
        (user_id,),
    )
    rows = cur.fetchall()
    conn.close()
    return rows


def get_habit_daily_stats(habit_id: int):
    """
    Возвращает список (date, count) по дням для построения графика.
    """
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT date, COUNT(*)
        FROM completions
        WHERE habit_id = ?
        GROUP BY date
        ORDER BY date
        """,
        (habit_id,),
    )
    rows = cur.fetchall()
    conn.close()
    return rows
