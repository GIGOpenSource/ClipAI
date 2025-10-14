from django.contrib import admin
from django import forms
from .models import SimpleTask, SimpleTaskRun


class SimpleTaskAdminForm(forms.ModelForm):
    # 人性化输入：用逗号分隔字符串填充 JSON 字段
    tags_text = forms.CharField(required=False, help_text='逗号分隔，如: ai,python,news')
    mentions_text = forms.CharField(required=False, help_text='逗号分隔，不带@，如: user1,user2')

    # 人性化输入：映射到 payload
    twitter_reply_to_tweet_id = forms.CharField(required=False, help_text='Twitter 回复的推文 ID')
    facebook_page_id = forms.CharField(required=False, help_text='Facebook 发帖 Page ID')
    facebook_comment_id = forms.CharField(required=False, help_text='Facebook 回复的评论 ID')

    class Meta:
        model = SimpleTask
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        inst = self.instance if getattr(self, 'instance', None) and self.instance.pk else None
        # 反显 tags/mentions
        self.fields['tags_text'].initial = ','.join((inst.tags or [])) if inst else ''
        self.fields['mentions_text'].initial = ','.join((inst.mentions or [])) if inst else ''
        # 反显 payload 的常用字段
        payload = (inst.payload or {}) if inst else {}
        self.fields['twitter_reply_to_tweet_id'].initial = payload.get('comment_id', '') if inst and inst.provider == 'twitter' and inst.type == 'reply_comment' else ''
        self.fields['facebook_page_id'].initial = payload.get('page_id', '') if inst and inst.provider == 'facebook' and inst.type == 'post' else ''
        self.fields['facebook_comment_id'].initial = payload.get('comment_id', '') if inst and inst.provider == 'facebook' and inst.type == 'reply_comment' else ''

    def clean(self):
        cleaned = super().clean()
        provider = (cleaned.get('provider') or '').lower()
        ttype = cleaned.get('type') or ''
        # 解析 tags/mentions
        tags_text = (cleaned.pop('tags_text', '') or '').strip()
        mentions_text = (cleaned.pop('mentions_text', '') or '').strip()
        cleaned['tags'] = [s.strip().lstrip('#') for s in tags_text.split(',') if s.strip()][:5]
        cleaned['mentions'] = [s.strip().lstrip('@') for s in mentions_text.split(',') if s.strip()]
        # 处理 payload
        payload = dict(cleaned.get('payload') or {})
        if provider == 'twitter' and ttype == 'reply_comment':
            twid = (cleaned.pop('twitter_reply_to_tweet_id', '') or '').strip()
            if not twid:
                raise forms.ValidationError('Twitter 回复需填写“Twitter 回复的推文 ID”')
            payload['comment_id'] = twid
        elif provider == 'facebook' and ttype == 'post':
            pid = (cleaned.pop('facebook_page_id', '') or '').strip()
            if not pid:
                raise forms.ValidationError('Facebook 发帖需填写“Facebook 发帖 Page ID”')
            payload['page_id'] = pid
        elif provider == 'facebook' and ttype == 'reply_comment':
            cid = (cleaned.pop('facebook_comment_id', '') or '').strip()
            if not cid:
                raise forms.ValidationError('Facebook 回复需填写“Facebook 回复的评论 ID”')
            payload['comment_id'] = cid
        cleaned['payload'] = payload
        return cleaned


@admin.register(SimpleTask)
class SimpleTaskAdmin(admin.ModelAdmin):
    form = SimpleTaskAdminForm
    list_display = ('id', 'owner', 'type', 'provider', 'last_status', 'last_success', 'last_failed', 'last_run_at', 'created_at', 'updated_at')
    list_filter = ('provider', 'type')
    search_fields = ('owner__username',)
    fieldsets = (
        (None, {
            'fields': (
                'owner', 'provider', 'type', 'language', 'prompt', 'text',
                'tags_text', 'mentions_text',
                'selected_accounts',
            )
        }),
        ('平台参数（按需填写）', {
            'fields': (
                'twitter_reply_to_tweet_id', 'facebook_page_id', 'facebook_comment_id',
            )
        }),
        ('调试', {
            'classes': ('collapse',),
            'fields': ('payload', 'last_text',),
        }),
    )


