import commands
import logging
from optparse import make_option
from os import unlink

from django.conf import settings
from django.core.files import File
from django.core.management.base import BaseCommand

from multidb.pinning import pin_this_thread

from gallery.models import Video
from upload.tasks import _create_image_thumbnail


generate_command = 'ffmpeg -i %(in)s -vcodec png -vframes 1 -an -ss 1 %(out)s'
VIDEO_PATH = settings.MEDIA_ROOT + '/' + settings.GALLERY_VIDEO_PATH
THUMBNAIL_PATH = (settings.MEDIA_ROOT + '/' +
                  settings.GALLERY_VIDEO_THUMBNAIL_PATH)
PREFIX = '__thumb__'
log = logging.getLogger('k.generate_video_thumbnails')


class FFMpegException(Exception):
    pass


def update_video(vid, verbosity):
    if vid.thumbnail:  # Nothing to do if there's already a thumbnail
        return False

    thumb_name = None
    for ext in ('webm', 'ogv', 'flv'):
        file = getattr(vid, ext)
        if not file:
            continue
        if file.path.endswith('.swf'):
            print 'SWF found for %s: %s, %s..' % (vid.pk, vid, file)
            return False

        if verbosity:
            print 'Generating thumbnail for %s: %s, %s..' % (vid.pk, vid, file)

        # else, generate thumbnail and break out
        thumb_name = vid.title + '.png'
        out = THUMBNAIL_PATH + PREFIX + thumb_name
        if ext == 'ogv':
            out = '-acodec libvorbis ' + out
        command = generate_command % {'in': file.path,
                                      'out': out}

        status, output = commands.getstatusoutput(command)
        if status != 0 or 'Error' in output:
            status_output = '%s: %s' % (status, output)
            raise FFMpegException(status_output)
        thumb_file = File(open(THUMBNAIL_PATH + PREFIX + thumb_name))
        if verbosity:
            print 'Shrinking thumbnail at %s...' % thumb_file.name

        # Shrink the thumbnail
        thumb_content = _create_image_thumbnail(thumb_file.name)
        # Save it
        vid.thumbnail.save(thumb_name, thumb_content, save=True)

        unlink(thumb_file.name)
        thumb_file.close()
        # alright we're done here
        break

    if not thumb_name:
        return False

    return True


class Command(BaseCommand):
    help = ('Generate thumbnails for migrated videos.\nUsage: '
            './manage.py generate_video_thumbnails all --verbosity 1|2|3')
    options_list = BaseCommand.option_list + (
        make_option('--path',
            action='store',
            dest='path',
            default=VIDEO_PATH,
            help='Path to the videos.'),
        )
    max_videos = 100000  # overwrite with 1st arg

    def handle(self, *args, **options):
        pin_this_thread()

        options['verbosity'] = int(options['verbosity'])

        if args:
            try:
                self.max_videos = int(args[0])
            except ValueError:
                import sys
                self.max_videos = sys.maxint

        if options['verbosity'] > 0:
            print 'Starting generation of thumbnails for videos...'

        videos = Video.objects.all()

        count = 0
        for vid in videos:
            try:
                if not update_video(vid, options['verbosity']):
                    continue
                count += 1
                if count == self.max_videos:
                    break
            except FFMpegException, e:
                print 'FFMPegException for video %s: %s' % (vid.pk, vid)
                message = '%s: %s %s' % (vid.pk, vid, e.message)
                log.debug(message)

        if options['verbosity'] > 0 and self.max_videos == count:
            print 'Reached maximum number of videos (%s).' % count
        else:
            print 'Generated thumbnails for %s videos.' % count
