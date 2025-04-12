import asyncio
import logging
import re
import datetime
from functools import wraps
import aiohttp

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    ReplyKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardRemove,
    InlineKeyboardMarkup,
    InlineKeyboardButton
)

from config import (
    BOT_TOKEN,
    DEFAULT_REFERRAL_STATUS,
    ADMIN_TG_ACCOUNT,
    BOT_USERNAME,
    COMPANY_NAME,
    COMPANY_REGISTRATION_NUMBER,
    COMPANY_ADDRESS,
    COMPANY_BANK,
    COMPANY_ACCOUNT,
    COMPANY_SWIFT,
    COMPANY_IBAN
)
from database import init_db, get_db
from models import User, Subscription, Whitelist, PromoCode

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

storage = MemoryStorage()
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=storage)

class RegistrationStates(StatesGroup):
    waiting_for_email = State()
    waiting_for_promo = State()

main_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="👤 Мой аккаунт"), KeyboardButton(text="🔗 Ваша реферальная ссылка")],
        [KeyboardButton(text="📊 Статус реф. ссылки"), KeyboardButton(text="⏳ Моя подписка")],
        [KeyboardButton(text="🆘 Поддержка")],
    ],
    resize_keyboard=True
)

def is_valid_email(email: str) -> bool:
    return "@" in email and "." in email

def check_registered_active(func):
    @wraps(func)
    async def wrapper(message_or_cq: types.Message | types.CallbackQuery, state: FSMContext | None = None, *args, **kwargs):
        if isinstance(message_or_cq, types.Message):
            user_tg = message_or_cq.from_user
            target_message = message_or_cq
        elif isinstance(message_or_cq, types.CallbackQuery):
            user_tg = message_or_cq.from_user
            target_message = message_or_cq.message
            await message_or_cq.answer()
        else:
            logger.error(f"check_registered_active applied to unsupported type: {type(message_or_cq)}")
            return

        telegram_id = user_tg.id
        user_db: User | None = None

        with get_db() as db:
            user_db = db.query(User).filter(User.telegram_id == telegram_id).first()

            if not user_db or not user_db.email or user_db.email.startswith("temp_") or not user_db.is_active:
                logger.warning(f"Access denied for {telegram_id} by check_registered_active: Not registered, no email, or inactive.")
                await target_message.answer("Пожалуйста, пройдите регистрацию (или убедитесь, что ваш аккаунт активен), используя /start.")
                if state and (not user_db or not user_db.email or user_db.email.startswith("temp_")):
                    logger.info(f"Redirecting user {telegram_id} to email input.")
                    if not user_db:
                        await state.update_data(new_telegram_id=telegram_id, new_username=user_tg.username)
                    else:
                        await state.update_data(user_id_to_update=user_db.id)
                    await target_message.answer("Пожалуйста, введите ваш email:", reply_markup=ReplyKeyboardRemove())
                    await state.set_state(RegistrationStates.waiting_for_email)
                return

            kwargs['user'] = user_db
            return await func(message_or_cq, *args, **kwargs)

    return wrapper

def check_access(handler):
    @wraps(handler)
    async def wrapper(message_or_cq: types.Message | types.CallbackQuery, state: FSMContext | None = None, *args, **kwargs):
        if isinstance(message_or_cq, types.Message):
            user_tg = message_or_cq.from_user
            target_message = message_or_cq
        elif isinstance(message_or_cq, types.CallbackQuery):
            user_tg = message_or_cq.from_user
            target_message = message_or_cq.message
            await message_or_cq.answer()
        else:
            logger.error(f"check_access applied to unsupported type: {type(message_or_cq)}")
            return
        
        telegram_id = user_tg.id
        user_db: User | None = None
        access_granted = False
        now = datetime.datetime.now(datetime.timezone.utc)

        with get_db() as db:
            user_db = db.query(User).filter(User.telegram_id == telegram_id).first()

            if not user_db or not user_db.email or user_db.email.startswith("temp_") or not user_db.is_active:
                logger.warning(f"Access denied for {telegram_id} by check_access: Not registered, no email, or inactive.")
                await target_message.answer("Пожалуйста, пройдите регистрацию (или убедитесь, что ваш аккаунт активен), используя /start.")
                if state and (not user_db or not user_db.email or user_db.email.startswith("temp_")):
                     logger.info(f"Redirecting user {telegram_id} to email input.")
                     if not user_db:
                         await state.update_data(new_telegram_id=telegram_id, new_username=user_tg.username)
                     else:
                         await state.update_data(user_id_to_update=user_db.id)
                     await target_message.answer("Пожалуйста, введите ваш email:", reply_markup=ReplyKeyboardRemove())
                     await state.set_state(RegistrationStates.waiting_for_email)
                return

            logger.debug(f"Checking whitelist for telegram_id: {telegram_id} (type: {type(telegram_id)})")
            whitelist_entry = db.query(Whitelist).filter(Whitelist.telegram_id == telegram_id).first()
            logger.debug(f"Whitelist query result for {telegram_id}: {whitelist_entry}")
            is_whitelisted = whitelist_entry is not None
            if is_whitelisted:
                logger.info(f"Access granted for {telegram_id}: Whitelisted.")
                access_granted = True
            else:
                active_subscription = (db.query(Subscription)
                                       .filter(Subscription.user_id == user_db.id)
                                       .filter(Subscription.end_date > now)
                                       .order_by(Subscription.end_date.desc())
                                       .first())
                if active_subscription:
                    logger.info(f"Access granted for {telegram_id}: Active subscription until {active_subscription.end_date}.")
                    access_granted = True

            if access_granted:
                kwargs['user'] = user_db
                return await handler(message_or_cq, *args, **kwargs)
            else:
                logger.warning(f"Access denied for {telegram_id}: No active subscription or whitelist entry.")
                await target_message.answer("❌ У вас нет активного доступа к курсу.")
                return

    return wrapper

@dp.message(CommandStart())
async def handle_start(message: types.Message, state: FSMContext):
    telegram_id = message.from_user.id
    username = message.from_user.username
    first_name = message.from_user.first_name
    logger.info(f"User {telegram_id} ({username}) started the bot.")

    start_param = message.text.split()[1] if len(message.text.split()) > 1 else None
    
    if start_param:
        if start_param == "offer":
            await message.answer(
                "Публичная оферта доступна по ссылке:\n"
                "https://docs.google.com/document/d/1tgPqQTkjQDgftj-a0vNOgs53mi7-sctjv4WJ2BF9DTA/edit",
                disable_web_page_preview=True
            )
            return
        elif start_param == "privacy":
            await message.answer(
                "Политика конфиденциальности доступна по ссылке:\n"
                "https://docs.google.com/document/d/10s0vc9sBXMeC8a-_VGSXzCPi0Z5k4AMy/edit",
                disable_web_page_preview=True
            )
            return

    with get_db() as db:
        user = db.query(User).filter(User.telegram_id == telegram_id).first()

        if user:
            logger.info(f"User {telegram_id} already exists.")
            if not user.is_active:
                await message.answer("Ваш аккаунт был деактивирован.")
                return
            if not user.email or user.email.startswith("temp_"):
                logger.info(f"User {telegram_id} needs email. Setting state.")
                await state.update_data(user_id_to_update=user.id)
                await message.answer(
                    f"Здравствуйте, {first_name}! Похоже, ваш email не был указан. "
                    "Пожалуйста, введите ваш email для продолжения.",
                    reply_markup=ReplyKeyboardRemove()
                )
                await state.set_state(RegistrationStates.waiting_for_email)
            else:
                await message.answer(f"С возвращением, {first_name}!", reply_markup=main_keyboard)
        else:
            logger.info(f"New user: {telegram_id} ({username}). Requesting email.")
            await state.update_data(
                new_telegram_id=telegram_id,
                new_username=username
            )
            await message.answer(
                f"Добро пожаловать, {first_name}! "
                "Для начала работы, пожалуйста, укажите вашу почту.",
                reply_markup=ReplyKeyboardRemove()
            )
            await state.set_state(RegistrationStates.waiting_for_email)

@dp.message(RegistrationStates.waiting_for_email, F.text)
async def handle_email(message: types.Message, state: FSMContext):
    email = message.text.strip()
    logger.info(f"Received email attempt: {email} from user {message.from_user.id}")

    if not is_valid_email(email):
        await message.answer("Не похоже на email. Пожалуйста, введите корректный адрес электронной почты.")
        return

    with get_db() as db:
        existing_user_by_email = db.query(User).filter(User.email == email).first()
        user_data = await state.get_data()
        user_id_to_update = user_data.get('user_id_to_update')

        if existing_user_by_email and (not user_id_to_update or existing_user_by_email.id != user_id_to_update):
                await message.answer("Этот email уже используется другим пользователем. Пожалуйста, введите другой email.")
                return

        if user_id_to_update:
            user_to_update = db.query(User).filter(User.id == user_id_to_update).first()
            if user_to_update:
                user_to_update.email = email
                db.commit()
                logger.info(f"Email updated for user {user_to_update.telegram_id}.")
                await message.answer("Спасибо! Ваш email обновлен.", reply_markup=main_keyboard)
                await state.clear()
            else:
                logger.error(f"Could not find user with id {user_id_to_update} to update email.")
                await message.answer("Произошла ошибка при обновлении email. Попробуйте /start снова.")
                await state.clear()
        else:
            new_telegram_id = user_data.get('new_telegram_id')
            new_username = user_data.get('new_username')

            if not new_telegram_id:
                 logger.error(f"Missing new_telegram_id in state data for user {message.from_user.id}")
                 await message.answer("Произошла ошибка регистрации. Попробуйте /start снова.")
                 await state.clear()
                 return

            new_user = User(
                telegram_id=new_telegram_id,
                telegram_username=new_username,
                email=email
            )
            db.add(new_user)
            db.commit()
            logger.info(f"New user {new_telegram_id} registered with email {email}.")
            await message.answer("Спасибо! Вы успешно зарегистрированы.", reply_markup=main_keyboard)
            await state.clear()

@dp.message(RegistrationStates.waiting_for_email)
async def handle_email_incorrect_input(message: types.Message):
    await message.answer("Пожалуйста, введите ваш email текстом.")

@dp.message(F.text == "👤 Мой аккаунт")
@check_registered_active
async def handle_my_account(message: types.Message, *, user: User):
    logger.info(f"User {user.telegram_id} requested account info.")
    
    now = datetime.datetime.now(datetime.timezone.utc)
    access_status_text = "❌ Доступ к курсу отсутствует"
    with get_db() as db:
        is_whitelisted = db.query(Whitelist).filter(Whitelist.telegram_id == user.telegram_id).first() is not None
        if is_whitelisted:
            access_status_text = "✅ Доступ к курсу есть (белый список)"
        else:
            active_subscription = (db.query(Subscription)
                                   .filter(Subscription.user_id == user.id)
                                   .filter(Subscription.end_date > now)
                                   .order_by(Subscription.end_date.desc())
                                   .first())
            if active_subscription:
                end_date_str = active_subscription.end_date.strftime("%d.%m.%Y %H:%M")
                access_status_text = f"✅ Доступ к курсу есть (до {end_date_str} UTC)"

    account_info = (
        f"👤 Ваш аккаунт:\n"
        f"\n🆔 Telegram ID: `{user.telegram_id}`"
        f"\n📧 Email: `{user.email}`"
        f"\n\n{access_status_text}"
    )
    await message.answer(account_info, parse_mode="Markdown")

@dp.message(F.text == "🔗 Ваша реферальная ссылка")
@check_access
async def handle_referral_link(message: types.Message, *, user: User):
    logger.info(f"User {user.telegram_id} requested referral link.")
    
    start_param = user.referral_link_override if user.referral_link_override else user.telegram_id
    
    ref_link = f"https://t.me/{BOT_USERNAME}?start={start_param}"
    
    await message.answer(f"🔗 Ваша реферальная ссылка:\n`{ref_link}`", parse_mode="Markdown")

@dp.message(F.text == "📊 Статус реф. ссылки")
@check_access
async def handle_referral_status(message: types.Message, *, user: User):
    logger.info(f"User {user.telegram_id} requested referral status.")
    status_flag = user.referral_status_override
    if status_flag is None:
        status_flag = DEFAULT_REFERRAL_STATUS

    status_icon = "✅" if status_flag else "❌"
    status_text = "Активна" if status_flag else "Не активна"

    await message.answer(f"📊 Статус вашей реферальной ссылки: {status_icon} ({status_text})")

@dp.message(F.text == "⏳ Моя подписка")
@check_registered_active
async def handle_my_subscription(message: types.Message, *, user: User):
    logger.info(f"User {user.telegram_id} requested subscription status.")
    now = datetime.datetime.now(datetime.timezone.utc)
    
    with get_db() as db:
        active_subscription = (db.query(Subscription)
                               .filter(Subscription.user_id == user.id)
                               .filter(Subscription.end_date > now)
                               .order_by(Subscription.end_date.desc())
                               .first())
        is_whitelisted = db.query(Whitelist).filter(Whitelist.telegram_id == user.telegram_id).first() is not None
        
        if active_subscription:
            end_date_str = active_subscription.end_date.strftime("%d.%m.%Y %H:%M UTC")
            keyboard = InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(text="Продлить подписку", callback_data="buy_access"),
                        InlineKeyboardButton(text="Ввести промокод", callback_data="enter_promo")
                    ],
                    [InlineKeyboardButton(text="Отключить автоплатеж", callback_data="disable_auto_renewal")]
                ]
            )
            
            await message.answer(
                f"✅ Ваш доступ к обучающему курсу активен до: {end_date_str}\n\n"
                f"{'🔄 Автоплатеж включен' if active_subscription.auto_renewal else '❌ Автоплатеж отключен'}\n\n"
                "Для продления подписки нажмите на кнопку ниже:",
                reply_markup=keyboard
            )
        elif is_whitelisted:
            await message.answer(
                "✅ У вас постоянный доступ к курсу (белый список)."
            )
        else:
            keyboard = InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(text="Оплатить 1500₽", callback_data="process_payment"),
                        InlineKeyboardButton(text="Ввести промокод", callback_data="enter_promo")
                    ],
                    [InlineKeyboardButton(text="Отключить автоплатеж", callback_data="disable_auto_renewal")]
                ]
            )
            await message.answer(
                "📚 Продукт: Приватный чат \"СИСТЕМНИК УБТ ПРИВАТ\"\n\n"
                "🗓 Тарифный план: СИСТЕМНИК УБТ (Карта РФ)\n\n"
                "— Тип платежа: Автоплатеж с интервалом 30d 0h 0m\n"
                "— Сумма к оплате: 1500 RUB\n\n"
                "После оплаты будет предоставлен доступ:\n\n"
                "— Группа «СИСТЕМНИК УБТ ПРИВАТ»\n\n"
                "Оплачивая подписку вы принимаете условия "
                "[Публичной оферты](https://docs.google.com/document/d/1tgPqQTkjQDgftj-a0vNOgs53mi7-sctjv4WJ2BF9DTA/edit) и "
                "[Политики конфиденциальности](https://docs.google.com/document/d/10s0vc9sBXMeC8a-_VGSXzCPi0Z5k4AMy/edit)",
                reply_markup=keyboard,
                parse_mode="Markdown",
                disable_web_page_preview=True
            )

@dp.callback_query(F.data == "enter_promo")
async def handle_enter_promo(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("Пожалуйста, введите промокод:")
    await state.set_state(RegistrationStates.waiting_for_promo)
    await callback.answer()

@dp.message(RegistrationStates.waiting_for_promo)
async def handle_promo_code(message: types.Message, state: FSMContext):
    promo_code = message.text.strip().upper()
    with get_db() as db:
        promo = db.query(PromoCode).filter(
            PromoCode.code == promo_code,
            PromoCode.is_active == True
        ).first()
        
        if not promo:
            keyboard = InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="Купить доступ", callback_data="buy_access")]
                ]
            )
            await message.answer(
                "❌ Неверный или неактивный промокод. Попробуйте еще раз или нажмите 'Купить доступ'.",
                reply_markup=keyboard
            )
            return
            
        if promo.max_uses is not None and promo.used_count >= promo.max_uses:
            keyboard = InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="Купить доступ", callback_data="buy_access")]
                ]
            )
            await message.answer(
                "❌ Промокод уже использован максимальное количество раз.",
                reply_markup=keyboard
            )
            return
            
        original_price = 1500
        discount = original_price * (promo.discount_percent / 100)
        final_price = original_price - discount
        
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text=f"Купить доступ за {int(final_price)}₽",
                        callback_data=f"buy_access_with_promo_{promo.id}"
                    )
                ]
            ]
        )
        
        await message.answer(
            f"✅ Промокод применен!\n\n"
            f"Стоимость: {int(final_price)}₽\n"
            f"<s>1500₽</s>",
            reply_markup=keyboard,
            parse_mode="HTML"
        )
        await state.clear()

@dp.callback_query(F.data.startswith("buy_access_with_promo_"))
async def handle_buy_with_promo(callback: types.CallbackQuery):
    promo_id = int(callback.data.split("_")[-1])
    await callback.answer("Функция оплаты с промокодом будет реализована позже")

@dp.callback_query(F.data == "buy_access")
async def handle_buy_access(callback: types.CallbackQuery):
    text = (
        "📚 Продукт: Приватный чат \"СИСТЕМНИК УБТ ПРИВАТ\"\n\n"
        "🗓 Тарифный план: СИСТЕМНИК УБТ (Карта РФ)\n\n"
        "— Тип платежа: Автоплатеж с интервалом 30d 0h 0m\n"
        "— Сумма к оплате: 1500 RUB\n\n"
        "После оплаты будет предоставлен доступ:\n\n"
        "— Группа «СИСТЕМНИК УБТ ПРИВАТ»\n\n"
        "Оплачивая подписку вы принимаете условия "
        "[Публичной оферты](https://docs.google.com/document/d/1tgPqQTkjQDgftj-a0vNOgs53mi7-sctjv4WJ2BF9DTA/edit) и "
        "[Политики конфиденциальности](https://docs.google.com/document/d/10s0vc9sBXMeC8a-_VGSXzCPi0Z5k4AMy/edit)"
    )
    
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Оплатить 1500₽", callback_data="process_payment")],
            [InlineKeyboardButton(text="Ввести промокод", callback_data="enter_promo")]
        ]
    )
    
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="Markdown", disable_web_page_preview=True)
    await callback.answer()

@dp.callback_query(F.data == "show_offer")
async def handle_show_offer(callback: types.CallbackQuery):
    offer_text = (
        "📜 *ПУБЛИЧНАЯ ОФЕРТА*\n\n"
        "1. ОБЩИЕ ПОЛОЖЕНИЯ\n\n"
        "1.1. Настоящая оферта является предложением заключить договор на оказание информационных услуг.\n"
        "1.2. Акцептом оферты является оплата услуг.\n\n"
        "2. УСЛОВИЯ ПОДПИСКИ\n\n"
        "2.1. Подписка предоставляется на 30 дней.\n"
        "2.2. Автопродление происходит автоматически.\n"
        "2.3. Отмена подписки возможна в любой момент.\n\n"
        "[Полный текст оферты](https://docs.google.com/document/d/1tgPqQTkjQDgftj-a0vNOgs53mi7-sctjv4WJ2BF9DTA/edit)"
    )
    
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="« Назад", callback_data="buy_access")]]
    )
    
    await callback.message.edit_text(offer_text, reply_markup=keyboard, parse_mode="Markdown", disable_web_page_preview=True)
    await callback.answer()

@dp.callback_query(F.data == "show_privacy")
async def handle_show_privacy(callback: types.CallbackQuery):
    privacy_text = (
        "🔒 *ПОЛИТИКА КОНФИДЕНЦИАЛЬНОСТИ*\n\n"
        "1. ОБРАБОТКА ДАННЫХ\n\n"
        "1.1. Мы обрабатываем только те данные, которые необходимы для оказания услуг.\n"
        "1.2. Ваши персональные данные не передаются третьим лицам.\n\n"
        "2. ХРАНЕНИЕ ИНФОРМАЦИИ\n\n"
        "2.1. Данные хранятся на защищенных серверах.\n"
        "2.2. Срок хранения определяется законодательством.\n\n"
        "[Полный текст политики](https://docs.google.com/document/d/10s0vc9sBXMeC8a-_VGSXzCPi0Z5k4AMy/edit)"
    )
    
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="« Назад", callback_data="buy_access")]]
    )
    
    await callback.message.edit_text(privacy_text, reply_markup=keyboard, parse_mode="Markdown", disable_web_page_preview=True)
    await callback.answer()

@dp.callback_query(F.data == "show_requisites")
async def handle_show_requisites(callback: types.CallbackQuery):
    requisites_text = (
        "📋 *РЕКВИЗИТЫ КОМПАНИИ*\n\n"
        f"Название компании: {COMPANY_NAME}\n"
        f"Регистрационный номер: {COMPANY_REGISTRATION_NUMBER}\n"
        f"Адрес: {COMPANY_ADDRESS}\n\n"
        "Банковские реквизиты:\n"
        f"Банк: {COMPANY_BANK}\n"
        f"Счет: {COMPANY_ACCOUNT}\n"
        f"SWIFT: {COMPANY_SWIFT}\n"
        f"IBAN: {COMPANY_IBAN}"
    )
    
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="« Назад", callback_data="buy_access")]]
    )
    
    await callback.message.edit_text(requisites_text, reply_markup=keyboard, parse_mode="Markdown")
    await callback.answer()

@dp.callback_query(F.data == "process_payment")
async def handle_process_payment(callback: types.CallbackQuery):
    await callback.message.answer(
        "📚 Продукт: Приватный чат \"СИСТЕМНИК УБТ ПРИВАТ\"\n\n"
        "🗓 Тарифный план: СИСТЕМНИК УБТ (Карта РФ)\n\n"
        "— Тип платежа: Автоплатеж с интервалом 30d 0h 0m\n"
        "— Сумма к оплате: 1500 RUB\n\n"
        "После оплаты будет предоставлен доступ:\n\n"
        "— Группа «СИСТЕМНИК УБТ ПРИВАТ»\n\n"
        "Оплачивая подписку вы принимаете условия "
        "[Публичной оферты](https://docs.google.com/document/d/1tgPqQTkjQDgftj-a0vNOgs53mi7-sctjv4WJ2BF9DTA/edit) и "
        "[Политики конфиденциальности](https://docs.google.com/document/d/10s0vc9sBXMeC8a-_VGSXzCPi0Z5k4AMy/edit)",
        parse_mode="Markdown",
        disable_web_page_preview=True
    )
    await callback.answer()

@dp.message(F.text == "🆘 Поддержка")
async def handle_support(message: types.Message):
    logger.info(f"User {message.from_user.id} requested support info.")
    support_contact = f"@{ADMIN_TG_ACCOUNT}"
    text = (
        "Если не получается оплатить, читаем:\n\n"
        "⚠️ Бот иногда не справляется с большими наплывами участников. "
        "Пробуйте раз в несколько минут, или через час, в любом случае рано или поздно всё прогрузится!\n\n"
        f"📨 Только по долгим проблемам с оплатой — {support_contact}"
    )
    await message.answer(text)

@dp.message(F.text)
@check_access
async def handle_unknown_text(message: types.Message, *, user: User):
    logger.warning(f"User {user.telegram_id} sent unknown text: {message.text}")
    await message.reply("Пожалуйста, используйте кнопки на клавиатуре для взаимодействия с ботом.", reply_markup=main_keyboard)

@dp.callback_query(F.data == "disable_auto_renewal")
@check_registered_active
async def handle_disable_auto_renewal(callback: types.CallbackQuery, *, user: User):
    logger.info(f"User {user.telegram_id} requested to disable auto renewal.")
    now = datetime.datetime.now(datetime.timezone.utc)
    
    with get_db() as db:
        active_subscription = (db.query(Subscription)
                               .filter(Subscription.user_id == user.id)
                               .filter(Subscription.end_date > now)
                               .order_by(Subscription.end_date.desc())
                               .first())
        
        if active_subscription:
            active_subscription.auto_renewal = False
            db.commit()
        
        await callback.message.edit_text(
            "Автоплатежи отключены! ✅\n"
            "В следующем месяце не будет списания.",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="« Назад к подписке", callback_data="show_subscription")]
                ]
            )
        )

@dp.callback_query(F.data == "show_subscription")
@check_registered_active
async def handle_show_subscription(callback: types.CallbackQuery, *, user: User):
    now = datetime.datetime.now(datetime.timezone.utc)
    
    with get_db() as db:
        active_subscription = (db.query(Subscription)
                               .filter(Subscription.user_id == user.id)
                               .filter(Subscription.end_date > now)
                               .order_by(Subscription.end_date.desc())
                               .first())
        is_whitelisted = db.query(Whitelist).filter(Whitelist.telegram_id == user.telegram_id).first() is not None
        
        if active_subscription:
            end_date_str = active_subscription.end_date.strftime("%d.%m.%Y %H:%M UTC")
            keyboard = InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(text="Продлить подписку", callback_data="buy_access"),
                        InlineKeyboardButton(text="Ввести промокод", callback_data="enter_promo")
                    ],
                    [InlineKeyboardButton(text="Отключить автоплатеж", callback_data="disable_auto_renewal")]
                ]
            )
            
            await callback.message.edit_text(
                f"✅ Ваш доступ к обучающему курсу активен до: {end_date_str}\n\n"
                f"{'🔄 Автоплатеж включен' if active_subscription.auto_renewal else '❌ Автоплатеж отключен'}\n\n"
                "Для продления подписки нажмите на кнопку ниже:",
                reply_markup=keyboard
            )
        elif is_whitelisted:
            await callback.message.edit_text(
                "✅ У вас постоянный доступ к курсу (белый список)."
            )
        else:
            keyboard = InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(text="Оплатить 1500₽", callback_data="process_payment"),
                        InlineKeyboardButton(text="Ввести промокод", callback_data="enter_promo")
                    ],
                    [InlineKeyboardButton(text="Отключить автоплатеж", callback_data="disable_auto_renewal")]
                ]
            )
            await callback.message.edit_text(
                "📚 Продукт: Приватный чат \"СИСТЕМНИК УБТ ПРИВАТ\"\n\n"
                "🗓 Тарифный план: СИСТЕМНИК УБТ (Карта РФ)\n\n"
                "— Тип платежа: Автоплатеж с интервалом 30d 0h 0m\n"
                "— Сумма к оплате: 1500 RUB\n\n"
                "После оплаты будет предоставлен доступ:\n\n"
                "— Группа «СИСТЕМНИК УБТ ПРИВАТ»\n\n"
                "Оплачивая подписку вы принимаете условия "
                "[Публичной оферты](https://docs.google.com/document/d/1tgPqQTkjQDgftj-a0vNOgs53mi7-sctjv4WJ2BF9DTA/edit) и "
                "[Политики конфиденциальности](https://docs.google.com/document/d/10s0vc9sBXMeC8a-_VGSXzCPi0Z5k4AMy/edit)",
                reply_markup=keyboard,
                parse_mode="Markdown",
                disable_web_page_preview=True
            )
    await callback.answer()

async def main():
    logger.info("Initializing database...")
    init_db()
    logger.info("Database initialized.")

    try:
        await bot.delete_webhook(drop_pending_updates=True)
        logger.info("Webhook deleted successfully")
    except Exception as e:
        logger.error(f"Failed to delete webhook: {e}")

    logger.info("Starting bot polling...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot stopped.") 