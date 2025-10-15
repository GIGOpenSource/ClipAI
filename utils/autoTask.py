from apscheduler.schedulers.background import BackgroundScheduler
from django_apscheduler.jobstores import DjangoJobStore
from django.utils import timezone
from pycparser.c_ast import Switch

from utils.scheduleUnit import createScheduleTriggers


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
                print("调度器启动成功")
            except Exception as e:
                print(f"调度器启动失败: {e}")
                self.shutdown()

    def shutdown(self):
        """关闭调度器"""
        if self.is_running:
            self.scheduler.shutdown()
            self.is_running = False
            print("调度器已关闭")

    def add_job(self, func, triggerType, job_id, replace_existing=True, **kwargs):
        """
        添加定时任务

        :param func: 任务函数
        :param triggerType: 触发器类型 (如 'cron周期特定时间点执行', 'interval间隔', 'date日期')
        :param job_id: 任务唯一标识
        :param replace_existing: 是否替换已存在的任务
        :param kwargs: 触发器参数 (如 hour, minute 等)
        """
        # if trigger == "data":
        #
        # if trigger == "interval":
        #
        # if trigger == "cron":
        trigger = createScheduleTriggers(triggerType, **kwargs)
        try:
            self.scheduler.add_job(
                func,
                trigger=trigger,
                id=job_id,
                replace_existing=replace_existing, **kwargs
            )
            print(f"任务 {job_id} 添加成功")
        except Exception as e:
            print(f"添加任务 {job_id} 失败: {e}")

    def remove_job(self, job_id):
        """删除定时任务"""
        try:
            self.scheduler.remove_job(job_id)
            print(f"任务 {job_id} 已删除")
        except Exception as e:
            print(f"删除任务 {job_id} 失败: {e}")

    def pause_job(self, job_id):
        """暂停定时任务"""
        try:
            self.scheduler.pause_job(job_id)
            print(f"任务 {job_id} 已暂停")
        except Exception as e:
            print(f"暂停任务 {job_id} 失败: {e}")

    def resume_job(self, job_id):
        """恢复定时任务"""
        try:
            self.scheduler.resume_job(job_id)
            print(f"任务 {job_id} 已恢复")
        except Exception as e:
            print(f"恢复任务 {job_id} 失败: {e}")

    def modify_job(self, job_id, **kwargs):
        """
        修改定时任务

        :param job_id: 任务唯一标识
        :param kwargs: 需要修改的参数 (如 hour, minute 等)
        """
        try:
            self.scheduler.modify_job(job_id, **kwargs)
            print(f"任务 {job_id} 已修改")
        except Exception as e:
            print(f"修改任务 {job_id} 失败: {e}")

    def get_all_jobs(self):
        """获取所有定时任务"""
        try:
            jobs = self.scheduler.get_jobs()
            print(f"获取到 {len(jobs)} 个任务")
            return jobs
        except Exception as e:
            print(f"获取任务失败: {e}")
            return []

# 初始化调度器
scheduler = DjangoTaskScheduler()
scheduler.start()
