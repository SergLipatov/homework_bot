import requests
from dotenv import load_dotenv
from telebot import TeleBot

import logging
import os
import sys
import time

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
    """Функция проверяет доступность переменных содержащих токены."""
    required_tokens = {
        'PRACTICUM_TOKEN': PRACTICUM_TOKEN,
        'TELEGRAM_TOKEN': TELEGRAM_TOKEN,
        'TELEGRAM_CHAT_ID': TELEGRAM_CHAT_ID,
    }

    for name, value in required_tokens.items():
        if not value:
            logger.critical(f'Отсутствует обязательная переменная окружения: {name}')
            raise Exception(f'Отсутствует переменная окружения: {name}')


def send_message(bot, message):
    """Функция отправляет сообщение в телеграмм-чат."""
    try:
        bot.send_message(TELEGRAM_CHAT_ID, message)
        logger.debug('Сообщение отправлено!')
    except Exception as err:
        logger.error(f'Ошибка отправки сообщения: {err}')


def get_api_answer(timestamp):
    """Функция выполняет запрос к API."""
    #params = {'from_date': timestamp}
    params = {'from_date': timestamp}
    response = requests.get(ENDPOINT, headers=HEADERS, params=params)
    response.raise_for_status()
    return response.json()


def check_response(response):
    """Функция проверяет ответ от API на корректность."""
    if 'homeworks' not in response:
        raise ValueError('Ключ "homeworks" отсутствует в ответе API')
    return response['homeworks']

def parse_status(homework):
    """Функция извлекает статус работы из ответа от API."""
    if 'homework_name' not in homework or 'status' not in homework:
        raise KeyError(
            'Ключи "homework_name" или "status" отсутствуют в ответе API')

    homework_name = homework['homework_name']
    status = homework['status']

    if status not in HOMEWORK_VERDICTS:
        raise ValueError(
            f'Недокументированный статус домашней работы: {status}')

    verdict = HOMEWORK_VERDICTS[status]
    return f'Изменился статус проверки работы "{homework_name}". {verdict}'


def main():
    """Основная логика работы бота."""

    check_tokens()

    bot = TeleBot(token=TELEGRAM_TOKEN)

    while True:
        try:
            timestamp = int(time.time())
            response = get_api_answer(timestamp)
            homeworks = check_response(response)

            for homework in homeworks:
                message = parse_status(homework)
                send_message(bot, message)


            time.sleep(RETRY_PERIOD)

        except Exception as error:
            message = f'Сбой в работе программы: {error}'
            send_message(bot, message)
            time.sleep(RETRY_PERIOD)

if __name__ == '__main__':
    main()
