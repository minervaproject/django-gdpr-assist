# -*- coding: utf-8 -*-
"""
Anonymisation support for Django ModelAdmin classes
"""
from __future__ import absolute_import
from __future__ import print_function
from __future__ import unicode_literals

from django.conf.urls import url
from django.contrib import admin
from django.contrib import messages
from django.http import HttpResponseRedirect
from django.template.response import TemplateResponse
from django.utils.safestring import mark_safe
from django.utils.translation import ugettext_lazy as _

from ..models import PrivacyManager
from ..models import EventLog

try:
    from django.urls import reverse  # NOQA
except ImportError:
    # Django <2.0
    from django.core.urlresolvers import reverse

from .. import app_settings


class ModelAdmin(admin.ModelAdmin):
    anonymise_template = 'gdpr_assist/admin/action_anonymise.html'

    def get_actions(self, request):
        actions = super(ModelAdmin, self).get_actions(request)
        if getattr(self.model, app_settings.GDPR_PRIVACY_INSTANCE_NAME):
            actions['anonymise'] = (
                self.anonymise_action,
                'anonymise',
                'Anonymise data',
            )
        return actions

    def anonymise_action(self, modeladmin, request, queryset):
        selected = request.POST.getlist(admin.ACTION_CHECKBOX_NAME)
        return HttpResponseRedirect(
            '{url}?ids={ids}'.format(
                url=reverse(
                    'admin:{}_{}_anonymise'.format(
                        self.model._meta.app_label,
                        self.model._meta.model_name,
                    )
                ),
                ids=",".join(selected),
            )
        )

    def get_urls(self):
        urls = super(ModelAdmin, self).get_urls()
        extra_urls = [
            url(
                r'^anonymise/$',
                self.admin_site.admin_view(self.anonymise_view),
                name='{}_{}_anonymise'.format(
                    self.model._meta.app_label,
                    self.model._meta.model_name,
                ),
            ),
        ]
        return extra_urls + urls

    def perform_anonymisation(self, request, objects):
        """Performs anonymisation on the queryset.

        This might take a long time and timeout.
        This is a good place to use a taks instead.
        """
        objects.anonymise(user=request.user)

    def success_message(self, request, verbose_name, count):
        messages.success(
            request,
            "{} {} anonymised".format(count, verbose_name),
        )

    def anonymise_view(self, request):
        ids_raw = (request.POST or request.GET).get('ids')

        manager = self.model._meta.default_manager
        if not isinstance(manager, PrivacyManager):
            manager = PrivacyManager._cast_class(manager)

        objects = manager.filter(pk__in=ids_raw.split(','))
        verbose_name = (
            self.model._meta.verbose_name.title()
            if len(objects) == 1 else
            self.model._meta.verbose_name_plural.title()
        )
        changelist_url = reverse(
            'admin:{}_{}_changelist'.format(
                self.model._meta.app_label,
                self.model._meta.model_name,
            ),
        )

        if request.POST:
            self.perform_anonymisation(request, objects)
            count = objects.count()
            self.success_message(request, verbose_name, count)
            return HttpResponseRedirect(changelist_url)

        tree_html = ""

        tree = self.model.get_anonymisation_tree(objs=objects).replace(" [set_field]", "").replace(" [fk]", "")
        this_html = "{model_name}:\n{tree}\n\n".format(model_name=self.model.__name__, tree=tree)
        this_html = "<pre>{html}</pre>".format(html=this_html)
        tree_html += this_html

        tree_html = mark_safe(tree_html)

        return TemplateResponse(request, self.anonymise_template, {
            'title': _("Are you sure?"),
            'ids': ids_raw,
            'verbose_name': verbose_name,
            'objects': objects,
            'cancel_url': changelist_url,
            'trees': tree_html
        })


@admin.register(EventLog)
class EventLogAdmin(admin.ModelAdmin):
    readonly_fields = ["event", "app_label", "model_name", "target_pk", "acting_user"]
    list_display = ["summary", "log_time", "event", "app_label", "model_name", "target_pk", "acting_user"]
    list_filter = ["log_time", "acting_user", "app_label", "model_name", "event"]
