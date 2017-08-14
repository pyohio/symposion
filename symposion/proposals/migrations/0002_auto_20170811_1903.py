# -*- coding: utf-8 -*-
# Generated by Django 1.9.2 on 2017-08-11 19:03
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('symposion_proposals', '0001_initial'),
    ]

    operations = [
        migrations.AlterField(
            model_name='proposalbase',
            name='abstract',
            field=models.TextField(blank=True, help_text="Detailed outline. Will be made public if your proposal is accepted. Edit using <a href='http://daringfireball.net/projects/markdown/basics' target='_blank'>Markdown</a>.", verbose_name='Detailed Abstract'),
        ),
        migrations.AlterField(
            model_name='proposalbase',
            name='description',
            field=models.TextField(blank=True, help_text='If your proposal is accepted this will be made public and printed in the program. Should be one paragraph, maximum 400 characters.', max_length=400, verbose_name='Brief Description'),
        ),
    ]