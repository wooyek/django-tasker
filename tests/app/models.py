# coding=utf-8
# Copyright (c) 2016 Janusz Skonieczny
from django.db import models
from django.db.models.fields import BooleanField

from django_tasker.decoration import queueable


class BaseModel(models.Model):
    foo = BooleanField(default=True)

    class Meta:
        abstract = True

    @queueable
    def process_me(self):
        self.foo = True
        self.save()

    def no_queable(self):
        pass


class SomeModel(BaseModel):
    bar = BooleanField(default=True)

    @queueable
    def do_stuff(self):
        pass

    @classmethod
    @queueable
    def do_whole_other_stuff(cls):
        pass
