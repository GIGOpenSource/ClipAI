from django.contrib import admin
from django import forms
from .models import SocialConfig, SocialAccount


@admin.register(SocialConfig)
class SocialConfigAdmin(admin.ModelAdmin):
    list_display = ('name', 'provider', 'owner', 'enabled', 'is_default', 'priority', 'created_at')
    list_filter = ('provider', 'enabled', 'is_default')
    search_fields = ('name', 'owner__username')


class SocialAccountAdminForm(forms.ModelForm):
    class Meta:
        model = SocialAccount
        fields = '__all__'

    def save(self, commit=True):
        instance: SocialAccount = super().save(commit=False)
        # 仅当表单中对应字段有变更时，才更新密钥字段，避免重复二次加密
        if 'access_token' in self.changed_data:
            raw = self.cleaned_data.get('access_token') or ''
            if raw:
                instance.set_access_token(raw)
        if 'refresh_token' in self.changed_data:
            raw = self.cleaned_data.get('refresh_token') or ''
            if raw:
                instance.set_refresh_token(raw)
        if commit:
            instance.save()
            self.save_m2m()
        return instance


class SocialAccountInline(admin.TabularInline):
    model = SocialAccount
    form = SocialAccountAdminForm
    extra = 0
    fields = (
        'owner', 'external_user_id', 'external_username', 'status',
        'access_token', 'refresh_token', 'expires_at',
    )
    show_change_link = True


@admin.register(SocialAccount)
class SocialAccountAdmin(admin.ModelAdmin):
    list_display = ('id','owner', 'provider', 'external_username', 'status', 'health_status', 'expires_at', 'last_checked_at', 'updated_at')
    list_filter = ('provider', 'status', 'health_status')
    search_fields = ('owner__username', 'external_username', 'external_user_id')

SocialConfigAdmin.inlines = [SocialAccountInline]

# Register your models here.
