# coding=utf-8
# Copyright (c) 2016 Janusz Skonieczny

from __future__ import absolute_import
from __future__ import unicode_literals

import json
import logging
import os
import threading
from datetime import date, datetime, timedelta

import six
from django.conf import settings
from django.contrib import admin
from django.core.mail import EmailMultiAlternatives
from django.core.mail import send_mail
from django.core.management import call_command, execute_from_command_line
from django.db import transaction
from django.test.testcases import TransactionTestCase
from django.test.utils import modify_settings, override_settings
from django.utils import timezone
from django.utils.timezone import is_naive, is_aware
from mock import patch, MagicMock

from django.test import TestCase

from django_tasker import exceptions
from django_tasker.models import TaskInfo
from django_tasker.decoration import queueable
from django_tasker import models, admin
from . import factories


class TaskInfoDecoratorTests(TestCase):
    def test_no_queue(self):
        @queueable
        def foo(a):
            return a

        self.assertEqual(1, foo(1))
        self.assertEqual('a', foo('a'))

    def test_decorate_no_args(self):
        @queueable
        def foo():
            return 1

        self.assertIsNotNone(foo.queue)
        self.assertTrue(callable(foo.queue))

    def test_decorate_with_options(self):
        @queueable(queue="some")
        def foo():
            return 1

        self.assertIsNotNone(foo.queue)
        self.assertTrue(callable(foo.queue))

    @patch("django_tasker.models.TaskInfo.queue")
    def test_queue(self, queue):
        @queueable(queue="some")
        def foo():
            return 1

        foo.queue(1, 2, a='b')
        queue.assert_called_with(1, 2, a='b')

    @patch("django_tasker.models.TaskInfo.setup")
    def test_setup(self, setup):
        @queueable(queue="some")
        def foo():
            return 1

        foo.queue(1, 2, a='b')
        setup.assert_called_with(foo.__wrapped__, None, queue='some')

    def test_no_call_no_create_missing_queue(self):
        @queueable(queue="some")
        def foo():
            return 1

        self.assertIsNone(models.TaskQueue.objects.filter(name='some').first())

    def test_create_missing_queue(self):
        @queueable(queue="some")
        def foo():
            return 1

        foo.queue(1, 2, a='b')
        queue = models.TaskQueue.objects.filter(name='some').first()
        self.assertIsNotNone(queue)
        self.assertIsNone(queue.rate_limit)

    def test_set_rate_limit(self):
        @queueable(queue="some", rate_limit=12)
        def foo():
            return 1

        foo.queue(1, 2, a='b')
        queue = models.TaskQueue.objects.filter(name='some').first()
        self.assertIsNotNone(queue)
        self.assertEqual(12, queue.rate_limit)


class TaskInfoInstanceTests(TestCase):
    def test_queue_on_model_instance(self):
        stub = models.TaskQueue.objects.create()
        queueable(stub.process_batch).queue(1, 2, some='foo')  # Re-use existing model as decorator target
        o = TaskInfo.objects.last()
        self.assertEqual('django_tasker.models.TaskQueue.process_batch', o.target.name)
        self.assertEqual(stub.pk, json.loads(o.payload)['pk'])
        self.assertEqual(json.dumps({'args': [1, 2], 'kwargs': {'some': 'foo'}, "pk": 1}), o.payload)
        self.assertIsNotNone(o.eta)
        self.assertEqual(models.TaskStatus.queued, o.status)

    def test_execute_arguments(self):
        stub = models.TaskQueue.objects.create()
        queueable(stub.process_batch).queue(1, 2, some='foo')  # Re-use existing model as decorator target
        o = TaskInfo.objects.last()
        with patch("django_tasker.models.TaskQueue.process_batch") as method:
            o.execute()
            method.assert_called_with(1, 2, some='foo')

    def test_execute_smoke(self):
        stub = models.TaskQueue.objects.create()
        queueable(stub.throttle).queue('ignored but needed by test')  # Re-use existing model as decorator target
        o = TaskInfo.objects.last()
        o.execute()
        self.assertEqual(None, o.status_message)
        self.assertEqual(o.status, models.TaskStatus.success)

    def test_success_status(self):
        queueable(models.TaskQueue.throttle).queue()  # Re-use existing model as decorator target
        o = TaskInfo.objects.last()
        with patch("django_tasker.models.TaskQueue.throttle") as method:
            o.execute()
        self.assertIsNone(o.status_message)
        self.assertEqual(models.TaskStatus.success, o.status)


class TaskInfoNonInstanceTests(TestCase):
    def test_queue_on_class_method(self):
        queueable(models.TaskQueue.throttle).queue(1, 2, some='foo')  # Re-use existing model as decorator target
        o = TaskInfo.objects.last()
        self.assertEqual('django_tasker.models.TaskQueue.throttle', o.target.name)
        self.assertEqual(json.dumps({'args': [1, 2], 'kwargs': {'some': 'foo'}}), o.payload)
        self.assertIsNotNone(o.eta)
        self.assertEqual(models.TaskStatus.queued, o.status)

    def test_execute(self):
        queueable(models.TaskQueue.throttle).queue(1, 2, some='foo')
        o = TaskInfo.objects.first()
        with patch("django_tasker.models.TaskQueue.throttle") as method:
            o.execute()
            method.assert_called_with(1, 2, some='foo')

    def test_execute_smoke(self):
        t = queueable(models.TaskInfo.process_one).queue(213412)  # Re-use existing model as decorator target
        self.assertEqual('django_tasker.models.TaskInfo.process_one', t.target.name)
        o = TaskInfo.objects.last()
        o.execute()
        self.assertEqual(None, o.status_message)
        self.assertEqual(o.status, models.TaskStatus.success)


class TaskInfoModuleFunction(TestCase):
    def test_queue(self):
        @queueable(queue="some")
        def foo():
            return 1

        foo.queue(1, 2, a='b')
        o = TaskInfo.objects.last()
        self.assertEqual('tests.tests.TaskInfoModuleFunction.test_queue.<locals>.foo', o.target.name)
        self.assertEqual(json.dumps({'args': [1, 2], 'kwargs': {'a': 'b'}}), o.payload)
        self.assertIsNotNone(o.eta)
        self.assertEqual(models.TaskStatus.queued, o.status)


class TaskInfoTests(TestCase):
    @patch('django_tasker.models.TaskInfo.execute')
    def test_process_one(self, execute):
        t = factories.TaskInfoFactory(status=models.TaskStatus.queued)
        models.TaskInfo.process_one(t.pk)
        execute.assert_called_with()
        models.TaskInfo.process_one(t.pk)
        self.assertEqual(1, execute.call_count)

    @patch('django_tasker.models.TaskInfo.execute')
    def test_process_one_retry(self, execute):
        t = factories.TaskInfoFactory(status=models.TaskStatus.retry)
        models.TaskInfo.process_one(t.pk)
        execute.assert_called_with()
        models.TaskInfo.process_one(t.pk)
        self.assertEqual(1, execute.call_count)

    def test_retry(self):
        t = factories.TaskInfoFactory()
        t._execute_call(1, None, None)
        self.assertEqual(models.TaskStatus.retry, t.status)
        self.assertEqual(1, t.retry_count)
        t._execute_call(1, None, None)
        self.assertEqual(2, t.retry_count)
        self.assertEqual(models.TaskStatus.retry, t.status)
        t.retry_count = 5
        t._execute_call(1, None, None)
        self.assertEqual(models.TaskStatus.error, t.status)

    def test_get_target_name_from_subclass_instance(self):
        from tests.app.models import SomeModel
        t = SomeModel.objects.create().process_me.queue()
        self.assertEqual('tests.app.models.SomeModel.process_me', t.target.name)

    def test_get_target_name_subclass_instance(self):
        from tests.app.models import SomeModel
        v = models.TaskInfo.get_target_name(SomeModel.process_me, SomeModel())
        self.assertEqual('tests.app.models.SomeModel.process_me', v)

    def test_get_target_name_subclass_instance2(self):
        from tests.app.models import SomeModel
        v = models.TaskInfo.get_target_name(SomeModel().process_me, None)
        self.assertEqual('tests.app.models.BaseModel.process_me', v)

    def test_get_target_name_subclass_class_method(self):
        from tests.app.models import SomeModel
        v = models.TaskInfo.get_target_name(SomeModel.process_me, None)
        self.assertEqual('tests.app.models.BaseModel.process_me', v)

    def test_get_target_name_subclass_instance_plain(self):
        from tests.app.models import SomeModel
        v = models.TaskInfo.get_target_name(SomeModel.no_queable, SomeModel())
        self.assertEqual('tests.app.models.SomeModel.no_queable', v)

    def test_get_target_name_subclass_instance2_plain(self):
        from tests.app.models import SomeModel
        v = models.TaskInfo.get_target_name(SomeModel().no_queable, None)
        self.assertEqual('tests.app.models.SomeModel.no_queable', v)

    def test_get_target_name_subclass_class_method_plain(self):
        from tests.app.models import SomeModel
        v = models.TaskInfo.get_target_name(SomeModel.no_queable, None)
        # Unbound (or just) functions don't know where there where taken from
        self.assertEqual('tests.app.models.BaseModel.no_queable', v)

    def test_is_not_unique(self):
        a = factories.TaskInfoFactory.create(status=models.TaskStatus.queued, payload="{}")
        b = factories.TaskInfoFactory.build(status=models.TaskStatus.queued, payload=a.payload, eta=a.eta, target=a.target)
        self.assertFalse(b.is_unique('{}'))

    def test_is_unique_fail(self):
        a = factories.TaskInfoFactory.create()
        self.assertRaises(AssertionError, a.is_unique, '{}')

    @patch('django_tasker.models.TaskInfo._get_payload')
    def test_queue_once_fail(self, get_payload):
        get_payload.return_value = None
        a = factories.TaskInfoFactory.create()
        self.assertRaises(AssertionError, a.queue_once)

    def test_is_unique(self):
        a = factories.TaskInfoFactory.create(status=models.TaskStatus.queued, payload="{}")
        b = factories.TaskInfoFactory.build(status=a.status, payload="{a}", eta=a.eta)
        self.assertTrue(b.is_unique('{}'))
        b = factories.TaskInfoFactory.build(status=a.status, target=a.target,  payload="{}", eta=a.eta + timedelta(seconds=1))
        self.assertNotEqual(a.eta, b.eta)
        self.assertTrue(b.is_unique('{}'))

    @override_settings(TASKER_ALWAYS_EAGER=False)
    def test_queue_once(self):
        dummy = factories.TaskQueueFactory()
        eta = timezone.now()
        models.TaskInfo.setup(dummy.throttle, dummy, eta=eta).queue()
        models.TaskInfo.setup(dummy.throttle, dummy, eta=eta).queue_once()
        self.assertEqual(1, TaskInfo.objects.count())

    def test_countdown(self):
        dummy = factories.TaskInfoFactory.create()
        when = timezone.now()
        task = models.TaskInfo.setup(dummy.is_unique, dummy, countdown=5)
        self.assertAlmostEqual(when + timedelta(seconds=5), task.eta, delta=timedelta(milliseconds=2))


# TODO: Test select_for_update
# class TaskInfoTestsTx(TransactionTestCase):
#     @patch('django_tasker.models.TaskInfo.execute')
#     def test_process_one(self, execute):
#         t = factories.TaskInfoFactory()
#         models.TaskInfo.process_one(t.pk)
#         execute.assert_called_with()
#         def another_call():
#             models.TaskInfo.process_one(t.pk)
#         thread = threading.Thread(target=another_call)
#         thread.start()
#         thread.join()
#         self.assertEqual(1, execute.call_count)


class TaskInfoAdminTests(TestCase):
    @patch("django_tasker.admin.messages")
    @patch("django_tasker.models.TaskInfo.execute")
    def test_execute_tasks(self, execute, messages):
        factories.TaskInfoFactory.create_batch(9)
        admin.TaskInfoAdmin.execute_tasks(None, None, models.TaskInfo.objects.all()[3:6])
        self.assertEqual(3, execute.call_count)
        self.assertTrue(messages.info.called)

    @patch("django_tasker.admin.messages")
    def test_set_retry_status(self, messages):
        tasks = factories.TaskInfoFactory.create_batch(9, status=models.TaskStatus.error)
        factories.TaskInfoFactory.create_batch(3, status=models.TaskStatus.retry)
        admin.TaskInfoAdmin.set_retry_status(None, None, models.TaskInfo.objects.filter(id__in=[t.pk for t in tasks[3:6]]))
        self.assertEqual(6, models.TaskInfo.objects.filter(status=models.TaskStatus.retry).count())
        self.assertTrue(messages.info.called)

    @patch("django_tasker.admin.messages")
    def test_reset_retry_count(self, messages):
        tasks = factories.TaskInfoFactory.create_batch(9, retry_count=5)
        admin.TaskInfoAdmin.reset_retry_count(None, None, models.TaskInfo.objects.filter(id__in=[t.pk for t in tasks[3:6]]))
        self.assertEqual(3, models.TaskInfo.objects.filter(retry_count=0).count())
        self.assertTrue(messages.info.called)

    @patch("django_tasker.admin.messages")
    def test_delete_completed(self, messages):
        factories.TaskInfoFactory.create_batch(10)
        factories.TaskInfoFactory.create_batch(3, status=models.TaskStatus.success)
        count = models.TaskInfo.objects.filter(status=models.TaskStatus.success).count()
        admin.TaskInfoAdmin.delete_completed(None, None, None)
        self.assertEqual(13 - count, models.TaskInfo.objects.count())


class TaskQueueTests(TestCase):
    @patch("time.sleep")
    def test_no_throttling(self, sleep):
        q = models.TaskQueue()
        q.throttle(timedelta(seconds=1))
        self.assertFalse(sleep.called)

    @patch("django_tasker.models.sleep")
    def test_throttle(self, sleep):
        q = models.TaskQueue(rate_limit=60)
        q.throttle(timedelta(seconds=1))
        sleep.assert_called_with(59)

    def test_time_interval(self):
        q = models.TaskQueue(rate_limit=1800)
        self.assertEqual(q.time_interval.total_seconds(), 2)

    @patch("django_tasker.models.sleep")
    def test_reamaining_throttle_empty(self, sleep):
        q = models.TaskQueue(max_tasks_per_hour=3600)
        q.throttle(timedelta(seconds=1))
        self.assertFalse(sleep.called)

    @patch("django_tasker.models.sleep")
    def test_reamaining_throttle_empty(self, sleep):
        q = models.TaskQueue(rate_limit=3600)
        q.throttle(timedelta(seconds=2))
        self.assertFalse(sleep.called)

    @patch('django_tasker.models.TaskInfo.process_one')
    def test_process_batch(self, process_one):
        task = factories.TaskInfoFactory(status=models.TaskStatus.queued, eta=datetime.now())
        q = task.target.queue
        empty_run = q.process_batch()
        self.assertFalse(empty_run)
        process_one.assert_called_with(task.pk)

    @patch('django_tasker.models.TaskInfo.process_one')
    def test_process_future(self, process_one):
        task = factories.TaskInfoFactory(status=models.TaskStatus.queued, eta=datetime.now() + timedelta(hours=1))
        q = task.target.queue
        empty_run = q.process_batch()
        self.assertTrue(empty_run)
        self.assertFalse(process_one.called)

    @patch('django_tasker.models.TaskInfo.process_one')
    def test_process_not_ququed(self, process_one):
        task = factories.TaskInfoFactory(status=models.TaskStatus.created, eta=datetime.now())
        q = task.target.queue
        q.process_batch()
        self.assertFalse(process_one.called)

    @override_settings(USE_TZ=True)
    def test_queue(self):
        task = models.TaskInfo.setup(lambda: 1, None)
        self.assertTrue(is_aware(task.eta))

    @patch('django_tasker.models.sleep')
    def test_back_off_time(self, sleep):
        worker = factories.TaskQueueFactory()
        s = worker.on_error_back_off(None, Exception())
        base_seconds = models.TaskQueue._meta.get_field('back_off_base_seconds').default
        back_off_max_seconds = models.TaskQueue._meta.get_field('back_off_max_seconds').default
        back_off_multiplier = models.TaskQueue._meta.get_field('back_off_multiplier').default
        sleep.assert_called_with(base_seconds)
        s = worker.on_error_back_off(s, Exception())
        sleep.assert_called_with(base_seconds * back_off_multiplier)
        s = worker.on_error_back_off(s, Exception())
        sleep.assert_called_with(base_seconds * back_off_multiplier ** 2)
        s = worker.on_error_back_off(s, Exception())
        sleep.assert_called_with(base_seconds * back_off_multiplier ** 3)
        s = worker.on_error_back_off(s, Exception())
        sleep.assert_called_with(base_seconds * back_off_multiplier ** 4)
        s = worker.on_error_back_off(s, Exception())
        sleep.assert_called_with(base_seconds * back_off_multiplier ** 5)
        s = worker.on_error_back_off(s, Exception())
        sleep.assert_called_with(back_off_max_seconds)

    def test_retry_busy_timeouts(self):
        queue = factories.TaskQueueFactory()
        factories.TaskInfoFactory.create_batch(3, status=models.TaskStatus.busy, target__queue=queue)
        when = timezone.now() - timedelta(seconds=models.TaskQueue._meta.get_field('busy_max_seconds').default)
        # Update in db, cause ts has auto_now=True
        models.TaskInfo.objects.filter(status=models.TaskStatus.busy).update(ts=when)
        factories.TaskInfoFactory.create_batch(10, target__queue=queue)
        rows = queue.retry_busy_timeouts()
        self.assertEqual(3, rows)


class TestAppTests(TestCase):
    def test_queue_base_method_runs_on_subclass(self):
        from tests.app.models import SomeModel
        o = SomeModel.objects.create()
        o.process_me.setup_task(max_retries=0).queue()
        t = models.TaskInfo.objects.first()
        t.execute()
        self.assertEqual(None, t.status_message)
        self.assertEqual(models.TaskStatus.success, t.status)

    def test_do_stuff(self):
        from tests.app.models import SomeModel
        o = SomeModel.objects.create()
        o.do_stuff.setup_task(max_retries=0).queue()
        t = models.TaskInfo.objects.first()
        t.execute()
        self.assertEqual(None, t.status_message)
        self.assertEqual(models.TaskStatus.success, t.status)

    def test_do_stuff_fails_not_saved_instance(self):
        from tests.app.models import SomeModel
        o = SomeModel()
        self.assertRaises(AssertionError, o.do_stuff.queue)

    def test_do_whole_other_stuff(self):
        from tests.app.models import SomeModel
        SomeModel.do_whole_other_stuff.setup_task(max_retries=0).queue()
        t = models.TaskInfo.objects.first()
        t.execute()
        self.assertEqual(None, t.status_message)
        self.assertEqual(models.TaskStatus.success, t.status)


class TestWorker(TestCase):
    @patch('django_tasker.models.sleep')
    def test_sleep_on_no_work(self, sleep):
        worker = factories.TaskWorkerFactory()
        worker.run_once()
        sleep.assert_called_with(10)

    @patch('django_tasker.models.sleep')
    def test_no_sleep_when_work_done(self, sleep):
        from tests.app.models import SomeModel
        task = SomeModel.objects.create().do_stuff.queue()
        worker = factories.TaskWorkerFactory(queue=task.target.queue)
        worker.run_once()
        self.assertFalse(sleep.called)

    @patch('django_tasker.models.TaskQueue.on_error_back_off')
    def test_sleep_on_erorr(self, on_error_back_off):
        worker = factories.TaskWorkerFactory()
        worker.queue.process_batch = MagicMock()
        ex = Exception()
        worker.queue.process_batch.side_effect = ex
        worker.run_once()
        on_error_back_off.assert_called_with(None, ex)

    @patch('django_tasker.models.TaskQueue.process_batch')
    @patch('django_tasker.models.TaskQueue.retry_busy_timeouts')
    def test_retry_busy_timeouts_called(self, retry_busy_timeouts, process_batch):
        worker = factories.TaskWorkerFactory()
        process_batch.return_value = False
        worker.run_once()
        self.assertTrue(retry_busy_timeouts.called)


class RetryLaterExceptionTests(TestCase):
    @override_settings(USE_TZ=True)
    def test_naive_eta_tz(self):
        ex = exceptions.RetryLaterException('', eta=datetime.now())
        self.assertIsNotNone(ex.eta.tzinfo)

    @override_settings(USE_TZ=True)
    def test_no_eta_tz(self):
        ex = exceptions.RetryLaterException('', countdown=3)
        self.assertIsNotNone(ex.eta.tzinfo)

    @override_settings(USE_TZ=True)
    def test_aware_eta_tz(self):
        ex = exceptions.RetryLaterException('', eta=timezone.now())
        self.assertIsNotNone(ex.eta.tzinfo)

    @override_settings(USE_TZ=False)
    def test_naive_eta_no_tz(self):
        ex = exceptions.RetryLaterException('', eta=datetime.now())
        self.assertIsNone(ex.eta.tzinfo)

    @override_settings(USE_TZ=False)
    def test_aware_eta_no_tz(self):
        ex = exceptions.RetryLaterException('', eta=timezone.now())
        self.assertIsNone(ex.eta.tzinfo)
