from django.db import connection

from nose import SkipTest
from nose.tools import eq_

from sumo.models import WikiPage
from sumo.tests import TestCase
from wiki.management.commands.migrate_kb import *
from wiki.tests import document, revision


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
        """Some warnings from check_content"""
        content = 'something\n<script>evil();</script>'
        assert WARNINGS['<script>'] in check_content(content)
        content = 'some\n<style>body {display: none;}</style>'
        assert WARNINGS['<style>'] in check_content(content)
        content = 'this\n||is|a|\ntable||'
        assert WARNINGS['<table>'] in check_content(content)


def create_extra_tables():
    cursor = connection.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS `tiki_translated_objects` (
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

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS `tiki_content` (
          `contentId` int(8) NOT NULL AUTO_INCREMENT,
          `description` text,
          `contentLabel` varchar(255) NOT NULL,
          `lang` varchar(16) DEFAULT NULL,
          PRIMARY KEY (`contentId`)
        ) ENGINE=MyISAM AUTO_INCREMENT=513 DEFAULT CHARSET=utf8
        """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS `tiki_programmed_content` (
          `pId` int(8) NOT NULL AUTO_INCREMENT,
          `contentId` int(8) NOT NULL DEFAULT '0',
          `publishDate` int(14) NOT NULL DEFAULT '0',
          `data` text,
          PRIMARY KEY (`pId`)
        ) ENGINE=MyISAM AUTO_INCREMENT=619 DEFAULT CHARSET=utf8
        """)

    cursor.execute(u"""
        INSERT IGNORE INTO `tiki_content` VALUES
        (107,'optionspreferences','optionspreferences','en'),
        (409,'','optionspreferences','fr'),
        (6,'closeFirefox','closeFirefox','en'),
        (74, 'Safe Mode \u3067\u958B\u304F','safemode','ja')
        """)

    cursor.execute(u"""
        INSERT INTO `tiki_programmed_content` VALUES
        (124,107,1263970260,'{DIV(class=noMac,type=span)}At the top of the Firefox window{DIV}{DIV(class=mac,type=span)}On the menu bar{DIV}, click on the {DIV(class=win,type=span)}{MENU()}Tools{MENU}{DIV}{DIV(class=mac,type=span)}{MENU()}Firefox{MENU}{DIV}{DIV(class=unix,type=span)}{MENU()}Edit{MENU}{DIV} menu, and select {DIV(class=win,type=span)}{MENU()}Options...{MENU}{DIV}{DIV(class=noWin,type=span)}{MENU()}Preferences...{MENU}{DIV}.'),
        (125,107,1263970000,'Old data'),
        (499,409,1265860440,'{DIV(class=noMac,type=span)}En haut de la fen\u00EAtre de Firefox{DIV}{DIV(class=mac,type=span)}Dans la barre de menu{DIV}, cliquez sur le menu {DIV(class=win,type=span)}{MENU()}Outils{MENU}{DIV}{DIV(class=mac,type=span)}{MENU()}Firefox{MENU}{DIV}{DIV(class=unix,type=span)}{MENU()}\u00C9dition{MENU}{DIV} et s\u00E9lectionnez {DIV(class=win,type=span)}{MENU()}Options...{MENU}{DIV}{DIV(class=noWin,type=span)}{MENU()}Pr\u00E9f\u00E9rences...{MENU}{DIV}.'),
        (100,6,1262377560,' From the menu {DIV(class=noMac,type=span)}at the top of the Firefox window{DIV}{DIV(class=mac,type=span)}bar{DIV}, select {DIV(class=noMac,type=span)}{MENU()}File{MENU}{DIV}{DIV(class=mac,type=span)}{MENU()}Firefox{MENU}{DIV} and then select the {DIV(class=win,type=span)}{MENU()}Exit{MENU}{DIV}{DIV(class=mac,type=span)}{MENU()}Quit Firefox{MENU}{DIV}{DIV(class=unix,type=span)}{MENU()}Quit{MENU}{DIV} menu item.'),
        (75,74,1244196540,'# Firefox \u3092\u5B8C\u5168\u306B\u7D42\u4E86\u3057\u3066\u304F\u3060\u3055\u3044: {DIV(class=noMac,type=span)}Firefox \u30A6\u30A3\u30F3\u30C9\u30A6\u4E0A\u90E8{DIV}{DIV(class=mac,type=span)}\u30E1\u30CB\u30E5\u30FC\u30D0\u30FC\u4E0A{DIV}\u306E {DIV(class=noMac,type=span)}{PATH()}>\u30D5\u30A1\u30A4\u30EB{PATH}{DIV}{DIV(class=mac,type=span)}{PATH()}Firefox{PATH}{DIV} \u30E1\u30CB\u30E5\u30FC\u3092\u30AF\u30EA\u30C3\u30AF\u3057\u3001{PATH()}{DIV(class=mac,type=span)}Firefox \u3092{DIV}\u7D42\u4E86{PATH} \u3092\u9078\u629E\u3057\u307E\u3059\u3002\\r\\n# {DIV(class=win,type=span)}Windows \u3067\u306F\u3001{DIV(class=button,type=>span)}\u30B9\u30BF\u30FC\u30C8{DIV} \u3092\u30AF\u30EA\u30C3\u30AF\u3057\u3066 {PATH()}\u3059\u3079\u3066\u306E\u30D7\u30ED\u30B0\u30E9\u30E0{PATH} \u30EA\u30B9\u30C8\u3092\u958B\u304D\u3001{PATH()}Mozilla Firefox{PATH} \u30D5\u30A9\u30EB\u30C0\u3092\u958B\u304D\u307E\u3059\u3002Mozilla Firefox \u30D5\u30A9\u30EB\u30C0\u5185\u306E {PATH()}Mozilla Firefox (\u30BB\u30FC\u30D5\u30E2\u30FC\u30C9){PATH} \u3092\u9078\u629E\u3057\u3066\u304F\u3060\u3055\u3044\u3002{DIV}{SHOWFOR(browser=firefox3,os=mac)}{TAG(tag=kbd)}Option{TAG} \u30AD\u30FC\u3092\u62BC\u3057\u306A\u304C\u3089 Firefox \u3092\u958B\u59CB\u3057\u307E\u3059\u3002{SHOWFOR}{DIV(class=unix,type=span)}__Terminal__ \u3092\u958B\u304D\u3001\u6B21\u306E\u30B3\u30DE\u30F3\u30C9\u3092>\u5B9F\u884C\u3057\u3066\u304F\u3060\u3055\u3044: {CODE()}/path/to/firefox/firefox -safe-mode{CODE}{DIV}\\r\\n# Firefox \u304C\u30BB\u30FC\u30D5\u30E2\u30FC\u30C9\u30C0\u30A4\u30A2\u30ED\u30B0\u3092\u958B\u3044\u3066\u958B\u59CB\u3057\u307E\u3059\u3002{DIV(class=win,type=span)} %%% ^__\u6CE8\u8A18:__ \u6B21\u306E\u65B9\u6CD5\u3067\u3082 Firefox \u3092\u30BB\u30FC\u30D5\u30E2\u30FC\u30C9\u3067\u958B\u59CB\u3067\u304D\u307E\u3059\u3002Windows \u306E{DIV(class=button,type=>span)}\u30B9\u30BF\u30FC\u30C8{DIV} \u3092\u30AF\u30EA\u30C3\u30AF\u3057\u3066 {PATH()}\u30D5\u30A1\u30A4\u30EB\u540D\u3092\u6307\u5B9A\u3057\u3066\u5B9F\u884C{PATH} \u3092\u9078\u629E (Windows Vista \u3067\u306F {FILE()}\u691C\u7D22\u306E\u958B\u59CB{FILE} \u30DC\u30C3\u30AF\u30B9\u3092\u4F7F\u7528) >\u3057\u3001\u6B21\u306E\u30B3\u30DE\u30F3\u30C9\u3092\u30C6\u30AD\u30B9\u30C8\u30D5\u30A3\u30FC\u30EB\u30C9\u306B\u5165\u529B\u3057\u3066\u304F\u3060\u3055\u3044:%%%{CODE()}firefox -safe-mode {CODE}^{DIV}')
        """)


def destroy_extra_tables():
    cursor = connection.cursor()
    cursor.execute('DROP TABLE IF EXISTS tiki_translated_objects')
    cursor.execute('DROP TABLE IF EXISTS tiki_content')
    cursor.execute('DROP TABLE IF EXISTS tiki_programmed_content')


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
        translations = get_translations(5965)
        d = get_parent_lang(translations, 5965)
        eq_(None, d)

    def test_get_parent_translation(self):
        """Returns the migrated English version for a translation"""
        td = WikiPage.objects.get(page_id=5965)
        parent = create_document(td)[0]
        translations = get_translations(6234)
        d, l = get_parent_lang(translations, 6234)
        eq_(parent, d)
        eq_('it', l)

    def test_get_parent_not_exist(self):
        """Returns None for untranslated documents."""
        td = WikiPage.objects.exclude(page_id=5965)[0]
        td.lang = 'fr'  # Set the locale so it's considered a translation
        td.save()
        translations = get_translations(td.page_id)
        d = get_parent_lang(translations, td.page_id)
        eq_(None, d)

    def test_get_category_english(self):
        """Category for english articles."""
        td = WikiPage.objects.get(page_id=2)
        eq_(30, get_category(td, get_translations(2)))

        td = WikiPage.objects.get(page_id=5)
        eq_(20, get_category(td, get_translations(5)))

        td = WikiPage.objects.get(page_id=5965)
        eq_(10, get_category(td, get_translations(5965)))

        td.title = 'group permissions'
        eq_(40, get_category(td, get_translations(5965)))

    def test_get_category_translation(self):
        """Category for translated articles."""
        # Save the English article
        td = WikiPage.objects.get(page_id=5965)
        d, _, _ = create_document(td)
        td = WikiPage.objects.get(page_id=6234)
        translations = get_translations(td.page_id)
        eq_(10, get_category(td, translations))
        d.category = 30  # pretend this is 3
        d.save()
        eq_(30, get_category(td, translations))

    def test_get_firefox_versions(self):
        """Returns a list of firefox version IDs"""
        td = WikiPage.objects.get(page_id=5965)
        d, _, _ = create_document(td)
        versions = get_firefox_versions(td, d)
        eq_(set([1, 2, 3]), versions)

        # Add this metadata
        create_document_metadata(d, td)

        # Now test for a translation
        td = WikiPage.objects.get(page_id=6234)
        d, _, _ = create_document(td)
        versions = get_firefox_versions(td, d)
        eq_(set([1, 2, 3]), versions)

    def test_get_operating_systems_desktop(self):
        """Operating systems for a desktop document."""
        self.test_get_firefox_versions()
        d = Document.objects.get(locale='en-US')
        os_ids = set([d_os.item_id for d_os in d.operating_systems.all()])
        eq_(set([1, 2, 3]), os_ids)

    def test_get_operating_systems_mobile(self):
        td = WikiPage.objects.get(page_id=5965)
        eq_(set([4, 5]), get_operating_systems(td, [4]))

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
        eq_(3, d.firefox_version_set.count())
        eq_(3, d.operating_system_set.count())
        fxver_ids = [i.item_id for i in d.firefox_version_set.all()]
        fxver_ids.sort()
        os_ids = [i.item_id for i in d.operating_system_set.all()]
        os_ids.sort()
        eq_([1, 2, 3], fxver_ids)
        eq_([1, 2, 3], os_ids)

        # check that adding metadata again doesn't get me the data twice
        create_document_metadata(d, td)
        eq_(3, d.firefox_version_set.count())
        eq_(3, d.operating_system_set.count())

    def test_create_document_translation(self):
        """Create a document that's a translation of another document."""
        td = WikiPage.objects.get(page_id=5965)
        d, _, _ = create_document(td)
        trans_td = WikiPage.objects.get(page_id=6234)
        trans_d, r, _ = create_document(trans_td)
        eq_('Eliminare i cookie', trans_d.title)
        eq_('it', trans_d.locale)
        translations = get_translations(trans_td.page_id)
        _, l = get_parent_lang(translations, trans_td.page_id)
        eq_(d, trans_d.parent)
        eq_('it', l)
        eq_(d.current_revision, get_based_on(trans_d, r))

    def test_document_warnings_default(self):
        """TODO: test some basic warnings"""
        raise SkipTest

    def test_create_revision_default(self):
        """A revision based on a tiki page is created for a document"""
        td = WikiPage.objects.get(title='Installing Firefox')
        d = document()
        d.save()
        r = create_revision(td, d, convert_content(td.content)[0])
        eq_(d, r.document)
        eq_(td.description, r.summary)
        assert r.content is not '', (
            "Revision's content should not be empty (%s)" % r.content)
        eq_('Grammatical tweak.', r.comment)
        eq_(ANONYMOUS_USER_NAME, r.creator.username)
        eq_('Chris_Ilias', r.reviewer.username)
        eq_(False, r.is_approved)
        eq_(None, r.based_on)

    def test_create_revision_based_on(self):
        td = WikiPage.objects.get(title='Installing Firefox')
        d = document()
        d.save()
        r = create_revision(td, d, convert_content(td.content)[0])
        r.is_approved = True
        r.save()
        new_r = revision(document=d)
        eq_(r, get_based_on(d, new_r))
        new_r.save()

        # translate to French, based on English
        d2 = document(locale='fr', parent=d)
        d2.save()
        new_r2 = revision(document=d2)
        eq_(r, get_based_on(d2, new_r2))

        # no current revision for English? No problem, just check approved ones
        new_r.is_approved = True
        new_r.save()
        d.current_revision = None
        d.save()
        eq_(new_r, get_based_on(d2, new_r2))

    def test_fetch_content_templates(self):
        """Content templates are properly fetched into a dict."""
        templates = fetch_content_templates()[0]
        eq_(4, len(templates))
        eq_('fr', templates[409]['locale'])
        eq_(409, templates[409]['id'])
        eq_('optionspreferences', templates[409]['label'])
        eq_('2010-02-10 19:54:00', str(templates[409]['published']))

    def test_create_template_en(self):
        """Creating an English template."""
        templates = fetch_content_templates()[0]
        d, r, _ = create_template(templates[107])

        eq_('Template:optionspreferences', d.title)
        eq_('Template:optionspreferences', d.slug)
        eq_('en-US', d.locale)
        eq_(40, d.category)
        eq_(None, d.parent)
        eq_(r, d.current_revision)
        eq_(d, r.document)
        eq_('admin', r.creator.username)
        eq_('admin', r.reviewer.username)
        eq_('', r.comment)
        eq_('', r.summary)
        eq_(True, r.is_approved)
        eq_('', r.keywords)
        eq_('{for win,linux}At the top of the Firefox window{/for}'
            '{for mac}On the menu bar{/for}, click on the {for win}'
            '{menu Tools}{/for}{for mac}{menu Firefox}{/for}{for linux}'
            '{menu Edit}{/for} menu, and select {for win}{menu Options...}'
            '{/for}{for mac,linux}{menu Preferences...}{/for}.',
            r.content)
        eq_('2010-01-19 22:51:00', str(r.created))

    def test_create_template_parent(self):
        """Creating a French template finds its English parent."""
        templates = fetch_content_templates()[0]
        parent_d = create_template(templates[107])[0]
        d, r, _ = create_template(templates[409])

        eq_(parent_d, d.parent)
