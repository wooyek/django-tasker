# coding=utf-8
# Copyright 2014 Janusz Skonieczny
import io
import sys
import os
import uuid
from setuptools import setup, find_packages
from pip.req import parse_requirements

ROOT_DIR = os.path.abspath(os.path.dirname(__file__))

install_requires = parse_requirements(
    os.path.join(os.path.dirname(__file__), "requirements.txt"),
    session=uuid.uuid1()
)
tests_require = parse_requirements(
    os.path.join(os.path.dirname(__file__), "requirements-dev.txt"),
    session=uuid.uuid1()
)
with io.open("README.rst", encoding="UTF-8") as readme:
    long_description = readme.read()

version = "0.2.27"

setup_kwargs = {
    'name': "django-tasker",
    'version': version,
    'packages': find_packages(),
    # 'packages': ['django_tasker'],
    'install_requires': [str(r.req) for r in install_requires],
    'tests_require': [str(r.req) for r in tests_require],
    'author': "Janusz Skonieczny",
    'author_email': "js+pypi@bravelabs.pl",
    'description': "Queening and storing email backed for django",
    'long_description': long_description,
    'license': "MIT",
    'keywords': "django async tasks background jobs queue",
    'url': "https://github.com/wooyek/django-tasker",
    'classifiers': [
        'Programming Language :: Python',
        'Development Status :: 4 - Beta',
        'Natural Language :: English',
        'Environment :: Web Environment',
        'Framework :: Django',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: MIT License',
        'Operating System :: OS Independent',
        'Topic :: Software Development :: Libraries :: Python Modules',
        'Topic :: Software Development :: Libraries :: Application Frameworks',
        'Topic :: Internet :: WWW/HTTP :: Dynamic Content',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.4',
        'Programming Language :: Python :: 3.5',
    ],
    'test_suite': 'runtests.runtests',
    'entry_points': {
        'console_scripts': [
            'django_tasker = django_tasker.worker:main',
        ],
    },
}

setup(**setup_kwargs)
