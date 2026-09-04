import threading

import plugins_func.loadplugins

plugins_func.loadplugins.auto_import_modules = lambda _package: None

from core.connection import ConnectionHandler


def test_chat_does_not_start_after_connection_close_begins():
    connection = object.__new__(ConnectionHandler)
    connection._closing_event = threading.Event()
    connection.stop_event = threading.Event()
    connection._closing_event.set()

    assert connection.chat("不应继续处理") is None
