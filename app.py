from flask import Flask, render_template, request, redirect, url_for, session, g
import os
import psycopg2 
import psycopg2.extras 
from dotenv import load_dotenv 

# --- 1. Конфигурация и Инициализация Flask ---

# Загрузка переменных окружения (для локального запуска)
load_dotenv() 

DATABASE_URL = os.environ.get('DATABASE_URL') 
SECRET_KEY = os.environ.get('SECRET_KEY', 'default_secret_key_v3')

if not DATABASE_URL:
    # Эта строка будет видна в логах Render, если переменная не установлена
    print("FATAL: Переменная DATABASE_URL не найдена. Проверьте настройки Render.")


template_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), 'templates'))
app = Flask(__name__, template_folder=template_dir) 
app.secret_key = SECRET_KEY

# --- 2. Функции Базы Данных ---

def get_db_connection():
    """Устанавливает соединение с БД PostgreSQL и сохраняет его в g."""
    if 'db' not in g:
        # !!! ПРОВЕРКА !!!: Если DATABASE_URL отсутствует, немедленно вызвать ошибку.
        if not DATABASE_URL:
             raise Exception("DATABASE_URL НЕ УСТАНОВЛЕН. Проверьте настройки окружения Render.") 
             
        try:
            g.db = psycopg2.connect(DATABASE_URL)
        except Exception as e:
            # Если не удалось подключиться
            print(f"ОШИБКА ПОДКЛЮЧЕНИЯ К БД: {e}")
            raise RuntimeError(f"Не удалось подключиться к базе данных: {e}")

    return g.db

@app.teardown_appcontext
def close_db_connection(exception):
    """Закрывает соединение с БД по завершении запроса."""
    db = g.pop('db', None)
    if db is not None:
        db.close()

def initialize_db():
    """Создает таблицы users и transactions."""
    conn = None
    try:
        # Прямое подключение для инициализации. Используем отдельное подключение.
        if not DATABASE_URL:
            print("ИНИЦИАЛИЗАЦИЯ: Пропущена, так как DATABASE_URL отсутствует.")
            return

        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()
        
        # Создание таблицы users
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                fio TEXT NOT NULL UNIQUE,
                password TEXT NOT NULL,
                balance_gamur REAL DEFAULT 0.00
            )
        """)

        # Создание таблицы transactions
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS transactions (
                id SERIAL PRIMARY KEY,
                user_id INTEGER REFERENCES users(id),
                description TEXT NOT NULL,
                amount REAL NOT NULL,
                transaction_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        conn.commit()
        print("ИНИЦИАЛИЗАЦИЯ БД: Таблицы users и transactions успешно проверены/созданы.")
    except Exception as e:
        # Эта ошибка будет видна при первом запуске, если БД недоступна или URL неверный
        print(f"ОШИБКА ИНИЦИАЛИЗАЦИИ БД: Не удалось создать таблицы. {e}")
    finally:
        if conn is not None:
             conn.close() 

with app.app_context():
    initialize_db()

# --- 3. Маршруты (Логика приложения) ---

@app.route('/')
def index():
    """Перенаправляет на дашборд, если авторизован, иначе на приветствие/регистрацию."""
    if 'user_fio' in session:
        return redirect(url_for('dashboard'))

    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM users")
        user_count = cursor.fetchone()[0]
    except Exception as e:
        # Если БД недоступна, мы перенаправляем на регистрацию, чтобы дать возможность работать дальше (или падать на /register, где будет диагностика)
        print(f"Ошибка БД при проверке пользователей: {e}")
        user_count = 0 # Предполагаем, что пользователей нет

    if user_count == 0:
        return redirect(url_for('register'))
    else:
        return redirect(url_for('welcome'))

@app.route('/welcome')
def welcome():
    if 'user_fio' in session:
        return redirect(url_for('dashboard'))
        
    return render_template('welcome.html')


@app.route('/register', methods=['GET', 'POST'])
def register():
    """Обработка регистрации нового пользователя и начального баланса."""
    error = None
    if request.method == 'POST':
        fio = request.form['fio'].strip()
        password = request.form['password']
        balance_str = request.form['balance'].strip()
        
        if not all([fio, password, balance_str]):
            error = "Пожалуйста, заполните все поля."
            return render_template('register.html', error=error)
        
        try:
            balance = float(balance_str) 
            if balance < 0:
                error = "Начальный баланс не может быть отрицательным."
                return render_template('register.html', error=error)
        except ValueError:
            error = "Баланс должен быть числом."
            return render_template('register.html', error=error)

        conn = None
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            
            # СОХРАНЕНИЕ БАЛАНСА В БД
            cursor.execute(
                "INSERT INTO users (fio, password, balance_gamur) VALUES (%s, %s, %s)",
                (fio, password, balance)
            )
            conn.commit()
        except psycopg2.errors.UniqueViolation:
            error = "Пользователь с таким Ф.И.О. уже существует."
            conn.rollback()
            return render_template('register.html', error=error)
        except Exception as e:
            # Логируем любую другую критическую ошибку
            print(f"Критическая ошибка при регистрации: {e}")
            error = "Критическая ошибка сервера. Проверьте логи БД."
            if conn:
                conn.rollback()
            return render_template('register.html', error=error)
        
        # УСТАНОВКА СЕССИИ
        session['user_fio'] = fio
        session['balance_gamur'] = balance
        return redirect(url_for('dashboard'))

    return render_template('register.html', error=error)


@app.route('/login', methods=['GET', 'POST'])
def login():
    """Обработка входа пользователя."""
    error = None
    if request.method == 'POST':
        password = request.form['password']
        
        conn = None
        user = None
        try:
            conn = get_db_connection()
            cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
            
            cursor.execute(
                "SELECT fio, balance_gamur FROM users WHERE password = %s", (password,)
            )
            user = cursor.fetchone()
        except Exception as e:
            # Логируем ошибку, если БД недоступна при попытке логина
            print(f"Критическая ошибка при входе: {e}")
            error = "Критическая ошибка сервера. Проверьте логи БД."
            return render_template('login.html', error=error)


        if user:
            session['user_fio'] = user['fio']
            session['balance_gamur'] = user['balance_gamur'] 
            return redirect(url_for('dashboard'))
        else:
            error = "Неверный пароль."
            return render_template('login.html', error=error)

    return render_template('login.html', error=error)


@app.route('/dashboard')
def dashboard():
    """Главная страница: отображение баланса и транзакций."""
    if 'user_fio' not in session:
        return redirect(url_for('login'))
        
    user_fio = session.get('user_fio', "Клиент")
    
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    
    # ЧТЕНИЕ БАЛАНСА ИЗ БД (всегда актуальное значение)
    try:
        cursor.execute(
            "SELECT id, balance_gamur FROM users WHERE fio = %s", (user_fio,)
        )
        user_data = cursor.fetchone()
    except Exception as e:
        print(f"Ошибка БД на дашборде: {e}")
        return render_template('error.html', message="Ошибка доступа к данным счета.")


    balance = user_data['balance_gamur'] if user_data and user_data['balance_gamur'] is not None else 0.00
    session['balance_gamur'] = balance # Обновляем сессию
    
    transactions = []
    
    if user_data:
        user_id = user_data['id']
        
        cursor.execute("""
            SELECT description, amount 
            FROM transactions 
            WHERE user_id = %s 
            ORDER BY transaction_date DESC 
            LIMIT 10
        """, (user_id,))
        transactions_raw = cursor.fetchall()
        
        transactions = [
            {"desc": row['description'], "amount": row['amount']} 
            for row in transactions_raw
        ]

    return render_template('dashboard.html', 
                           fio=user_fio.split()[0], 
                           balance=balance, 
                           transactions=transactions)


@app.route('/accounts')
def accounts():
    if 'user_fio' not in session:
        return redirect(url_for('login'))
        
    user_fio = session.get('user_fio')
    
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cursor.execute(
        "SELECT balance_gamur FROM users WHERE fio = %s", (user_fio,)
    )
    user_data = cursor.fetchone()
    
    current_balance = user_data['balance_gamur'] if user_data else 0.00
    
    accounts_list = [
        {"name": "Счет Гамур (основной)", "balance": current_balance, "currency": "ГМР", "number": "4081781000001"},
        {"name": "Накопительный счет", "balance": 55000.00, "currency": "ГМР", "number": "4081781000002"},
        {"name": "Карта VISA", "balance": 1250.50, "currency": "ГМР", "number": "4081781000003"}
    ]

    return render_template('accounts.html', 
                           fio=user_fio.split()[0],
                           accounts=accounts_list)


@app.route('/deposit', methods=['GET', 'POST'])
def deposit():
    """Обработка пополнения счета."""
    if 'user_fio' not in session:
        return redirect(url_for('login'))

    user_fio = session.get('user_fio')
    message = None
    error = None
    
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    
    cursor.execute(
        "SELECT id, balance_gamur FROM users WHERE fio = %s", (user_fio,)
    )
    user = cursor.fetchone()
    current_balance = user['balance_gamur'] if user else 0.00
    
    if request.method == 'POST':
        amount_str = request.form['amount'].strip()
        
        try:
            amount = float(amount_str)
            
            if amount <= 0:
                error = "Сумма пополнения должна быть положительной."
            else:
                new_balance = current_balance + amount
                
                # 1. Обновление баланса
                cursor.execute(
                    "UPDATE users SET balance_gamur = %s WHERE id = %s", 
                    (new_balance, user['id'])
                )
                
                # 2. ЗАПИСЬ ТРАНЗАКЦИИ
                description = f"Пополнение счета на {amount:,.2f} ГМР"
                cursor.execute(
                    "INSERT INTO transactions (user_id, description, amount) VALUES (%s, %s, %s)",
                    (user['id'], description, amount)
                )
                
                conn.commit()
                
                session['balance_gamur'] = new_balance
                current_balance = new_balance
                message = f"Счет успешно пополнен на {amount:,.2f} ГМР!"
                
        except ValueError:
            error = "Сумма пополнения должна быть числом."
        except Exception as e:
            error = f"Ошибка при пополнении: {e}"
            conn.rollback() # Откат в случае ошибки
    
    return render_template('deposit.html', 
                           fio=user_fio.split()[0], 
                           balance=current_balance,
                           message=message,
                           error=error)


@app.route('/payments', methods=['GET', 'POST'])
def payments():
    """Обработка платежей."""
    if 'user_fio' not in session:
        return redirect(url_for('login'))

    user_fio = session.get('user_fio')
    message = None
    error = None
    
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cursor.execute(
        "SELECT id, balance_gamur FROM users WHERE fio = %s", (user_fio,)
    )
    user_data = cursor.fetchone()
    
    current_balance = user_data['balance_gamur'] if user_data else 0.00
    session['balance_gamur'] = current_balance 

    if request.method == 'POST':
        phone_number = request.form['phone_number'].strip()
        amount_str = request.form['amount'].strip()
        
        try:
            amount = float(amount_str)
            
            if amount <= 0:
                error = "Сумма платежа должна быть положительной."
            elif current_balance < amount:
                error = "Недостаточно средств на счете Гамур для этого платежа."
            
            if not error:
                
                user = user_data
                
                if user:
                    new_balance = user['balance_gamur'] - amount
                    
                    # 1. Обновление баланса
                    cursor.execute(
                        "UPDATE users SET balance_gamur = %s WHERE id = %s", 
                        (new_balance, user['id'])
                    )
                    
                    # 2. ЗАПИСЬ ТРАНЗАКЦИИ
                    transaction_amount = -amount
                    description = f"Оплата мобильной связи ({phone_number})"
                    cursor.execute(
                        "INSERT INTO transactions (user_id, description, amount) VALUES (%s, %s, %s)",
                        (user['id'], description, transaction_amount)
                    )
                    
                    conn.commit()
                    
                    session['balance_gamur'] = new_balance
                    current_balance = new_balance
                    message = f"Оплата мобильной связи ({phone_number}) на сумму {amount:,.2f} ГМР успешно выполнена!"
                else:
                    error = "Ошибка: Пользователь не найден в базе данных."

        except ValueError:
            error = "Сумма платежа должна быть числом."
        except Exception as e:
            error = f"Ошибка при платеже: {e}"
            conn.rollback()
        
    return render_template('payments.html', 
                           fio=user_fio.split()[0], 
                           balance=current_balance,
                           message=message, 
                           error=error)


@app.route('/transfer', methods=['GET', 'POST'])
def transfer():
    if 'user_fio' not in session:
        return redirect(url_for('login'))

    user_fio = session.get('user_fio')
    current_balance = session.get('balance_gamur', 0.00)
    message = None
    error = None

    if request.method == 'POST':
        recipient_fio = request.form['recipient_fio'].strip()
        amount_str = request.form['amount'].strip()
        
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)

        try:
            amount = float(amount_str)
            if amount <= 0:
                error = "Сумма перевода должна быть положительной."
            elif recipient_fio == user_fio:
                error = "Нельзя перевести деньги самому себе."
            
            if not error:
                
                # 1. Находим отправителя
                cursor.execute(
                    "SELECT id, balance_gamur FROM users WHERE fio = %s", (user_fio,)
                )
                sender = cursor.fetchone()
                
                # 2. Находим получателя
                cursor.execute(
                    "SELECT id, balance_gamur, fio FROM users WHERE fio = %s", (recipient_fio,)
                )
                recipient = cursor.fetchone()

                if not recipient:
                    error = f"Получатель с ФИО '{recipient_fio}' не найден."
                elif sender['balance_gamur'] < amount:
                    error = "Недостаточно средств на счете Гамур."
                else:
                    # 3. Обновление баланса Отправителя
                    new_sender_balance = sender['balance_gamur'] - amount
                    cursor.execute(
                        "UPDATE users SET balance_gamur = %s WHERE id = %s", 
                        (new_sender_balance, sender['id'])
                    )
                    
                    # 4. Обновление баланса Получателя
                    new_recipient_balance = recipient['balance_gamur'] + amount
                    cursor.execute(
                        "UPDATE users SET balance_gamur = %s WHERE id = %s", 
                        (new_recipient_balance, recipient['id'])
                    )

                    # 5. ЗАПИСЬ ТРАНЗАКЦИИ для ОТПРАВИТЕЛЯ
                    cursor.execute(
                        "INSERT INTO transactions (user_id, description, amount) VALUES (%s, %s, %s)",
                        (sender['id'], f"Перевод пользователю {recipient_fio}", -amount)
                    )

                    # 6. ЗАПИСЬ ТРАНЗАКЦИИ для ПОЛУЧАТЕЛЯ
                    cursor.execute(
                        "INSERT INTO transactions (user_id, description, amount) VALUES (%s, %s, %s)",
                        (recipient['id'], f"Перевод от {user_fio}", amount)
                    )
                    
                    conn.commit()
                    message = f"Перевод {amount:,.2f} ГМР пользователю {recipient_fio} успешно выполнен!"
                    
                    current_balance = new_sender_balance
                    session['balance_gamur'] = current_balance

        except ValueError:
            error = "Сумма перевода должна быть числом."
        except Exception as e:
            error = f"Ошибка при переводе: {e}"
            conn.rollback()
        
    return render_template('transfer.html', 
                           fio=user_fio.split()[0], 
                           balance=current_balance,
                           message=message, 
                           error=error)


@app.route('/bonuses')
def bonuses():
    if 'user_fio' not in session:
        return redirect(url_for('login'))

    user_fio = session.get('user_fio').split()[0]
    
    bonus_balance = 7350
    
    bonus_history = [
        {"date": "2025-11-28", "description": "Покупка в супермаркете", "amount": 125},
        {"date": "2025-11-25", "description": "Оплата мобильной связи", "amount": 10},
        {"date": "2025-11-20", "description": "Бонус за активность", "amount": 500},
        {"date": "2025-11-15", "description": "Покупка билетов", "amount": 95},
    ]

    return render_template('bonuses.html', 
                           fio=user_fio,
                           bonus_balance=bonus_balance,
                           history=bonus_history)

@app.route('/analytics')
def analytics():
    if 'user_fio' not in session:
        return redirect(url_for('login'))

    user_fio = session.get('user_fio').split()[0]
    
    return render_template('analytics.html', 
                           fio=user_fio)


@app.route('/logout')
def logout():
    session.pop('user_fio', None)
    session.pop('balance_gamur', None)
    return redirect(url_for('login'))

if __name__ == '__main__':
    # При локальном запуске (не на Render)
    app.run(debug=True)