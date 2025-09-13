from django.contrib import admin
from .models import PoolAccount


@admin.register(PoolAccount)
class PoolAccountAdmin(admin.ModelAdmin):
    list_display = ('id', 'provider', 'name', 'status', 'is_ban', 'updated_at')
    list_filter = ('provider', 'status', 'is_ban')
    search_fields = ('name',)
