# -*- coding: utf-8 -*-
# Generated by Django 1.10.6 on 2017-05-23 15:54
from __future__ import unicode_literals

from django.db import migrations, models
import django_tasker.models


class Migration(migrations.Migration):

    dependencies = [
        ('django_tasker', '0009_auto_20170512_2240'),
    ]

    operations = [
        migrations.AlterField(
            model_name='taskinfo',
            name='status',
            field=models.IntegerField(choices=[(0, 'Created'), (1, 'Queued'), (2, 'Eager'), (3, 'Retry'), (4, 'Busy'), (5, 'Success'), (6, 'Error'), (7, 'Corrupted')], default=django_tasker.models.TaskStatus(0)),
        ),
        migrations.AlterIndexTogether(
            name='taskinfo',
            index_together=set([('target', 'status'), ('id', 'target'), ('id', 'target', 'status', 'eta'), ('status', 'ts'), ('status', 'eta'), ('id', 'eta', 'status'), ('target', 'eta')]),
        ),
    ]
