# -*- coding: utf-8 -*-
# Generated by Django 1.10.4 on 2017-01-07 23:02
from __future__ import unicode_literals

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('django_tasker', '0004_auto_20170102_1510'),
    ]

    operations = [
        migrations.AlterIndexTogether(
            name='taskinfo',
            index_together=set([('id', 'target', 'status', 'eta'), ('target', 'eta'), ('id', 'eta', 'status'), ('id', 'target')]),
        ),
    ]
