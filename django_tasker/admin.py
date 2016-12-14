from django.contrib import admin, messages
from django.contrib.admin import register
from django.utils.translation import ugettext_lazy as _

from django_tasker import models


@register(models.TaskInfo)
class TaskInfoAdmin(admin.ModelAdmin):
    list_display = ('ts', 'target_model', 'target_pk', 'target_method', 'status', 'attempts', 'created', 'executed')
    list_filter = ('status', 'target_model', 'target_method')
    search_fields = ('target_model', 'target_func')
    actions = ['delete_all', 'delete_completed']

    # noinspection PyUnusedLocal
    def delete_all(self, request, queryset):
        qry = models.TaskInfo.objects.all()
        status = qry.delete()
        messages.info(request, "Deleted {} tasks".format(status[0]))

    delete_all.short_description = _("Delete all tasks")

    # noinspection PyUnusedLocal
    def delete_completed(self, request, queryset):
        qry = models.TaskInfo.objects.filter(status=models.TaskStatus.Success)
        status = qry.delete()
        messages.info(request, "Deleted {} tasks".format(status[0]))

    delete_completed.short_description = _("Delete completed tasks")


@register(models.TaskQueue)
class TaskQueueAdmin(admin.ModelAdmin):
    list_display = ('name', 'status', 'max_tasks_per_hour')
    list_filter = ('name', 'status', 'max_tasks_per_hour')
    search_fields = ('name',)
    actions = ['disable']

    # noinspection PyUnusedLocal
    def disable(self, request, queryset):
        rows = queryset.update(status=models.QueueStatus.disabled)
        messages.info(request, "Disabled {} queues".format(len(rows)))

    disable.short_description = _("Disable queues")


@register(models.TaskTarget)
class TaskQueueAdmin(admin.ModelAdmin):
    list_display = ('name', 'queue')
    list_filter = ('name', 'queue')
    search_fields = ('name',)
