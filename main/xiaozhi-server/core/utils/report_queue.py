import queue


def drain_report_queue(stop_event, report_queue, process_report, logger, tag, poll_timeout=0.2):
    """按顺序处理聊天记录队列。

    停止事件只阻止继续等待新数据，已入队的记录仍会处理完。
    """
    while True:
        if stop_event.is_set() and report_queue.empty():
            break
        try:
            item = report_queue.get(timeout=poll_timeout)
            if item is None:
                report_queue.task_done()
                break
            try:
                process_report(*item)
            except Exception as error:
                logger.bind(tag=tag).error(f"聊天记录上报线程异常: {error}")
        except queue.Empty:
            continue
        except Exception as error:
            logger.bind(tag=tag).error(f"聊天记录上报工作线程异常: {error}")
