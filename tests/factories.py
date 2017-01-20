# coding=utf-8
# Copyright (c) 2016 Janusz Skonieczny

from __future__ import absolute_import

from datetime import datetime

import factory
from factory import fuzzy

from django_tasker import models


class TaskQueueFactory(factory.DjangoModelFactory):
    name = factory.Faker('company')

    class Meta:
        model = models.TaskQueue


class TaskTargetFactory(factory.DjangoModelFactory):
    name = factory.Faker('name')
    queue = factory.SubFactory(TaskQueueFactory)

    class Meta:
        model = models.TaskTarget


class TaskInfoFactory(factory.DjangoModelFactory):
    target = factory.SubFactory(TaskTargetFactory)
    status = fuzzy.FuzzyChoice(models.TaskStatus.values())
    eta = datetime.now()

    class Meta:
        model = models.TaskInfo


class TaskWorkerFactory(factory.Factory):
    queue = factory.SubFactory(TaskQueueFactory)

    class Meta:
        model = models.TaskWorker
