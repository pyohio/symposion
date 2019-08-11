import logging
import os
import sys

import requests

from django.core.management.base import BaseCommand

from symposion.schedule.models import Presentation

VIDEO_DATA_URL = os.environ["VIDEO_DATA_URL"]
STATIC_SITE_WEBHOOK = os.environ.get("STATIC_SITE_WEBHOOK")

logging.basicConfig(stream=sys.stdout, level=logging.DEBUG)
logger = logging.getLogger()

class Command(BaseCommand):

    def handle(self, *args, **options):

        presentation_videos = self.get_video_urls()
        any_updates = False
        for presentation_id, youtube_url in presentation_videos.items():
            try:
                presentation = Presentation.objects.get(id=presentation_id)
            except:
                logger.warning("Presentation not found! ID: %s", presentation_id)
                continue

            if presentation.youtube_url != youtube_url:
                logger.info("Updating Presentation %s youtube URL to: %s", presentation_id, youtube_url)
                presentation.youtube_url = youtube_url
                presentation.save()
                any_updates = True

        if any_updates:
            self.trigger_static_site_build()

    def get_video_urls(self):
        logger.info("Getting video data...")
        response = requests.get(VIDEO_DATA_URL)
        response.raise_for_status()
        response_data = response.json()
        presentation_videos = {}
        for slot in response_data:
            if slot["state"] >= 10:
                presentation_id = slot.get("conf_url", "").split("/")[-1]
                youtube_url = slot.get("host_url", "")
                logger.info("Presentation %s has youtube URL: %s", presentation_id, youtube_url)
                if youtube_url:
                    presentation_videos[presentation_id] = youtube_url
        return presentation_videos

    def trigger_static_site_build(self):
        if STATIC_SITE_WEBHOOK is not None:
            logger.info("Triggering static site build...")
            response = requests.post(STATIC_SITE_WEBHOOK, data={})
            logger.info("Webhook POST response: %s", response.status_code)

