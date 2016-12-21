# coding=utf-8
# Copyright (c) 2016 Janusz Skonieczny

from __future__ import absolute_import

from datetime import datetime

import factory

from django_tasker import models


class TaskQueueFactory(factory.DjangoModelFactory):
    name = 'default'

    class Meta:
        model = models.TaskQueue


class TaskTargetFactory(factory.DjangoModelFactory):
    name = 'foo.bar'
    queue = factory.SubFactory(TaskQueueFactory)

    class Meta:
        model = models.TaskTarget


class TaskInfoFactory(factory.DjangoModelFactory):
    target = factory.SubFactory(TaskTargetFactory)
    status = models.TaskStatus.queued
    eta = datetime.now()

    class Meta:
        model = models.TaskInfo


class TaskWorkerFactory(factory.Factory):
    queue = factory.SubFactory(TaskQueueFactory)

    class Meta:
        model = models.TaskWorker
