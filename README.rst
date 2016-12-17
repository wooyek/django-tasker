django-tasker
==================

Dead simple async task queue. Stores tasks in database.
No overhead infrastructure required just for throwing something off process.

https://github.com/wooyek/django-tasker

.. image:: https://img.shields.io/travis/wooyek/django-tasker.svg
    :target: https://travis-ci.org/wooyek/django-tasker

.. image:: https://img.shields.io/coveralls/wooyek/django-tasker.svg
    :target: https://coveralls.io/github/wooyek/django-tasker

.. image:: https://img.shields.io/pypi/v/django-tasker.svg?maxAge=2592000
    :target: https://pypi.python.org/pypi/django-tasker/

.. image:: https://img.shields.io/pypi/dm/django-tasker.svg?maxAge=2592000
    :target: https://pypi.python.org/pypi/django-tasker/

.. image:: https://img.shields.io/pypi/pyversions/django-tasker.svg
    :target: https://pypi.python.org/pypi/django-tasker/

Usage
-----

You are free to make task from function or class and instance methods. No boilerplate functions are required to wrap task logic.

With django models instances tasks will remember an instance primary key, load an instance and call a method.

.. code-block:: python

    class SomeModel(models.Model):
        ...

        @queueable
        def update_this_instance(self, *args, **kwargs):
            ...

        def must_do_something(self):
            ...
            self.update_this_instance.queue()
            ...
        
With plain old class object tasks will call it's classmethod. Normal functions are also supported.


.. code-block:: python

    class PocoClass(Object):

        @queueable
        def do_stuff_with_models(cls, limit):
            ...

    @queueable
    def background_job(cls, with_this, and_that):
        ...

    PocoClass.do_stuff_with_models.queue(10)
    background_job.queue(foo, bar)

Limited support for arguments serialization
-------------------------------------------

Call arguments are supported as long as they are json serializable and they're serialized up to a ``TaskInfo.payload`` fields ``max_length``.
We don't wan;t to be holding too much information, preferably models instances are holding just enough information for parametrize task execution.


Why not Celery?
---------------

`Celery <http://www.celeryproject.org/>`_ is great! But it's sometimes an overkill. It's a full-on messaging implementation with all the bells and whistles
you need for sending tasks to some worker and *getting a result back*.

Maintaining all that infrastructure just to send an email every couple of request seems a bit too much.

Why not RQ?
-----------

`Python-RQ <http://python-rq.org>`_ is super. But it need's Redis. It's fine when your background work does not pile up.
Using Redis to hold gigabytes of task data is like burning money.


Why DB as storage?
------------------

Because you already have it, it's the simplest storage to use. And with fanout resulting in millions
of tasks the only cheaper storage is disk.

Why not fire up more workers?
-----------------------------

Sometimes you just can't crunch task quick enough, for eg. because of the API throttling limits. It's more sensible
to store them and spread execution in time.
