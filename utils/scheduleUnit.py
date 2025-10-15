#!/usr/bin/env python
# -*- coding: UTF-8 -*-
"""
@Project ：ClipAI 
@File    ：scheduleUnit.py
@Author  ：LYP
@Date    ：2025/10/15 9:37 
@description :定时任务调度
"""
# 特定时间执行一次任务
from apscheduler.triggers.date import DateTrigger
# 间隔性时间任务
from apscheduler.triggers.interval import IntervalTrigger
# 重复性时间任务
from apscheduler.triggers.cron import CronTrigger



def createScheduleTriggers(triggersType: str = 'date' or 'interval' or 'cron', *args, **kwargs):
    """
    获取定时任务触发器
    :param triggersType: one,interval,cron
    :param args:
    :param kwargs:
    :return:
    """

    if triggersType == "date":
        triggers = DateTrigger(run_date=kwargs.get("run_date"))
    elif triggersType == "interval":
        triggers = IntervalTrigger(**kwargs)
    else:
        triggers = CronTrigger(**kwargs)
    return triggers
