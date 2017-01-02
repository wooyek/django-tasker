# coding=utf-8
import json
import logging
import signal
from datetime import datetime, timedelta
from enum import IntEnum
from threading import Thread
from time import sleep

import six
from django.conf import settings
from django.db import DatabaseError
from django.db import models
from django.db import transaction
from django.utils import timezone
from django.utils.module_loading import import_string
from django.utils.translation import ugettext_lazy as _

from django_tasker.exceptions import RetryLaterException

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
        self.back_off_seconds = None

    def __call__(self):
        logging.info("Worker booting for queue: %s", self.queue)
        while True:
            if self._stop_requested:
                logging.info('Stopping on request')
                break
            self.run_once()

    def run_once(self):
        queue = self.queue
        try:
            queue.retry_busy_timeouts()
            emtpy_run = queue.process_batch()
        except Exception as ex:
            self.back_off_seconds = queue.on_error_back_off(self.back_off_seconds, ex)
        else:
            self.back_off_seconds = None
            if emtpy_run:
                seconds = getattr(settings, 'TASKER_SLEEP_TIME', 10)
                logging.debug("Queue %s had empty run, it will sleep for %s seconds", queue.name, seconds)
                sleep(seconds)

    def request_stop(self):
        self._stop_requested = True

    @classmethod
    def run_queues(cls, queue_names):
        logging.info("Running workers for queues: %s if they are enabled", queue_names)
        qry = TaskQueue.objects.filter(status=QueueStatus.enabled)
        if queue_names:
            qry = qry.filter(name__in=queue_names)
        workers = [cls(q) for q in qry]
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
    back_off_base_seconds = models.PositiveSmallIntegerField(default=60)
    back_off_max_seconds = models.PositiveIntegerField(default=86400)
    back_off_multiplier = models.FloatField(default=4)
    busy_max_seconds = models.PositiveIntegerField(default=3600)

    def __init__(self, *args, **kwargs):
        super(TaskQueue, self).__init__(*args, **kwargs)
        if self.rate_limit:
            self.time_interval = timedelta(seconds=3600 / self.rate_limit)

    def __str__(self):
        return "TaskQueue:{}:{}.{}".format(self.pk, self.name, self.get_status_display())

    def process_batch(self, limit=1):
        qry = TaskInfo.objects.filter(eta__lte=timezone.now(), status__in=(TaskStatus.queued, TaskStatus.retry), target__queue=self)
        batch = qry.values_list('id', flat=True)[:limit]
        empty_run = True
        for pk in batch:
            empty_run = False
            start = datetime.now()
            if TaskInfo.process_one(pk):
                self.throttle(datetime.now() - start)
        return empty_run

    def throttle(self, duration):
        if self.rate_limit:
            wait = self.time_interval - duration
            if wait > timedelta():
                logging.debug("Throttle limiting for seconds: %s", wait.total_seconds())
                sleep(wait.seconds)

    def on_error_back_off(self, seconds, ex):
        if seconds is None:
            seconds = self.back_off_base_seconds
        else:
            seconds *= self.back_off_multiplier
        logging.error("Work failed on %s, backing off for %s seconds", self.name, seconds, exc_info=ex)
        sleep(min(seconds, self.back_off_max_seconds))
        return seconds

    def retry_busy_timeouts(self):
        when = timezone.now() - timedelta(seconds=self.busy_max_seconds)
        rows = TaskInfo.objects.filter(ts__lte=when, status=TaskStatus.busy, target__queue=self).update(status=TaskStatus.retry)
        if rows:
            logging.info("Retrying busy %s timeouts in %s queue", rows, self)
        return rows


@six.python_2_unicode_compatible
class TaskTarget(models.Model):
    name = models.CharField(max_length=100, unique=True)
    queue = models.ForeignKey(TaskQueue)
    max_retries = models.PositiveSmallIntegerField(default=5)

    def __str__(self):
        return self.name


class TaskStatus(ChoicesIntEnum):
    created = 0
    queued = 1
    eager = 2
    retry = 3
    busy = 4
    success = 5
    error = 6
    corrupted = 7


@six.python_2_unicode_compatible
class TaskInfo(models.Model):
    created = models.DateTimeField(auto_now_add=True)
    executed = models.DateTimeField(blank=True, null=True)
    ts = models.DateTimeField(auto_now=True, db_index=True)
    retry_count = models.PositiveSmallIntegerField(default=0, db_index=True)
    eta = models.DateTimeField(null=True, blank=True, db_index=True)
    target = models.ForeignKey(TaskTarget)
    payload = models.CharField(max_length=300, null=True, blank=True)
    status = models.IntegerField(default=TaskStatus.created, choices=TaskStatus.choices())
    status_message = models.TextField(default=None, blank=None, null=True)

    class Meta:
        index_together = (
            ('id', 'eta', 'status'),
            ('id', 'target'),
            ('target', 'status'),
            ('target', 'eta'),
        )

    def __str__(self):
        return "TaskInfo:{}:{}:{}:{}:{}".format(self.pk, self.get_status_display(), self.target, self.retry_count, self.eta)

    @classmethod
    def setup(cls, target, instance, queue='default', rate_limit=None, countdown=0, eta=None, max_retries=5):
        logging.debug("method.__name__: %s", target.__name__)
        now = timezone.now()
        eta = eta or (now + timedelta(seconds=countdown))
        target_name = cls.get_target_name(target, instance)
        target = TaskTarget.objects.filter(name=target_name).first()
        if target is None:
            queue, created = TaskQueue.objects.get_or_create(name=queue, defaults={'rate_limit': rate_limit})
            target, created = TaskTarget.objects.get_or_create(name=target_name, defaults={'queue': queue, 'max_retries': max_retries})

        eager = getattr(settings, 'TASKER_ALWAYS_EAGER', None)
        task = cls(target=target, eta=eta, status=TaskStatus.eager if eager else TaskStatus.queued, )
        task.instance = instance
        return task

    @staticmethod
    def get_target_name(target, instance):
        instance = instance or getattr(target, '__self__', None)
        # class methods will have __self__ set with class
        if instance and not isinstance(instance, type):
            target_name = '.'.join((instance.__module__, instance.__class__.__name__, target.__name__))
        else:
            target_name = '.'.join((target.__module__, target.__qualname__))
        return target_name

    def queue_once(self, *args, **kwargs):
        """Queue this task only if another similar task does not exits already"""
        payload = self._get_payload(args, kwargs)
        if self.is_unique(payload):
            return self._queue_payload(payload)

    def is_unique(self, payload):
        assert self.pk is None, "Checking for uniques is not supported for saved tasks"
        return not TaskInfo.objects.filter(
            eta=self.eta,
            target=self.target,
            payload=payload,
        ).exists()

    def queue(self, *args, **kwargs):
        payload = self._get_payload(args, kwargs)
        return self._queue_payload(payload)

    def _queue_payload(self, payload):
        self.payload = payload
        self.save()
        if self.status == TaskStatus.eager:
            self.execute()
        return self

    def _get_payload(self, args, kwargs):
        payload = {}
        if args:
            payload['args'] = args
        if kwargs:
            payload['kwargs'] = kwargs
        if isinstance(self.instance, models.Model):
            assert hasattr(self.instance, 'pk'), "Model instance must have a 'pk' attribute, so task can store it for retrieval before execution"
            pk = getattr(self.instance, 'pk')
            assert pk is not None, "Model instance must be saved and have a 'pk' value, before it's method can be queued. Alternatively you can use queue a classmethod without pk set"
            payload['pk'] = pk
        return json.dumps(payload) if payload else None

    def execute(self):
        logging.info("Executing task:%s", self.target)
        try:
            target, args, kwargs = self.prepare_call()
            self._execute_call(target, args, kwargs)
        except Exception as ex:
            logging.warning("{} execution failed".format(str(self)), exc_info=ex)
            self.error(self.get_error_status_message(ex), status=TaskStatus.corrupted)

    def _execute_call(self, target, args, kwargs):
        try:
            with transaction.atomic():
                target(*args, **kwargs)
        except RetryLaterException as ex:
            self.retry(ex)
        except Exception as ex:
            self.error(ex)
        else:
            self.success()

    def prepare_call(self):
        payload = json.loads(self.payload) if self.payload else {}
        args = payload.get('args', [])
        kwargs = payload.get('kwargs', {})
        pk = payload.get('pk', None)
        where, target = self.target.name.rsplit('.', 1)
        where = import_string(where)
        if pk:
            where = where.objects.get(pk=pk)
        target = getattr(where, target)
        return target, args, kwargs

    @classmethod
    def process_one(cls, pk):
        try:
            with transaction.atomic():
                qry = cls.objects.select_for_update(nowait=True)
                task = qry.filter(pk=pk, status__in=(TaskStatus.queued, TaskStatus.retry)).first()
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
            return task

    def success(self):
        self.status = TaskStatus.success
        self.executed = timezone.now()
        self.save()

    def retry(self, ex, status=TaskStatus.retry):
        # This is a task controlled retry, it does not count toward max_retries
        # if tasks wants to retry indefinitely we will not object
        if getattr(settings, 'TASKER_ALWAYS_EAGER', None):
            logging.error("Failing permanently on task in eager mode", exc_info=ex)
            # there is no point in retrying this in eager mode, it fail each time
            return
        logging.warning("Retrying on task request", exc_info=ex)
        self.eta = ex.eta
        self.status_message = self.get_error_status_message(ex)
        self.status = status
        self.save()

    def error(self, ex, status=TaskStatus.error):
        logging.error("{} execution failed".format(str(self)), exc_info=True)
        self.status = status
        self.status_message = self.get_error_status_message(ex)
        self.retry_count += 1

        if self.retry_count <= self.target.max_retries:
            self.status = TaskStatus.retry
            countdown = get_retry_countdown(self.retry_count)
            self.eta = timezone.now() + timedelta(seconds=countdown)
        else:
            logging.error("Exceed max_retries on task %s", self, exc_info=ex)
        self.save()

    # noinspection PyMethodMayBeStatic
    def get_error_status_message(self, ex):
        return str(ex)


def get_retry_countdown(retries):
    return {
        0: 30,
        1: 60,
        2: 300,
        3: 1200,
    }.get(retries, 3600)
