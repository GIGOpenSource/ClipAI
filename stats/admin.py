from django.contrib import admin
from django.db.models import Avg, Count, Q
from django.utils.html import format_html
from django.utils import timezone
from datetime import datetime
from tasks.models import TaskRun
from .models import StatsBoard, DailyStat
from .utils import rebuild_daily_stats


@admin.register(DailyStat)
class DailyStatAdmin(admin.ModelAdmin):
    list_display = ('date', 'owner_id', 'account_count', 'ins', 'x', 'fb', 'post_count', 'reply_comment_count', 'reply_message_count', 'total_impressions', 'updated_at')
    list_filter = ('owner_id',)
    search_fields = ('owner_id',)
    date_hierarchy = 'date'
    actions = ['action_rebuild_selected', 'action_rebuild_range']

    @admin.action(description='重建所选日期/用户的统计')
    def action_rebuild_selected(self, request, queryset):
        cnt = 0
        for ds in queryset:
            cnt += rebuild_daily_stats(ds.date, ds.date, owner_id=ds.owner_id)
        self.message_user(request, f'重建完成：{cnt} 行')

    @admin.action(description='重建指定日期范围（参数用 GET 传：date_from=YYYY-MM-DD&date_to=YYYY-MM-DD&owner_id=可选）')
    def action_rebuild_range(self, request, queryset):
        try:
            df = request.GET.get('date_from')
            dt = request.GET.get('date_to')
            owner_id = request.GET.get('owner_id')
            owner_id = int(owner_id) if owner_id else None
            date_from = datetime.fromisoformat(df).date() if df else timezone.now().date()
            date_to = datetime.fromisoformat(dt).date() if dt else date_from
            cnt = rebuild_daily_stats(date_from, date_to, owner_id=owner_id)
            self.message_user(request, f'重建完成：{cnt} 行')
        except Exception as e:
            self.message_user(request, f'参数错误：{e}', level='error')


# Register your models here.
