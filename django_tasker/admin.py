from django.contrib import admin, messages
from django.contrib.admin import register
from django.db import connections
from django.db.models import QuerySet
from django.utils.translation import ugettext_lazy as _

from django_tasker import models


class ApproxQuerySet(QuerySet):
    def _approx_count(self, default):
        raise NotImplementedError('Do not use this class itself.')

    def count(self):
        if self._result_cache is not None:
            if hasattr(self, '_iter') and not self._iter:
                return len(self._result_cache)

        query = self.query
        default_count = self.query.get_count

        if (query.high_mark is None and
                    query.low_mark == 0 and
                not query.where and
                not query.select and
                not query.group_by and
                not query.having and
                not query.distinct):
            return self._approx_count(default_count)

        return default_count(using=self.db)

    @classmethod
    def wrap_query(cls, qry):
        return qry._clone(klass=cls)


class TableStatusQuerySet(ApproxQuerySet):
    def _approx_count(self, default_count):
        # For MySQL, by Nova
        # http://stackoverflow.com/a/10446271/366908
        if 'mysql' in connections[self.db].client.executable_name.lower():
            cursor = connections[self.db].cursor()
            cursor.execute('SHOW TABLE STATUS LIKE %s', (self.model._meta.db_table,))
            return cursor.fetchall()[0][4]

        # For Postgres, by Woody Anderson
        # http://stackoverflow.com/a/23118765/366908
        elif hasattr(connections[self.db].client.connection, 'pg_version'):
            parts = [p.strip('"') for p in self.model._meta.db_table.split('.')]
            cursor = connections[self.db].cursor()
            if len(parts) == 1:
                cursor.execute('SELECT reltuples::bigint FROM pg_class WHERE relname = %s', parts)
            else:
                cursor.execute('SELECT reltuples::bigint FROM pg_class c JOIN pg_namespace n ON (c.relnamespace = n.oid) WHERE n.nspname = %s AND c.relname = %s', parts)

        return default_count(using=self.db)


@register(models.TaskInfo)
class TaskInfoAdmin(admin.ModelAdmin):
    list_display = ('ts', 'target', 'status', 'retry_count', 'created', 'eta', 'executed')
    list_filter = ('status', 'target',)
    search_fields = ('target_model', 'target_func')
    actions = ['delete_all', 'delete_completed', 'execute_tasks', 'set_retry_status', 'reset_retry_count']

    # noinspection PyUnusedLocal
    def delete_all(self, request, queryset):
        qry = models.TaskInfo.objects.all()
        status = qry.delete()
        messages.info(request, "Deleted {} tasks".format(status[0]))

    delete_all.short_description = _("Delete all tasks")

    # noinspection PyUnusedLocal
    def delete_completed(self, request, queryset):
        qry = models.TaskInfo.objects.filter(status=models.TaskStatus.success)
        status = qry.delete()
        messages.info(request, "Deleted {} tasks".format(status[0]))

    delete_completed.short_description = _("Delete completed tasks")

    def execute_tasks(self, request, queryset):
        for item in queryset:
            item.execute()
        messages.info(request, "Executed {} tasks".format(queryset.count()))
    execute_tasks.short_description = _("Execute selected tasks")

    def set_retry_status(self, request, queryset):
        rows = queryset.update(status=models.TaskStatus.retry)
        messages.info(request, "Set status on {} tasks".format(rows))
    set_retry_status.short_description = _("Set {} status on tasks".format(models.TaskStatus.retry.name))

    def reset_retry_count(self, request, queryset):
        rows = queryset.update(retry_count=0)
        messages.info(request, "Reseted retry_count on {} tasks".format(rows))
    reset_retry_count.short_description = _("Reset retry_count tasks")

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return TableStatusQuerySet.wrap_query(qs)


@register(models.TaskQueue)
class TaskQueueAdmin(admin.ModelAdmin):
    list_display = ('name', 'status', 'rate_limit')
    list_filter = ('name', 'status', 'rate_limit')
    search_fields = ('name',)
    actions = ['disable']

    # noinspection PyUnusedLocal
    def disable(self, request, queryset):
        rows = queryset.update(status=models.QueueStatus.disabled)
        messages.info(request, "Disabled {} queues".format(len(rows)))

    disable.short_description = _("Disable queues")


@register(models.TaskTarget)
class TaskTargetAdmin(admin.ModelAdmin):
    list_display = ('name', 'queue', 'max_retries')
    list_filter = ('name', 'queue', 'max_retries')
    search_fields = ('name',)
