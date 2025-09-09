from django.contrib import admin
from .models import KeywordConfig


@admin.register(KeywordConfig)
class KeywordConfigAdmin(admin.ModelAdmin):
    list_display = ('name', 'owner', 'provider', 'match_mode', 'enabled', 'updated_at')
    list_filter = ('provider', 'match_mode', 'enabled')
    search_fields = ('name', 'owner__username')

# Register your models here.
