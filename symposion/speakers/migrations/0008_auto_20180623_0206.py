# -*- coding: utf-8 -*-
# Generated by Django 1.11.9 on 2018-06-23 06:06
from __future__ import unicode_literals

from django.db import migrations, models
import symposion.speakers.models


class Migration(migrations.Migration):

    dependencies = [
        ('symposion_speakers', '0007_auto_20170810_1651'),
    ]

    operations = [
        migrations.AlterField(
            model_name='speakerbase',
            name='photo',
            field=models.ImageField(blank=True, upload_to=symposion.speakers.models.speaker_image_path, verbose_name='Photo'),
        ),
    ]