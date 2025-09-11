from django.test import TestCase
from django.contrib.auth import get_user_model
from .serializers import ScheduledTaskSerializer


class ScheduledTaskValidationTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username='u1', password='p')

    def test_follow_only_twitter(self):
        # follow + facebook -> invalid
        data = {
            'owner': self.user.id,
            'type': 'follow',
            'provider': 'facebook',
            'payload_template': {},
        }
        s = ScheduledTaskSerializer(data=data)
        self.assertFalse(s.is_valid())
        self.assertIn('关注任务目前仅支持 Twitter 平台', str(s.errors))

        # follow + twitter -> valid
        data['provider'] = 'twitter'
        s2 = ScheduledTaskSerializer(data=data)
        self.assertTrue(s2.is_valid(), s2.errors)

    def test_instagram_post_requires_media_url(self):
        # missing media -> invalid
        data = {
            'owner': self.user.id,
            'type': 'post',
            'provider': 'instagram',
            'payload_template': {'caption': 'hello'},
        }
        s = ScheduledTaskSerializer(data=data)
        self.assertFalse(s.is_valid())
        self.assertIn('Instagram 发帖需要提供 image_url 或 video_url', str(s.errors))

        # with image_url -> valid
        data['payload_template'] = {'caption': 'hello', 'image_url': 'https://example.com/a.jpg'}
        s2 = ScheduledTaskSerializer(data=data)
        self.assertTrue(s2.is_valid(), s2.errors)
