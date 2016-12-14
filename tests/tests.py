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
from mock import patch, MagicMock

from django.test import TestCase

from django_tasker.models import queueable, TaskInfo
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
        @queueable(name="some")
        def foo():
            return 1

        self.assertIsNotNone(foo.queue)
        self.assertTrue(callable(foo.queue))

    @patch("django_tasker.models.TaskInfo.queue")
    def test_queue(self, queue):
        @queueable(name="some")
        def foo():
            return 1

        foo.queue(1, 2, a='b')
        queue.assert_called_with(foo.__wrapped__, (1, 2), {'a': 'b'}, name='some')


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

    def test_execute(self):
        stub = models.TaskQueue.objects.create()
        queueable(stub.process_batch).queue(1, 2, some='foo')  # Re-use existing model as decorator target
        o = TaskInfo.objects.last()
        with patch("django_tasker.models.TaskQueue.process_batch") as method:
            o.execute()
            method.assert_called_with(stub, 1, 2, some='foo')

    def test_success_status(self):
        queueable(models.TaskQueue.get_default).queue()  # Re-use existing model as decorator target
        o = TaskInfo.objects.last()
        with patch("django_tasker.models.TaskQueue.get_default") as method:
            o.execute()
        self.assertIsNone(o.status_message)
        self.assertEqual(models.TaskStatus.success, o.status)


class TaskInfoNonInstanceTests(TestCase):
    def test_queue_on_class_method(self):
        queueable(models.TaskQueue.get_default).queue(1, 2, some='foo')  # Re-use existing model as decorator target
        o = TaskInfo.objects.last()
        self.assertEqual('django_tasker.models.TaskQueue.get_default', o.target.name)
        self.assertEqual(json.dumps({'args': [1, 2], 'kwargs': {'some': 'foo'}}), o.payload)
        self.assertIsNotNone(o.eta)
        self.assertEqual(models.TaskStatus.queued, o.status)

    def test_execute(self):
        queueable(models.TaskQueue.get_default).queue(1, 2, some='foo')
        o = TaskInfo.objects.first()
        with patch("django_tasker.models.TaskQueue.get_default") as method:
            o.execute()
            method.assert_called_with(models.TaskQueue, 1, 2, some='foo')


class TaskInfoModuleFunction(TestCase):
    def test_queue(self):
        @queueable(name="some")
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
        q = models.TaskQueue(max_tasks_per_hour=60)
        q.throttle(timedelta(seconds=1))
        sleep.assert_called_with(59)

    @patch("django_tasker.models.sleep")
    def test_reamaining_throttle_empty(self, sleep):
        q = models.TaskQueue(max_tasks_per_hour=3600)
        q.throttle(timedelta(seconds=1))
        self.assertFalse(sleep.called)

    @patch("django_tasker.models.sleep")
    def test_reamaining_throttle_empty(self, sleep):
        q = models.TaskQueue(max_tasks_per_hour=3600)
        q.throttle(timedelta(seconds=2))
        self.assertFalse(sleep.called)

    @patch('django_tasker.models.TaskInfo.process_one')
    def test_process_batch(self, process_one):
        task = factories.TaskInfoFactory(status=models.TaskStatus.queued, eta=datetime.now())
        q = models.TaskQueue.get_default()
        empty_run = q.process_batch()
        self.assertFalse(empty_run)
        process_one.assert_called_with(task.pk)

    @patch('django_tasker.models.TaskInfo.process_one')
    def test_process_future(self, process_one):
        task = factories.TaskInfoFactory(status=models.TaskStatus.queued, eta=datetime.now() + timedelta(hours=1))
        q = models.TaskQueue.get_default()
        empty_run = q.process_batch()
        self.assertTrue(empty_run)
        self.assertFalse(process_one.called)

    @patch('django_tasker.models.TaskInfo.process_one')
    def test_process_not_ququed(self, process_one):
        task = factories.TaskInfoFactory(status=models.TaskStatus.created, eta=datetime.now())
        q = models.TaskQueue.get_default()
        q.process_batch()
        self.assertFalse(process_one.called)
