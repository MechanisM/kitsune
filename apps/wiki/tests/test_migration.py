from django.db import connection

from nose import SkipTest
from nose.tools import eq_

from sumo.models import WikiPage
from sumo.tests import TestCase
from wiki.management.commands.migrate_kb import (
    create_document, create_revision, get_parent, get_locale, get_slug,
    get_title_is_approved, get_firefox_versions, create_document_metadata,
    get_category, check_content, get_comment_reviewer, ANONYMOUS_USER_NAME)
from wiki.tests import document


class HelpersNoFixtures(TestCase):
    """Test migration helpers with no fixtures"""
    def test_title_is_approved(self):
        """Title and is_approved are properly set for staging vs approved
        pages"""
        eq_((False, 'test'), get_title_is_approved('*test'))
        eq_((True, 'test'), get_title_is_approved('test'))

    def test_get_locale(self):
        """Locale works and uses en-US as fallback"""
        eq_('en-US', get_locale('en'))
        eq_('fr', get_locale('fr'))

    def test_get_slug(self):
        """Slug returns properly for various titles"""
        eq_('SLuG', get_slug('SLuG'))
        eq_(u'\u062d\u0630\u0641 \u06a9\u0648\u06a9\u06cc \u0647\u0627',
            get_slug(u'\u062d\u0630\u0641 \u06a9\u0648\u06a9\u06cc '
                     u'\u0647\u0627'))

    def test_check_content(self):
        """TODO"""
        raise SkipTest


def create_extra_tables():
    cursor = connection.cursor()
    cursor.execute("""
        CREATE TABLE `tiki_translated_objects` (
          `traId` int(14) NOT NULL AUTO_INCREMENT,
          `type` varchar(50) NOT NULL,
          `objId` varchar(255) NOT NULL,
          `lang` varchar(16) DEFAULT NULL,
          PRIMARY KEY (`type`,`objId`),
          KEY `traId` (`traId`)
        ) ENGINE=MyISAM AUTO_INCREMENT=1304 DEFAULT CHARSET=utf8
        """)

    cursor.execute("""
        INSERT IGNORE INTO tiki_translated_objects
            (traId, type, objId, lang) VALUES
            (31, 'wiki page', 5, 'en'),
            (1073, 'wiki page', 5965, 'en'),
            (1073, 'wiki page', 6234, 'it')
        """)


def destroy_extra_tables():
    cursor = connection.cursor()
    cursor.execute('DROP TABLE IF EXISTS tiki_translated_objects')


class HelpersFixtures(TestCase):
    fixtures = ['pages.json', 'users.json']
    created_tables = False

    @classmethod
    def setUpClass(cls):
        if not cls.created_tables:
            create_extra_tables()
            cls.created_tables = True

    @classmethod
    def tearDownClass(cls):
        destroy_extra_tables()
        cls.created_tables = False

    def test_get_parent_english(self):
        """Returns None for English"""
        d = get_parent(5965)
        eq_(None, d)

    def test_get_parent_translation(self):
        """Returns the migrated English version for a translation"""
        td = WikiPage.objects.get(page_id=5965)
        parent = create_document(td)[0]
        d = get_parent(6234)
        eq_(parent, d)

    def test_get_parent_notexist(self):
        """Returns None for untranslated documents."""
        td = WikiPage.objects.exclude(page_id=5965)[0]
        td.lang = 'fr'  # Set the locale so it's considered a translation
        td.save()
        d = get_parent(td.page_id)
        eq_(None, d)

    def test_get_category(self):
        """TODO"""
        raise SkipTest

    def test_get_firefox_versions(self):
        """Returns a list of firefox version IDs"""
        td = WikiPage.objects.get(page_id=5965)
        versions = get_firefox_versions(td)
        versions.sort()
        eq_([2, 3], versions)

    def test_get_comment_reviewer_empty_comment(self):
        """Empty comment, anonymous user."""
        c, r = get_comment_reviewer('[approved by NotExist]')
        eq_('', c)
        eq_(ANONYMOUS_USER_NAME, r.username)

    def test_get_comment_reviewer_empty_reviewer(self):
        """Comment, empty user."""
        c, r = get_comment_reviewer('Some comment.')
        eq_('Some comment.', c)
        eq_(ANONYMOUS_USER_NAME, r.username)

    def test_get_comment_reviewer_empty_comment_user(self):
        """Empty comment, registered user."""
        c, r = get_comment_reviewer('[approved by jsocol]')
        eq_('', c)
        eq_('jsocol', r.username)

    def test_get_comment_reviewer_comment_user(self):
        """Comment, registered user."""
        c, r = get_comment_reviewer('A comment. [approved by admin]')
        eq_('A comment.', c)
        eq_('admin', r.username)

    def test_create_document_default(self):
        """A usual en-US document is created"""
        td = WikiPage.objects.get(title='Installing Firefox')
        d, r, _ = create_document(td)
        eq_('Installing Firefox', d.title)
        eq_('en-US', d.locale)
        eq_(None, d.parent)
        assert d.html is not '', (
            "Document's HTML should not be empty (%s)" % d.html)

    def test_create_document_metadata(self):
        """Document metadata: fxver + OS is created"""
        td = WikiPage.objects.get(title='Deleting cookies')
        d, r, _ = create_document(td)
        create_document_metadata(d, td)
        eq_(2, d.firefox_version_set.count())
        eq_(3, d.operating_system_set.count())
        fxver_ids = [i.item_id for i in d.firefox_version_set.all()]
        fxver_ids.sort()
        os_ids = [i.item_id for i in d.operating_system_set.all()]
        os_ids.sort()
        eq_([2, 3], fxver_ids)
        eq_([1, 2, 3], os_ids)

    def test_create_document_translation(self):
        """Create a document that's a translation of another document."""
        td = WikiPage.objects.get(page_id=5965)
        create_document(td)
        trans_td = WikiPage.objects.get(page_id=6234)
        trans_d = create_document(trans_td)[0]
        eq_('Eliminare i cookie', trans_d.title)
        eq_('it', trans_d.locale)
        d = get_parent(trans_td.page_id)
        eq_(d, trans_d.parent)

    def test_document_warnings_default(self):
        """TODO: test some basic warnings"""
        raise SkipTest

    def test_create_revision_default(self):
        """A revision based on a tiki page is created for a document"""
        td = WikiPage.objects.get(title='Installing Firefox')
        d = document()
        d.save()
        r = create_revision(td, d)
        eq_(d, r.document)
        eq_(td.description, r.summary)
        assert r.content is not '', (
            "Revision's content should not be empty (%s)" % r.content)
        eq_(40, r.significance)
        eq_('Grammatical tweak.', r.comment)
        eq_(ANONYMOUS_USER_NAME, r.creator.username)
        eq_('Chris_Ilias', r.reviewer.username)
        eq_(False, r.is_approved)
