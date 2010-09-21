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
import logging
import re
from datetime import datetime
from xml.sax.saxutils import unescape

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


log = logging.getLogger('k.migrate')
# Converts TikiWiki syntax to MediaWiki syntax
converter = TikiMarkupConverter()
ANONYMOUS_USER_NAME = 'AnonymousUser'
RE_REVIEWER = re.compile('\[?approved by ([^\]]+?)\]')
TIKI_CATEGORY_MAP = {
    14: 3,  # Firefox 3.0
    25: 2,  # Firefox 3.5-3.6
}
WARNINGS = {'no_parent': 'This document is missing its parent.',
            'skip': 'This document is not being migrated.'}


def get_django_user(obj, field_name='user'):
    """Get the django user for this thread's username."""
    u = getattr(obj, field_name)
    try:
        user = User.objects.get(username=u)
    except User.DoesNotExist:
        # Assign a dummy user to this thread
        user = User.objects.get(username=ANONYMOUS_USER_NAME)

    return user


def get_title_is_approved(title):
    """Returns a tuple (is_approved, title), special cased for staging
    articles"""
    # No surrounding whitespace, please
    title = title.strip()
    if title.startswith('*'):
        return (False, title[1:])
    return (True, title)


def get_slug(title):
    """Slugify a documment title"""
    return title  # Agreed to just use the title as the slug


def get_locale(lang):
    """Validate against SUMO_LANGUAGES, return default if not found."""
    lang = lang.strip()
    return (lang if lang in settings.SUMO_LANGUAGES
                 else settings.WIKI_DEFAULT_LANGUAGE)


def get_parent_lang(page_id):
    """Returns the migrated English Document of a WikiPage, if found.

    Assumptions:
        * the corresponding English Document for the WikiPage exists, i.e.
          was already migrated
        * every document is translated from English

    """
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
    parent_id = page_id
    while True:
        translation = c.fetchone()
        if not translation:
            break
        elif int(translation[0]) == page_id:
            translated_locale = get_locale(translation[1])
        elif translation[1] == 'en':
            parent_id = int(translation[0])
        translations.append(translation)

    if parent_id != page_id:
        # get the parent tiki document
        parent_td = WikiPage.objects.get(page_id=parent_id)
        # We assume that the parent exists
        _, title = get_title_is_approved(parent_td.title)
        try:
            return (Document.objects.get(
                        title=title, locale=settings.WIKI_DEFAULT_LANGUAGE),
                    translated_locale)
        except Document.DoesNotExist:
            return None

    return None


TIKI_CATEGORY = {
    3: [  # Administration
        'about firefox support',
        'group permissions',
        'introduction to live chat',
        'knowledge base policies',
        'live chat closed',
        'terms of service',
        'ask a question',
        ],
    2: [  # How to contribute
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
        'how to contribute',  # TODO: needs custom migration
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
        # TODO: Windows start page redirect to start page
        ],
}


TIKI_CATEGORY_IDS = {
    1: 'KB',
    3: 'Staging',
    7: 'Sandbox',
    8: 'Administration',
    9: 'Waiting for review',
    20: 'Live chat',
    23: 'HTC',
    24: 'Archive',
}


def get_category(td):
    # TODO: finalize list of documents (TIKI_CATEGORY)
    #       according to Cheng/Michael/Matthew's responses
    tiki_objects = TikiObject.objects.filter(type='wiki page', itemId=td.title)
    obj_ids = [t_o.objectId for t_o in tiki_objects]
    categories = CategoryObject.objects.filter(
        categId__in=TIKI_CATEGORY_IDS.keys(), catObjectId__in=obj_ids)
    cat_ids = [c.categId for c in categories]
    if 1 in cat_ids or 3 in cat_ids:  # Staging and KB
        return 1  # Troubleshooting

    if 7 in cat_ids or 24 in cat_ids:
        return -1  # This means don't even show warning

    if td.lang == 'en':
        title = td.title.strip().lower()
        for k, docs in TIKI_CATEGORY.iteritems():
            if title in docs:
                return k
        return 0
    # For translations, check parent's category and use that.
    parent_info = get_parent_lang(td.page_id)
    if parent_info:
        parent, _ = parent_info
        return parent.category
    # Remaining translations default to Troubleshooting
    return 1


def get_firefox_versions(td):
    """Returns a list of integers, the Document's Firefox versions."""
    tiki_objects = TikiObject.objects.filter(type='wiki page', itemId=td.title)
    obj_ids = [t_o.objectId for t_o in tiki_objects]
    versions = CategoryObject.objects.filter(
        categId__in=TIKI_CATEGORY_MAP.keys(),
        catObjectId__in=obj_ids)
    return [TIKI_CATEGORY_MAP[v.categId] for v in versions]


def get_operating_systems(td):
    """Just set all articles to Windows, Mac and Linux"""
    return [1, 2, 3]  # IDs for Windows, Mac and Linux


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


def check_content(content):
    """Returns warnings regarding potentially legacy TikiWiki syntax."""
    # TODO
    return []


def create_revision(td, document, is_approved=False):
    """Create revision for a document using a Tiki document."""
    summary = td.description
    content = unescape((td.content or '').strip())
    content, warnings = converter.parse(content)
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
    revision.save()
    return (revision, warnings)


def create_document(td):
    """Create a document from a Tiki document."""
    is_approved, title = get_title_is_approved(td.title)
    slug = get_slug(title)

    warnings = []

    locale = get_locale(td.lang)

    if locale == settings.WIKI_DEFAULT_LANGUAGE:
        parent, translated_locale = (None, settings.WIKI_DEFAULT_LANGUAGE)
    else:
        parent_info = get_parent_lang(td.page_id)
        if parent_info:
            parent, translated_locale = parent_info
        else:
            parent = None
            translated_locale = locale
    category = get_category(td)
    if not category:  # Skip this
        warnings.append(WARNINGS['skip'])
    if not category or category == -1:  # -1 doesn't show warning
        return (None, None, warnings)

    # Create the document first
    document = Document(title=title, slug=slug, locale=locale,
                        parent=parent, category=category)
    try:
        document.save()
    except SlugCollision:  # A staging or approved copy was previously migrated
        d = Document.objects.get(title=title, locale=locale)
        revision, r_warnings = create_revision(td, d, is_approved)
        warnings.extend(r_warnings)
        if is_approved:  # This one is approved, so mark it as current
            d.current_revision = revision
            d.save()
        return (d, revision, warnings)
    """
    except IntegrityError:  # Usually caused by same parent for this locale
        warnings.append(u'Using translated language (%s) instead of page '
                        u'language (%s).' % (translated_locale, locale))
        document.locale = translated_locale
        try:
            document.save()
        except SlugCollision:
            if is_approved:
                Document.objects.filter(title=title, locale=locale).delete()
                return create_document(td)
        except IntegrityError:
            warnings.append(u"Integrity error, could't figure out what "
                            u'to do...')
    """

    warnings.extend(check_content(document.html))

    # Then create its first revision
    revision, warnings = create_revision(td, document, is_approved)

    if is_approved:
        # Update the document's current revision
        document.current_revision = revision
        document.save()

    warnings.extend(check_content(document.html))

    return (document, revision, warnings)


def create_template(content_template):
    """Creates a template from a content template dict.

    Note: assumes the English template was migrated first (if there was one).

    """
    title = 'Template:' + content_template['label']
    slug = get_slug(title)
    category = CATEGORIES[3][0]  # Templates category
    locale = get_locale(content_template['locale'])
    try:
        parent = Document.objects.get(title=title,
                                      locale=settings.WIKI_DEFAULT_LANGUAGE)
    except Document.DoesNotExist:
        parent = None

    # Create the template document first
    document = Document(title=title, slug=slug, locale=locale,
                        parent=parent, category=category)
    #if 'toparticles' in title:
    #    import pdb; pdb.set_trace()
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
    fxver_ids = get_firefox_versions(tiki_document)
    fxvers = [FirefoxVersion(item_id=id) for id in fxver_ids]
    document.firefox_versions.add(*fxvers)

    os_ids = get_operating_systems(tiki_document)
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
        'page_id')[offset:offset + count]


def fetch_rest_documents(count, offset):
    return WikiPage.objects.exclude(lang='en').order_by(
        'page_id')[offset:offset + count]


class Command(NoArgsCommand):
    help = 'Migrate data for tiki pages.'
    max_documents = 2000  # Max number of documents to store at any time
    max_total_documents = 2000  # Max number of documents to migrate
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
                    '(%s) Template:%s | #%s -- Warning: %s' % (
                    template['locale'], template['label'],
                    template['id'], w))

        def print_template_info(template):
            if options['verbosity'] > 1:
                print 'Processng (%s) Template:%s | #%s...' % (
                    template['locale'], template['label'],
                    template['id'])

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
        documents = self.fetch_documents(self.max_documents, document_offset)
        document_counter = 0
        document_i = 0
        while documents and document_counter <= self.max_total_documents:
            percent = document_counter * 100 / self.max_total_documents
            if not document_counter % (self.max_total_documents / 10):
                print u'%s percent done.' % percent

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
                print u'Processing (%s) %s | #%s...' % (
                    tiki_document.lang, tiki_document.title,
                    tiki_document.page_id)

            # Create document...
            document, _, warnings = create_document(tiki_document)
            if document:
                # Then create its metadata: fx version, OS...
                create_document_metadata(document, tiki_document)

            document_i += 1
            document_counter += 1

            if document and document.parent is None and \
               document.locale != settings.WIKI_DEFAULT_LANGUAGE:
                warnings.append(WARNINGS['no_parent'])

            for w in warnings:
                log.debug(u'(%s) %s | #%s -- Warning: %s' % (
                          tiki_document.lang, tiki_document.title,
                          tiki_document.page_id, w))

        if options['verbosity'] > 0:
            print u'Successfully migrated documents in KB'

        if options['verbosity'] > 0 and \
            document_counter >= self.max_total_documents:
            print ('Reached maximum number of documents to migrate ' +
                   '(%s) and stopped.' % self.max_total_documents)
