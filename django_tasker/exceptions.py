# coding=utf-8
class RetryLaterException(Exception):
    def __init__(self, countdown, message):
        self.message = message
        self.countdown = countdown

    def __str__(self):
        return "RetryLaterException: countdown={}, {}".format(self.countdown, self.message)