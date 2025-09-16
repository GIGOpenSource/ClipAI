from django.db.models import Sum
from datetime import timedelta
from django.utils import timezone
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.http import HttpResponse
import csv
from drf_spectacular.utils import extend_schema
from .models import DailyStat
from .serializers import SummaryResponseSerializer


class SummaryView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(summary='统计概览（仅昨天当前用户）', tags=['数据统计'], responses=SummaryResponseSerializer)
    def get(self, request):
        if not (request.user and request.user.is_authenticated):
            return Response({'total_runs': 0, 'succeeded': 0, 'failed': 0, 'success_rate': 0, 'avg_duration_ms': 0, 'sla_met_rate': None})
        yesterday = timezone.now().date() - timedelta(days=1)
        stat = DailyStat.objects.filter(date=yesterday, owner_id=request.user.id).first()
        post = getattr(stat, 'post_count', 0) if stat else 0
        r_c = getattr(stat, 'reply_comment_count', 0) if stat else 0
        r_m = getattr(stat, 'reply_message_count', 0) if stat else 0
        total = int(post) + int(r_c) + int(r_m)
        return Response({
            'total_runs': total,
            'succeeded': total,
            'failed': 0,
            'success_rate': 1 if total else 0,
            'avg_duration_ms': 0,
            'sla_met_rate': None,
        })


class OverviewView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(summary='昨日统计明细（当前用户，单日一行）', tags=['数据统计'])
    def get(self, request):
        if not (request.user and request.user.is_authenticated):
            return Response({'results': []})
        yesterday = (timezone.now().date() - timedelta(days=1))
        stats_qs = DailyStat.objects.filter(date=yesterday, owner_id=request.user.id)
        data = list(stats_qs.values(
            'date', 'account_count', 'ins', 'x', 'fb', 'post_count',
            'reply_comment_count', 'reply_message_count', 'total_impressions'
        ).order_by('-date'))
        print(data)
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
        return Response(data)
