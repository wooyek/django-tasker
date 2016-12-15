# coding=utf-8
import json
import logging
import signal
import types
from datetime import datetime, timedelta
from enum import IntEnum
from threading import Thread
from time import sleep

import six
import sys

from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist
from django.utils.translation import ugettext as __, ugettext_lazy as _
from django.db import DatabaseError
from django.db import models
from django.db import transaction
from django.utils import timezone
from django.utils.module_loading import import_string

logging = logging.getLogger(__name__)


class ChoicesIntEnum(IntEnum):
    """Extends IntEum with django choices generation capability"""

    @classmethod
    def choices(cls):
        return [(item.value, _(item.name.replace("_", " ").capitalize())) for item in cls]

    @classmethod
    def values(cls):
        return [item.value for item in cls]


class QueueStatus(ChoicesIntEnum):
    enabled = 0
    disabled = 1


class TaskWorker(object):
    def __init__(self, queue):
        self.queue = queue
        self._stop_requested = False

    def __call__(self):
        logging.info("Worker booting for queue: %s", self.queue)
        while True:
            if self._stop_requested:
                logging.info('Stopping on request')
                break
            try:
                emtpy_run = self.queue.process_batch()
            except Exception as ex:
                logging.error("Queue process batch failed, backing off for a minute", exc_info=ex)
                sleep(60)
            else:
                if emtpy_run:
                    seconds = getattr(settings, 'TASKER_SLEEP_TIME', 10)
                    logging.debug("Will sleep for %s seconds", seconds)
                    sleep(seconds)

    def request_stop(self):
        self._stop_requested = True

    @classmethod
    def run_queues(cls, queue_names):
        logging.info("Running workers for queues: %s if they are enabled", queue_names)
        workers = [cls(q) for q in TaskQueue.objects.filter(name__in=queue_names, status=QueueStatus.enabled)]
        threads = [Thread(target=w) for w in workers]
        for t in threads:
            t.start()

        cls.setup_signals(workers)

    @classmethod
    def setup_signals(cls, workers):
        def request_workers_stop(signum, frame):
            logging.info("Warm shut down requested: %s", signum)
            for w in workers:
                w.request_stop()

        # TODO: handle signals correctly
        signal.signal(signal.SIGINT, request_workers_stop)
        signal.signal(signal.SIGTERM, request_workers_stop)
        signals_to_names = {}
        for n in dir(signal):
            if n.startswith('SIG') and not n.startswith('SIG_'):
                signals_to_names[getattr(signal, n)] = n
        for s, name in sorted(signals_to_names.items()):
            handler = signal.getsignal(s)
            if handler is signal.SIG_DFL:
                handler = 'SIG_DFL'
            elif handler is signal.SIG_IGN:
                handler = 'SIG_IGN'
            print('%-10s (%2d):' % (name, s), handler)


class TaskQueue(models.Model):
    name = models.CharField(max_length=100, default='default', unique=True)
    rate_limit = models.PositiveSmallIntegerField(null=True, blank=True, help_text='Maximum number of tasks to run per hour')
    status = models.PositiveSmallIntegerField(default=QueueStatus.enabled, choices=QueueStatus.choices())

    def __init__(self, *args, **kwargs):
        super(TaskQueue, self).__init__(*args, **kwargs)
        if self.rate_limit:
            self.time_interval = timedelta(seconds=3600 / self.rate_limit)

    def __str__(self):
        return "TaskQueue:{}:{}.{}".format(self.pk, self.name, self.get_status_display())

    def process_batch(self, limit=10):
        qry = TaskInfo.objects.filter(eta__lte=datetime.now(), status=TaskStatus.queued, target__queue=self)
        batch = qry.values_list('id', flat=True)[:limit]
        empty_run = True
        for pk in batch:
            start = datetime.now()
            if TaskInfo.process_one(pk):
                empty_run = False
                self.throttle(datetime.now() - start)
        return empty_run

    def throttle(self, duration):
        if self.rate_limit:
            wait = self.time_interval - duration
            if wait > timedelta():
                sleep(wait.seconds)


@six.python_2_unicode_compatible
class TaskTarget(models.Model):
    name = models.CharField(max_length=100, unique=True)
    queue = models.ForeignKey(TaskQueue)

    def __str__(self):
        return "TaskTarget:{}:{}".format(self.pk, self.name)

    @classmethod
    def by_name(cls, name, defaults):
        target, created = cls.objects.get_or_create(name=name, defaults=defaults)
        return target


class TaskStatus(ChoicesIntEnum):
    created = 0
    queued = 1
    busy = 2
    success = 4
    error = 5
    corrupted = 6


@six.python_2_unicode_compatible
class TaskInfo(models.Model):
    created = models.DateTimeField(auto_now_add=True)
    executed = models.DateTimeField(blank=True, null=True)
    ts = models.DateTimeField(auto_now=True)
    attempts = models.PositiveSmallIntegerField(default=0)
    eta = models.DateTimeField(null=True, blank=True)
    target = models.ForeignKey(TaskTarget)
    payload = models.CharField(max_length=300, null=True, blank=True)
    status = models.IntegerField(default=TaskStatus.created, choices=TaskStatus.choices())
    status_message = models.TextField(default=None, blank=None, null=True)

    class Meta:
        index_together = ('id', 'status')

    def __str__(self):
        return "TaskInfo:{}:{}.{}".format(self.pk, self.target, self.get_status_display())

    @classmethod
    def queue(cls, target, args, kwargs, queue='default', rate_limit=None):

        logging.debug("method.__name__: %s", target.__name__)

        payload = {}
        if args:
            payload['args'] = args
        if kwargs:
            payload['kwargs'] = kwargs
        if isinstance(target, types.MethodType) and isinstance(target.__self__, models.Model):
            payload['model_pk'] = getattr(target.__self__, 'pk')
        payload = json.dumps(payload) if payload else None

        target_name = target.__module__ + '.' + target.__qualname__
        target = TaskTarget.objects.filter(name=target_name).first()
        if target is None:
            queue, created = TaskQueue.objects.get_or_create(name=queue, defaults={'rate_limit': rate_limit})
            target, created = TaskTarget.objects.get_or_create(name=target_name, defaults={'queue': queue})

        eta = datetime.now()
        cls.objects.create(
            target=target,
            payload=payload,
            eta=eta,
            status=TaskStatus.queued,
        )

    def execute(self):
        try:
            where, target, args, kwargs = self.prepare_call()
            self._execute_call(where, target, args, kwargs)
        except Exception as ex:
            logging.warning("{} execution failed".format(str(self)), exc_info=ex)
            self.error(self.get_error_status_message(ex), status=TaskStatus.corrupted)

    def _execute_call(self, where, target, args, kwargs):
        logging.info("Executing task:%s", self.target)
        try:
            with transaction.atomic():
                target(where, *args, **kwargs)
        except RetryLaterException as ex:
            if settings.TASKER_ALWAYS_EAGER:
                logging.error("Failing permanently on task in eager mode", exc_info=ex)
                # there is no point in retrying this in eager mode, it fail each time
                return
            logging.warning(exc_info=ex)
            self.eta = datetime.now() + timedelta(seconds=ex.countdown)
            self.save()

        except Exception as exc:
            logging.warning("{} execution failed".format(str(self)))
            self.error(self.get_error_status_message(exc))
        else:
            self.success()

    def prepare_call(self):
        payload = json.loads(self.payload) if self.payload else {}
        args, kwargs, model_pk = payload.get('args', []), payload.get('kwargs', {}), payload.get('model_pk', None)
        where, target = self.target.name.rsplit('.', 1)
        where = import_string(where)
        if model_pk:
            where = where.objects.get(pk=model_pk)
        target = getattr(where, target)
        return where, target, args, kwargs

    @classmethod
    def process_one(cls, pk):
        try:
            with transaction.atomic():
                task = cls.objects.select_for_update(nowait=True).filter(pk=pk, status=TaskStatus.queued).first()
                if task is None:
                    return
                task.status = TaskStatus.busy
                task.save()
        except DatabaseError:
            # This will happen if another worker took this task
            # https://docs.djangoproject.com/en/1.10/ref/models/querysets/#select-for-update
            pass
        else:
            task.execute()

    def success(self):
        self.status = TaskStatus.success
        self.executed = timezone.now()
        self.attempts += 1
        self.save()

    def error(self, status_message, status=TaskStatus.error):
        self.status = status
        self.status_message = status_message
        self.attempts += 1
        self.save()

    def get_error_status_message(self, ex):
        return str(ex)


def get_retry_countdown(retries):
    return {
        0: 30,
        1: 60,
        2: 300,
    }.get(retries, 3600)


class RetryLaterException(Exception):
    def __init__(self, countdown, message):
        self.message = message
        self.countdown = countdown

    def __str__(self):
        return "RetryLaterException: countdown={}, {}".format(self.countdown, self.message)


def queueable(*args, **options):
    def decorator(func):
        @six.wraps(func)
        def proxy(*args, **kwargs):
            return func(*args, **kwargs)

        def queue(*args, **kwargs):
            return TaskInfo.queue(func, args, kwargs, **options)

        proxy.queue = queue
        return proxy

    if len(args) == 1 and callable(args[0]):
        return decorator(args[0])
    return decorator
