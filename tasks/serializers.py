from rest_framework import serializers
from .models import SimpleTask
from social.models import PoolAccount
from prompts.models import PromptConfig


class SimpleTaskSerializer(serializers.ModelSerializer):
    owner = serializers.HiddenField(default=serializers.CurrentUserDefault())
    selected_accounts = serializers.PrimaryKeyRelatedField(queryset=PoolAccount.objects.all(), many=True, required=False)
    prompt = serializers.PrimaryKeyRelatedField(queryset=PromptConfig.objects.all(), required=False, allow_null=True)

    # 人性化输入字段（后端会映射到 payload）
    twitter_reply_to_tweet_id = serializers.CharField(write_only=True, required=False, allow_blank=True, help_text='Twitter 回复的推文 ID（仅当 type=reply_comment 且 provider=twitter）')
    facebook_page_id = serializers.CharField(write_only=True, required=False, allow_blank=True, help_text='Facebook 发帖 Page ID（仅当 type=post 且 provider=facebook）')
    facebook_comment_id = serializers.CharField(write_only=True, required=False, allow_blank=True, help_text='Facebook 回复的评论 ID（仅当 type=reply_comment 且 provider=facebook）')

    class Meta:
        model = SimpleTask
        fields = [
            'id', 'owner', 'type', 'provider', 'language', 'text', 'mentions', 'tags', 'payload', 'selected_accounts', 'prompt',
            # 人性化输入字段（write-only）
            'twitter_reply_to_tweet_id', 'facebook_page_id', 'facebook_comment_id',
            # 只读运行结果
            'last_status', 'last_success', 'last_failed', 'last_run_at', 'last_text',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['owner', 'last_status', 'last_success', 'last_failed', 'last_run_at', 'last_text', 'created_at', 'updated_at']

    def validate(self, attrs):
        provider = (attrs.get('provider') or getattr(self.instance or object(), 'provider', '')).lower()
        task_type = attrs.get('type') or getattr(self.instance or object(), 'type', '')
        attrs['provider'] = provider
        # 话题限制最多 5 个
        tags = attrs.get('tags', []) or []
        if not isinstance(tags, list) or any(not isinstance(x, str) for x in tags):
            raise serializers.ValidationError('tags 必须为字符串数组')
        if len(tags) > 5:
            raise serializers.ValidationError('最多 5 个话题标签')
        mentions = attrs.get('mentions', []) or []
        if not isinstance(mentions, list):
            raise serializers.ValidationError('mentions 必须为数组')
        if provider not in {'twitter', 'facebook'}:
            raise serializers.ValidationError('provider 仅支持 twitter/facebook')
        if task_type not in {'post', 'reply_comment'}:
            raise serializers.ValidationError('type 仅支持 post/reply_comment')

        # 人性化字段校验并写回 payload
        payload = dict(attrs.get('payload') or {})
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
        accounts = validated_data.pop('selected_accounts', [])
        if self.context.get('request') and self.context['request'].user.is_authenticated and 'owner' not in validated_data:
            validated_data['owner'] = self.context['request'].user
        obj = super().create(validated_data)
        if accounts:
            obj.selected_accounts.set(accounts)
        return obj

    def update(self, instance, validated_data):
        accounts = validated_data.pop('selected_accounts', None)
        obj = super().update(instance, validated_data)
        if accounts is not None:
            obj.selected_accounts.set(accounts)
        return obj

