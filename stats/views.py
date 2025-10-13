from django.db.models import Sum
from drf_spectacular.types import OpenApiTypes
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
import atexit
import threading
from rest_framework.views import APIView
from rest_framework.response import Response
from django.http import HttpResponse
import csv
from drf_spectacular.utils import extend_schema

from utils.utils import logger
from .models import DailyStat
from .serializers import SummaryResponseSerializer
from tasks.models import TArticle
from social.models import PoolAccount

# 全局调度器实例和锁
_scheduler_instance = None
_scheduler_lock = threading.Lock()


def get_global_scheduler():
    """
    获取全局 APScheduler 调度器实例
    """
    global _scheduler_instance
    with _scheduler_lock:
        if _scheduler_instance is None:
            _scheduler_instance = BackgroundScheduler()
            _scheduler_instance.start()
            # 程序退出时关闭调度器
            atexit.register(lambda: _scheduler_instance.shutdown() if _scheduler_instance.running else None)
        return _scheduler_instance


class SummaryView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(summary='统计概览（仅昨天当前用户）', tags=['数据统计'], responses=SummaryResponseSerializer)
    def get(self, request):
        # if not (request.user and request.user.is_authenticated):
        #     return Response({'total_runs': 0, 'succeeded': 0, 'failed': 0, 'success_rate': 0, 'avg_duration_ms': 0, 'sla_met_rate': None})
        # yesterday = timezone.now().date() - timedelta(days=1)
        # stat = DailyStat.objects.filter(date=yesterday, owner_id=request.user.id).first()
        # post = getattr(stat, 'post_count', 0) if stat else 0
        # r_c = getattr(stat, 'reply_comment_count', 0) if stat else 0
        # r_m = getattr(stat, 'reply_message_count', 0) if stat else 0
        # total = int(post) + int(r_c) + int(r_m)
        # return Response({
        #     'total_runs': total,
        #     'succeeded': total,
        #     'failed': 0,
        #     'success_rate': 1 if total else 0,
        #     'avg_duration_ms': 0,
        #     'sla_met_rate': None,
        # })
        userId = request.user
        robotList = PoolAccount.objects.filter(owner_id=userId).values('id')
        robotList = [robot["id"] for robot in robotList]
        articleData = TArticle.objects.filter(robot_id__in=robotList).values('platform').annotate(
            total_impression_count=Sum('impression_count'),
            total_comment_count=Sum('comment_count'),
            total_message_count=Sum('message_count'),
            total_like_count=Sum('like_count'),
            total_click_count=Sum('click_count'))
        articleData = {item['platform']: {k: v for k, v in item.items() if k != 'platform'} for item in articleData}
        return Response(data=articleData)


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
        logger.info(data)
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


from drf_spectacular.utils import extend_schema
from drf_spectacular.types import OpenApiTypes
from django.utils import timezone
from datetime import timedelta

# 修改 stats/views.py 中的 CollectArticalView 类
from utils.c_scheduler import collect_recent_articles_data


class CollectArticalView(APIView):
    """
    定时收集推文和评论数据的视图
    """
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary='手动触发推文数据收集',
        description='立即执行一次推文和评论数据的收集任务',
        tags=['数据统计'],
        responses={
            200: OpenApiTypes.OBJECT,
            400: OpenApiTypes.OBJECT
        }
    )
    def get(self, request):
        """
        手动触发收集任务
        """
        try:
            results = collect_recent_articles_data()
            return Response({'status': 'success', 'message': '数据收集完成', 'results': results})
        except Exception as e:
            logger.error(f"收集推文数据失败: {e}")
            return Response({'status': 'error', 'message': str(e)})

    @extend_schema(
        summary='设置定时收集任务',
        description='启动定时任务，每6小时自动收集推文和评论数据',
        tags=['数据统计'],
        responses={
            200: OpenApiTypes.OBJECT,
            400: OpenApiTypes.OBJECT
        }
    )
    def post(self, request):
        """
        启动定时任务（每6小时执行一次）
        """
        try:
            scheduler = get_global_scheduler()
            # 移除已存在的同名任务
            try:
                scheduler.remove_job('collect_artical_data')
            except:
                pass  # 如果任务不存在则忽略
            # 添加新的定时任务
            scheduler.add_job(
                func=collect_recent_articles_data,
                trigger=IntervalTrigger(hours=6),
                id='collect_artical_data',
                name='Collect Artical Data Every 6 Hours',
                replace_existing=True,
            )
            return Response({
                'status': 'success',
                'message': '定时任务已启动，将每6小时执行一次数据收集'
            })
        except Exception as e:
            logger.error(f"设置定时任务失败: {e}")
            return Response({'status': 'error', 'message': str(e)})
