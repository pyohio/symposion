# -*- coding: utf-8 -*-
# Generated by Django 1.11.9 on 2018-06-30 05:40
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('symposion_schedule', '0003_remove_presentation_additional_speakers'),
    ]

    operations = [
        migrations.AlterField(
            model_name='slot',
            name='name',
            field=models.CharField(editable=False, max_length=200),
        ),
    ]
