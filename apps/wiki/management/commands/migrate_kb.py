"""
migrate_pages: a management command to migrate SUMO's tiki_pages and associated
data over to our new wiki app.

Goes through each wiki page and creates all data belonging to it. Also
migrates the page metadata.

Required tiki tables:
tiki_pages
tiki_freetags
tiki_freetagged_objects
tiki_objects
tiki_categories
tiki_category_objects

Uses a markup converter to transform TikiWiki syntax to MediaWiki syntax.

"""
# TODO: warnings for unrecognized {DIV}s (with inline styling)
#       default right now to just turn into <div></div>
# TODO: Add non-localizable document support (separate bug ######)

import logging
import re
from datetime import datetime
from HTMLParser import HTMLParser

from django.conf import settings
from django.contrib.auth.models import User
from django.core.management.base import NoArgsCommand
from django.db import connection
from django.db.utils import IntegrityError

from multidb.pinning import pin_this_thread

from wiki.models import (Document, Revision, CATEGORIES,
                         FirefoxVersion, OperatingSystem, SlugCollision)
from sumo.converter import TikiMarkupConverter
from sumo.models import WikiPage, CategoryObject, TikiObject
from sumo import ProgrammingError


hdlr = logging.FileHandler('log.txt')
fmt = '%(asctime)s %(name)s:%(levelname)s %(message)s :%(pathname)s:%(lineno)s'
hdlr.setFormatter(logging.Formatter(fmt, datefmt='%H:%M:%S'))
log = logging.getLogger('k.migrate')
log.addHandler(hdlr)
# Converts TikiWiki syntax to MediaWiki syntax
converter = TikiMarkupConverter()
htmlparser = HTMLParser()
ANONYMOUS_USER_NAME = 'AnonymousUser'
RE_REVIEWER = re.compile('\[?approved by ([^\]]+?)\]')
TIKI_CATEGORY_MAP = {
    14: 3,  # Firefox 3.0, fx3
    25: 2,  # Firefox 3.5-3.6, fx35
    26: 4,  # Mobile Firefox 4, m4
}
WARNINGS = {'no_parent': 'This document is missing its parent.',
            'skip': 'This document is not being migrated.',
            'same_content':
              'This document has the same content an existing revision (%s).',
            'empty_content': 'This document was skipped as it has no content.',
            '<table>': 'This document contains a table.',
            '<script>': 'This document contains <script> tags.',
            '<style>': 'This document contains <style> tags.'}


def get_django_user(obj, field_name='user'):
    """Get the django user for this thread's username."""
    u = getattr(obj, field_name)
    try:
        user = User.objects.get(username=u)
    except User.DoesNotExist:
        # Assign a dummy user to this thread
        user = User.objects.get(username=ANONYMOUS_USER_NAME)

    return user


def get_title_is_approved_preliminary(title):
    """Returns a tuple (is_approved, title), special cased for staging
    articles"""
    # No surrounding whitespace, please
    title = title.replace('/', ' ').strip()
    if title.startswith('*'):
        return (False, title[1:].strip())
    return (True, title)


def get_title_is_approved(td, cat_ids):
    """Returns a tuple (is_approved, title), special cased for never-before
    seen-footage, aka. never-approved"""
    is_approved, title = get_title_is_approved_preliminary(td.title)
    if is_approved and 3 in cat_ids:
        staging = u'*' + td.title
        # If there is a staging copy already, this page has been approved
        # otherwise it hasn't
        is_approved = WikiPage.objects.filter(lang=td.lang,
                                              title=staging).exists()
    return (is_approved, title)


def get_slug(title):
    """Slugify a documment title"""
    return title  # Agreed to just use the title as the slug


def get_locale(lang):
    """Validate against SUMO_LANGUAGES, return default if not found."""
    lang = (lang or '').strip()
    return (lang if lang in settings.SUMO_LANGUAGES
                 else settings.WIKI_DEFAULT_LANGUAGE)


def get_translations(page_id):
    c = connection.cursor()
    c.execute("""
        SELECT
            t2.objId AS page_id, t2.lang
        FROM
            tiki_translated_objects t1,
            tiki_translated_objects t2
            LEFT JOIN tiki_pages p
                ON p.page_id = t2.objId
        WHERE
            t1.traId = t2.traId
            AND t1.type = "wiki page"
            AND t1.objId = %s""", [page_id])
    translations = []
    while True:
        translation = c.fetchone()
        if not translation:
            break
        translations.append(translation)
    return translations


def get_parent_lang(translations, page_id):
    """Returns the migrated English Document of a WikiPage, if found.

    Assumptions:
        * the corresponding English Document for the WikiPage exists, i.e.
          was already migrated
        * every document is translated from English

    """
    parent_id = page_id
    for translation in translations:
        if int(translation[0]) == page_id:
            translated_locale = get_locale(translation[1])
        elif translation[1] == 'en':
            parent_id = int(translation[0])

    if parent_id != page_id:
        # get the parent tiki document
        parent_td = WikiPage.objects.get(page_id=parent_id)
        # We assume that the parent exists
        _, title = get_title_is_approved_preliminary(parent_td.title)
        try:
            return (Document.objects.get(
                        title=title, locale=settings.WIKI_DEFAULT_LANGUAGE),
                    translated_locale)
        except Document.DoesNotExist:
            return None

    return None


TIKI_CATEGORY = {
    40: [  # Administration
        'about firefox support',
        'group permissions',
        'introduction to live chat',
        'knowledge base policies',
        'live chat closed',
        'terms of service',
        'ask a question',
        'get help with firefox 4 beta',
        ],
    30: [  # How to contribute
        # TODO: make non-localizable
        'live chat canned responses',
        'live chat basic support handbook',
        'live chat coverage',
        'live chat troubleshooting guide',
        'installing and configuring spark',
        'live chat approval criteria',
        'helping with live chat',
        # ENDTODO
        'translating articles',
        'translating the interface',  # TODO: document gettext process
        'using poll data to judge your edits',
        'using showfor',
        'style guide',
        'tikiwiki vs mediawiki markup',
        'monitoring categories',
        'providing forum support',
        'markup chart',
        'measuring knowledge base success',
        'localizing firefox support',
        'helping with forum support',
        'how to contribute',  # TODO: needs manual migration
        'how we are different',
        'improving articles',
        'helping firefox users on twitter',
        'getting notified of new article translations',
        'forum and chat rules and guidelines',
        'editing articles',
        'creating articles',
        'contributor home page',
        'contributing to the knowledge base',
        'best practices for support documents',
        'approving articles and edits',
        'adding screenshots',
        'adding screencasts',
        ],
}


TIKI_CATEGORY_IDS = {
    1: 'KB',
    3: 'Staging',
    7: 'Sandbox',
    8: 'Administration',
    9: 'Waiting for review',
    18: 'Help article',
    20: 'Live chat',
    23: 'HTC',
    24: 'Archive',
}


skipped_en_document_ids = []


def get_cat_ids(td):
    """Get a list of category ids from Tiki."""
    tiki_objects = TikiObject.objects.filter(type='wiki page', itemId=td.title)
    obj_ids = [t_o.objectId for t_o in tiki_objects]
    categories = CategoryObject.objects.filter(
        categId__in=TIKI_CATEGORY_IDS.keys(), catObjectId__in=obj_ids)
    return [c.categId for c in categories]


def get_category(td, translations, cat_ids):
    """Get the category. Yes, it's as complicated as it looks."""
    parent_info = None
    locale = get_locale(td.lang)
    if locale != 'en-US':
        parent_info = get_parent_lang(translations, td.page_id)

    if not parent_info:
        if 18 in cat_ids:
            return 20  # How to

        # For non-English documents, we don't migrate all staging copies
        # For English documents, we migrate staging and KB
        if 1 in cat_ids or (3 in cat_ids and locale == 'en-US'):
            return 10  # Troubleshooting

        if 7 in cat_ids or 24 in cat_ids:
            return -1  # This means don't even show warning

        if locale == 'en-US':
            title = td.title.strip().lower()
            for k, docs in TIKI_CATEGORY.iteritems():
                if title in docs:
                    return k
            skipped_en_document_ids.append(td.page_id)
            return 0

    # For translations, check parent's category and use that.
    if parent_info:
        parent, _ = parent_info
        return parent.category
    else:
        parent_id = None
        for translation in translations:
            if translation[1] == 'en':
                parent_id = int(translation[0])
        if parent_id in skipped_en_document_ids:
            return 0
        # XXX: This part has only been ad-hoc tested
        # Skip if there is no parent and
        #       (it's not in KB nor in staging
        #        OR it's a staging article which doesn't have a KB copy)
        if not parent_id:
            is_approved, title = get_title_is_approved(td, cat_ids)
            if not (is_approved or 3 in cat_ids):  # not kb, not staging
                return 0
            elif is_approved and not WikiPage.objects.filter(
                lang=td.lang, title=title).exists():
                return 0

    # Remaining translations default to Troubleshooting
    return 10


def get_firefox_versions(td, d):
    """Returns a list of integers, the Document's Firefox versions."""
    if d.parent:
        return set([fxver.item_id for
                    fxver in d.parent.firefox_versions.all()])
    tiki_objects = TikiObject.objects.filter(type='wiki page', itemId=td.title)
    obj_ids = [t_o.objectId for t_o in tiki_objects]
    versions = CategoryObject.objects.filter(
        categId__in=TIKI_CATEGORY_MAP.keys(),
        catObjectId__in=obj_ids)
    versions = [TIKI_CATEGORY_MAP[v.categId] for v in versions]
    versions.append(1)  # All articles are for Firefox 4
    return set(versions)


def get_operating_systems(td, fxver_ids):
    """Just set all articles to Windows, Mac and Linux"""
    if 4 in fxver_ids:
        return set([4, 5])  # IDs for Android and Maemo
    return set([1, 2, 3])  # IDs for Windows, Mac and Linux


def get_comment_reviewer(comment):
    """Returns a tuple (comment, reviewer) based on the comment.

    Looks up the username mentioned in the comment, using the RE_REVIEWER
    regex. If the reviewer cannot be found, it returns the fallback,
    anonymous user.

    """
    anon = User.objects.get(username=ANONYMOUS_USER_NAME)
    comment = comment.strip()
    if '[' in comment:
        if comment.startswith('['):
            reviewer = comment
            comment = ''
        else:
            comment, reviewer = [v.strip() for
                                 v in comment.strip().split('[', 1)]

        m = RE_REVIEWER.match(reviewer)
        if m:
            try:
                reviewer = User.objects.get(username=m.group(1))
            except User.DoesNotExist:
                reviewer = anon
        else:
            reviewer = anon
        return (comment, reviewer)

    return (comment, anon)


CHECK_CONTENT_PATTERNS = {
    '<table>': re.compile('^\|\|', re.MULTILINE),
}


def check_content(content):
    """Returns warnings regarding potentially legacy TikiWiki syntax."""
    warnings = []
    for s in ('<script>', '<style>'):
        if s in content:
            warnings.append(WARNINGS[s])

    for k, v in CHECK_CONTENT_PATTERNS.iteritems():
        if v.search(content):
            warnings.append(WARNINGS[k])

    return warnings


def get_based_on(document, revision):
    if document.parent:
        if document.parent.current_revision:
            return document.parent.current_revision
        older_parent_revisions = document.parent.revisions.filter(
            created__lte=revision.created,
            is_approved=True).order_by('-created')
        if older_parent_revisions.exists():
            return older_parent_revisions[0]
    if document.locale == settings.WIKI_DEFAULT_LANGUAGE:
        previous_revisions = document.revisions.filter(
            created__lte=revision.created,
            is_approved=True).order_by('-created')
        if previous_revisions.exists():
            return previous_revisions[0]
    return None


def create_revision(td, document, content, is_approved=False):
    """Create revision for a document using a Tiki document."""
    summary = td.description
    keywords = td.keywords
    if keywords is None:  # this can be None
        keywords = ''
    created = datetime.fromtimestamp(td.lastModif)
    if is_approved:
        reviewed = created
    else:
        reviewed = None
    creator = get_django_user(td, 'user')
    comment, reviewer = get_comment_reviewer(td.comment)

    revision = Revision(document=document, summary=summary, content=content,
                        keywords=keywords, created=created, reviewed=reviewed,
                        comment=comment, is_approved=is_approved,
                        reviewer=reviewer, creator=creator)
    revision.based_on = get_based_on(document, revision)
    try:
        revision.save()
    except ProgrammingError:
        log.debug('ProgrammingError: #%s [%s] %s based on #%s [%s] %s.' % (
            revision.document.id,
            revision.document.locale, revision.document.title,
            revision.based_on.id, revision.based_on.document.locale,
            revision.based_on.document.title))
    return revision


def convert_content(tiki_content):
    content = htmlparser.unescape((tiki_content or '').strip())
    return converter.parse(content)


def create_revision_on_slug_collision(td, title, locale, is_approved, content):
    try:
        document = Document.uncached.get(title=title, locale=locale)
    except Document.DoesNotExist:
        log.debug('Failed to find %s %s on migrating %s.' % (
                    title, locale, td))
        return (None, None)
    revision = create_revision(td, document, content, is_approved)
    if is_approved:  # This one is approved, so mark it as current
        document.current_revision = revision
        document.save()
    return (document, revision)


def save_document(document, td, warnings, title, locale,
                  is_approved, content, translated_locale, verbosity):
    try:
        document.save()

    except SlugCollision:  # A staging or approved copy was previously migrated
        document, revision = create_revision_on_slug_collision(
            td, title, translated_locale, is_approved, content)
        return (document, revision, warnings)

    except IntegrityError:  # Usually caused by same parent for this locale
        # Can we try to use the translation table's locale?
        # If not, warn and fail
        if translated_locale == locale:
            warnings.append(u'A translation already exists for this document '
                            u' in %s.' % locale)
            return (None, None, warnings)

        # Attempting a different locale
        if verbosity > 1:
            warnings.append(u'Using page language (%s) '
                            u'instead of language from translation table (%s).'
                            % (locale, translated_locale))
        document.locale = locale
        try:
            document.save()
        except SlugCollision:  # A staging or approved copy exists
            document, revision = create_revision_on_slug_collision(
                td, title, locale, is_approved, content)
            return (document, revision, warnings)
        except IntegrityError:
            warnings.append(u'A translation already exists for this document '
                            u'in %s locale.' % locale)
            return (None, None, warnings)
    return True


def create_document(td, verbosity=1):
    """Create a document from a Tiki document."""
    warnings = []

    cat_ids = get_cat_ids(td)
    is_approved, title = get_title_is_approved(td, cat_ids)
    slug = get_slug(title)

    locale = get_locale(td.lang)
    # English articles are localizable, translations are not.
    if locale == settings.WIKI_DEFAULT_LANGUAGE:
        is_localizable = True
    else:
        is_localizable = False

    # Check for duplicate content and bail if there's already some
    content, warnings = convert_content(td.content)

    if locale == settings.WIKI_DEFAULT_LANGUAGE:
        parent, translated_locale = (None, settings.WIKI_DEFAULT_LANGUAGE)
        translations = []
    else:
        translations = get_translations(td.page_id)
        parent_info = get_parent_lang(translations, td.page_id)
        if parent_info:
            parent, translated_locale = parent_info
        else:
            parent = None
            translated_locale = locale

    category = get_category(td, translations, cat_ids)
    if not category:  # Skip this
        warnings.append(WARNINGS['skip'])
    if not category or category == -1:  # -1 doesn't show warning
        return (None, None, warnings)
    if not content:  # Why should I bother to migrate this?
        if verbosity > 1:
            warnings.append(WARNINGS['empty_content'])
        return (None, None, warnings)

    # Get revisions with the same content as this tiki page
    same_content_revs = Revision.objects.filter(content=content,
                                                document__locale=locale)

    if same_content_revs.exists():
        # We migrated staging first?
        if is_approved and not same_content_revs[0].is_approved:
            revision = same_content_revs[0]
            revision.is_approved = True
            revision.save()
            document = revision.document
            document.current_revision = revision
            if not document.parent and parent:
                document.parent = parent
            result = save_document(
                document, td, warnings, title, locale, is_approved, content,
                translated_locale, verbosity)
            if isinstance(result, tuple):
                return result
        if verbosity > 1:
            warnings.append(WARNINGS['same_content'] % same_content_revs[0].id)
        return (None, None, warnings)

    # Create the document first
    # XXX: consider using locale if translated_locale breaks too many things
    document = Document(title=title, slug=slug, locale=translated_locale,
                        parent=parent, category=category,
                        is_localizable=is_localizable)
    result = save_document(document, td, warnings, title, locale, is_approved,
                           content, translated_locale, verbosity)
    if isinstance(result, tuple):
        return result

    warnings.extend(check_content(content))

    # Then create its first revision
    revision = create_revision(td, document, content, is_approved)

    if is_approved:
        # Update the document's current revision
        document.current_revision = revision
        document.save()

    return (document, revision, warnings)


def create_template(content_template):
    """Creates a template from a content template dict.

    Note: assumes the English template was migrated first (if there was one).

    """
    title = 'Template:' + content_template['label']
    slug = get_slug(title)
    category = CATEGORIES[3][0]  # Templates category
    locale = get_locale(content_template['locale'])
    # English articles are localizable, translations are not.
    if locale == settings.WIKI_DEFAULT_LANGUAGE:
        is_localizable = True
    else:
        is_localizable = False
    try:
        parent = Document.objects.get(title=title,
                                      locale=settings.WIKI_DEFAULT_LANGUAGE)
    except Document.DoesNotExist:
        parent = None

    # Create the template document first
    document = Document(title=title, slug=slug, locale=locale,
                        parent=parent, category=category,
                        is_localizable=is_localizable)
    document.save()

    # Then create its first revision
    summary = ''
    content = content_template['data'].strip()
    content, warnings = converter.parse(content)
    keywords = ''
    creator = User.objects.get(pk=1)
    created = content_template['published']
    comment = ''
    reviewer = creator

    revision = Revision(document=document, summary=summary, content=content,
                        keywords=keywords, created=created,
                        comment=comment, is_approved=True,
                        reviewer=reviewer, creator=creator)
    revision.save()

    # Update the document's current revision
    document.current_revision = revision
    document.save()

    return (document, revision, warnings)


def create_document_metadata(document, tiki_document):
    """Look up metadata for the document, create it and attach it."""
    # if there is any fxver/version info added, don't add it again
    if document.firefox_versions.exists() or \
       document.operating_systems.exists():
        return False

    fxver_ids = get_firefox_versions(tiki_document, document)
    fxvers = [FirefoxVersion(item_id=id) for id in fxver_ids]
    document.firefox_versions.add(*fxvers)

    os_ids = get_operating_systems(tiki_document, fxver_ids)
    oses = [OperatingSystem(item_id=id) for id in os_ids]
    document.operating_systems.add(*oses)


def fetch_content_templates():
    """Gets content templates."""
    c = connection.cursor()
    c.execute("""
        SELECT DISTINCT
            tc.lang, tc.contentId, tc.contentLabel, tpc.data, tpc.publishDate
        FROM
            tiki_content tc, tiki_programmed_content tpc
        WHERE
            tc.contentId = tpc.contentId
            AND tc.contentLabel != ''
            AND tc.lang != '' AND tc.lang IS NOT NULL
        ORDER BY publishDate DESC, tc.contentId DESC""")
    tiki_templates = c.fetchall()

    templates = {}
    hashes = []
    en_ids = []
    rest_ids = []
    for tiki_t in tiki_templates:
        id = int(tiki_t[1])
        locale = tiki_t[0]
        label = tiki_t[2].strip()
        # We're only migrating the top data for each content, skip if already
        # migrated for this locale
        hash = locale.lower() + '@' + label.lower()
        if hash in hashes:
            continue

        # Separate into English and non-English articles
        if locale == 'en':
            en_ids.append(id)
        else:
            rest_ids.append(id)
        hashes.append(hash)  # append this
        templates[id] = {
            'locale': locale,
            'id': id,
            'label': label,
            'data': tiki_t[3],
            'published': datetime.fromtimestamp(int(tiki_t[4])),
        }

    en_ids, rest_ids = set(en_ids), set(rest_ids)

    return (templates, en_ids, rest_ids)


def fetch_en_documents(count, offset):
    return WikiPage.objects.filter(lang='en').order_by(
        'lastModif')[offset:offset + count]


def fetch_rest_documents(count, offset):
    return WikiPage.objects.exclude(lang='en').order_by(
        'lastModif')[offset:offset + count]


class Command(NoArgsCommand):
    help = 'Migrate data for tiki pages.'
    max_documents = 9000  # Max number of documents to store at any time
    max_total_documents = 9000  # Max number of documents to migrate
    _exhausted_en_documents = False

    def fetch_documents(self, count, offset):
        """Gets english documents first, and then non-English documents"""
        if self._exhausted_en_documents:
            return fetch_rest_documents(count, offset - self.en_offset)
        documents = fetch_en_documents(count, offset)

        self.en_offset = len(documents)
        self._exhausted_en_documents = (self.en_offset == 0 or
                                        self.en_offset < count)
        return documents

    def migrate_templates(self, options):
        """Migrates the content templates."""
        templates, en_ids, rest_ids = fetch_content_templates()

        def create_with_warning(template):
            warnings = create_template(template)[-1]
            for w in warnings:
                log.debug(
                    u'Warning: %s -- (%s) Template:%s | #%s' % (
                    w, template['locale'], template['label'], template['id']))

        def print_template_info(template):
            if options['verbosity'] > 1:
                log.debug(u'Processing (%s) Template:%s | #%s...' % (
                    template['locale'], template['label'],
                    template['id']))

        # Go through en_ids first
        for id in en_ids:
            print_template_info(templates[id])
            create_with_warning(templates[id])
        # ... and then the rest.
        for id in rest_ids:
            print_template_info(templates[id])
            create_with_warning(templates[id])

    def handle_noargs(self, *args, **options):
        pin_this_thread()

        options['verbosity'] = int(options['verbosity'])

        if options['verbosity'] > 0:
            print 'Starting migration for KB.'
            print 'Migrating templates...'

        self.migrate_templates(options)

        if options['verbosity'] > 0:
            print 'Done migrating templates. Migrating documents...'

        # Create the documents
        document_offset = 0
        total_documents = WikiPage.objects.count()
        documents = self.fetch_documents(self.max_documents, document_offset)
        document_counter = 0
        document_i = 0
        last_percent = 0
        while documents and document_counter <= self.max_total_documents:
            percent = document_counter * 100 / total_documents
            if not percent % 10 and last_percent != percent:
                print u'%s percent done.' % percent
                last_percent = percent

            try:
                tiki_document = documents[document_i]
            except IndexError:
                # we're done with this list, next!
                document_offset = document_offset + len(documents)
                documents = self.fetch_documents(
                    self.max_documents, document_offset)
                document_i = 0
                continue

            if options['verbosity'] > 1:
                log.debug(u'Processing (%s) %s | #%s...' % (
                    tiki_document.lang, tiki_document.title,
                    tiki_document.page_id))

            # Create document...
            document, _, warnings = create_document(tiki_document,
                                                    options['verbosity'])
            if document and document.parent is None:
                # Then create its metadata: fx version, OS...
                create_document_metadata(document, tiki_document)

            document_i += 1
            document_counter += 1

            if document and document.parent is None and \
               document.locale != settings.WIKI_DEFAULT_LANGUAGE:
                warnings.append(WARNINGS['no_parent'])

            for w in warnings:
                log.debug(u'Warning: %s -- (%s) %s | #%s' % (
                          w, tiki_document.lang, tiki_document.title,
                          tiki_document.page_id))

        if options['verbosity'] > 0:
            print u'Successfully migrated documents in KB'

        if options['verbosity'] > 0 and \
            document_counter >= self.max_total_documents:
            print ('Reached maximum number of documents to migrate ' +
                   '(%s) and stopped.' % self.max_total_documents)
