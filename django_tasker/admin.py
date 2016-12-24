from django.contrib import admin, messages
from django.contrib.admin import register
from django.utils.translation import ugettext_lazy as _

from django_tasker import models


@register(models.TaskInfo)
class TaskInfoAdmin(admin.ModelAdmin):
    list_display = ('ts', 'target', 'status', 'retry_count', 'created', 'eta', 'executed')
    list_filter = ('status', 'target',)
    search_fields = ('target_model', 'target_func')
    actions = ['delete_all', 'delete_completed' ,'execute_tasks', 'set_retry_status', 'reset_retry_count']

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
