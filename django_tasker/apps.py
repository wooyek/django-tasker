from django.apps import AppConfig
from django.utils.translation import ugettext as __, ugettext_lazy as _


class TaskerConfig(AppConfig):
    name = 'django_tasker'
    verbose_name = _('tasker')
