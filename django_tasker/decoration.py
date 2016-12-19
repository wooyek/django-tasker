# coding=utf-8
import logging

from django_tasker.models import TaskInfo


# Kudos for inspiration
# https://www.ianlewis.org/en/dynamically-adding-method-classes-or-class-instanc
# http://metapython.blogspot.com/2010/11/python-instance-methods-how-are-they.html

class BaseProxy(object):
    def __init__(self, function, options, instance=None):
        self.options = options
        self.__wrapped__ = function
        self.instance = instance
        self.__qualname__ = function.__qualname__
        self.__module__ = function.__module__
        self.__name__ = function.__name__

    def queue(self, *args, **kwargs):
        return self.setup_task().queue(*args, **kwargs)

    def setup_task(self, **kwargs):
        options = self.options.copy()
        options.update(kwargs)
        return TaskInfo.setup(self.__wrapped__, self.instance, **options)

    # For very limited Celery compatibility, map default celery function
    delay = queue

class MethodProxy(BaseProxy):
    def __call__(self, *args, **kwargs):
        return self.__wrapped__(*args, **kwargs)

    def __get__(self, instance, owner_type):
        logging.debug("owner_type: %s", owner_type)
        logging.debug("instance: %s", instance)

        if instance is None:
            return self

        return BoundMethodProxy(self.__wrapped__, self.options, instance)


class BoundMethodProxy(BaseProxy):

    def __init__(self, function, options, instance=None):
        assert instance
        super(BoundMethodProxy, self).__init__(function, options, instance)

    def __call__(self, *args, **kwargs):
        return self.__wrapped__(self.instance, *args, **kwargs)


def queueable(*args, **options):
    def decorator(func):
        if hasattr(func, '__self__') and not isinstance(func.__self__, type):
            return BoundMethodProxy(func, options, func.__self__)
        else:
            return MethodProxy(func, options)

    if len(args) == 1 and callable(args[0]):
        return decorator(args[0])
    return decorator
