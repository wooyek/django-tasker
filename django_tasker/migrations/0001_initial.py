# -*- coding: utf-8 -*-
# Generated by Django 1.10.4 on 2016-12-15 16:46
from __future__ import unicode_literals

from django.db import migrations, models
import django.db.models.deletion
import django_tasker.models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='TaskInfo',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created', models.DateTimeField(auto_now_add=True)),
                ('executed', models.DateTimeField(blank=True, null=True)),
                ('ts', models.DateTimeField(auto_now=True)),
                ('retry_count', models.PositiveSmallIntegerField(default=0)),
                ('eta', models.DateTimeField(blank=True, null=True)),
                ('payload', models.CharField(blank=True, max_length=300, null=True)),
                ('status', models.IntegerField(choices=[(0, 'Created'), (1, 'Queued'), (2, 'Eager'), (3, 'Retry'), (4, 'Busy'), (5, 'Success'), (6, 'Error'), (7, 'Corrupted')], default=django_tasker.models.TaskStatus(0))),
                ('status_message', models.TextField(blank=None, default=None, null=True)),
            ],
        ),
        migrations.CreateModel(
            name='TaskQueue',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(default='default', max_length=100, unique=True)),
                ('rate_limit', models.PositiveSmallIntegerField(blank=True, help_text='Maximum number of tasks to run per hour', null=True)),
                ('status', models.PositiveSmallIntegerField(choices=[(0, 'Enabled'), (1, 'Disabled')], default=django_tasker.models.QueueStatus(0))),
            ],
        ),
        migrations.CreateModel(
            name='TaskTarget',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=100, unique=True)),
                ('max_retries', models.PositiveSmallIntegerField(default=5)),
                ('queue', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='django_tasker.TaskQueue')),
            ],
        ),
        migrations.AddField(
            model_name='taskinfo',
            name='target',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='django_tasker.TaskTarget'),
        ),
        migrations.AlterIndexTogether(
            name='taskinfo',
            index_together=set([('id', 'status')]),
        ),
    ]
