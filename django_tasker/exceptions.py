# coding=utf-8
from datetime import timedelta

from django.conf import settings
from django.utils import timezone


class RetryLaterException(Exception):
    def __init__(self, message, countdown=None, eta=None):
        self.message = message
        assert eta or countdown
        if eta and settings.USE_TZ and timezone.is_naive(eta):
            eta = timezone.make_aware(eta)
        self.countdown = countdown or(eta - timezone.now()).total_seconds()
        self.eta = eta or (timezone.now() + timedelta(seconds=countdown))

    def __str__(self):
        return "RetryLaterException: countdown={}, {}".format(self.countdown, self.message)