from django.conf import settings
from django.contrib.auth.models import User

from nose.tools import eq_

from sumo.tests import TestCase
from users.helpers import (profile_url, profile_avatar, public_email,
                           display_name)
from users.models import Profile


class HelperTestCase(TestCase):
    def setUp(self):
        super(HelperTestCase, self).setUp()
        self.u = User.objects.create(pk=500000, username=u'testuser')

    def test_profile_url(self):
        eq_(u'/user/500000', profile_url(self.u))

    def test_profile_avatar_default(self):
        Profile.objects.create(user=self.u)
        eq_(settings.DEFAULT_AVATAR, profile_avatar(self.u))

    def test_profile_avatar(self):
        profile = Profile(user=self.u)
        profile.avatar = 'images/foo.png'
        profile.save()
        eq_('%simages/foo.png' % settings.MEDIA_URL, profile_avatar(self.u))

    def test_public_email(self):
        eq_(u'&#109;&#101;&#64;&#100;&#111;&#109;&#97;&#105;&#110;&#46;&#99;'
             '&#111;&#109;', public_email('me@domain.com'))
        eq_(u'&#110;&#111;&#116;&#46;&#97;&#110;&#46;&#101;&#109;&#97;&#105;'
             '&#108;', public_email('not.an.email'))

    def test_display_name(self):
        eq_(u'testuser', display_name(self.u))
        p = Profile(user=self.u)
        p.name = u'Test User'
        p.save()
        eq_(u'Test User', display_name(self.u))
