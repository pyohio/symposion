# -*- coding: utf-8 -*-
# Generated by Django 1.11.22 on 2019-07-19 11:50
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('symposion_schedule', '0006_slot_title_override'),
    ]

    operations = [
        migrations.AddField(
            model_name='presentation',
            name='feedback_url',
            field=models.URLField(null=True),
        ),
    ]
