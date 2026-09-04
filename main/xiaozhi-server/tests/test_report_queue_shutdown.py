import queue
import threading

from core.utils.report_queue import drain_report_queue


class _Logger:
    def bind(self, **_kwargs):
        return self

    def debug(self, *_args, **_kwargs):
        return None

    def info(self, *_args, **_kwargs):
        return None

    def error(self, *_args, **_kwargs):
        return None


def test_report_worker_drains_existing_items_after_stop():
    stop_event = threading.Event()
    report_queue = queue.Queue()
    processed = []

    def process_report(*item):
        processed.append(item)
        report_queue.task_done()

    report_queue.put((1, "用户的最后一句", None, 1))
    report_queue.put((2, "小布布的最后一句", None, 2))
    stop_event.set()

    drain_report_queue(stop_event, report_queue, process_report, _Logger(), "test")

    assert [item[1] for item in processed] == ["用户的最后一句", "小布布的最后一句"]
    assert report_queue.unfinished_tasks == 0
