# -*- coding: utf-8 -*-
# Generated by Django 1.10.4 on 2016-12-25 12:23
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('django_tasker', '0002_auto_20161221_1254'),
    ]

    operations = [
        migrations.AddField(
            model_name='taskqueue',
            name='busy_max_seconds',
            field=models.PositiveIntegerField(default=3600),
        ),
        migrations.AlterIndexTogether(
            name='taskinfo',
            index_together=set([('id', 'eta', 'status')]),
        ),
    ]