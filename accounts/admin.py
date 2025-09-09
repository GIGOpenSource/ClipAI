from django.contrib import admin
from .models import AuditLog


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = (
        'timestamp', 'actor', 'action', 'target_type', 'target_id', 'success'
    )
    list_filter = ('success', 'target_type', 'action')
    search_fields = ('action', 'target_type', 'target_id', 'actor__username')
    readonly_fields = ('timestamp',)

# Register your models here.
