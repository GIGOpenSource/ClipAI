from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('social', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='poolaccount',
            name='usage_policy',
            field=models.CharField(
                choices=[('limited', 'Limited (2 per day)'), ('unlimited', 'Unlimited')],
                default='unlimited',
                help_text='limited: 每天最多 2 次；unlimited: 不限次',
                max_length=16,
            ),
        ),
    ]


