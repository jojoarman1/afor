import asyncio
import logging
import random
import re
import string
from datetime import datetime, timedelta
import aiofiles.os
import pytz
from aiogram import Bot, Dispatcher, types
from aiogram.types import InputFile
from aiogram.types import ParseMode, InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils import executor
from aiogram.utils.exceptions import TelegramAPIError

TOKEN = '6426877553:AAH21xz52t9CWn0uC4BMjnAYXmTeS-36Wtk'
CHANNEL_ID = '-1002231203534'
ADMIN_CHAT_ID = '735291377'

bot = Bot(token=TOKEN)
dp = Dispatcher(bot)

# Словарь для хранения афоризмов пользователей и id сообщений
user_aphorisms = {}
user_order_selections = {}  # Для хранения выбранного порядка слов
user_attempts = {}
user_message_ids = {}  # Для хранения id сообщений каждого пользователя
user_sent_aphorism = {}  # Новый словарь для отслеживания отправленных афоризмов
active_order_post = False  # Флаг для отслеживания активного поста с выбором порядка слов
first_message_id = None  # Переменная для хранения id первого сообщения
user_order_finalized = {}  # Новый словарь для отслеживания завершения выбора порядка слов
order_post_time = None
correct_aphorisms = {}
incorrect_aphorisms = {}
user_buttons_order = {}
user_failed_attempts = {}  # Новый словарь для хранения информации о неверном выборе порядка слов
shuffled_order = {}
bot_message_ids = {}
message_status = {}

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

user_state = {}  # Хранение состояния пользователя: 'waiting_for_aphorism', 'aphorism_received', и т.д.


@dp.message_handler(commands=['start'])
async def start_handler(message: types.Message):
    user_id = message.from_user.id
    args = message.get_args()
    logger.info(f'Команда /start от пользователя {user_id}, args: {args}')

    # Удаление всех сообщений, отправленных ботом ранее для этого пользователя
    if user_id in user_message_ids:
        try:
            await bot.delete_message(chat_id=message.chat.id, message_id=user_message_ids[user_id])
            logger.info(f'Удалено сообщение бота с ID {user_message_ids[user_id]} для пользователя {user_id}.')
        except Exception as e:
            logger.error(
                f'Ошибка при удалении сообщения бота с ID {user_message_ids[user_id]} для пользователя {user_id}: {e}')
        del user_message_ids[user_id]  # Очистка списка сообщений, отправленных ботом

    # Получаем текущую дату
    moscow_tz = pytz.timezone('Europe/Moscow')

    # Получаем текущее время в московском времени
    now = datetime.now(moscow_tz)
    today_date = now.strftime('%d.%m.%Y')

    # Создаем кнопку "Вернуться в канал"
    channel_link = f'https://t.me/c/{CHANNEL_ID[4:]}'
    return_to_channel_button = InlineKeyboardButton('Назад в сообщество', url=channel_link)
    inline_keyboard = InlineKeyboardMarkup().add(return_to_channel_button)

    if user_failed_attempts.get(user_id, False):
        sent_message = await message.answer(
            "Ваш ответ уже принят. Продолжение будет завтра.",
            parse_mode='Markdown',
            reply_markup=inline_keyboard
        )
        user_message_ids[user_id] = sent_message.message_id
        return

    if args.startswith('order'):
        target_user_id = int(args.split('_')[1])

        shuffled_words = shuffled_order.get(target_user_id, [])

        if user_order_finalized.get(user_id, False):
            sent_message = await message.answer(
                "Ваш ответ уже принят. Продолжение будет завтра.",
                parse_mode='Markdown',
                reply_markup=inline_keyboard
            )
            user_message_ids[user_id] = sent_message.message_id
            return

        if user_id in user_attempts:
            sent_message = await message.answer(
                f"*ДУХОВНАЯ ЭРУДИЦИЯ {today_date}.*\n\n"
                "Вы уже сделали выбор.",
                parse_mode='Markdown',
                reply_markup=inline_keyboard
            )
            user_message_ids[user_id] = sent_message.message_id
            return

        buttons = [InlineKeyboardButton(word.upper(), callback_data=f'word_{target_user_id}_{i}') for i, word in
                   enumerate(shuffled_words)]

        user_buttons_order[user_id] = buttons

        keyboard = InlineKeyboardMarkup(row_width=3)
        keyboard.add(*buttons)
        keyboard.add(InlineKeyboardButton('Очистить', callback_data=f'clear_{target_user_id}'))
        keyboard.add(InlineKeyboardButton('Готово', callback_data=f'finalize_{target_user_id}'))

        # Проверяем, есть ли выбранные слова
        selected_words = user_order_selections.get(user_id, [])
        if selected_words:
            selected_words_text = ' '.join(selected_words)
            message_text = (
                f'*ДУХОВНАЯ ЭРУДИЦИЯ {today_date}.*\n\n'
                f'Выбранные слова: _{selected_words_text}_\n\n'
                f'Пожалуйста, выберите правильный порядок слов.'
            )
        else:
            message_text = (
                f'*ДУХОВНАЯ ЭРУДИЦИЯ {today_date}.*\n\n'
                f'Пожалуйста, выберите правильный порядок слов.'
            )

        sent_message = await message.answer(message_text, reply_markup=keyboard, parse_mode='Markdown')
        user_message_ids[user_id] = sent_message.message_id
        user_order_selections[user_id] = []
        logger.info(f'Пользователь {user_id} начал выбор порядка слов. ID сообщения: {sent_message.message_id}')

    elif args.startswith('comment'):
        sent_message = await message.answer(
            f"*ДУХОВНАЯ ЭРУДИЦИЯ {today_date}.*\n\n"
            "Пожалуйста, передайте послание в виде одного предложения.",
            parse_mode='Markdown',
            reply_markup=inline_keyboard
        )
        user_message_ids[user_id] = sent_message.message_id
        logger.info(f'Пользователь {user_id} начал ввод афоризма.')

    else:
        if test_completed:
            sent_message = await message.answer(
                "Тест завершен. Спасибо за участие!",
                parse_mode='Markdown',
                reply_markup=inline_keyboard
            )
            user_message_ids[user_id] = sent_message.message_id
            logger.info(f'Пользователь {user_id} получил уведомление о завершении теста.')
        else:
            sent_message = await message.answer(
                "Привет! Пожалуйста, напишите ваш афоризм.",
                parse_mode='Markdown',
                reply_markup=inline_keyboard
            )
            user_message_ids[user_id] = sent_message.message_id
            logger.info(f'Пользователь {user_id} начал ввод афоризма.')


async def send_post():
    global first_message_id
    bot_username = (await bot.get_me()).username

    comment_link = f'https://t.me/{bot_username}?start=comment'

    # Определяем московский часовой пояс
    moscow_tz = pytz.timezone('Europe/Moscow')

    # Получаем текущее время в московском времени
    now = datetime.now(moscow_tz)
    today_date = now.strftime('%d.%m.%Y')
    photo_path = '1.png'  # Замените на реальный путь к вашему изображению

    logger.info("Проверка состояния aphorism_received.")
    global aphorism_received
    if aphorism_received:
        logger.info("Прием афоризмов активен. Пост не отправляется.")
        return

    try:
        logger.info("Попытка отправки поста.")
        # Отправка нового поста с картинкой
        with open(photo_path, 'rb') as photo_file:
            sent_message = await bot.send_photo(
                chat_id=CHANNEL_ID,
                photo=photo_file,
                caption=f'<b>ДУХОВНАЯ ЭРУДИЦИЯ {today_date}.</b>\n\nПожалуйста, получите по духовному каналу '
                        f'послание и передайте его одним предложением ❤️',
                parse_mode='HTML',
                reply_markup=InlineKeyboardMarkup().add(
                    InlineKeyboardButton('Передать послание', url=comment_link)
                )
            )
        first_message_id = sent_message.message_id  # Обновляем ID сообщения
        logger.info(
            f'Отправлено новое сообщение с картинкой в канал с ID {CHANNEL_ID}. ID сообщения: {sent_message.message_id}')
    except Exception as e:
        logger.error(f'Ошибка при отправке сообщения: {e}')


@dp.callback_query_handler(lambda c: c.data == 'comment')
async def comment_handler(callback_query: types.CallbackQuery):
    try:
        # Переход по ссылке вызывает команду /start с параметром 'comment'
        await bot.send_message(callback_query.from_user.id, 'Пожалуйста, введите ваш афоризм.')
        logger.info(f'Отправлено сообщение пользователю {callback_query.from_user.id} с просьбой ввести афоризм.')
    except Exception as e:
        logger.error(f'Ошибка при отправке сообщения пользователю {callback_query.from_user.id}: {e}')
    await callback_query.answer()


user_info = {}

aphorism_received = False  # Глобальная переменная для отслеживания получения афоризма


@dp.message_handler(lambda message: message.chat.type == 'private')
async def receive_aphorism(message: types.Message):
    global aphorism_received

    user_id = message.from_user.id

    logger.info(f"Получено сообщение от пользователя {user_id}: {message.text}")

    # Если прием посланий завершен, отправляем сообщение об этом
    if aphorism_received:
        channel_link = f'https://t.me/c/{CHANNEL_ID[4:]}'
        return_to_channel_button = InlineKeyboardButton('Назад в сообщество', url=channel_link)
        inline_keyboard = InlineKeyboardMarkup().add(return_to_channel_button)

        await message.answer(
            'Прием посланий завершен. Вы можете передать свое послание завтра.',
            reply_markup=inline_keyboard
        )
        logger.info(f"Сообщение от пользователя {user_id} отклонено, так как прием посланий уже завершен.")
        return

    # Обработка афоризма, если прием еще не завершен
    cleaned_aphorism = message.text
    logger.info(f"Афоризм пользователя {user_id} после очистки: {cleaned_aphorism}")

    user_aphorisms[user_id] = cleaned_aphorism
    user_sent_aphorism[user_id] = True

    # Устанавливаем флаг, что афоризм уже получен
    aphorism_received = True

    user_info[user_id] = {
        'username': message.from_user.username,
        'first_name': message.from_user.first_name,
        'last_name': message.from_user.last_name
    }

    channel_link = f'https://t.me/c/{CHANNEL_ID[4:]}'
    return_to_channel_button = InlineKeyboardButton('Назад в сообщество', url=channel_link)
    inline_keyboard = InlineKeyboardMarkup().add(return_to_channel_button)

    # Получаем текущее время в московском времени
    moscow_tz = pytz.timezone('Europe/Moscow')
    now = datetime.now(moscow_tz)

    try:
        sent_message = await message.answer(
            f'*ДУХОВНАЯ ЭРУДИЦИЯ {now.strftime("%d.%m.%Y")}.*\n\n'  # Используем московское время для даты
            f'Послание: {cleaned_aphorism}\n\n'
            f'Благодарим! Ваше послание принято.',
            reply_markup=inline_keyboard,
            parse_mode='Markdown'
        )
        logger.info(f"Афоризм от пользователя {user_id} отправлен успешно.")
    except Exception as e:
        logger.error(f'Ошибка при отправке подтверждения пользователю {user_id}: {e}')
        return

    if user_id in user_message_ids:
        try:
            await bot.delete_message(chat_id=message.chat.id, message_id=user_message_ids[user_id])
            logger.info(f"Старое сообщение пользователя {user_id} удалено.")
        except Exception as e:
            logger.error(f'Ошибка при удалении старого сообщения пользователя {user_id}: {e}')
        del user_message_ids[user_id]

    user_message_ids[user_id] = sent_message.message_id

    admin_keyboard = InlineKeyboardMarkup().add(
        InlineKeyboardButton('Отклонить', callback_data=f'reject_{user_id}'),
        InlineKeyboardButton('Опубликовать', callback_data=f'publish_{user_id}')
    )

    user_data = user_info.get(user_id, {})
    username = user_data.get('username')
    first_name = user_data.get('first_name')
    last_name = user_data.get('last_name')

    if username:
        user_name = f'@{username}'
    else:
        if first_name and last_name:
            user_name = f'@ {first_name} {last_name}'
        elif first_name:
            user_name = f'@ {first_name}'
        else:
            user_name = 'Неизвестный автор'

    try:
        await bot.send_message(
            chat_id=ADMIN_CHAT_ID,
            text=f'{user_name}: {cleaned_aphorism}',
            reply_markup=admin_keyboard
        )
        logger.info(f"Афоризм от пользователя {user_id} отправлен админу.")
    except Exception as e:
        logger.error(f'Ошибка при отправке афоризма пользователя {user_id} админу: {e}')

    try:
        await bot.delete_message(chat_id=CHANNEL_ID, message_id=first_message_id)
        logger.info(f'Удалено сообщение с ID {first_message_id} в канале {CHANNEL_ID}.')
    except Exception as e:
        logger.error(f'Ошибка при удалении сообщения с ID {first_message_id} в канале {CHANNEL_ID}: {e}')


async def get_user_info(user_id: int) -> dict:
    try:
        user = await bot.get_chat_member(chat_id=user_id, user_id=user_id)
        return {
            'first_name': user.user.first_name,
            'last_name': user.user.last_name,
            'username': user.user.username
        }
    except Exception as e:
        logger.error(f"Ошибка при получении информации о пользователе {user_id}: {e}")
        return {}


@dp.callback_query_handler(lambda c: c.data.startswith(('reject_', 'publish_')))
async def admin_actions_handler(callback_query: types.CallbackQuery):
    await callback_query.answer()  # Сразу отвечаем на колбэк, чтобы избежать таймаута
    action, user_id = callback_query.data.split('_')
    user_id = int(user_id)

    # Изначально статус пустой
    status_message = ""

    # Проверяем, есть ли уже установленный статус в сообщении
    existing_status_match = re.search(r"Статус: (\S+)", callback_query.message.text)
    if existing_status_match:
        status_message = existing_status_match.group(1)

    try:
        if action == 'reject':
            if not status_message or status_message != "Отклонено":
                await reject_handler(callback_query)
                status_message = "Отклонено"

        elif action == 'publish':
            if not status_message or status_message != "Опубликовано":
                await publish_handler(callback_query)
                status_message = "Опубликовано"


    except Exception as e:
        logger.error(f"Ошибка при обработке афоризма: {e}")

    try:
        channel_link = f'https://t.me/c/{CHANNEL_ID[4:]}'
        return_to_channel_button = InlineKeyboardButton('Назад в сообщество', url=channel_link)
        inline_keyboard = InlineKeyboardMarkup().add(return_to_channel_button)

        current_text = callback_query.message.text

        # Удаляем все упоминания после символа @, но оставляем сам @
        cleaned_text = re.sub(r'@\s*\S+', '', current_text).strip()

        # Получаем информацию о пользователе, чье сообщение обрабатывается
        user_info = await get_user_info(user_id)
        user_first_name = user_info.get('first_name', "")
        user_last_name = user_info.get('last_name', "")
        user_username = user_info.get('username', "")

        user_name = f"@{user_username}" if user_username else f"@ {user_first_name} {user_last_name}".strip() or "Неизвестный автор"

        updated_text = (f"Автор: {user_name}\n\n"
                        f"Послание: {cleaned_text}\n\n"
                        f"Статус: {status_message}")

        await bot.edit_message_text(
            chat_id=callback_query.message.chat.id,
            message_id=callback_query.message.message_id,
            text=updated_text,
            reply_markup=inline_keyboard
        )
    except Exception as e:
        logger.error(f"Ошибка при обновлении сообщения: {e}")


messages_to_delete = {}


@dp.callback_query_handler(lambda c: c.data.startswith('reject_'))
async def reject_handler(callback_query: types.CallbackQuery):
    user_id = int(callback_query.data.split('_')[1])

    # Сбрасываем состояние приема афоризмов
    global aphorism_received
    aphorism_received = False

    # Удаляем сообщение с афоризмом
    if user_id in user_message_ids:
        try:
            await bot.delete_message(chat_id=callback_query.message.chat.id, message_id=user_message_ids[user_id])
            logger.info(f"Удалено сообщение с афоризмом пользователя {user_id}.")
        except Exception as e:
            logger.error(f'Ошибка при удалении сообщения с афоризмом пользователя {user_id}: {e}')
        del user_message_ids[user_id]

    # Удаляем сообщение от бота в канале с афоризмом
    try:
        await bot.delete_message(chat_id=CHANNEL_ID, message_id=first_message_id)
        logger.info(f'Удалено сообщение с ID {first_message_id} в канале {CHANNEL_ID}.')
    except Exception as e:
        logger.error(f'Ошибка при удалении сообщения с ID {first_message_id} в канале {CHANNEL_ID}: {e}')

    # Отправляем новый пост
    await send_post()

    await callback_query.answer()


def shuffle_aphorism(aphorism):
    words = aphorism.split()
    shuffled_words = words[:]

    while shuffled_words == words:
        random.shuffle(shuffled_words)

    return ' '.join(shuffled_words)


def remove_punctuation(text):
    return text.translate(str.maketrans('', '', string.punctuation))


@dp.callback_query_handler(lambda c: c.data.startswith('publish_'))
async def publish_handler(callback_query: types.CallbackQuery):
    global first_message_id, active_order_post, order_post_time, user_order_finalized, shuffled_text_cache

    user_id = int(callback_query.data.split('_')[1])

    try:
        # Извлекаем афоризм пользователя и сохраняем порядок слов
        aphorism = user_aphorisms.get(user_id, "").upper()
        # Удаляем пунктуацию из афоризма
        aphorism = remove_punctuation(aphorism)
        original_words = aphorism.split()
        user_aphorisms[user_id] = original_words

        # Перемешиваем слова и сохраняем перемешанный порядок
        shuffled_words = original_words[:]
        shuffled_text_cache = shuffle_aphorism(aphorism)
        shuffled_order[user_id] = shuffled_text_cache.split()

        if user_id not in user_buttons_order:
            shuffled_buttons = [InlineKeyboardButton(word.upper(), callback_data=f'word_{user_id}_{i}') for i, word in
                                enumerate(shuffled_order[user_id])]
            user_buttons_order[user_id] = shuffled_buttons

        bot_username = (await bot.get_me()).username
        bot_url = f"https://t.me/{bot_username}?start=order_{user_id}"

        msk_tz = pytz.timezone('Europe/Moscow')
        publication_time = datetime.now(msk_tz).strftime('%H:%M:%S')  # Форматируем только время
        today_date = datetime.now().strftime('%d.%m.%Y')

        # Создаем кнопку для возврата в сообщество
        channel_link = f'https://t.me/c/{CHANNEL_ID[4:]}'
        return_to_channel_button = InlineKeyboardButton('Назад в сообщество', url=channel_link)
        inline_keyboard = InlineKeyboardMarkup().add(return_to_channel_button)

        # Создаем клавиатуру для упорядочивания слов
        keyboard = InlineKeyboardMarkup().add(
            InlineKeyboardButton('Упорядочить слова', url=bot_url)
        )

        correct_count = sum(user_order_finalized.values())
        incorrect_count = len(user_order_finalized) - correct_count

        results_message = (
            f'<b>ДУХОВНАЯ ЭРУДИЦИЯ {today_date}.</b>\n\n'
            f'Пожалуйста, нажмите на кнопку ниже и расположите в правильном порядке слова послания 🙏🏻\n\n '
            f'{shuffled_text_cache}\n\n'
            f'Правильных ответов: {correct_count}\n'
            f'Неправильных ответов: {incorrect_count}\n\n'
        )

        # Получаем информацию о пользователе, отправившем афоризм
        user_data = user_info.get(user_id, {})
        username = user_data.get('username')
        first_name = user_data.get('first_name')
        last_name = user_data.get('last_name')

        # Формируем имя пользователя
        if username:
            user_name = f'@{username}'
        else:
            if first_name and last_name:
                user_name = f'@ {first_name} {last_name}'
            elif first_name:
                user_name = f'@ {first_name}'
            else:
                user_name = 'Неизвестный автор'

        # Храним статус сообщения перед обновлением
        status_message = "Опубликовано"
        message_status[callback_query.message.message_id] = status_message

        # Немедленно обновляем текст сообщения
        updated_text = (f"Автор: {user_name}\n\n"
                        f"Послание: {aphorism}\n\n"
                        f"Статус: {status_message}")

        try:
            await bot.edit_message_text(
                chat_id=callback_query.message.chat.id,
                message_id=callback_query.message.message_id,
                text=updated_text,
                parse_mode='HTML',
                reply_markup=inline_keyboard
            )
        except Exception as e:
            logger.error(f"Ошибка при обновлении сообщения: {e}")

        # Устанавливаем метки времени и флаги
        order_post_time = asyncio.get_event_loop().time()
        active_order_post = True

        # После обновления сообщения сразу вызываем функцию для публикации результатов
        await update_results_post()

    except Exception as e:
        logger.error(f'Ошибка при публикации афоризма: {e}')
        await callback_query.message.answer("Произошла ошибка при публикации афоризма. Попробуйте снова.")

    await callback_query.answer()


@dp.callback_query_handler(lambda c: c.data.startswith('word_'))
async def select_order_handler(callback_query: types.CallbackQuery):
    user_id = callback_query.from_user.id
    target_user_id, word_index = map(int, callback_query.data.split('_')[1:])

    if user_order_finalized.get(user_id, False):
        await callback_query.answer('Вы уже завершили выбор порядка слов и не можете изменить его.', show_alert=True)
        return

    shuffled_words = shuffled_order.get(target_user_id, [])
    selected_words = user_order_selections.get(user_id, [])
    if word_index < len(shuffled_words):
        selected_words.append(shuffled_words[word_index])
        user_order_selections[user_id] = selected_words

    buttons = [InlineKeyboardButton(word.upper(), callback_data=f'word_{target_user_id}_{i}') for i, word in
               enumerate(shuffled_words)]

    keyboard = InlineKeyboardMarkup(row_width=3)
    keyboard.add(*buttons)
    keyboard.add(InlineKeyboardButton('Очистить', callback_data=f'clear_{target_user_id}'))
    keyboard.add(InlineKeyboardButton('Готово', callback_data=f'finalize_{target_user_id}'))

    selected_words_text = ' '.join(selected_words)
    moscow_tz = pytz.timezone('Europe/Moscow')

    # Получаем текущее время в московском времени
    now = datetime.now(moscow_tz)
    today_date = now.strftime('%d.%m.%Y')
    message_text = (
        f'*ДУХОВНАЯ ЭРУДИЦИЯ {today_date}.*\n\n'
        f'Выбранные слова: _{selected_words_text}_\n\n'
        f'Пожалуйста, выберите правильный порядок слов.'
    )

    await callback_query.message.edit_text(message_text, reply_markup=keyboard, parse_mode='Markdown')
    await callback_query.answer()


@dp.callback_query_handler(lambda c: c.data.startswith('clear_'))
async def clear_order_handler(callback_query: types.CallbackQuery):
    user_id = callback_query.from_user.id
    target_user_id = int(callback_query.data.split('_')[1])
    logger.info(f'Пользователь {user_id} очистил выбор порядка слов для пользователя {target_user_id}')

    # Очищаем выбранные слова для пользователя
    if user_id in user_order_selections:
        user_order_selections[user_id] = []

    # Используем сохранённый порядок кнопок
    buttons = user_buttons_order.get(user_id)

    # Если кнопки не найдены, создаем их заново
    if buttons is None:
        logger.error(
            f'Кнопки для пользователя {user_id} не найдены. Используем перемешанные слова для создания новых кнопок.')
        aphorism = remove_punctuation(user_aphorisms.get(target_user_id, "").upper()).split()
        buttons = [InlineKeyboardButton(word.upper(), callback_data=f'word_{target_user_id}_{i}') for i, word in
                   enumerate(aphorism)]
        user_buttons_order[user_id] = buttons

    keyboard = InlineKeyboardMarkup(row_width=3)
    keyboard.add(*buttons)
    keyboard.add(InlineKeyboardButton('Очистить', callback_data=f'clear_{target_user_id}'))
    keyboard.add(InlineKeyboardButton('Готово', callback_data=f'finalize_{target_user_id}'))

    # Получаем текущую дату
    moscow_tz = pytz.timezone('Europe/Moscow')

    # Получаем текущее время в московском времени
    now = datetime.now(moscow_tz)
    today_date = now.strftime('%d.%m.%Y')

    # Формируем текст сообщения
    selected_words = user_order_selections.get(user_id, [])
    if not selected_words:
        message_text = (
            f'*ДУХОВНАЯ ЭРУДИЦИЯ {today_date}.*\n\n'
            f'Пожалуйста, выберите правильный порядок слов.'
        )
    else:
        selected_words_text = ' '.join(selected_words)
        message_text = (
            f'*ДУХОВНАЯ ЭРУДИЦИЯ {today_date}.*\n\n'
            f'Выбранные слова: _{selected_words_text}_\n\n'
            f'Пожалуйста, выберите правильный порядок слов.'
        )

    await callback_query.message.edit_text(message_text, reply_markup=keyboard, parse_mode='Markdown')
    await callback_query.answer()


# Флаг для предотвращения повторного вызова send_results_post
send_results_post_called = False


async def update_results_post():
    global first_message_id, shuffled_text_cache, send_results_post_called

    if first_message_id is None:
        logger.info('Не удалось обновить сообщение, так как first_message_id равен None.')
        return

    current_status = message_status.get(first_message_id)

    if current_status == "Опубликовано":
        logger.info(f"Сообщение уже опубликовано, статус не изменяется.")
        return

    correct_count = sum(user_order_finalized.values())
    incorrect_count = len(user_order_finalized) - correct_count

    sample_user_id = next(iter(user_aphorisms))
    correct_aphorism = user_aphorisms[sample_user_id]
    shuffled_text = shuffled_text_cache
    # Определяем московский часовой пояс
    moscow_tz = pytz.timezone('Europe/Moscow')

    # Получаем текущее время в московском времени
    now = datetime.now(moscow_tz)
    today_date = now.strftime('%d.%m.%Y')

    results_message = (
        f'<b>ДУХОВНАЯ ЭРУДИЦИЯ {today_date}.</b>\n\n'
        f'Пожалуйста, нажмите на кнопку ниже и расположите в правильном порядке слова послания 🙏🏻\n\n'
        f'{shuffled_text.upper()}\n\n'
        f'Правильных ответов: {correct_count}\n'
        f'Неправильных ответов: {incorrect_count}\n\n'
    )

    image_path = '2.png'

    try:
        await bot.delete_message(chat_id=CHANNEL_ID, message_id=first_message_id)
        logger.info(f'Удалено старое сообщение с ID {first_message_id} из канала {CHANNEL_ID}.')
    except Exception as e:
        logger.error(f'Ошибка при удалении старого сообщения с ID {first_message_id}: {e}')

    try:
        bot_me = await bot.get_me()
        bot_username = bot_me.username

        sent_message = await bot.send_photo(
            chat_id=CHANNEL_ID,
            photo=InputFile(image_path),
            caption=results_message,
            parse_mode='HTML',  # Добавлено для использования HTML-разметки
            reply_markup=InlineKeyboardMarkup().add(
                InlineKeyboardButton(
                    text='Упорядочить слова',
                    url=f'https://t.me/{bot_username}?start=order_{sample_user_id}'
                )
            ),
            disable_notification=True
        )
        first_message_id = sent_message.message_id
        logger.info(f'Обновлено сообщение в канале с ID {CHANNEL_ID}. ID нового сообщения: {sent_message.message_id}')

        # Запускаем функцию schedule_results_post для вызова send_results_post через 10 секунд
        if not send_results_post_called:
            send_results_post_called = True
            await schedule_results_post()

    except Exception as e:
        logger.error(f'Ошибка при обновлении сообщения в канале: {e}')


async def send_results_post():
    global send_results_post_called, first_message_id, test_completed

    logger.info('Starting send_results_post.')
    send_results_post_called = True

    try:
        correct_count = sum(user_order_finalized.values())
        incorrect_count = len(user_order_finalized) - correct_count
        logger.info(f'Correct answers: {correct_count}, Incorrect answers: {incorrect_count}')

        if not user_aphorisms:
            logger.error('Список афоризмов пуст, невозможно отправить результат.')
            return

        sample_user_id = next(iter(user_aphorisms))
        correct_aphorism = ' '.join(user_aphorisms[sample_user_id]).upper()  # Преобразование афоризма в верхний регистр
        logger.info(f'Sample user ID: {sample_user_id}, Correct aphorism: {correct_aphorism}')

        # Получение данных пользователя
        user_info = await bot.get_chat(sample_user_id)
        author_name = user_info.username or f"{user_info.first_name} {user_info.last_name}".strip()
        if not author_name:
            author_name = f"Пользователь {sample_user_id}"

        moscow_tz = pytz.timezone('Europe/Moscow')

        # Получаем текущее время в московском времени
        now = datetime.now(moscow_tz)
        today_date = now.strftime('%d.%m.%Y')

        # Формирование сообщения с результатами
        results_message = (
            f'<b>ИТОГИ. ДУХОВНАЯ ЭРУДИЦИЯ {today_date}.</b>\n\n'
            f'Правильный порядок слов послания ✨\n\n'
            f'{correct_aphorism}\n\n'
            f'Автор послания: {"@" + user_info.username if user_info.username else "@ " + user_info.first_name + " " + user_info.last_name}\n\n'
            f'Правильных ответов: {correct_count}\n'
            f'Неправильных ответов: {incorrect_count}\n\n'
        )

        logger.info('Results message generated.')

        image_path = '3.png'
        logger.info(f'Checking if image exists at path: {image_path}')
        if not await aiofiles.os.path.isfile(image_path):
            logger.error(f'Файл изображения не найден: {image_path}')
            return

        logger.info('Sending results to channel.')
        await bot.send_photo(
            chat_id=CHANNEL_ID,
            photo=InputFile(image_path),
            caption=results_message,
            parse_mode=ParseMode.HTML
        )
        logger.info('Результаты успешно отправлены в канал.')

        # Удаление сообщения, опубликованного update_results_post
        if first_message_id:
            try:
                await bot.delete_message(chat_id=CHANNEL_ID, message_id=first_message_id)
                logger.info(f'Сообщение с ID {first_message_id}, опубликованное update_results_post, удалено.')
                first_message_id = None  # Сброс переменной, так как сообщение было удалено
            except Exception as e:
                logger.error(f'Ошибка при удалении сообщения с ID {first_message_id}: {e}')

        # Устанавливаем флаг завершения теста
        test_completed = True

    except TelegramAPIError as e:
        logger.error(f'Ошибка при отправке результатов: {e}')
    except Exception as e:
        logger.error(f'Неизвестная ошибка при отправке результатов: {e}')
    finally:
        send_results_post_called = False
        logger.info('Resetting send_results_post_called to False.')


async def schedule_results_post():
    while True:
        moscow_tz = pytz.timezone('Europe/Moscow')
        now = datetime.now(moscow_tz)
        target_time = now.replace(hour=21, minute=0, second=0, microsecond=0)
        if now > target_time:
            target_time = target_time + timedelta(days=1)
        wait_time = (target_time - now).total_seconds()
        await asyncio.sleep(wait_time)
        await send_results_post()

# Определяем московский часовой пояс
moscow_tz = pytz.timezone('Europe/Moscow')

def get_next_execution_time(hour, minute):
    """Возвращает следующую дату и время для выполнения задачи в заданное время дня."""
    now = datetime.now(moscow_tz)
    next_time = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if now > next_time:
        next_time += timedelta(days=1)
    return next_time

async def notify_time_remaining():
    """Выводит в лог время до следующего поста и результатов."""
    while True:
        now = datetime.now(moscow_tz)
        next_post_time = get_next_execution_time(9, 0)  # 09:00
        next_results_time = get_next_execution_time(21, 0)  # 21:00

        time_until_post = next_post_time - now
        time_until_results = next_results_time - now

        logger.info(f'Осталось времени до следующего поста: {time_until_post}')
        logger.info(f'Осталось времени до следующего результата: {time_until_results}')

        await asyncio.sleep(60)  # Проверяем каждую минуту
async def schedule_tasks():
    """Запускает задачи по расписанию и отслеживает оставшееся до них время."""
    while True:
        now = datetime.now(moscow_tz)
        next_post_time = get_next_execution_time(9, 0)  # 09:00
        next_results_time = get_next_execution_time(21, 0)  # 21:00

        # Сколько времени до следующего поста
        time_until_post = (next_post_time - now).total_seconds()
        # Сколько времени до следующего результата
        time_until_results = (next_results_time - now).total_seconds()

        if time_until_post <= 0:
            await send_post()
            next_post_time = get_next_execution_time(9, 0)  # Устанавливаем время следующего поста
        if time_until_results <= 0:
            await send_results_post()
            next_results_time = get_next_execution_time(21, 0)  # Устанавливаем время следующего результата

        await asyncio.sleep(60)  # Проверяем каждую минуту


@dp.callback_query_handler(lambda c: c.data.startswith('finalize_'))
async def finalize_order_handler(callback_query: types.CallbackQuery):
    user_id = callback_query.from_user.id
    target_user_id = int(callback_query.data.split('_')[1])

    if user_order_finalized.get(user_id, False):
        await callback_query.message.edit_text('Вы уже завершили выбор порядка слов.')
        return

    logger.info(f'Пользователь {user_id} завершил выбор порядка слов для пользователя {target_user_id}')

    original_words = remove_punctuation(" ".join(user_aphorisms.get(target_user_id, []))).upper().split()
    ordered_words = user_order_selections.get(user_id, [])

    if ordered_words == original_words:
        user_order_finalized[user_id] = True
        final_message_text = 'Поздравляем! Выбран правильный порядок слов.'
        logger.info(f'Пользователь {user_id} успешно выбрал правильный порядок слов.')
    else:
        user_order_finalized[user_id] = False
        user_failed_attempts[user_id] = True
        final_message_text = 'Выбран неправильный порядок слов.'
        logger.info(f'Пользователь {user_id} выбрал неверный порядок слов.')

    # Получаем текущую дату
    moscow_tz = pytz.timezone('Europe/Moscow')

    # Получаем текущее время в московском времени
    now = datetime.now(moscow_tz)
    today_date = now.strftime('%d.%m.%Y')

    # Создаем и добавляем новую кнопку "Вернуться в канал"
    channel_link = f'https://t.me/c/{CHANNEL_ID[4:]}'
    return_to_channel_button = InlineKeyboardButton('Назад в сообщество', url=channel_link)
    inline_keyboard = InlineKeyboardMarkup().add(return_to_channel_button)

    ordered_words_text = ' '.join(ordered_words) if ordered_words else 'Не выбран'

    final_message_with_details = (
        f'*ДУХОВНАЯ ЭРУДИЦИЯ {today_date}.*\n\n'
        f'Ваш ответ: {ordered_words_text}\n\n'
        f'{final_message_text}\n'
    )

    # Редактируем сообщение, убирая старые кнопки и добавляя новую кнопку
    await callback_query.message.edit_text(final_message_with_details, reply_markup=inline_keyboard,
                                           parse_mode='Markdown')
    # Очищаем временные данные пользователя
    if user_id in user_message_ids:
        del user_message_ids[user_id]
    if user_id in user_order_selections:
        del user_order_selections[user_id]

    await send_results_post()  # Запуск отправки результатов сразу после завершения заказа


if __name__ == '__main__':
    # Запускаем отслеживание оставшегося времени
    loop = asyncio.get_event_loop()
    loop.create_task(notify_time_remaining())
    loop.create_task(schedule_tasks())

    # Запускаем бота
    executor.start_polling(dp, skip_updates=True)