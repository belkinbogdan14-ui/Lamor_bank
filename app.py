import os
import re
import datetime
from dotenv import load_dotenv
from flask import Flask, render_template, request, redirect, url_for, session, flash
from werkzeug.security import check_password_hash, generate_password_hash

# --- Database setup (db.py content integrated) ---
import psycopg2

load_dotenv()

class Database:
    def __init__(self):
        self.conn = None
        self.cursor = None
        self.connect()

    def connect(self):
        try:
            # Используем DATABASE_URL от Render
            DATABASE_URL = os.environ.get('DATABASE_URL')
            if not DATABASE_URL:
                 raise ValueError("DATABASE_URL environment variable is not set.")

            self.conn = psycopg2.connect(DATABASE_URL)
            self.cursor = self.conn.cursor()
            print("УСПЕХ: Соединение с PostgreSQL установлено.")
            self.create_tables()

        except Exception as e:
            print(f"ОШИБКА: Не удалось подключиться к базе данных: {e}")
            self.conn = None
            self.cursor = None
            # Продолжаем, даже если соединение не удалось, чтобы показать страницу ошибки
            # или использовать заглушку.

    def create_tables(self):
        if not self.conn:
            print("ПРЕДУПРЕЖДЕНИЕ: Не удалось создать таблицы, нет соединения с БД.")
            return

        commands = (
            """
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                fio VARCHAR(255) NOT NULL,
                email VARCHAR(255) UNIQUE NOT NULL,
                password_hash VARCHAR(255) NOT NULL,
                balance_rub NUMERIC(15, 2) DEFAULT 0.00,
                balance_gamur NUMERIC(15, 2) DEFAULT 0.00
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS transactions (
                id SERIAL PRIMARY KEY,
                user_id INTEGER REFERENCES users (id),
                type VARCHAR(50) NOT NULL, -- 'deposit', 'transfer', 'payment'
                amount NUMERIC(15, 2) NOT NULL,
                currency VARCHAR(10) NOT NULL, -- 'RUB', 'GMR'
                target_fio VARCHAR(255),
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        try:
            for command in commands:
                self.cursor.execute(command)
            self.conn.commit()
            print("ИНИЦИАЛИЗАЦИЯ БД: Таблицы users и transactions успешно проверены/созданы.")
        except Exception as e:
            print(f"ОШИБКА БД при создании таблиц: {e}")
            self.conn.rollback()

    def fetch_one(self, query, params=None):
        if not self.conn: return None
        try:
            self.cursor.execute(query, params)
            return self.cursor.fetchone()
        except Exception as e:
            print(f"ОШИБКА БД (fetch_one): {e}")
            return None

    def fetch_all(self, query, params=None):
        if not self.conn: return []
        try:
            self.cursor.execute(query, params)
            return self.cursor.fetchall()
        except Exception as e:
            print(f"ОШИБКА БД (fetch_all): {e}")
            return []

    def execute(self, query, params=None):
        if not self.conn: return False
        try:
            self.cursor.execute(query, params)
            self.conn.commit()
            return True
        except Exception as e:
            print(f"ОШИБКА БД (execute): {e}")
            self.conn.rollback()
            return False

db = Database()
# --- End of Database setup ---


# --- Flask App Configuration ---
app = Flask(__name__)
# Устанавливаем SECURE RANDOM KEY
app.secret_key = os.environ.get('SECRET_KEY', 'default_secret_key_if_not_set')

# --- Helper Functions ---
def is_logged_in():
    return 'user_id' in session

def get_user_data(user_id):
    # Извлекаем все данные пользователя
    user_data = db.fetch_one(
        "SELECT id, fio, email, balance_rub, balance_gamur FROM users WHERE id = %s",
        (user_id,)
    )
    if user_data:
        # Обновляем сессию последними данными
        session['user_id'], session['user_fio'], session['user_email'], session['balance_rub'], session['balance_gamur'] = user_data
    return user_data

# --- Before Request Hook (Обновление данных пользователя перед каждым запросом) ---
@app.before_request
def load_user_data():
    if 'user_id' in session:
        # Пытаемся получить данные
        data = get_user_data(session['user_id'])
        # Если данные не получены, пользователь, возможно, был удален или БД недоступна
        if not data and request.endpoint not in ['login', 'register', 'welcome']:
            session.clear()
            return redirect(url_for('login'))


# --- Routes ---

@app.route('/')
def index():
    if is_logged_in():
        return redirect(url_for('dashboard'))
    return redirect(url_for('welcome'))

@app.route('/welcome')
def welcome():
    return render_template('welcome.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    error = None
    if request.method == 'POST':
        fio = request.form.get('fio')
        email = request.form.get('email')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')

        if not all([fio, email, password, confirm_password]):
            error = 'Все поля обязательны для заполнения.'
        elif password != confirm_password:
            error = 'Пароли не совпадают.'
        elif len(password) < 6:
            error = 'Пароль должен быть не менее 6 символов.'
        
        # Проверка формата email
        if not error and not re.match(r"[^@]+@[^@]+\.[^@]+", email):
            error = 'Неверный формат email.'

        if not error:
            # Проверяем, существует ли пользователь с таким email
            existing_user = db.fetch_one("SELECT id FROM users WHERE email = %s", (email,))
            if existing_user:
                error = 'Пользователь с таким email уже существует.'
            else:
                # Хешируем пароль и регистрируем
                password_hash = generate_password_hash(password)
                success = db.execute(
                    "INSERT INTO users (fio, email, password_hash, balance_rub, balance_gamur) VALUES (%s, %s, %s, %s, %s)",
                    (fio, email, password_hash, 1000.00, 50.00) # Начальный баланс
                )
                if success:
                    flash('Регистрация прошла успешно! Теперь войдите в систему.', 'success')
                    return redirect(url_for('login'))
                else:
                    error = 'Ошибка регистрации. Попробуйте снова.'

    # ИЗМЕНЕНИЕ: Передаем error в шаблон
    return render_template('register.html', error=error)


@app.route('/login', methods=['GET', 'POST'])
def login():
    error = None
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')

        if not all([email, password]):
            error = 'Введите email и пароль.'
        else:
            # Ищем пользователя по email и получаем хеш
            user = db.fetch_one("SELECT id, fio, password_hash, balance_rub, balance_gamur FROM users WHERE email = %s", (email,))
            
            if user and check_password_hash(user[2], password): # user[2] это password_hash
                # Успешный вход
                session['user_id'] = user[0]
                session['user_fio'] = user[1]
                session['balance_rub'] = user[3]
                session['balance_gamur'] = user[4]
                flash('Вы успешно вошли!', 'success')
                return redirect(url_for('dashboard'))
            else:
                error = 'Неверный email или пароль.'

    # ИЗМЕНЕНИЕ: Передаем error в шаблон
    return render_template('login.html', error=error)

@app.route('/logout')
def logout():
    session.clear()
    flash('Вы вышли из системы.', 'info')
    return redirect(url_for('login'))

# --- Защищенные маршруты (требуют входа) ---

@app.route('/dashboard')
def dashboard():
    if not is_logged_in():
        return redirect(url_for('login'))
    
    # Получение последних транзакций
    transactions = db.fetch_all(
        "SELECT type, amount, currency, timestamp FROM transactions WHERE user_id = %s ORDER BY timestamp DESC LIMIT 5",
        (session['user_id'],)
    )
    
    # Форматирование транзакций для отображения
    formatted_transactions = []
    for type, amount, currency, timestamp in transactions:
        formatted_transactions.append({
            'type': type,
            'amount': f"{amount:,.2f} {currency}",
            'timestamp': timestamp.strftime('%d.%m.%Y %H:%M')
        })
        
    return render_template('dashboard.html', transactions=formatted_transactions)

# Создайте заглушки для других маршрутов, чтобы они не выдавали 404/500
@app.route('/accounts')
def accounts():
    if not is_logged_in(): return redirect(url_for('login'))
    return render_template('accounts.html')

@app.route('/deposit')
def deposit():
    if not is_logged_in(): return redirect(url_for('login'))
    return render_template('deposit.html')

@app.route('/payments')
def payments():
    if not is_logged_in(): return redirect(url_for('login'))
    return render_template('payments.html')

@app.route('/transfer')
def transfer():
    if not is_logged_in(): return redirect(url_for('login'))
    return render_template('transfer.html')

@app.route('/bonuses')
def bonuses():
    if not is_logged_in(): return redirect(url_for('login'))
    return render_template('bonuses.html')

@app.route('/analytics')
def analytics():
    if not is_logged_in(): return redirect(url_for('login'))
    return render_template('analytics.html')

if __name__ == '__main__':
    app.run(debug=True)