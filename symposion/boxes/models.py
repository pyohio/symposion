from django.db import models

import reversion

from markitup.fields import MarkupField

from symposion.utils.user import User


class Box(models.Model):

    label = models.CharField(max_length=100, db_index=True)
    content = MarkupField(blank=True)

    created_by = models.ForeignKey(User, related_name="boxes")
    last_updated_by = models.ForeignKey(User, related_name="updated_boxes")

    def __unicode__(self):
        return self.label

    class Meta:
        verbose_name_plural = "boxes"


reversion.register(Box)
