from django.db.models import Count, Avg, Q, Sum
from django.db.models.functions import TruncDay, TruncHour
from django.utils.dateparse import parse_datetime
from datetime import datetime, timedelta, date
from django.utils import timezone
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.pagination import PageNumberPagination
from django.http import HttpResponse
import csv
from drf_spectacular.utils import extend_schema, OpenApiParameter
from accounts.permissions import IsStaffUser
from tasks.models import TaskRun
from .models import DailyStat
from .utils import rebuild_daily_stats
from social.models import SocialAccount
from .serializers import OverviewResponseSerializer, SummaryResponseSerializer, ProviderBreakdownItemSerializer, TypeBreakdownItemSerializer, TaskRunItemSerializer, OverviewV2ResponseSerializer, TrendItemSerializer, DailyTableItemSerializer


def _filters(request):
    qs = TaskRun.objects.all()
    # 管理员可查看全部（可通过 owner_id 过滤）；普通用户只能查看自己的数据；未登录无数据
    if request.user and request.user.is_authenticated:
        if request.user.is_staff:
            owner_id = request.query_params.get('owner_id')
            if owner_id:
                qs = qs.filter(owner_id=owner_id)
        else:
            qs = qs.filter(owner_id=request.user.id)
    else:
        return TaskRun.objects.none()
    provider = request.query_params.get('provider')
    if provider:
        qs = qs.filter(provider=provider)
    task_type = request.query_params.get('type')
    if task_type:
        qs = qs.filter(task_type=task_type)
    success = request.query_params.get('success')
    if success in {'true', 'false'}:
        qs = qs.filter(success=(success == 'true'))
    date_from = request.query_params.get('date_from')
    date_to = request.query_params.get('date_to')
    if date_from:
        qs = qs.filter(started_at__gte=parse_datetime(date_from))
    if date_to:
        qs = qs.filter(started_at__lte=parse_datetime(date_to))
    return qs


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        # Accept YYYY-MM-DD or full datetime; always convert to date in server tz
        dt = parse_datetime(value)
        if dt is None:
            return datetime.fromisoformat(value).date()
        if timezone.is_naive(dt):
            dt = timezone.make_aware(dt, timezone.get_default_timezone())
        return dt.astimezone(timezone.get_default_timezone()).date()
    except Exception:
        return None


def _daterange(start: date, end: date):
    current = start
    while current <= end:
        yield current
        current = current + timedelta(days=1)


def _rebuild_daily_stats(request, date_start: date, date_end: date):
    """Recompute DailyStat from TaskRun for the requested scope and date range.
    Rules:
    - Only count success=True for action counts
    - Provider mapping: instagram→ins, twitter→x, facebook→fb
    - post_count / reply_comment_count / reply_message_count based on task_type
    - total_impressions is sum of impressions for success=True
    - account_count: number of active social accounts for owner on that day (approximate by current active count)
    """
    task_qs = _filters(request)
    if not task_qs.exists():
        # Still ensure DailyStat rows exist as zero rows for the range
        owner_ids = []
        if request.user and request.user.is_authenticated and not request.user.is_staff:
            owner_ids = [request.user.id]
        elif request.user and request.user.is_staff:
            owner_param = request.query_params.get('owner_id')
            if owner_param:
                owner_ids = [int(owner_param)]
        for d in _daterange(date_start, date_end):
            if owner_ids:
                for oid in owner_ids:
                    DailyStat.objects.update_or_create(
                        date=d, owner_id=oid,
                        defaults=dict(
                            account_count=SocialAccount.objects.filter(owner_id=oid, status='active').count(),
                            ins=0, x=0, fb=0, post_count=0,
                            reply_comment_count=0, reply_message_count=0,
                            total_impressions=0,
                        )
                    )
            else:
                DailyStat.objects.update_or_create(
                    date=d, owner_id=None,
                    defaults=dict(
                        account_count=0, ins=0, x=0, fb=0, post_count=0,
                        reply_comment_count=0, reply_message_count=0, total_impressions=0,
                    )
                )
        return

    # Restrict by date range for TaskRun
    start_dt = datetime.combine(date_start, datetime.min.time()).astimezone(timezone.get_default_timezone())
    end_dt = datetime.combine(date_end, datetime.max.time()).astimezone(timezone.get_default_timezone())
    task_qs = task_qs.filter(started_at__gte=start_dt, started_at__lte=end_dt)

    grouped = task_qs.annotate(day=TruncDay('started_at')).values('day', 'owner_id').annotate(
        ins=Count('id', filter=Q(success=True, provider='instagram')),
        x=Count('id', filter=Q(success=True, provider='twitter')),
        fb=Count('id', filter=Q(success=True, provider='facebook')),
        post_count=Count('id', filter=Q(success=True, task_type='post')),
        reply_comment_count=Count('id', filter=Q(success=True, task_type='reply_comment')),
        reply_message_count=Count('id', filter=Q(success=True, task_type='reply_message')),
        total_impressions=Sum('impressions', filter=Q(success=True)),
    )

    # Prepare account counts per owner (approximate as current active accounts)
    owner_ids = {row['owner_id'] for row in grouped}
    owner_to_acc = {oid: SocialAccount.objects.filter(owner_id=oid, status='active').count() for oid in owner_ids if oid}

    # Upsert DailyStat per (day, owner)
    seen_keys = set()
    for row in grouped:
        d = row['day'].date()
        oid = row['owner_id']
        seen_keys.add((d, oid))
        DailyStat.objects.update_or_create(
            date=d, owner_id=oid,
            defaults=dict(
                account_count=owner_to_acc.get(oid, 0),
                ins=row['ins'] or 0,
                x=row['x'] or 0,
                fb=row['fb'] or 0,
                post_count=row['post_count'] or 0,
                reply_comment_count=row['reply_comment_count'] or 0,
                reply_message_count=row['reply_message_count'] or 0,
                total_impressions=row['total_impressions'] or 0,
            )
        )

    # Zero-fill missing dates within range for the relevant owner scope
    owner_scope: list[int | None] = []
    if request.user and request.user.is_authenticated and not request.user.is_staff:
        owner_scope = [request.user.id]
    elif request.user and request.user.is_staff:
        owner_param = request.query_params.get('owner_id')
        if owner_param:
            try:
                owner_scope = [int(owner_param)]
            except Exception:
                owner_scope = []
    # Only zero-fill when scope明确，避免对全量用户做空洞填充造成压力
    if owner_scope:
        for d in _daterange(date_start, date_end):
            for oid in owner_scope:
                if (d, oid) not in seen_keys:
                    DailyStat.objects.update_or_create(
                        date=d, owner_id=oid,
                        defaults=dict(
                            account_count=SocialAccount.objects.filter(owner_id=oid, status='active').count(),
                            ins=0, x=0, fb=0, post_count=0,
                            reply_comment_count=0, reply_message_count=0,
                            total_impressions=0,
                        )
                    )


class SummaryView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(summary='统计概览', tags=['数据统计'], responses=SummaryResponseSerializer)
    def get(self, request):
        qs = _filters(request)
        total = qs.count()
        succ = qs.filter(success=True).count()
        fail = total - succ
        avg_duration = qs.aggregate(v=Avg('duration_ms'))['v'] or 0
        sla_total = qs.filter(sla_met__isnull=False).count()
        sla_met = qs.filter(sla_met=True).count()
        data = {
            'total_runs': total,
            'succeeded': succ,
            'failed': fail,
            'success_rate': (succ / total) if total else 0,
            'avg_duration_ms': int(avg_duration),
            'sla_met_rate': (sla_met / sla_total) if sla_total else None,
        }
        return Response(data)


class BreakdownProviderView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(summary='按平台分布', tags=['数据统计'], responses=ProviderBreakdownItemSerializer(many=True))
    def get(self, request):
        qs = _filters(request)
        rows = qs.values('provider').annotate(
            total=Count('id'),
            succ=Count('id', filter=Q(success=True)),
            avg_duration=Avg('duration_ms'),
        ).order_by('-total')
        for r in rows:
            r['success_rate'] = (r['succ'] / r['total']) if r['total'] else 0
            r['avg_duration_ms'] = int(r.pop('avg_duration') or 0)
        return Response(rows)


class BreakdownTypeView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(summary='按任务类型分布', tags=['数据统计'], responses=TypeBreakdownItemSerializer(many=True))
    def get(self, request):
        qs = _filters(request)
        rows = qs.values('task_type').annotate(
            total=Count('id'),
            succ=Count('id', filter=Q(success=True)),
            avg_duration=Avg('duration_ms'),
        ).order_by('-total')
        for r in rows:
            r['success_rate'] = (r['succ'] / r['total']) if r['total'] else 0
            r['avg_duration_ms'] = int(r.pop('avg_duration') or 0)
        return Response(rows)


class OverviewView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary='按天统计表（最新在前）',
        description='返回按天聚合的统计行。管理员可加 aggregate=all 汇总所有用户；format=csv 导出。',
        tags=['数据统计'],
        parameters=[
            OpenApiParameter(name='owner_id', description='（管理员）按用户过滤；普通用户忽略', required=False, type=str),
            OpenApiParameter(name='date_from', description='起始时间（ISO8601）', required=False, type=str),
            OpenApiParameter(name='date_to', description='结束时间（ISO8601）', required=False, type=str),
            OpenApiParameter(name='aggregate', description='管理员汇总：all', required=False, type=str),
            OpenApiParameter(name='page', description='页码', required=False, type=int),
            OpenApiParameter(name='page_size', description='每页条数', required=False, type=int),
            OpenApiParameter(name='format', description='csv 导出当前查询结果', required=False, type=str),
        ],
        responses=TrendItemSerializer(many=True)
    )
    def get(self, request):
        qs = _filters(request)
        # 刷新指定日期范围的数据，再从 DailyStat 读取，保证口径一致
        date_from = _parse_date(request.query_params.get('date_from'))
        date_to = _parse_date(request.query_params.get('date_to'))
        if not date_to:
            date_to = timezone.now().date()
        if not date_from:
            date_from = date_to - timedelta(days=29)
        if date_from > date_to:
            date_from, date_to = date_to, date_from
        _rebuild_daily_stats(request, date_from, date_to)

        stats_qs = DailyStat.objects.filter(date__gte=date_from, date__lte=date_to)
        if request.user and request.user.is_authenticated:
            if request.user.is_staff:
                # 管理员可查看全部；若显式传 owner_id 则按其过滤
                owner_id = request.query_params.get('owner_id')
                if owner_id:
                    stats_qs = stats_qs.filter(owner_id=owner_id)
            else:
                # 非管理员固定查看自己的数据
                stats_qs = stats_qs.filter(owner_id=request.user.id)
        # 管理员 aggregate=all → 按天汇总所有 owner
        if request.user.is_staff and request.query_params.get('aggregate') == 'all':
            rows = stats_qs.values('date').annotate(
                account_count=Sum('account_count'),
                ins=Sum('ins'),
                x=Sum('x'),
                fb=Sum('fb'),
                post_count=Sum('post_count'),
                reply_comment_count=Sum('reply_comment_count'),
                reply_message_count=Sum('reply_message_count'),
                total_impressions=Sum('total_impressions'),
            ).order_by('-date')
            data = [
                {
                    'date': r['date'],
                    'account_count': r['account_count'] or 0,
                    'ins': r['ins'] or 0,
                    'x': r['x'] or 0,
                    'fb': r['fb'] or 0,
                    'post_count': r['post_count'] or 0,
                    'reply_comment_count': r['reply_comment_count'] or 0,
                    'reply_message_count': r['reply_message_count'] or 0,
                    'total_impressions': r['total_impressions'] or 0,
                }
                for r in rows
            ]
        else:
            data = list(
                stats_qs.values(
                    'date', 'account_count', 'ins', 'x', 'fb', 'post_count',
                    'reply_comment_count', 'reply_message_count', 'total_impressions'
                ).order_by('-date')
            )

        # CSV 导出
        if request.query_params.get('format') == 'csv':
            response = HttpResponse(content_type='text/csv; charset=utf-8')
            response['Content-Disposition'] = 'attachment; filename="daily_stats.csv"'
            writer = csv.writer(response)
            writer.writerow(['日期', '账号数量', 'ins', 'x', 'fb', '发帖数', '回复评论数', '回复消息数', '总曝光量'])
            for r in data:
                writer.writerow([
                    r['date'], r['account_count'], r['ins'], r['x'], r['fb'],
                    r['post_count'], r['reply_comment_count'], r['reply_message_count'], r['total_impressions']
                ])
            return response
        # 分页：标准 DRF PageNumberPagination 响应
        paginator = PageNumberPagination()
        try:
            paginator.page_size = int(request.query_params.get('page_size', '20'))
        except ValueError:
            paginator.page_size = 20
        page = paginator.paginate_queryset(data, request, view=self)
        # 校验结构以便文档展示（仅对当前页校验）
        DailyTableItemSerializer(page, many=True).data
        return paginator.get_paginated_response(page)


class OverviewExportView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(summary='按天统计表 CSV 导出', tags=['数据统计'])
    def get(self, request):
        # 复用 OverviewView 的数据聚合逻辑（简化版：直接读 DailyStat）
        stats_qs = DailyStat.objects.all()
        if request.user and request.user.is_authenticated:
            if request.user.is_staff:
                owner_id = request.query_params.get('owner_id')
                if owner_id:
                    stats_qs = stats_qs.filter(owner_id=owner_id)
            else:
                stats_qs = stats_qs.filter(owner_id=request.user.id)
        if request.user.is_staff and request.query_params.get('aggregate') == 'all':
            rows = stats_qs.values('date').annotate(
                account_count=Sum('account_count'),
                ins=Sum('ins'),
                x=Sum('x'),
                fb=Sum('fb'),
                post_count=Sum('post_count'),
                reply_comment_count=Sum('reply_comment_count'),
                reply_message_count=Sum('reply_message_count'),
                total_impressions=Sum('total_impressions'),
            ).order_by('-date')
            data = [
                {
                    'date': r['date'],
                    'account_count': r['account_count'] or 0,
                    'ins': r['ins'] or 0,
                    'x': r['x'] or 0,
                    'fb': r['fb'] or 0,
                    'post_count': r['post_count'] or 0,
                    'reply_comment_count': r['reply_comment_count'] or 0,
                    'reply_message_count': r['reply_message_count'] or 0,
                    'total_impressions': r['total_impressions'] or 0,
                }
                for r in rows
            ]
        else:
            data = list(
                stats_qs.values(
                    'date', 'account_count', 'ins', 'x', 'fb', 'post_count',
                    'reply_comment_count', 'reply_message_count', 'total_impressions'
                ).order_by('-date')
            )

        response = HttpResponse(content_type='text/csv; charset=utf-8')
        response['Content-Disposition'] = 'attachment; filename="daily_stats.csv"'
        writer = csv.writer(response)
        writer.writerow(['日期', '账号数量', 'ins', 'x', 'fb', '发帖数', '回复评论数', '回复消息数', '总曝光量'])
        for r in data:
            writer.writerow([
                r['date'], r['account_count'], r['ins'], r['x'], r['fb'],
                r['post_count'], r['reply_comment_count'], r['reply_message_count'], r['total_impressions']
            ])
        return response


# Create your views here.


class RebuildNowView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary='立即重建指定日期范围的按天统计（基于已有 TaskRun）',
        description='管理员可指定 owner_id；普通用户仅可重建自己的数据。默认最近30天。支持传 date_from、date_to（YYYY-MM-DD 或 ISO8601）。',
        tags=['数据统计'],
        parameters=[
            OpenApiParameter(name='owner_id', description='（管理员）按用户过滤；普通用户忽略', required=False, type=str),
            OpenApiParameter(name='date_from', description='起始日期/时间', required=False, type=str),
            OpenApiParameter(name='date_to', description='结束日期/时间', required=False, type=str),
        ]
    )
    def post(self, request):
        # 解析日期范围
        df = _parse_date(request.data.get('date_from') or request.query_params.get('date_from'))
        dt = _parse_date(request.data.get('date_to') or request.query_params.get('date_to'))
        if not dt:
            dt = timezone.now().date()
        if not df:
            df = dt - timedelta(days=29)
        if df > dt:
            df, dt = dt, df

        # 确定 owner 范围
        owner_param = request.data.get('owner_id') or request.query_params.get('owner_id')
        owner_scope = None
        if request.user and request.user.is_authenticated and request.user.is_staff:
            owner_scope = int(owner_param) if owner_param else None
        else:
            owner_scope = request.user.id if (request.user and request.user.is_authenticated) else None

        # 重建并返回结果
        rows = rebuild_daily_stats(df, dt, owner_id=owner_scope)
        stats_qs = DailyStat.objects.filter(date__gte=df, date__lte=dt)
        if owner_scope is not None:
            stats_qs = stats_qs.filter(owner_id=owner_scope)
        data = list(stats_qs.values(
            'date', 'owner_id', 'account_count', 'ins', 'x', 'fb', 'post_count',
            'reply_comment_count', 'reply_message_count', 'total_impressions', 'updated_at'
        ).order_by('-date'))
        return Response({'rows_updated': rows, 'data': data})
