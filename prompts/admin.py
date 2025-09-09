from django.contrib import admin
from .models import PromptConfig


@admin.register(PromptConfig)
class PromptConfigAdmin(admin.ModelAdmin):
    list_display = ('owner', 'scene', 'name', 'enabled', 'updated_at')
    list_filter = ('scene', 'enabled')
    search_fields = ('owner__username', 'name')

# Register your models here.
