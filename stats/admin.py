from django.contrib import admin
from django.db.models import Avg, Count, Q
from django.utils.html import format_html
from tasks.models import TaskRun
from .models import StatsBoard


@admin.register(StatsBoard)
class StatsBoardAdmin(admin.ModelAdmin):
    change_list_template = 'admin/stats_board.html'
    list_display = ()

    def get_queryset(self, request):
        # 避免对不存在的 stats_statsboard 表进行查询
        return TaskRun.objects.none()

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def changelist_view(self, request, extra_context=None):
        qs = TaskRun.objects.all()
        owner_id = request.GET.get('owner_id')
        if owner_id:
            qs = qs.filter(owner_id=owner_id)
        provider = request.GET.get('provider')
        if provider:
            qs = qs.filter(provider=provider)
        task_type = request.GET.get('task_type')
        if task_type:
            qs = qs.filter(task_type=task_type)

        total = qs.count()
        succ = qs.filter(success=True).count()
        avg_duration = int(qs.aggregate(v=Avg('duration_ms'))['v'] or 0)
        provider_rows = qs.values('provider').annotate(
            total=Count('id'),
            succ=Count('id', filter=Q(success=True)),
            avg=Avg('duration_ms')
        ).order_by('-total')

        html = [
            f'<h2>概览</h2>',
            f'<p>总运行: {total}，成功: {succ}，成功率: { (succ/total*100 if total else 0):.1f}% ，平均耗时: {avg_duration} ms</p>',
            '<h3>按平台分布</h3>',
            '<table class="adminstats"><tr><th>平台</th><th>总数</th><th>成功</th><th>成功率</th><th>平均耗时(ms)</th></tr>'
        ]
        for r in provider_rows:
            rate = (r['succ']/r['total']*100) if r['total'] else 0
            html.append(f"<tr><td>{r['provider'] or ''}</td><td>{r['total']}</td><td>{r['succ']}</td><td>{rate:.1f}%</td><td>{int(r['avg'] or 0)}</td></tr>")
        html.append('</table>')

        extra_context = extra_context or {}
        extra_context['stats_html'] = format_html(''.join(html))
        return super().changelist_view(request, extra_context=extra_context)

# Register your models here.
