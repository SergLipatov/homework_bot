import logging
import os
import sys
import time
from http import HTTPStatus

from dotenv import load_dotenv
from telebot import TeleBot
import requests
from requests.exceptions import HTTPError

load_dotenv()
log_file = __file__ + '.log'
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s %(name)s [%(filename)s:%(lineno)d in %(funcName)s] '
           '%(levelname)s: %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(log_file, encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)

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


class APIError(Exception):
    """Исключение, вызываемое при ошибках в ответе API."""

    pass


def check_tokens():
    """Проверяет доступность необходимых переменных окружения."""
    missing_tokens = [name for name in [
        'PRACTICUM_TOKEN', 'TELEGRAM_TOKEN', 'TELEGRAM_CHAT_ID'
    ] if not globals()[name]]

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

        if response.status_code != HTTPStatus.OK:
            error_msg = API_ENDPOINT_UNAVAILABLE.format(
                endpoint=ENDPOINT,
                status_code=response.status_code,
                params=params,
                headers=HEADERS
            )
            raise HTTPError(error_msg)

        json_response = response.json()

        if 'code' in json_response or 'error' in json_response:
            error_info = json_response.get('code') or json_response.get(
                'error')
            error_msg = API_ERROR_RESPONSE.format(
                error_info=error_info,
                endpoint=ENDPOINT,
                params=params,
                headers=HEADERS
            )
            raise APIError(error_msg)

        return json_response

    except requests.RequestException as err:
        error_msg = API_REQUEST_ERROR.format(
            error=err,
            endpoint=ENDPOINT,
            params=params,
            headers=HEADERS
        )
        raise APIError(error_msg)

    except ValueError as err:
        error_msg = JSON_DECODE_ERROR.format(
            error=err,
            endpoint=ENDPOINT,
            params=params,
            headers=HEADERS
        )
        raise ValueError(error_msg)


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
    required_keys = ('homework_name', 'status')
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
    # timestamp = 0

    while True:
        try:
            response = get_api_answer(timestamp)
            homeworks = check_response(response)
            new_timestamp = response.get('current_date')
            if new_timestamp is None:
                logger.error(MISSING_CURRENT_DATE)
                time.sleep(RETRY_PERIOD)
                continue
            if homeworks:
                homework = homeworks[0]
                message = parse_status(homework)
                if send_message(bot, message):
                    logger.info(
                        NEW_STATUS_PROCESSED.format(
                            homework_name=homework.get("homework_name")
                        )
                    )
                    timestamp = new_timestamp
                else:
                    logger.error(SEND_ERROR_TIMESTAMP)
            else:
                logger.debug(NO_NEW_HOMEWORK_STATUSES)
                timestamp = new_timestamp
        except requests.exceptions.ConnectionError as error:
            error_msg = CONNECTION_ERROR.format(error=error)
            logger.error(error_msg)
            send_message(bot, error_msg)
        except requests.exceptions.Timeout as error:
            error_msg = TIMEOUT_ERROR.format(error=error)
            logger.error(error_msg)
            send_message(bot, error_msg)
        except requests.exceptions.HTTPError as error:
            error_msg = HTTP_ERROR.format(error=error)
            logger.error(error_msg)
            send_message(bot, error_msg)
        except APIError as error:
            error_msg = API_RESPONSE_ERROR.format(error=error)
            logger.error(error_msg)
            send_message(bot, error_msg)
        except KeyError as error:
            error_msg = KEY_ACCESS_ERROR.format(error=error)
            logger.error(error_msg)
            send_message(bot, error_msg)
        except TypeError as error:
            error_msg = TYPE_ERROR.format(error=error)
            logger.error(error_msg)
            send_message(bot, error_msg)
        except Exception as error:
            error_msg = UNEXPECTED_ERROR.format(error=error)
            logger.error(error_msg)
            send_message(bot, error_msg)

        time.sleep(RETRY_PERIOD)


if __name__ == '__main__':
    # from unittest import TestCase, mock, main as uni_main
    main()

    # class TestHomeworkBot(TestCase):
    #     @mock.patch('requests.get')
    #     def test_connection_error(self, mock_get):
    #         mock_get.side_effect = requests.exceptions.ConnectionError(
    #             "Сеть недоступна")
    #         main()

    #     @mock.patch('requests.get')
    #     def test_api_error_response(self, mock_get):
    #         mock_response = mock.Mock()
    #         mock_response.status_code = 200
    #         mock_response.json.return_value = {
    #             'error': 'Внутренняя ошибка сервера'}
    #         mock_get.return_value = mock_response
    #         main()
    #
    #     @mock.patch('requests.get')
    #     def test_unexpected_status_code(self, mock_get):
    #         mock_response = mock.Mock()
    #         mock_response.status_code = 500
    #         mock_get.return_value = mock_response
    #         main()
    #
    #     @mock.patch('requests.get')
    #     def test_unknown_homework_status(self, mock_get):
    #         mock_response = mock.Mock()
    #         mock_response.status_code = 200
    #         mock_response.json.return_value = {
    #             'homeworks': [
    #                 {
    #                     'homework_name': 'тестовая_домашка',
    #                     'status': 'неизвестный_статус'
    #                 }
    #             ],
    #             'current_date': 1234567890
    #         }
    #         mock_get.return_value = mock_response
    #         main()
    #
    #     @mock.patch('requests.get')
    #     def test_malformed_json_response(self, mock_get):
    #         mock_response = mock.Mock()
    #         mock_response.status_code = 200
    #         mock_response.json.return_value = {
    #             'homeworks': "Это должен быть список, а не строка",
    #             'current_date': 1234567890
    #         }
    #         mock_get.return_value = mock_response
    #         main()
    #
    #
    #     @mock.patch('requests.get')
    #     def test_missing_homework_name(self, mock_get):
    #         mock_response = mock.Mock()
    #         mock_response.status_code = 200
    #         mock_response.json.return_value = {
    #             'homeworks': [
    #                 {
    #                     'status': 'approved'  # Отсутствует поле
    #                       '                   # homework_name
    #                 }
    #             ],
    #             'current_date': 1234567890
    #         }
    #         mock_get.return_value = mock_response
    #         main()

    #
    #
    #     @mock.patch('requests.get')
    #     def test_missing_current_date(self, mock_get):
    #         mock_response = mock.Mock()
    #         mock_response.status_code = 200
    #         mock_response.json.return_value = {
    #             'homeworks': [
    #                 {
    #                     'homework_name': 'тестовая_домашка',
    #                     'status': 'approved'
    #                 }
    #             ]
    #         }
    #         mock_get.return_value = mock_response
    #         main()
    #
    #
    #     @mock.patch('requests.get')
    #     def test_timeout_error(self, mock_get):
    #         mock_get.side_effect = requests.exceptions.Timeout(
    #             "Превышено время ожидания")
    #         main()
    # uni_main()
