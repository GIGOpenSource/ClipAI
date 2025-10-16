from math import trunc

from django.contrib.auth.models import User
from rest_framework import serializers
from urllib3 import request
from django.db.models import Q

from utils.autoTask import scheduler

from .models import SimpleTask, SimpleTaskRun
from social.models import PoolAccount
from prompts.models import PromptConfig
from models.models import SocialPoolaccount, TasksSimpletaskrun, TasksSimpletask, TasksSimpletaskSelectedAccounts


class SimpleTaskSerializer(serializers.ModelSerializer):
    owner = serializers.HiddenField(default=serializers.CurrentUserDefault())

    class SelectedAccountSerializer(serializers.ModelSerializer):
        class Meta:
            model = PoolAccount
            fields = ['id', 'name']

        def to_internal_value(self, data):
            result = super().to_internal_value(data)
            # 确保 id 字段不丢失
            if isinstance(data, dict) and 'id' in data:
                result['id'] = data['id']
            return result

    # selected_accounts = serializers.PrimaryKeyRelatedField(queryset=PoolAccount.objects.all(), many=True, required=False)
    selected_accounts = SelectedAccountSerializer(many=True, required=False)
    prompt = serializers.PrimaryKeyRelatedField(queryset=PromptConfig.objects.all(), required=False, allow_null=True)
    # mentions = serializers.CharField(required=False, allow_blank=True)
    # tags = serializers.CharField(required=False, allow_blank=True)
    task_remark = serializers.CharField(required=False, allow_blank=True)
    select_status = serializers.BooleanField(required=False, default=None)
    task_timing_type = serializers.CharField(required=False, allow_blank=True,
                                             help_text='任务执行时间类型，可选值：once/timing')
    prompt_name = serializers.SerializerMethodField()
    # 人性化输入字段（后端会映射到 payload）
    twitter_reply_to_tweet_id = serializers.CharField(write_only=True, required=False, allow_blank=True,
                                                      help_text='Twitter 回复的推文 ID（仅当 type=reply_comment 且 provider=twitter）')
    facebook_page_id = serializers.CharField(write_only=True, required=False, allow_blank=True,
                                             help_text='Facebook 发帖 Page ID（仅当 type=post 且 provider=facebook）')
    facebook_comment_id = serializers.CharField(write_only=True, required=False, allow_blank=True,
                                                help_text='Facebook 回复的评论 ID（仅当 type=reply_comment 且 provider=facebook）')

    exec_type = serializers.CharField(required=False, allow_blank=True,
                                      help_text='"daily"（每日多次）或"fixed"（固定时间一次）')
    exec_datetime = serializers.DateTimeField(required=False, allow_null=True,
                                              help_text='固定执行时间（格式：YYYY-MM-DD HH:MM:SS）')
    exec_nums = serializers.IntegerField(required=False, allow_null=True,
                                         help_text='执行次数（仅当 exec_type=fixed 时有效）')
    mission_id = serializers.CharField(required=False, allow_blank=True,
                                      help_text='任务 ID（仅当 exec_type=fixed 时有效）')
    mission_status = serializers.CharField(required=False, allow_blank=True,
                                             help_text='任务状态（仅当 exec_type=fixed 时有效）')
    def get_prompt_name(self, obj):
        """获取关联的 prompt name"""
        if obj.prompt:
            return obj.prompt.name
        return None

    class Meta:
        model = SimpleTask
        fields = [
            'id', 'owner', 'type', 'provider', 'language', 'text', 'mentions', 'tags', 'payload', 'selected_accounts',
            'prompt', 'prompt_name',
            # 人性化输入字段（write-only）
            'twitter_reply_to_tweet_id', 'facebook_page_id', 'facebook_comment_id', 'last_run_at',
            # 只读运行结果
            'last_status', 'last_success', 'last_failed', 'last_run_at', 'last_text', 'task_remark',
            'created_at', 'select_status', 'task_timing_type','exec_type','exec_datetime','exec_nums','mission_id',
            'mission_status'
        ]
        read_only_fields = ['owner', 'last_status', 'last_success', 'last_failed', 'last_run_at', 'last_text',
                            'created_at', 'updated_at']

    def validate(self, attrs):
        # 无条件移除只写字段，确保它们不会传递给模型
        twitter_reply_id = attrs.pop('twitter_reply_to_tweet_id', None)
        facebook_page_id = attrs.pop('facebook_page_id', None)
        facebook_comment_id = attrs.pop('facebook_comment_id', None)

        provider = (attrs.get('provider') or getattr(self.instance or object(), 'provider', '')).lower()
        task_type = attrs.get('type') or getattr(self.instance or object(), 'type', '')
        attrs['provider'] = provider
        # 话题限制最多 5 个
        tags = attrs.get('tags', []) or []
        if not isinstance(tags, list) or any(not isinstance(x, str) for x in tags):
            raise serializers.ValidationError('tags 必须为字符串数组')
        if len(tags) > 5:
            raise serializers.ValidationError('最多 5 个话题标签')
        # mentions = attrs.get('mentions', []) or []
        # if not isinstance(mentions, list):
        #     raise serializers.ValidationError('mentions 必须为数组')
        if provider not in {'twitter', 'facebook'}:
            raise serializers.ValidationError('provider 仅支持 twitter/facebook')
        if task_type not in {'post', 'reply_comment'}:
            raise serializers.ValidationError('type 仅支持 post/reply_comment')

        # 人性化字段校验并写回 payload
        payload = attrs.get('payload')
        if payload is None:
            payload = {}
        elif not isinstance(payload, dict):
            # 如果 payload 不是字典类型，初始化为空字典
            payload = {}
        if provider == 'twitter' and task_type == 'reply_comment':
            tw_reply = attrs.pop('twitter_reply_to_tweet_id', None) or payload.get('comment_id')
            if not tw_reply:
                raise serializers.ValidationError('Twitter 回复需提供 twitter_reply_to_tweet_id')
            payload['comment_id'] = str(tw_reply)
        elif provider == 'facebook' and task_type == 'post':
            page_id = attrs.pop('facebook_page_id', None) or payload.get('page_id')
            if not page_id:
                raise serializers.ValidationError('Facebook 发帖需提供 facebook_page_id')
            payload['page_id'] = str(page_id)
        elif provider == 'facebook' and task_type == 'reply_comment':
            fb_cid = attrs.pop('facebook_comment_id', None) or payload.get('comment_id')
            if not fb_cid:
                raise serializers.ValidationError('Facebook 回复需提供 facebook_comment_id')
            payload['comment_id'] = str(fb_cid)

        attrs['payload'] = payload
        return attrs

    def create(self, validated_data):
        accounts_data = validated_data.pop('selected_accounts', [])
        exec_type = validated_data.pop('exec_type', [])
        exec_datetime = validated_data.pop('exec_datetime', [])
        exec_nums = validated_data.pop('exec_nums', [])
        selectStatus = validated_data["select_status"]
        task_timing_type = validated_data['task_timing_type']  # 任务类型  once/ timing'
        if self.context.get('request') and self.context[
            'request'].user.is_authenticated and 'owner' not in validated_data:
            validated_data['owner'] = self.context['request'].user
        obj = super().create(validated_data)
        accounts_data_ids = [item["id"] for item in accounts_data]
        owner = validated_data["owner"]
        if owner.is_superuser:
            datas = SocialPoolaccount.objects.filter(provider=validated_data["provider"],
                                                     status="active").values('id', 'name')
        else:
            datas = SocialPoolaccount.objects.filter(owner_id=owner.id, provider=validated_data["provider"],
                                                     status="active").values('id', 'name')
        if selectStatus is True:
            if len(accounts_data_ids) != 0:
                datas = datas.filter(Q(id__in=accounts_data_ids))
        if selectStatus is False:
            datas = datas.filter(~Q(id__in=accounts_data_ids))
        accounts_data = [item["id"] for item in datas]
        if task_timing_type == "timing":
            from utils.runTimingTask import run_timing_task
            from utils.autoTask import scheduler
            try:
                job_id = ''
                if exec_type == 'daily':
                    job_id = f'mission_daily_{obj.id}'
                    scheduler.add_job(
                        func=run_timing_task,
                        trigger='daily',  # 明确指定具体小时
                        job_id=job_id,
                        nums=exec_nums,
                        args=(obj.id,),
                        kwargs={}
                    )
                if exec_type == 'fixed':
                    job_id = f'mission_fixed_{obj.id}'
                    scheduler.add_job(
                        func=run_timing_task,
                        trigger="fixed",
                        job_id=job_id,
                        fixed_time=exec_datetime,
                        args=(obj.id,),
                        kwargs={},
                        replace_existing=True
                    )
                res = SimpleTask.objects.get(id=obj.id)
                res.mission_id = job_id
                res.save()
            except Exception as e:
                # 处理定时任务调度异常
                pass
        else:
            # 即时任务先保存再 调用启动
            print("1")
        obj.selected_accounts.set(accounts_data)
        return obj


def update(self, instance, validated_data):
    isSuper = validated_data["owner"].is_superuser
    if isSuper:
        datas = SocialPoolaccount.objects.filter(status="active").values('id', 'name')
    else:
        ownerId = validated_data["owner"].id
        datas = SocialPoolaccount.objects.filter(owner_id=ownerId, provider=validated_data["provider"],
                                                 status="active").values('id', 'name')
    accounts_data = validated_data.pop('selected_accounts', None)
    selectStatus = validated_data["select_status"]
    accounts_list = [item["id"] for item in accounts_data]
    if selectStatus is True:
        if len(accounts_list) != 0:
            datas = datas.filter(Q(id__in=accounts_list))
        accounts_data = [{"id": item["id"], "name": item["name"]} for item in datas]
    if selectStatus is False:
        datas = datas.filter(~Q(id__in=accounts_list))
        accounts_data = [{"id": item["id"], "name": item["name"]} for item in datas]
    obj = super().update(instance, validated_data)

    # 正确处理 selected_accounts 关联
    if accounts_data is not None:
        if accounts_data:
            # 从嵌套数据中提取实际的 PoolAccount 对象
            account_objects = []
            for account in accounts_data:
                if isinstance(account, dict) and 'id' in account:
                    try:
                        account_obj = PoolAccount.objects.get(id=account['id'])
                        account_objects.append(account_obj)
                    except PoolAccount.DoesNotExist:
                        raise serializers.ValidationError(f"账户 ID {account['id']} 不存在")
                elif isinstance(account, int):
                    try:
                        account_obj = PoolAccount.objects.get(id=account)
                        account_objects.append(account_obj)
                    except PoolAccount.DoesNotExist:
                        raise serializers.ValidationError(f"账户 ID {account} 不存在")
                elif hasattr(account, 'id'):  # 如果已经是模型实例
                    account_objects.append(account)

            # 设置多对多关系
            obj.selected_accounts.set(account_objects)
        else:
            # 如果传递空数组，清空所有关联
            obj.selected_accounts.clear()

    return obj


class SimpleTaskRunSerializer(serializers.ModelSerializer):
    owner_name = serializers.ReadOnlyField(source='owner.username')
    task_id = serializers.ReadOnlyField(source='task.id')
    task_provider = serializers.ReadOnlyField(source='task.provider')
    prompt_id = serializers.ReadOnlyField(source='prompt.id')
    prompt_name = serializers.ReadOnlyField(source='prompt.name')
    account_count = serializers.SerializerMethodField()
    success_count = serializers.SerializerMethodField()
    fail_count = serializers.SerializerMethodField()

    def get_account_count(self, obj):
        # 通过 TasksSimpletaskSelectedAccounts 中间表获取关联的 PoolAccount 数量
        return TasksSimpletaskSelectedAccounts.objects.filter(simpletask=obj).count()

    def get_success_count(self, obj):
        # 获取任务成功执行的次数
        return TasksSimpletaskrun.objects.filter(task=obj, success='success').count()

    def get_fail_count(self, obj):
        # 获取任务失败执行的次数
        return TasksSimpletaskrun.objects.filter(task=obj, success='failed').count()

    class Meta:
        model = TasksSimpletask
        fields = ['id', 'provider', 'type', 'text', 'created_at', 'owner_id', 'task_id', 'prompt_name',
                  'task_provider', 'owner_name', 'prompt_id', 'account_count', 'success_count', 'fail_count']


class SimpleTaskRunDetailSerializer(serializers.ModelSerializer):
    class Meta:
        model = TasksSimpletaskrun
        fields = '__all__'
