import logging
import os
import sys
import time

from dotenv import load_dotenv
import requests
from telebot import TeleBot

load_dotenv()
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
stream_handler = logging.StreamHandler(sys.stdout)
stream_handler.setLevel(logging.DEBUG)
formatter = logging.Formatter('%(asctime)s %(name)s %(levelname)s %(message)s')
stream_handler.setFormatter(formatter)
logger.addHandler(stream_handler)

PRACTICUM_TOKEN = os.getenv('PRACTICUM_TOKEN')
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')
RETRY_PERIOD = 600
ENDPOINT = 'https://practicum.yandex.ru/api/user_api/homework_statuses/'
HEADERS = {'Authorization': f'OAuth {PRACTICUM_TOKEN}'}

HOMEWORK_VERDICTS = {
    'approved': 'Работа проверена: ревьюеру всё понравилось. Ура!',
    'reviewing': 'Работа взята на проверку ревьюером.',
    'rejected': 'Работа проверена: у ревьюера есть замечания.'
}


def check_tokens():
    """Проверяет доступность необходимых переменных окружения."""
    missing_tokens = [
        name for name, value in {
            'PRACTICUM_TOKEN': PRACTICUM_TOKEN,
            'TELEGRAM_TOKEN': TELEGRAM_TOKEN,
            'TELEGRAM_CHAT_ID': TELEGRAM_CHAT_ID,
        }.items() if not value
    ]
    if missing_tokens:
        error_msg = (f'Отсутствуют обязательные переменные окружения: '
                     f'{", ".join(missing_tokens)}')
        logger.critical(error_msg)
        raise ValueError(error_msg)


def send_message(bot, message):
    """Отправляет сообщение в Telegram чат."""
    try:
        bot.send_message(TELEGRAM_CHAT_ID, message)
        logger.debug(f'Отправлено сообщение: {message}')
        return True
    except Exception as err:
        logger.error(f'Ошибка отправки сообщения: {err}')
        return False


def get_api_answer(timestamp):
    """Выполняет запрос к API сервиса."""
    params = {'from_date': timestamp}
    try:
        response = requests.get(ENDPOINT, headers=HEADERS, params=params)
        if response.status_code != 200:
            error_msg = (f'Эндпоинт {ENDPOINT} недоступен. '
                         f'Код ответа: {response.status_code}')
            logger.error(error_msg)
            raise Exception(error_msg)
        return response.json()
    except requests.RequestException as err:
        error_msg = f'Ошибка при запросе к API: {err}'
        logger.error(error_msg)
        raise Exception(error_msg)
    except ValueError as err:
        error_msg = f'Ошибка декодирования JSON: {err}'
        logger.error(error_msg)
        raise ValueError(error_msg)


def check_response(response):
    """Проверяет корректность ответа API."""
    if not isinstance(response, dict):
        raise TypeError('Ответ API должен быть словарем')
    if 'homeworks' not in response:
        raise KeyError('В ответе API отсутствует ключ "homeworks"')
    homeworks = response['homeworks']
    if not isinstance(homeworks, list):
        raise TypeError('Значение ключа "homeworks" должно быть списком')
    return homeworks


def parse_status(homework):
    """Извлекает и возвращает статус работы из информации о домашней работе."""
    required_keys = ('homework_name', 'status')
    for key in required_keys:
        if key not in homework:
            raise KeyError(f'В ответе API отсутствует ключ "{key}"')
    homework_name = homework['homework_name']
    status = homework['status']
    if status not in HOMEWORK_VERDICTS:
        raise ValueError(f'Неизвестный статус работы: {status}')
    verdict = HOMEWORK_VERDICTS[status]
    return f'Изменился статус проверки работы "{homework_name}". {verdict}'


def process_homeworks(bot, homeworks, prev_statuses):
    """Обработка новых статусов домашних работ и отправка уведомлений."""
    for homework in homeworks:
        hw_key = (f"{homework.get('homework_name', 'unknown')}_"
                  f"{homework.get('status', 'unknown')}")
        if hw_key not in prev_statuses:
            message = parse_status(homework)
            if send_message(bot, message):
                prev_statuses[hw_key] = True
    return prev_statuses


def poll_api_with_backoff(bot, timestamp, prev_statuses, error_reported):
    """Опрос API и обработка ответа с обработкой ошибок."""
    try:
        if error_reported:
            success_msg = 'Работа программы восстановлена'
            send_message(bot, success_msg)
            logger.info(success_msg)
            error_reported = False

        response = get_api_answer(timestamp)
        homeworks = check_response(response)
        new_timestamp = response.get('current_date', int(time.time()))

        if homeworks:
            prev_statuses = process_homeworks(bot, homeworks, prev_statuses)
        else:
            logger.debug('Нет новых статусов домашних работ')

        return new_timestamp, prev_statuses, error_reported
    except Exception as error:
        error_msg = f'Сбой в работе программы: {error}'
        logger.error(error_msg)
        if not error_reported and bot:
            send_message(bot, error_msg)
            error_reported = True
        return timestamp, prev_statuses, error_reported


def main():
    """Основная логика работы бота."""
    try:
        check_tokens()
    except Exception as error:
        logger.critical(f'Программа остановлена: {error}')
        sys.exit(1)

    bot = TeleBot(token=TELEGRAM_TOKEN)
    timestamp = int(time.time())
    prev_statuses = {}
    error_reported = False

    while True:
        timestamp, prev_statuses, error_reported = poll_api_with_backoff(
            bot, timestamp, prev_statuses, error_reported
        )
        time.sleep(RETRY_PERIOD)


if __name__ == '__main__':
    main()
