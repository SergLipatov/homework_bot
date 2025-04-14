import logging
import os
import sys
import time
from http import HTTPStatus

from dotenv import load_dotenv
from telebot import TeleBot
import requests

load_dotenv()
logger = logging.getLogger(__name__)

PRACTICUM_TOKEN = os.getenv('PRACTICUM_TOKEN')
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')
TOKENS = ('PRACTICUM_TOKEN', 'TELEGRAM_TOKEN', 'TELEGRAM_CHAT_ID')
RETRY_PERIOD = 600
ENDPOINT = 'https://practicum.yandex.ru/api/user_api/homework_statuses/'
HEADERS = {'Authorization': f'OAuth {PRACTICUM_TOKEN}'}

HOMEWORK_VERDICTS = {
    'approved': 'Работа проверена: ревьюеру всё понравилось. Ура!',
    'reviewing': 'Работа взята на проверку ревьюером.',
    'rejected': 'Работа проверена: у ревьюера есть замечания.'
}

# Шаблоны сообщений
HOMEWORK_STATUS_CHANGED = (
    'Изменился статус проверки работы "{homework_name}". {verdict}')
MISSING_ENV_VARS = ('Отсутствуют обязательные переменные окружения: '
                    '{missing_vars}')
MESSAGE_SENT = 'Отправлено сообщение: {message}'
MESSAGE_SEND_ERROR = 'Ошибка отправки сообщения "{message}": {error}'
API_ENDPOINT_UNAVAILABLE = (
    'Эндпоинт {endpoint} недоступен. Код ответа: {status_code}. '
    'Параметры запроса: {params}, заголовки: {headers}')
API_ERROR_RESPONSE = (
    'API вернуло ошибку: {error_info}. '
    'Эндпоинт: {endpoint}, параметры: {params}, заголовки: {headers}')
API_REQUEST_ERROR = (
    'Ошибка при запросе к API: {error}. '
    'Эндпоинт: {endpoint}, параметры: {params}, заголовки: {headers}')
JSON_DECODE_ERROR = (
    'Ошибка декодирования JSON: {error}. '
    'Эндпоинт: {endpoint}, параметры: {params}, заголовки: {headers}')
API_RESPONSE_TYPE_ERROR = 'Ответ API должен быть словарем, получен {type_name}'
MISSING_HOMEWORKS_KEY = 'В ответе API отсутствует ключ "homeworks"'
HOMEWORKS_TYPE_ERROR = (
    'Значение ключа "homeworks" должно быть списком, получен {type_name}')
MISSING_KEY_ERROR = 'В ответе API отсутствует ключ "{key}"'
UNKNOWN_STATUS_ERROR = 'Неизвестный статус работы: {status}'
MISSING_CURRENT_DATE = 'API не вернул "current_date" в ответе'
NEW_STATUS_PROCESSED = 'Обработан новый статус для работы "{homework_name}"'
SEND_ERROR_TIMESTAMP = 'Не удалось отправить сообщение, timestamp не обновлен'
NO_NEW_HOMEWORK_STATUSES = 'Нет новых статусов домашних работ'
CONNECTION_ERROR = 'Ошибка соединения при запросе к API: {error}'
TIMEOUT_ERROR = 'Превышено время ожидания ответа API: {error}'
HTTP_ERROR = 'HTTP-ошибка при запросе к API: {error}'
API_RESPONSE_ERROR = 'Ошибка в ответе API: {error}'
KEY_ACCESS_ERROR = 'Ошибка доступа к ключу в данных: {error}'
TYPE_ERROR = 'Ошибка типа данных: {error}'
UNEXPECTED_ERROR = 'Непредвиденная ошибка: {error}'

ERROR_TYPES = {
    requests.RequestException: CONNECTION_ERROR,
    requests.exceptions.Timeout: TIMEOUT_ERROR,
    requests.exceptions.HTTPError: HTTP_ERROR,
    ValueError: API_RESPONSE_ERROR,
    KeyError: KEY_ACCESS_ERROR,
    TypeError: TYPE_ERROR
}


def check_tokens():
    """Проверяет доступность необходимых переменных окружения."""
    missing_tokens = [name for name in TOKENS if not globals()[name]]

    if missing_tokens:
        error_message = MISSING_ENV_VARS.format(missing_vars=missing_tokens)
        logger.critical(error_message)
        raise ValueError(error_message)


def send_message(bot, message):
    """Отправляет сообщение в Telegram чат."""
    try:
        bot.send_message(TELEGRAM_CHAT_ID, message)
        logger.debug(MESSAGE_SENT.format(message=message))
        return True
    except Exception as err:
        logger.error(
            MESSAGE_SEND_ERROR.format(message=message, error=err),
            exc_info=True
        )
        return False


def get_api_answer(timestamp):
    """Выполняет запрос к API сервиса."""
    params = {'from_date': timestamp}
    try:
        response = requests.get(ENDPOINT, headers=HEADERS, params=params)
    except requests.RequestException as err:
        raise requests.RequestException(API_REQUEST_ERROR.format(
            error=err,
            endpoint=ENDPOINT,
            params=params,
            headers=HEADERS
        ))

    if response.status_code != HTTPStatus.OK:
        raise requests.RequestException(
            API_ENDPOINT_UNAVAILABLE.format(
                endpoint=ENDPOINT,
                status_code=response.status_code,
                params=params,
                headers=HEADERS
            )
        )

    try:
        json_response = response.json()
    except ValueError as err:
        raise ValueError(JSON_DECODE_ERROR.format(
            error=err,
            endpoint=ENDPOINT,
            params=params,
            headers=HEADERS
        ))

    found_errors_keys = {}
    for key in ['code', 'error']:
        if key in json_response:
            found_errors_keys[key] = json_response.get(key)
    if found_errors_keys:
        error_info = ", ".join(
            [f"'{key}': {value}" for key, value in
             found_errors_keys.items()])
        raise ValueError(API_ERROR_RESPONSE.format(
            error_info=error_info,
            endpoint=ENDPOINT,
            params=params,
            headers=HEADERS
        ))

    return json_response


def check_response(response):
    """Проверяет корректность ответа API."""
    if not isinstance(response, dict):
        raise TypeError(
            API_RESPONSE_TYPE_ERROR.format(type_name=type(response).__name__)
        )
    if 'homeworks' not in response:
        raise KeyError(MISSING_HOMEWORKS_KEY)
    homeworks = response['homeworks']
    if not isinstance(homeworks, list):
        raise TypeError(
            HOMEWORKS_TYPE_ERROR.format(type_name=type(homeworks).__name__)
        )
    return homeworks


def parse_status(homework):
    """Извлекает и возвращает статус работы из информации о домашней работе."""
    required_keys = ('homework_name', 'status', 'current_date')
    for key in required_keys:
        if key not in homework:
            raise KeyError(MISSING_KEY_ERROR.format(key=key))
    status = homework['status']
    if status not in HOMEWORK_VERDICTS:
        raise ValueError(UNKNOWN_STATUS_ERROR.format(status=status))
    return HOMEWORK_STATUS_CHANGED.format(
        homework_name=homework["homework_name"],
        verdict=HOMEWORK_VERDICTS[status]
    )


def main():
    """Основная логика работы бота."""
    check_tokens()
    bot = TeleBot(token=TELEGRAM_TOKEN)
    timestamp = int(time.time())
    last_error_message = None

    while True:
        try:
            response = get_api_answer(timestamp)
            homeworks = check_response(response)
            new_timestamp = response.get('current_date', timestamp)
            message = parse_status(homeworks[0]) if homeworks else None
            if message and send_message(bot, message):
                logger.info(NEW_STATUS_PROCESSED.format(
                    homework_name=homeworks[0]['homework_name']
                ))
                timestamp = new_timestamp
            elif message:
                logger.error(SEND_ERROR_TIMESTAMP)
            else:
                logger.debug(NO_NEW_HOMEWORK_STATUSES)
            last_error_message = None
        except Exception as error:
            for error_type, message_template in ERROR_TYPES.items():
                if isinstance(error, error_type):
                    error_message = message_template.format(error=error)
                    break
            else:
                error_message = UNEXPECTED_ERROR.format(error=error)
            logger.error(error_message)
            if error_message != last_error_message:
                send_message(bot, error_message)
                last_error_message = error_message
        time.sleep(RETRY_PERIOD)


if __name__ == '__main__':
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s %(name)s [%(filename)s:%(lineno)d in '
               '%(funcName)s] %(levelname)s: %(message)s',
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(f'{__file__}.log', encoding='utf-8')
        ]
    )
    main()
