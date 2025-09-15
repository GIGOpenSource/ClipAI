from django.contrib import admin
from .models import AIConfig


@admin.register(AIConfig)
class AIConfigAdmin(admin.ModelAdmin):
    list_display = ('name', 'provider', 'model', 'enabled', 'is_default', 'priority', 'created_at')
    list_filter = ('provider', 'enabled', 'is_default')
    search_fields = ('name', 'model')

# Register your models here.
