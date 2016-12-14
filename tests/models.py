# coding=utf-8
# Copyright (c) 2016 Janusz Skonieczny
from django.db import models
from django.db.models.fields import BooleanField

from django_tasker.models import queueable


class SomeModel(models.Model):
    foo = BooleanField()

    @queueable
    def process_me(self):
        self.foo = True
        self.save()
