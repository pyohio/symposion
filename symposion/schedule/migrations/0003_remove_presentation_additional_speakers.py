# -*- coding: utf-8 -*-
# Generated by Django 1.11.9 on 2018-06-23 06:06
from __future__ import unicode_literals

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('symposion_schedule', '0002_slot_name'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='presentation',
            name='additional_speakers',
        ),
    ]
