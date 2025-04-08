import requests
from dotenv import load_dotenv
from telebot import TeleBot

import os
import time

load_dotenv()


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
    if not PRACTICUM_TOKEN or not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        raise Exception('Отсутствуют обязательные переменные окружения.')


def send_message(bot, message):
    bot.send_message(TELEGRAM_CHAT_ID, message)


def get_api_answer(timestamp):
    return requests.get(ENDPOINT, headers=HEADERS, params={'from_date': {timestamp}})


def check_response(response):
    pass

def parse_status(homework):
    pass

    #return f'Изменился статус проверки работы "{homework_name}". {verdict}'


def main():
    """Основная логика работы бота."""

    check_tokens()

    # Создаем объект класса бота
    bot = TeleBot(token=TELEGRAM_TOKEN)
    timestamp = int(time.time())
    #print(HEADERS)
    homework_statuses = get_api_answer(timestamp)
    print(homework_statuses)


    while True:
        try:

            homework_statuses = get_api_answer(timestamp)
            print(homework_statuses)

        except Exception as error:
            message = f'Сбой в работе программы: {error}'
        break


if __name__ == '__main__':
    main()
