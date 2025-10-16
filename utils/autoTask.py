import pickle
import random
from datetime import datetime

from apscheduler.schedulers.background import BackgroundScheduler
from django_apscheduler.jobstores import DjangoJobStore
from django.utils import timezone

from utils.utils import logger

fixed_exec_time = timezone.make_aware(
    datetime(2025, 10, 16, 10, 42, 0)  # 年、月、日、时、分、秒
)

class DjangoTaskScheduler:
    def __init__(self):
        # 初始化调度器
        self.scheduler = BackgroundScheduler(
            timezone=timezone.get_current_timezone_name()
        )
        # 添加数据库存储
        self.scheduler.add_jobstore(DjangoJobStore(), 'default')
        self.is_running = False

    def start(self):
        """启动调度器"""
        if not self.is_running:
            try:
                self.scheduler.start()
                self.is_running = True
                logger.info("调度器启动成功")
            except Exception as e:
                logger.info(f"调度器启动失败:  ")
                self.shutdown()

    def shutdown(self):
        """关闭调度器"""
        if self.is_running:
            self.scheduler.shutdown()
            self.is_running = False
            logger.info("调度器已关闭")

    def add_job(self, func, trigger, job_id, fixed_time=None,replace_existing=True, nums=None, **kwargs):
        """
        添加定时任务
        :param func: 任务函数
        :param trigger: 触发器类型 (如 'cron周期特定时间点执行', 'interval间隔', 'date日期')
        :param job_id: 任务唯一标识
        :param replace_existing: 是否替换已存在的任务
        :param kwargs: 触发器参数 (如 hour, minute 等)
        """
        try:
            if trigger == "daily":
                """
                每日执行N次  trigger=daily    nums=1~5
                """
                if nums is None or not (1 <= nums <= 5):
                    raise ValueError("当trigger为'daily'时，nums必须为1~5之间的整数")
                random_hours = random.sample(range(24), nums)
                random_hours.sort()
                hour_str = ",".join(map(str, random_hours))
                self.scheduler.add_job(
                    func,
                    trigger='cron',
                    id=job_id,
                    hour=hour_str,
                    minute=kwargs.get('minute', 0),  # 可指定分钟，默认0分
                    replace_existing=replace_existing,
                    args=kwargs.get('args', ()),
                    kwargs=kwargs.get('kwargs', {})
                )
                logger.info(f"每日随机任务 {job_id} 添加成功，每日执行{nums}次，时间点：{random_hours}时")
            if trigger == "fixed":
                """
                每fixed 
                """
                scheduler.add_job(
                    func,
                    trigger='date',
                    job_id=job_id,
                    run_date=fixed_time,
                    args=kwargs.get('args', ()),
                    kwargs=kwargs.get('kwargs', {})
                )
                logger.info(f"固定任务 {job_id} 添加成功，每日执行{nums}次，时间点：{fixed_time}时")
            if trigger == "fixed213":
                self.scheduler.add_job(
                        func,
                        trigger=trigger,
                        id=job_id,
                        replace_existing=replace_existing, **kwargs
                )
                logger.info(f"任务 {job_id} 添加成功")
        except Exception as e:
            logger.info(f"添加任务 {job_id} 失败: {e}")

    def remove_job(self, job_id):
        """删除定时任务"""
        try:
            self.scheduler.remove_job(job_id)
            logger.info(f"任务 {job_id} 已删除")
        except Exception as e:
            logger.info(f"删除任务 {job_id} 失败: {e}")

    def pause_job(self, job_id):
        """暂停定时任务"""
        try:
            self.scheduler.pause_job(job_id)
            logger.info(f"任务 {job_id} 已暂停")
        except Exception as e:
            logger.info(f"暂停任务 {job_id} 失败: {e}")

    def resume_job(self, job_id):
        """恢复定时任务"""
        try:
            self.scheduler.resume_job(job_id)
            logger.info(f"任务 {job_id} 已恢复")
        except Exception as e:
            logger.info(f"恢复任务 {job_id} 失败: {e}")

    def modify_job(self, job_id, **kwargs):
        """
        修改定时任务

        :param job_id: 任务唯一标识
        :param kwargs: 需要修改的参数 (如 hour, minute 等)
        """
        try:
            self.scheduler.modify_job(job_id, **kwargs)
            logger.info(f"任务 {job_id} 已修改")
        except Exception as e:
            logger.info(f"修改任务 {job_id} 失败: {e}")

    def get_all_jobs(self):
        """获取所有定时任务"""
        try:
            jobs = self.scheduler.get_jobs()
            logger.info(f"获取到 {len(jobs)} 个任务")
            return jobs
        except Exception as e:
            logger.info(f"获取任务失败: {e}")
            return []

    def get_job(self, job_id):
        """获取指定任务（修正版）"""
        try:
            job = self.scheduler.get_job(job_id)
            if not job:
                return "任务不存在"
            if job:
                logger.info(f"获取任务 {job_id} 成功")
                # 直接从 job 对象获取参数（无需手动反序列化 job_state）
                args = job.args  # 位置参数
                kwargs = job.kwargs  # 关键字参数
                func_name = job.func.__name__  # 任务函数名
                func_module = job.func.__module__  # 任务函数所在模块
                logger.info(f"任务函数: {func_module}.{func_name}")
                logger.info(f"位置参数: {args}")
                logger.info(f"关键字参数: {kwargs}")
                return job
            else:
                logger.info(f"任务 {job_id} 不存在")
                return None
        except Exception as e:
            logger.info(f"获取任务 {job_id} 失败: {e}")

# 初始化调度器
scheduler = DjangoTaskScheduler()
scheduler.start()

def user_stat_task(user_id, task_desc):
    """用户统计任务函数"""
    logger.info(f"执行用户统计任务：用户ID={user_id}，任务描述={task_desc}")

# scheduler.get_all_jobs("user_stat_daily_1001")