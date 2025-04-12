import os
import sys
import logging
from functools import wraps
# Ensure the project root is in the path *before* other imports
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, project_root)

from flask import Flask, render_template, request, redirect, url_for, flash, session
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
from dotenv import load_dotenv
import asyncio
from config import DATABASE_URL, ADMIN_USERNAME, ADMIN_PASSWORD, BOT_TOKEN
from models import User, Subscription, Whitelist, SessionLocal, init_db, PromoCode, Referral, Admin
from aiogram import Bot
from flask_sqlalchemy import SQLAlchemy

# Настройка логирования
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Load .env from project root
load_dotenv(os.path.join(project_root, '.env'))

# Initialize database before creating app
try:
    init_db()
    logger.info("База данных успешно инициализирована")
except Exception as e:
    logger.error(f"Ошибка при инициализации базы данных: {e}")

app = Flask(__name__)
app.config['SECRET_KEY'] = os.urandom(24)
app.config['SQLALCHEMY_DATABASE_URI'] = DATABASE_URL
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# Initialize bot instance
try:
    bot = Bot(token=BOT_TOKEN)
    logger.info("Бот успешно инициализирован")
except Exception as e:
    logger.error(f"Ошибка при инициализации бота: {e}")
    bot = None

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('logged_in'):
            logger.debug(f"Доступ к {f.__name__} запрещен: пользователь не вошел")
            return redirect(url_for('login'))
        logger.debug(f"Доступ к {f.__name__} разрешен")
        return f(*args, **kwargs)
    return decorated_function

@app.route('/')
def index():
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    logger.debug("Перенаправление с / на /users")
    return redirect(url_for('users'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        if username == ADMIN_USERNAME and check_password_hash(generate_password_hash(ADMIN_PASSWORD), password):
            session['logged_in'] = True
            return redirect(url_for('users'))
        else:
            flash('Неверные учетные данные', 'error')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('logged_in', None)
    return redirect(url_for('login'))

@app.route('/users')
@login_required
def users():
    logger.debug("Запрос к /users")
    try:
        db = next(get_db())
        logger.debug("Получен доступ к БД для /users")
        users = db.query(User).all()
        logger.debug(f"Найдено {len(users)} пользователей")
        return render_template('users.html', users=users)
    except Exception as e:
        logger.exception("Ошибка при получении списка пользователей:")
        flash(f'Ошибка при получении списка пользователей: {str(e)}', 'error')
        logger.debug("Перенаправление с /users на / из-за ошибки")
        return redirect(url_for('index'))

@app.route('/edit_user/<int:user_id>', methods=['GET', 'POST'])
@login_required
def edit_user(user_id):
    try:
        db = next(get_db())
        user = db.get(User, user_id)
        if not user:
            flash('Пользователь не найден', 'error')
            return redirect(url_for('users'))
        
        if request.method == 'POST':
            user.referral_link_override = request.form.get('referral_link')
            user.referral_status_override = request.form.get('referral_status') == 'true'
            user.is_active = request.form.get('is_active') == 'true'
            db.commit()
            flash('Пользователь успешно обновлен', 'success')
            return redirect(url_for('users'))
        
        return render_template('edit_user.html', user=user)
    except Exception as e:
        flash(f'Ошибка при редактировании пользователя: {str(e)}', 'error')
        return redirect(url_for('users'))

@app.route('/whitelist', methods=['GET', 'POST'])
@login_required
def whitelist():
    try:
        db = next(get_db())
        if request.method == 'POST':
            telegram_id = request.form.get('telegram_id')
            if telegram_id:
                try:
                    telegram_id = int(telegram_id)
                    whitelist_entry = Whitelist(telegram_id=telegram_id)
                    db.add(whitelist_entry)
                    db.commit()
                    flash('Telegram ID успешно добавлен в белый список', 'success')
                except ValueError:
                    flash('Telegram ID должен быть числом', 'error')
                except Exception as e:
                    flash(f'Ошибка при добавлении в белый список: {str(e)}', 'error')
        
        whitelist_entries = db.query(Whitelist).all()
        return render_template('whitelist.html', whitelist_entries=whitelist_entries)
    except Exception as e:
        flash(f'Ошибка при работе с белым списком: {str(e)}', 'error')
        return redirect(url_for('index'))

@app.route('/delete_whitelist/<int:entry_id>')
@login_required
def delete_whitelist(entry_id):
    try:
        db = next(get_db())
        entry = db.get(Whitelist, entry_id)
        if entry:
            db.delete(entry)
            db.commit()
            flash('Запись успешно удалена из белого списка', 'success')
        else:
            flash('Запись не найдена', 'error')
    except Exception as e:
        flash(f'Ошибка при удалении записи: {str(e)}', 'error')
    return redirect(url_for('whitelist'))

@app.route('/subscriptions')
@login_required
def subscriptions():
    try:
        db = next(get_db())
        today = datetime.now().date()
        tomorrow = today + timedelta(days=1)
        
        payments_today = db.query(Subscription).filter(
            Subscription.start_date >= today,
            Subscription.start_date < tomorrow
        ).all()
        
        ending_today = db.query(Subscription).filter(
            Subscription.end_date >= today,
            Subscription.end_date < tomorrow
        ).all()
        
        return render_template('subscriptions.html', 
                             payments_today=payments_today,
                             ending_today=ending_today)
    except Exception as e:
        flash(f'Ошибка при получении информации о подписках: {str(e)}', 'error')
        return redirect(url_for('index'))

@app.route('/broadcast')
@login_required
def broadcast_page():
    try:
        db = next(get_db())
        users = db.query(User).filter(User.telegram_id.isnot(None)).all()
        return render_template('broadcast.html', users=users)
    except Exception as e:
        flash(f'Ошибка при загрузке страницы рассылки: {str(e)}', 'error')
        return redirect(url_for('index'))

async def send_message_async(user_id, text):
    try:
        logger.debug(f"Попытка отправить сообщение пользователю {user_id}")
        await bot.send_message(user_id, text)
        logger.info(f"Сообщение успешно отправлено пользователю {user_id}")
        return True, None
    except Exception as e:
        logger.error(f"Ошибка при отправке сообщения пользователю {user_id}: {e}")
        return False, str(e)

@app.route('/send_broadcast', methods=['POST'])
@login_required
def send_broadcast():
    if bot is None:
        logger.error("Бот не инициализирован. Рассылка невозможна.")
        flash('Ошибка: Бот не инициализирован.', 'error')
        return redirect(url_for('broadcast_page'))

    try:
        message = request.form.get('message_text')
        broadcast_type = request.form.get('broadcast_type')
        selected_user_form_id = request.form.get('selected_user_id')

        message_log = f"{message[:20]}..." if message else "[пустое сообщение]"
        logger.debug(f"Получен запрос на рассылку: тип={broadcast_type}, выбранный пользователь ID={selected_user_form_id}, сообщение='{message_log}'")

        if not message:
            flash('Введите текст сообщения', 'error')
            return redirect(url_for('broadcast_page'))

        db = next(get_db())
        target_users = []
        logger.debug("Начинаем поиск целевых пользователей...")

        if broadcast_type == 'selected' and selected_user_form_id:
            try:
                user = db.get(User, int(selected_user_form_id))
                if user and user.telegram_id:
                    target_users.append(user)
                    logger.debug(f"Выбран один пользователь: id={user.id}, telegram_id={user.telegram_id}")
                elif user:
                    logger.warning(f"Выбранный пользователь {user.id} не имеет telegram_id.")
                else:
                    logger.warning(f"Выбранный пользователь с ID {selected_user_form_id} не найден.")
            except ValueError:
                logger.warning(f"Некорректный ID пользователя: {selected_user_form_id}")
        else:
            target_users = db.query(User).filter(User.telegram_id.isnot(None)).all()
            logger.debug(f"Выбраны все пользователи с telegram_id, найдено {len(target_users)}")

        if not target_users:
            flash('Нет пользователей для рассылки', 'error')
            return redirect(url_for('broadcast_page'))

        success_count = 0
        error_count = 0
        error_messages = []

        for user in target_users:
            success, error = asyncio.run(send_message_async(user.telegram_id, message))
            if success:
                success_count += 1
            else:
                error_count += 1
                error_messages.append(f"Пользователь {user.id}: {error}")

        if error_count > 0:
            flash(f'Рассылка завершена. Успешно: {success_count}, Ошибок: {error_count}. Подробности: {", ".join(error_messages)}', 'warning')
        else:
            flash(f'Рассылка успешно завершена. Отправлено сообщений: {success_count}', 'success')

        return redirect(url_for('broadcast_page'))

    except Exception as e:
        logger.exception("Ошибка при выполнении рассылки:")
        flash(f'Ошибка при выполнении рассылки: {str(e)}', 'error')
        return redirect(url_for('broadcast_page'))

# Новый маршрут для активации/деактивации пользователя
@app.route('/toggle_user_active/<int:user_id>', methods=['POST'])
@login_required
def toggle_user_active(user_id):
    logger.debug(f"Запрос на переключение активности для user_id={user_id}")
    try:
        db = next(get_db())
        user = db.get(User, user_id)
        if user:
            user.is_active = not user.is_active
            db.commit()
            status = "активирован" if user.is_active else "деактивирован"
            flash(f'Пользователь {user.telegram_id or user.email} успешно {status}.', 'success')
            logger.info(f"Статус активности пользователя {user_id} изменен на {user.is_active}")
        else:
            flash(f'Пользователь с ID {user_id} не найден.', 'error')
            logger.warning(f"Попытка изменить статус несуществующего пользователя {user_id}")
    except Exception as e:
        logger.exception(f"Ошибка при изменении статуса активности пользователя {user_id}:")
        flash(f'Ошибка при изменении статуса пользователя: {str(e)}', 'error')
    return redirect(url_for('users'))

@app.route('/promocodes')
@login_required
def promocodes():
    db = SessionLocal()
    promocodes = db.query(PromoCode).all()
    db.close()
    return render_template('promocodes.html', promocodes=promocodes)

@app.route('/add_promocode', methods=['POST'])
@login_required
def add_promocode():
    code = request.form.get('code')
    discount_percent = int(request.form.get('discount_percent'))
    max_uses = request.form.get('max_uses')
    
    db = SessionLocal()
    try:
        promo = PromoCode(
            code=code,
            discount_percent=discount_percent,
            max_uses=int(max_uses) if max_uses else None
        )
        db.add(promo)
        db.commit()
        flash('Промокод успешно добавлен', 'success')
    except Exception as e:
        db.rollback()
        flash(f'Ошибка при добавлении промокода: {str(e)}', 'danger')
    finally:
        db.close()
    
    return redirect(url_for('promocodes'))

@app.route('/toggle_promocode/<int:promo_id>', methods=['POST'])
@login_required
def toggle_promocode(promo_id):
    db = SessionLocal()
    try:
        promo = db.query(PromoCode).filter(PromoCode.id == promo_id).first()
        if promo:
            promo.is_active = not promo.is_active
            db.commit()
            flash('Статус промокода успешно изменен', 'success')
        else:
            flash('Промокод не найден', 'danger')
    except Exception as e:
        db.rollback()
        flash(f'Ошибка при изменении статуса промокода: {str(e)}', 'danger')
    finally:
        db.close()
    
    return redirect(url_for('promocodes'))

@app.route('/referrals')
def referrals():
    if 'admin_id' not in session:
        return redirect(url_for('login'))
    referrals = Referral.query.all()
    return render_template('referrals.html', referrals=referrals)

@app.route('/create_promo_code', methods=['POST'])
def create_promo_code():
    if 'admin_id' not in session:
        return redirect(url_for('login'))
    
    code = request.form.get('code')
    discount = float(request.form.get('discount'))
    max_uses = int(request.form.get('max_uses'))
    
    promo_code = PromoCode(code=code, discount=discount, max_uses=max_uses)
    db.session.add(promo_code)
    db.session.commit()
    
    return redirect(url_for('promo_codes'))

if __name__ == '__main__':
    logger.info("Запуск Flask приложения...")
    app.run(debug=True) 