# coding=utf-8
# Copyright (c) 2016 Janusz Skonieczny

from __future__ import absolute_import

import getpass
import logging
import os

import sys
from time import sleep


logging.basicConfig(format='%(asctime)s %(levelname)-7s %(thread)-5d %(filename)s:%(lineno)s | %(funcName)s | %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
logging.getLogger().setLevel(logging.DEBUG)
logging.disable(logging.NOTSET)

log = logging.getLogger(__name__)

assert 'DJANGO_SETTINGS_MODULE' in os.environ, "DJANGO_SETTINGS_MODULE is missing from environment, you must set if before running this worker"
log.info("os.environ['DJANGO_SETTINGS_MODULE']: %s" % os.environ['DJANGO_SETTINGS_MODULE'])

cwd = os.getcwd()

if cwd not in sys.path:  # pragma: no cover
    sys.path.append(cwd)

# Show a debugging info on console
log.debug("__file__ = %s", __file__)
log.debug("sys.version = %s", sys.version)
log.debug("os.getpid() = %s", os.getpid())
log.debug("os.getcwd() = %s", cwd)
log.debug("os.curdir = %s", os.curdir)
log.debug("sys.path:\n\t%s", "\n\t".join(sys.path))
log.debug("PYTHONPATH:\n\t%s", "\n\t".join(os.environ.get('PYTHONPATH', "").split(';')))
log.debug("sys.modules.keys() = %s", repr(sys.modules.keys()))
log.debug("sys.modules.has_key('website') = %s", 'website' in sys.modules)

from django.conf import settings
import django

django.setup()
log.debug("settings.__dir__: %s", settings.__dir__())
log.debug("settings.DEBUG: %s", settings.DEBUG)


def main(argv=sys.argv[1:]):  # pragma: no cover
    from .models import TaskWorker
    TaskWorker.run_queues(argv)


if __name__ == '__main__':  # pragma: no cover
    main()
