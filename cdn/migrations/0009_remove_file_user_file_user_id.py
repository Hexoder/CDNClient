# Generated by Django 5.0.4 on 2025-01-30 10:57

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('cdn', '0008_alter_file_user'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='file',
            name='user',
        ),
        migrations.AddField(
            model_name='file',
            name='user_id',
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
    ]
