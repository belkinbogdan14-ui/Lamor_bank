from flask import Flask, render_template, request, redirect, url_for, session
import os
import psycopg2 
import psycopg2.extras 
from dotenv import load_dotenv 

# --- 1. Конфигурация и Функции Базы Данных ---

load_dotenv() 

DATABASE_URL = os.environ.get('DATABASE_URL') 
if not DATABASE_URL:
    print("Ошибка: Переменная DATABASE_URL не найдена. Установите ее в настройках Render.")

# 1.1. ФУНКЦИИ БАЗЫ ДАННЫХ
def get_db_connection():
    """Устанавливает соединение с БД PostgreSQL."""
    conn = psycopg2.connect(DATABASE_URL)
    return conn

def initialize_db():
    """Создает таблицу пользователей в PostgreSQL, если она не существует."""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                fio TEXT NOT NULL,
                password TEXT NOT NULL,
                balance_gamur REAL DEFAULT 0.00
            )
        """)
        conn.commit()
    except Exception as e:
        print(f"Ошибка инициализации БД: {e}")
    finally:
        if conn:
            conn.close()

# 1.2. ИНИЦИАЛИЗАЦИЯ FLASK
template_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), 'templates'))
app = Flask(__name__, template_folder=template_dir) 
app.secret_key = 'super_secret_key_lamor_bank_v2' 

with app.app_context():
    initialize_db()


# --- 2. Маршруты (Логика приложения) ---

@app.route('/')
def index():
    if 'user_fio' in session:
        return redirect(url_for('dashboard'))

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM users")
    user_count = cursor.fetchone()[0]
    conn.close()

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
    error = None
    if request.method == 'POST':
        fio = request.form['fio']
        password = request.form['password']
        balance_str = request.form['balance']
        
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

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO users (fio, password, balance_gamur) VALUES (%s, %s, %s)",
            (fio, password, balance)
        )
        conn.commit()
        conn.close()
        
        session['user_fio'] = fio
        session['balance_gamur'] = balance
        return redirect(url_for('dashboard'))

    return render_template('register.html', error=error)


@app.route('/login', methods=['GET', 'POST'])
def login():
    error = None
    if request.method == 'POST':
        password = request.form['password']
        
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        
        cursor.execute(
            "SELECT fio, balance_gamur FROM users WHERE password = %s", (password,)
        )
        user = cursor.fetchone()
        conn.close()

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
    if 'user_fio' not in session:
        return redirect(url_for('login'))
        
    user_fio = session.get('user_fio', "Клиент")
    
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cursor.execute(
        "SELECT balance_gamur FROM users WHERE fio = %s", (user_fio,)
    )
    current_balance_row = cursor.fetchone()
    conn.close()
    
    balance = current_balance_row['balance_gamur'] if current_balance_row else 0.00
    session['balance_gamur'] = balance

    transactions = [
        {"desc": "Пополнение ЗП", "amount": 450000},
        {"desc": "Перевод на Счет N", "amount": -12000},
        {"desc": "Оплата мобильной связи", "amount": -850},
        {"desc": "Перевод от Петрова", "amount": 10000},
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
    conn.close()
    
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
                cursor.execute(
                    "UPDATE users SET balance_gamur = %s WHERE id = %s", 
                    (new_balance, user['id'])
                )
                conn.commit()
                
                session['balance_gamur'] = new_balance
                current_balance = new_balance
                message = f"Счет успешно пополнен на {amount:,.2f} ГМР!"
                
        except ValueError:
            error = "Сумма пополнения должна быть числом."
    
    conn.close()
    return render_template('deposit.html', 
                           fio=user_fio.split()[0], 
                           balance=current_balance,
                           message=message,
                           error=error)


@app.route('/payments', methods=['GET', 'POST'])
def payments():
    if 'user_fio' not in session:
        return redirect(url_for('login'))

    user_fio = session.get('user_fio')
    message = None
    error = None
    
    conn_check = get_db_connection()
    cursor_check = conn_check.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cursor_check.execute(
        "SELECT balance_gamur FROM users WHERE fio = %s", (user_fio,)
    )
    user_data = cursor_check.fetchone()
    conn_check.close()
    
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
                conn = get_db_connection()
                cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
                
                cursor.execute(
                    "SELECT id, balance_gamur FROM users WHERE fio = %s", (user_fio,)
                )
                user = cursor.fetchone()
                
                if user:
                    new_balance = user['balance_gamur'] - amount
                    cursor.execute(
                        "UPDATE users SET balance_gamur = %s WHERE id = %s", 
                        (new_balance, user['id'])
                    )
                    
                    conn.commit()
                    conn.close()
                    
                    session['balance_gamur'] = new_balance
                    current_balance = new_balance
                    message = f"Оплата мобильной связи ({phone_number}) на сумму {amount:,.2f} ГМР успешно выполнена!"
                else:
                    error = "Ошибка: Пользователь не найден в базе данных."

        except ValueError:
            error = "Сумма платежа должна быть числом."
        
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
        recipient_fio = request.form['recipient_fio']
        amount_str = request.form['amount']
        
        try:
            amount = float(amount_str)
            if amount <= 0:
                error = "Сумма перевода должна быть положительной."
            elif recipient_fio == user_fio:
                error = "Нельзя перевести деньги самому себе."
            
            if not error:
                conn = get_db_connection()
                cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
                
                cursor.execute(
                    "SELECT id, balance_gamur FROM users WHERE fio = %s", (user_fio,)
                )
                sender = cursor.fetchone()
                
                cursor.execute(
                    "SELECT id, balance_gamur FROM users WHERE fio = %s", (recipient_fio,)
                )
                recipient = cursor.fetchone()

                if not recipient:
                    error = f"Получатель с ФИО '{recipient_fio}' не найден."
                elif sender['balance_gamur'] < amount:
                    error = "Недостаточно средств на счете Гамур."
                else:
                    new_sender_balance = sender['balance_gamur'] - amount
                    cursor.execute(
                        "UPDATE users SET balance_gamur = %s WHERE id = %s", 
                        (new_sender_balance, sender['id'])
                    )
                    
                    new_recipient_balance = recipient['balance_gamur'] + amount
                    cursor.execute(
                        "UPDATE users SET balance_gamur = %s WHERE id = %s", 
                        (new_recipient_balance, recipient['id'])
                    )
                    
                    conn.commit()
                    message = f"Перевод {amount:,.2f} ГМР пользователю {recipient_fio} успешно выполнен!"
                    
                    current_balance = new_sender_balance
                    session['balance_gamur'] = current_balance

                conn.close()

        except ValueError:
            error = "Сумма перевода должна быть числом."
        
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

# --- 3. Запуск (В самом низу, только для локального теста) ---

if __name__ == '__main__':
    app.run(debug=True)