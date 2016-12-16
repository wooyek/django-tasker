# coding=utf-8
# Copyright (c) 2016 Janusz Skonieczny


SECRET_KEY = 'fake-key'
INSTALLED_APPS = [
    "django_tasker.apps.TaskerConfig",
    "tests.app",
]

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': ":memory:"
    }
}
