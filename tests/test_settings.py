# coding=utf-8
# Copyright (c) 2016 Janusz Skonieczny

EMAIL_BACKEND = 'django_email_queue.backends.EmailBackend'
EMAIL_QUEUE_EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'

# The name of the class to use to run the test suite
TEST_RUNNER = 'django.test.runner.DiscoverRunner'

SECRET_KEY = 'fake-key'
INSTALLED_APPS = [
    "django_tasker.apps.TaskerConfig",
]

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': ":memory:"
    }
}
