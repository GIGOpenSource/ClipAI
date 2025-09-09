from django.db.models import Count, Avg, Q, Sum
from django.db.models.functions import TruncDay, TruncHour
from django.utils.dateparse import parse_datetime
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
from .serializers import OverviewResponseSerializer, SummaryResponseSerializer, ProviderBreakdownItemSerializer, TypeBreakdownItemSerializer, TaskRunItemSerializer, OverviewV2ResponseSerializer, TrendItemSerializer, DailyTableItemSerializer


def _filters(request):
    qs = TaskRun.objects.all()
    owner_id = request.query_params.get('owner_id')
    if owner_id:
        qs = qs.filter(owner_id=owner_id)
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


class SummaryView(APIView):
    permission_classes = [IsAuthenticated, IsStaffUser]

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
    permission_classes = [IsAuthenticated, IsStaffUser]

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
    permission_classes = [IsAuthenticated, IsStaffUser]

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
    permission_classes = [IsAuthenticated, IsStaffUser]

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
        # 先从 DailyStat 读取；缺失的日期再按需增量计算并保存，避免重复聚合
        stats_qs = DailyStat.objects.all()
        if request.user and request.user.is_authenticated:
            if request.user.is_superuser:
                # 管理员可查看全部；若显式传 owner_id 则按其过滤
                owner_id = request.query_params.get('owner_id')
                if owner_id:
                    stats_qs = stats_qs.filter(owner_id=owner_id)
            else:
                # 非管理员固定查看自己的数据
                stats_qs = stats_qs.filter(owner_id=request.user.id)
        # 若请求无范围，默认最近30天（此处省略区间限制，读取现有 DailyStat）
        date_from = request.query_params.get('date_from')
        date_to = request.query_params.get('date_to')
        # 管理员 aggregate=all → 按天汇总所有 owner
        if request.user.is_superuser and request.query_params.get('aggregate') == 'all':
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
    permission_classes = [IsAuthenticated, IsStaffUser]

    @extend_schema(summary='按天统计表 CSV 导出', tags=['数据统计'])
    def get(self, request):
        # 复用 OverviewView 的数据聚合逻辑（简化版：直接读 DailyStat）
        stats_qs = DailyStat.objects.all()
        if request.user and request.user.is_authenticated:
            if request.user.is_superuser:
                owner_id = request.query_params.get('owner_id')
                if owner_id:
                    stats_qs = stats_qs.filter(owner_id=owner_id)
            else:
                stats_qs = stats_qs.filter(owner_id=request.user.id)
        if request.user.is_superuser and request.query_params.get('aggregate') == 'all':
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
