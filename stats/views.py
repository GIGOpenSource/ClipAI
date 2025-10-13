from django.db.models import Sum, Count
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
from models.models import AuthUser
from utils.utils import logger, ApiResponse
from .models import DailyStat
from .serializers import SummaryResponseSerializer
from tasks.models import TArticle
from social.models import PoolAccount
from drf_spectacular.utils import extend_schema, OpenApiParameter
from drf_spectacular.types import OpenApiTypes

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
    @extend_schema(
        summary='统计概览（大于等于日期数据）',
        tags=['数据统计'],
        responses=SummaryResponseSerializer,
        parameters=[
            OpenApiParameter(
                name='start_date',
                type=OpenApiTypes.DATE,
                location=OpenApiParameter.QUERY,
                description='开始日期 (格式: YYYY-MM-DD)，返回大于等于该日期的数据,不带日期是总数',
                required=False
            ),
            OpenApiParameter(
                name='end_date',
                type=OpenApiTypes.DATE,
                location=OpenApiParameter.QUERY,
                description='结束日期 (格式: YYYY-MM-DD)，返回小于等于该日期的数据',
                required=False
            ),
            OpenApiParameter(
                name='enterprise_id',
                type=OpenApiTypes.INT,
                location=OpenApiParameter.QUERY,
                description='企业用户ID，仅超级管理员可使用此参数查询指定企业的数据',
                required=False
            )
        ]
    )
    def get(self, request):
        userId = request.user.id
        userData = AuthUser.objects.get(id=userId)
        if userData.is_superuser:
            robotList = PoolAccount.objects.all()
            enterprise_id = request.query_params.get('enterprise_id')
            if enterprise_id:
                robotList = robotList.filter(owner_id=enterprise_id)
            robotList = [robot["id"] for robot in robotList.values('id')]
        else:
            robotList = PoolAccount.objects.filter(owner_id=userId).values('id')
            robotList = [robot["id"] for robot in robotList]
        # 获取查询参数中的开始日期
        start_date = request.query_params.get('start_date')
        end_date = request.query_params.get('end_date')
        # 构建查询集
        article_query = TArticle.objects.filter(robot_id__in=robotList)
        from datetime import datetime
        # 如果提供了开始日期，则过滤大于等于该日期的数据
        if start_date:
            try:
                start_date_obj = datetime.strptime(start_date, '%Y-%m-%d').date()
                article_query = article_query.filter(created_at__date__gte=start_date_obj)
            except ValueError:
                return ApiResponse({'error': '日期格式错误，请使用 YYYY-MM-DD 格式'}, status=400)
        if end_date:
            try:
                end_date_obj = datetime.strptime(end_date, '%Y-%m-%d').date()
                article_query = article_query.filter(created_at__date__lte=end_date_obj)
            except ValueError as e:
                logger.error(f"结束日期解析失败: {e}")
                return ApiResponse(message=f'结束日期格式错误: {str(e)}，请使用 YYYY-MM-DD 格式', status=400)
            except Exception as e:
                logger.error(f"处理结束日期时发生未知错误: {e}")
                return ApiResponse(message=f'处理结束日期时发生错误: {str(e)}', status=400)

        # 如果传了日期，按平台分组返回数据
        if start_date or end_date:
            articleData = article_query.values('platform').annotate(
                total_impression_count=Sum('impression_count'),
                total_comment_count=Sum('comment_count'),
                total_message_count=Sum('message_count'),
                total_like_count=Sum('like_count'),
                total_click_count=Sum('click_count'),
                total_public_count = Count('id')
            )
            articleData = {item['platform']: {k: v for k, v in item.items() if k != 'platform'} for item in articleData}
            return ApiResponse(data=articleData)
        else:
            # 如果未传日期，按平台分组计算所有数据的总和
            articleData = article_query.values('platform').annotate(
                total_impression_count=Sum('impression_count'),
                total_comment_count=Sum('comment_count'),
                total_message_count=Sum('message_count'),
                total_like_count=Sum('like_count'),
                total_click_count=Sum('click_count'),
                total_public_count=Count('id')
            )

            result = {}
            for item in articleData:
                platform = item['platform']
                platform_data = {k: v if v is not None else 0 for k, v in item.items() if k != 'platform'}

                # 计算各种率
                total_posts = platform_data['total_public_count']
                if total_posts > 0:
                    # 点赞率 曝光率
                    platform_data['exposure_rate'] = round(platform_data['total_impression_count'] / total_posts, 4)
                    platform_data['like_rate'] = round(platform_data['total_like_count'] / total_posts, 4)
                else:
                    platform_data['exposure_rate'] = 0
                    platform_data['like_rate'] = 0

                total_impressions = platform_data['total_impression_count']
                if total_impressions > 0:
                    platform_data['click_rate'] = round(platform_data['total_click_count'] / total_impressions, 4)
                else:
                    platform_data['click_rate'] = 0
                result[platform] = platform_data
            return ApiResponse(data=result)

class DetailView(APIView):
    permission_classes = [IsAuthenticated]
    @extend_schema(
        summary='统计数据详情',
        tags=['数据统计'],
        responses=OpenApiTypes.OBJECT,
        parameters=[
            OpenApiParameter(
                name='platform',
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                description='平台名称 twitter ins fb',
                required=True
            ),
            OpenApiParameter(
                name='start_date',
                type=OpenApiTypes.DATE,
                location=OpenApiParameter.QUERY,
                description='开始日期 (格式: YYYY-MM-DD)',
                required=False
            ),
            OpenApiParameter(
                name='enterprise_id',
                type=OpenApiTypes.INT,
                location=OpenApiParameter.QUERY,
                description='企业用户ID，仅超级管理员可使用此参数查询指定企业的数据',
                required=False
            )
        ]
    )
    def get(self, request):
        userId = request.user.id
        userData = AuthUser.objects.get(id=userId)
        if userData.is_superuser:
            robotList = PoolAccount.objects.all()
            enterprise_id = request.query_params.get('enterprise_id')
            if enterprise_id:
                robotList = robotList.filter(owner_id=enterprise_id)
            robotList = [robot["id"] for robot in robotList.values('id')]
        else:
            robotList = PoolAccount.objects.filter(owner_id=userId).values('id')
            robotList = [robot["id"] for robot in robotList]
        # 获取查询参数
        platform = request.query_params.get('platform')
        start_date = request.query_params.get('start_date')
        end_date = request.query_params.get('end_date')
        if not platform:
            return ApiResponse({'error': 'platform参数是必需的'}, status=400)
        # 构建查询集
        article_query = TArticle.objects.filter(
            robot_id__in=robotList,
            platform=platform
        )
        # 处理开始日期
        if start_date:
            try:
                from datetime import datetime
                start_date_obj = datetime.strptime(start_date, '%Y-%m-%d').date()
                article_query = article_query.filter(created_at__date__gte=start_date_obj)
            except ValueError:
                return ApiResponse(message=f'开始日期格式错误，请使用 YYYY-MM-DD 格式', status=400)
        # 处理结束日期
        if end_date:
            try:
                from datetime import datetime
                end_date_obj = datetime.strptime(end_date, '%Y-%m-%d').date()
                article_query = article_query.filter(created_at__date__lte=end_date_obj)
            except ValueError:
                return ApiResponse(message=f'结束日期格式错误，请使用 YYYY-MM-DD 格式', status=400)
        # 查询详细数据
        detail_data = article_query.values(
            'created_at',
            'impression_count',
            'comment_count',
            'message_count',
            'like_count',
            'click_count'
        ).order_by('-created_at')
        return ApiResponse(data=list(detail_data))

class OverviewView(APIView):
    permission_classes = [IsAuthenticated]
    @extend_schema(summary='昨日统计明细（当前用户，单日一行）', tags=['数据统计'])
    def get(self, request):
        if not (request.user and request.user.is_authenticated):
            return ApiResponse({'results': []})
        yesterday = (timezone.now().date() - timedelta(days=1))
        stats_qs = DailyStat.objects.filter(date=yesterday, owner_id=request.user.id)
        data = list(stats_qs.values(
            'date', 'account_count', 'ins', 'twitter', 'fb', 'post_count',
            'reply_comment_count', 'reply_message_count', 'total_impressions'
        ).order_by('-date'))
        logger.info(data)
        # CSV 导出
        if request.query_params.get('format') == 'csv':
            response = HttpResponse(content_type='text/csv; charset=utf-8')
            response['Content-Disposition'] = 'attachment; filename="daily_stats.csv"'
            writer = csv.writer(response)
            writer.writerow(['日期', '账号数量', 'ins', 'twitter', 'fb', '发帖数', '回复评论数', '回复消息数', '总曝光量'])
            for r in data:
                writer.writerow([
                    r['date'], r['account_count'], r['ins'], r['twitter'], r['fb'],
                    r['post_count'], r['reply_comment_count'], r['reply_message_count'], r['total_impressions']
                ])
            return response
        return ApiResponse(data)




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
            return ApiResponse({'status': 'success', 'message': '数据收集完成', 'results': results})
        except Exception as e:
            logger.error(f"收集推文数据失败: {e}")
            return ApiResponse(f'message: {str(e)}')

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
            return ApiResponse({
                'status': 'success',
                'message': '定时任务已启动，将每6小时执行一次数据收集'
            })
        except Exception as e:
            logger.error(f"设置定时任务失败: {e}")
            return ApiResponse({'status': 'error', 'message': str(e)})
