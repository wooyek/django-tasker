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
from django.utils.timezone import is_naive, is_aware
from mock import patch, MagicMock

from django.test import TestCase

from django_tasker.models import TaskInfo
from django_tasker.decoration import queueable
from django_tasker import models
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
        self.assertEqual(stub.pk, json.loads(o.payload)['model_pk'])
        self.assertEqual(json.dumps({'args': [1, 2], 'kwargs': {'some': 'foo'}, "model_pk": 1}), o.payload)
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
        queueable(models.TaskInfo.process_one).queue(213412)  # Re-use existing model as decorator target
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
        t = factories.TaskInfoFactory()
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
