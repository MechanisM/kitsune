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
# TODO: What do we do for non-English tiki_pages that have no English
#       equivalent???
import re
from datetime import datetime
from multidb.pinning import pin_this_thread

from django.conf import settings
from django.contrib.auth.models import User
from django.core.management.base import NoArgsCommand
from django.db import connection

from wiki.models import (Document, Revision, SIGNIFICANCES, CATEGORIES,
                         FirefoxVersion, OperatingSystem)
from sumo.converter import TikiMarkupConverter
from sumo.models import WikiPage, CategoryObject, TikiObject


# Converts TikiWiki syntax to MediaWiki syntax
converter = TikiMarkupConverter()
ANONYMOUS_USER_NAME = 'AnonymousUser'
RE_REVIEWER = re.compile('\[?approved by ([^\]]+?)\]')
TIKI_CATEGORY_MAP = {
    14: 3,  # Firefox 3.0
    25: 2,  # Firefox 3.5-3.6
}
WARNINGS = {'no_parent': 'This document is missing its parent.'}


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
    if title.startswith('*'):
        return (False, title[1:])
    return (True, title)


def get_slug(title):
    """Slugify a documment title"""
    return title  # Agreed to just use the title as the slug


def get_locale(lang):
    """Validate against SUMO_LANGUAGES, return default if not found."""
    return (lang if lang in settings.SUMO_LANGUAGES
                 else settings.WIKI_DEFAULT_LANGUAGE)


def get_parent(page_id):
    """Returns the migrated English Document of a WikiPage, if found.

    Assumptions:
        * the corresponding English Document for the WikiPage exists, i.e.
          was already migrated
        * every document is translated from English

    """
    c = connection.cursor()
    c.execute("""
        SELECT
            t2.objId AS page_id
        FROM
            tiki_translated_objects t1,
            tiki_translated_objects t2
            LEFT JOIN tiki_pages p
                ON p.page_id = t2.objId
        WHERE
            t1.traId = t2.traId
            AND t2.lang = "en"
            AND t1.type = "wiki page"
            AND t1.objId = %s""", [page_id])
    parent_d = None
    parent_id = c.fetchone()
    if not parent_id:
        return parent_d

    parent_id = int(parent_id[0])
    if parent_id != page_id:
        # get the parent tiki document
        parent_td = WikiPage.objects.get(page_id=parent_id)
        # We assume that the parent exists
        title = get_title_is_approved(parent_td.title)[1]
        locale = get_locale(parent_td.lang)
        parent_d = Document.objects.get(title=title, locale=locale)

    return parent_d


def get_category(td):
    # TODO: get category based on tiki_category and tiki_category_objects
    return CATEGORIES[0][0]


def get_firefox_versions(td):
    """Returns a list of integers, the Document's Firefox versions."""
    tiki_object = TikiObject.objects.get(type='wiki page', itemId=td.title)
    versions = CategoryObject.objects.filter(
        categId__in=TIKI_CATEGORY_MAP.keys(),
        catObjectId=tiki_object.objectId)
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
    return ()


def create_revision(td, document, is_approved=False):
    """Create revision for a document using a Tiki document."""
    summary = td.description
    content = converter.convert(td.content.strip())
    keywords = td.keywords
    if keywords is None:  # this can be None
        keywords = ''
    created = datetime.fromtimestamp(td.created)
    significance = SIGNIFICANCES[-1][0]
    creator = get_django_user(td, 'user')
    comment, reviewer = get_comment_reviewer(td.comment)

    revision = Revision(document=document, summary=summary, content=content,
                        keywords=keywords, created=created,
                        significance=significance, comment=comment,
                        reviewer=reviewer, creator=creator,
                        is_approved=is_approved)
    revision.save()
    return revision


def create_document(td):
    """Create a document from a Tiki document."""
    is_approved, title = get_title_is_approved(td.title)
    slug = get_slug(title)

    locale = get_locale(td.lang)
    parent = get_parent(td.page_id)
    category = get_category(td)

    # Create the document first
    document = Document(title=title, slug=slug, locale=locale,
                        parent=parent, category=category)
    document.save()

    # Then create its first revision
    revision = create_revision(td, document, is_approved)

    # Update the document's current revision
    document.current_revision = revision
    document.save()

    warnings = check_content(document.html)

    return (document, revision, warnings)


def create_document_metadata(document, tiki_document):
    """Look up metadata for the document, create it and attach it."""
    fxver_ids = get_firefox_versions(tiki_document)
    fxvers = [FirefoxVersion(item_id=id) for id in fxver_ids]
    document.firefox_versions.add(*fxvers)

    os_ids = get_operating_systems(tiki_document)
    oses = [OperatingSystem(item_id=id) for id in os_ids]
    document.operating_systems.add(*oses)


def fetch_en_documents(count, offset):
    return WikiPage.objects.filter(lang='en')[offset:offset + count]


def fetch_rest_documents(count, offset):
    return WikiPage.objects.exclude(lang='en')[offset:offset + count]


class Command(NoArgsCommand):
    help = 'Migrate data for tiki pages.'
    max_documents = 10  # Max number of documents to store at any time
    max_total_documents = 10  # Max number of documents to migrate
    _exhausted_en_documents = False

    def fetch_documents(self, count, offset):
        """Gets english documents first, and then non-English documents"""
        if self._exhausted_en_documents:
            return fetch_rest_documents(count, offset)
        documents = fetch_en_documents(count, offset)
        self._exhausted_en_documents = (len(documents) == 0)
        return documents

    def handle_noargs(self, *args, **options):
        pin_this_thread()

        options['verbosity'] = int(options['verbosity'])

        if options['verbosity'] > 0:
            print ('Starting migration for KB.')

        # Create the documents
        document_offset = 0
        documents = self.fetch_documents(self.max_documents, document_offset)
        document_counter = self.max_documents
        document_i = 0
        while documents and document_counter <= self.max_total_documents:
            try:
                tiki_document = documents[document_i]
            except IndexError:
                # we're done with this list, next!
                document_offset = document_offset + self.max_documents
                documents = self.fetch_documents(
                    self.max_documents, document_offset)
                document_counter += self.max_documents
                document_i = 0
                continue

            if options['verbosity'] > 1:
                print 'Processing (%s) %s | #%s...' % (
                    tiki_document.lang, tiki_document.title,
                    tiki_document.page_id)

            # Create document...
            document, _, warnings = create_document(tiki_document)
            # Then create its metadata: fx version, OS...
            create_document_metadata(document, tiki_document)

            document_i = document_i + 1

            if document.locale != settings.WIKI_DEFAULT_LANGUAGE and \
               document.parent is None:
                warnings.push(WARNINGS['no_parent'])

            for w in warnings:
                print '(%s) %s | #%s -- Warning: %s' % (
                    tiki_document.lang, tiki_document.title,
                    tiki_document.page_id, w)

        if options['verbosity'] > 0:
            print ('Successfully migrated documents in KB')

        if options['verbosity'] > 0 and \
            document_counter >= self.max_total_documents:
            print ('Reached maximum number of documents to migrate ' +
                   '(%s) and stopped.' % self.max_total_documents)
