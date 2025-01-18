# Generated by Django 5.1.4 on 2025-01-15 22:09

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('cdn', '0003_alter_file_uuid'),
        ('contenttypes', '0002_remove_content_type_name'),
    ]

    operations = [
        migrations.AddField(
            model_name='file',
            name='content_type',
            field=models.ForeignKey(default=1, on_delete=django.db.models.deletion.CASCADE, to='contenttypes.contenttype'),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='file',
            name='object_id',
            field=models.PositiveIntegerField(default=1),
            preserve_default=False,
        ),
    ]
