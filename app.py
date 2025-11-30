from flask import Flask, render_template, request, redirect, url_for, session
import sqlite3
import os

# --- 1. Конфигурация с ФИКСОМ ПУТИ ---

# 1. Находим абсолютный путь к папке templates 
template_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), 'templates'))

# 2. Инициализируем Flask, используя найденный путь
app = Flask(__name__, template_folder=template_dir) 

# ВАЖНО: Секретный ключ для сессий Flask
app.secret_key = 'super_secret_key_lamor_bank_v2' 

DB_NAME = 'lamor_bank.db'

# --- 2. Функции Базы Данных ---

def initialize_db():
    """Создает базу данных и таблицу пользователей, если они не существуют."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY,
            fio TEXT NOT NULL,
            password TEXT NOT NULL,
            balance_gamur REAL DEFAULT 0.00
        )
    """)
    conn.commit()
    conn.close()

def get_db_connection():
    """Устанавливает соединение с БД и настраивает его для получения результатов как словарей."""
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn

# --- 3. Маршруты (Логика приложения) ---

@app.route('/')
def index():
    """Перенаправляет пользователя на Главную страницу, Вход или Регистрацию."""
    if 'user_fio' in session:
        return redirect(url_for('dashboard'))

    conn = get_db_connection()
    user_count = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    conn.close()

    if user_count == 0:
        return redirect(url_for('register'))
    else:
        return redirect(url_for('login'))


@app.route('/register', methods=['GET', 'POST'])
def register():
    """Маршрут для регистрации."""
    conn = get_db_connection()
    user_count = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    conn.close()
    
    if request.method == 'POST':
        fio = request.form['fio']
        password = request.form['password']
        balance_str = request.form['balance']
        
        if not all([fio, password, balance_str]):
            return render_template('register.html', error="Пожалуйста, заполните все поля.")
        
        try:
            balance = float(balance_str)
            if balance < 0:
                return render_template('register.html', error="Начальный баланс не может быть отрицательным.")
        except ValueError:
            return render_template('register.html', error="Баланс должен быть числом.")

        conn = get_db_connection()
        conn.execute(
            "INSERT INTO users (fio, password, balance_gamur) VALUES (?, ?, ?)",
            (fio, password, balance)
        )
        conn.commit()
        conn.close()
        
        session['user_fio'] = fio
        session['balance_gamur'] = balance
        return redirect(url_for('dashboard'))

    return render_template('register.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    """Маршрут для авторизации."""
    if request.method == 'POST':
        password = request.form['password']
        
        conn = get_db_connection()
        user = conn.execute(
            "SELECT fio, balance_gamur FROM users WHERE password = ?", (password,)
        ).fetchone()
        conn.close()

        if user:
            session['user_fio'] = user['fio']
            session['balance_gamur'] = user['balance_gamur']
            return redirect(url_for('dashboard'))
        else:
            return render_template('login.html', error="Неверный пароль.")

    return render_template('login.html')


@app.route('/dashboard')
def dashboard():
    """Главный экран (Личный кабинет)"""
    if 'user_fio' not in session:
        return redirect(url_for('login'))
        
    user_fio = session.get('user_fio', "Клиент").split()[0]
    
    # Обновляем баланс в сессии (актуальный баланс)
    conn = get_db_connection()
    current_balance_row = conn.execute(
        "SELECT balance_gamur FROM users WHERE fio = ?", (session['user_fio'],)
    ).fetchone()
    conn.close()
    
    if current_balance_row:
        balance = current_balance_row['balance_gamur']
        session['balance_gamur'] = balance
    else:
        balance = session.get('balance_gamur', 0.00)

    # ФИКЦИВНЫЕ ДАННЫЕ для транзакций
    transactions = [
        {"desc": "Пополнение ЗП", "amount": 450000},
        {"desc": "Перевод на Счет N", "amount": -12000},
        {"desc": "Оплата мобильной связи", "amount": -850},
        {"desc": "Перевод от Петрова", "amount": 10000},
    ]

    return render_template('dashboard.html', 
                           fio=user_fio, 
                           balance=balance, 
                           transactions=transactions)


@app.route('/accounts')
def accounts():
    """Маршрут для страницы счетов."""
    if 'user_fio' not in session:
        return redirect(url_for('login'))
        
    user_fio = session.get('user_fio')
    balance = session.get('balance_gamur', 0.00)

    # Временно используем фиктивный список счетов
    accounts_list = [
        {"name": "Счет Гамур (основной)", "balance": balance, "currency": "ГМР", "number": "4081781000001"},
        {"name": "Накопительный счет", "balance": 55000.00, "currency": "ГМР", "number": "4081781000002"},
        {"name": "Карта VISA", "balance": 1250.50, "currency": "ГМР", "number": "4081781000003"}
    ]

    return render_template('accounts.html', 
                           fio=user_fio.split()[0],
                           accounts=accounts_list)


@app.route('/payments', methods=['GET', 'POST'])
def payments():
    """Маршрут для осуществления платежей (например, мобильная связь)."""
    if 'user_fio' not in session:
        return redirect(url_for('login'))

    user_fio = session.get('user_fio')
    
    # Получаем актуальный баланс из базы данных
    conn_check = get_db_connection()
    user_data = conn_check.execute(
        "SELECT balance_gamur FROM users WHERE fio = ?", (user_fio,)
    ).fetchone()
    conn_check.close()
    
    current_balance = user_data['balance_gamur'] if user_data else 0.00
    session['balance_gamur'] = current_balance 

    message = None
    error = None

    if request.method == 'POST':
        phone_number = request.form['phone_number'].strip()
        amount_str = request.form['amount'].strip()
        
        # Улучшенная проверка номера телефона
        if not phone_number.isdigit() or len(phone_number) < 7:
             error = "Пожалуйста, введите корректный номер телефона (минимум 7 цифр, только цифры)."
        
        try:
            amount = float(amount_str)
            
            if amount <= 0:
                error = "Сумма платежа должна быть положительной."
            elif current_balance < amount:
                error = "Недостаточно средств на счете Гамур для этого платежа."
            
            # Если ошибок нет, выполняем платеж
            if not error:
                conn = get_db_connection()
                
                # Получаем ID пользователя и баланс для обновления
                user = conn.execute(
                    "SELECT id, balance_gamur FROM users WHERE fio = ?", (user_fio,)
                ).fetchone()
                
                if user:
                    # Обновляем баланс
                    new_balance = user['balance_gamur'] - amount
                    conn.execute(
                        "UPDATE users SET balance_gamur = ? WHERE id = ?", 
                        (new_balance, user['id'])
                    )
                    
                    conn.commit()
                    conn.close()
                    
                    # Обновляем сессию и текущий баланс для отображения
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
    """Маршрут для осуществления перевода средств."""
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
            else:
                conn = get_db_connection()
                
                sender = conn.execute(
                    "SELECT id, balance_gamur FROM users WHERE fio = ?", (user_fio,)
                ).fetchone()
                
                recipient = conn.execute(
                    "SELECT id, balance_gamur FROM users WHERE fio = ?", (recipient_fio,)
                ).fetchone()

                if not recipient:
                    error = f"Получатель с ФИО '{recipient_fio}' не найден."
                elif sender['balance_gamur'] < amount:
                    error = "Недостаточно средств на счете Гамур."
                else:
                    new_sender_balance = sender['balance_gamur'] - amount
                    conn.execute(
                        "UPDATE users SET balance_gamur = ? WHERE id = ?", 
                        (new_sender_balance, sender['id'])
                    )
                    
                    new_recipient_balance = recipient['balance_gamur'] + amount
                    conn.execute(
                        "UPDATE users SET balance_gamur = ? WHERE id = ?", 
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
    """Маршрут для страницы бонусов и истории их начисления."""
    if 'user_fio' not in session:
        return redirect(url_for('login'))

    user_fio = session.get('user_fio').split()[0]
    
    # ФИКЦИВНЫЕ ДАННЫЕ ДЛЯ БОНУСОВ
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
    """Заглушка для страницы аналитики."""
    if 'user_fio' not in session:
        return redirect(url_for('login'))

    user_fio = session.get('user_fio').split()[0]
    
    return render_template('analytics.html', 
                           fio=user_fio)


@app.route('/logout')
def logout():
    """Очистка сессии и выход."""
    session.pop('user_fio', None)
    session.pop('balance_gamur', None)
    return redirect(url_for('login'))

# --- 4. Запуск ---

if __name__ == '__main__':
    with app.app_context():
        initialize_db()
        
    app.run(debug=True)