"""
New syntax summary:

* {DIV}
  * unknown class => <span class="<unknown class>">
  * class=noclass => <div></div>
  * class=firefox version or operating system => {for mapped-version/os}
  * class=button, menu, filepath => {button ...}, {menu ...}, {filepath ...}
  * class=kbd => {key ...}
* {SHOWFOR(browser=...,os=)} => {for browsers}{for oses}..

* These don't allow nesting: (the above do)
  * {PATH()}...{PATH} turns into {menu ...}
  * {MENU()}...{MENU} turns into {menu ...}
  * {FILE()}...{FILE} turns into {filepath ...}
  * {PREF()}  turns into <span class="pref">
  * ~tc~ ... ~/tc~ turns into HTML comment <!-- ... -->
                    we don't support this atm afaik
  * ~np~ ... ~/np~ turns into <nowiki> ... </nowiki>
  * ~hc~ ... ~/hc~ -- HTML comment, turns into <!-- ... -->
  * {img src="img/wiki_up/file.png"} turns into [[Image:file.png]]
  * {REDIRECT(page=<page>)} turns into REDIRECT_CONTENT % '<page>'
  These show warnings if you nest:
  * {TAG}
  * {SCREENCAST(file=>some-file-hash)}{SCRENCAST} turns into
    [[Video:some-file-hash]]
"""

# TODO: convert ;: at beginning of line

import re
from xml.sax.saxutils import quoteattr

from wiki.models import FIREFOX_VERSIONS, OPERATING_SYSTEMS, REDIRECT_CONTENT

REDIRECTOR_REGEX = REDIRECT_CONTENT % '\g<page>'

ID_LABEL_MAP = {
    20: 'suljefirefox',
    147: 'mozillahispano2',
    466: 'profileFolder',
    467: 'closeFirefox',
    9: 'toparticles',
}


def _content_templates(matchobj):
    """Turns {content label=blah} or {content id=blah_id} into [[T:blah]]."""
    name = matchobj.group(1)
    value = matchobj.group(2)
    if name == 'id':
        try:
            value = int(value)
        except ValueError:
            return ''
        if not (value in ID_LABEL_MAP):
            return ''
        value = ID_LABEL_MAP[value]
    elif name == 'idlabel':
        # Turn '123string' into 'string'
        try:
            while int(value[0]) in range(0, 9):
                value = value[1:]
        except ValueError:
            pass
    return '[[T:%s]]' % value


def _img_convert_param(param, use_wiki_syntax):
    """Switch use_wiki_syntax to False to output HTML attrs instead."""
    name_value = param.lower().split('=', 1)
    if len(name_value) == 1:
        return ''
    name, value = name_value
    name, value = name.strip(), value.strip()
    if name == 'vertical-imalign':
        # Circular imports FTL...
        from sumo.parser import IMAGE_PARAMS
        if not (value in IMAGE_PARAMS['valign']):
            return ''
        if use_wiki_syntax:
            return 'valign=' + value

        return ' style="vertical-align: ' + value + '"'

    return ''


def _img_get_params(params_group, use_wiki_syntax=True):
    if params_group:
        params_list = [_img_convert_param(p, use_wiki_syntax) for
                       p in params_group.split(' ')]
        if use_wiki_syntax:
            return '|' + '|'.join(params_list)
        return params_list
    return ''


def _internal_img_regex(matchobj):
    """Turns {img src="blah.png" [vertical-imalign=middle]} to [[Image:...]]"""
    file = matchobj.group('file')
    params = _img_get_params(matchobj.group('params'))

    return '[[Image:%s%s]]' % (file, params)


def _external_img_regex(matchobj):
    """Turns {img src="http://..."} to <img src="http://...">."""
    url = matchobj.group('url')
    params = _img_get_params(matchobj.group('params'), use_wiki_syntax=False)

    return '<img src="%s"%s>' % (url, ' '.join(params))


CONVERTER_PATTERNS = (
    # Turns [external|link] into [external link] but not [[internal|links]]
    (r'(?!\[\[)\[(?P<href>[^\]]*?)\|(?P<name>[^\]]*?)\]',
     '[\g<href> \g<name>]'),
    (r'===(?P<underlined>.*?)===', '<u>\g<underlined></u>'),
    (r'__(?P<bold>.*?)__', "'''\g<bold>'''"),
    # Internal anchors only
    (r'\(\(\|?(?P<hashlabel>#[^)]*?)\)\)', '[[\g<hashlabel>]]'),
    # Link + anchor + text, because Tiki is vewwy special
    (r'\(\((?P<href>[^)]*?)\|(?P<anchor>[^)]*?)\|(?P<name>[^)]*?)\)\)',
     '[[\g<href>\g<anchor>|\g<name>]]'),
    # Link + text
    (r'\(\((?P<href>[^)]*?)\|(?P<name>[^)]*?)\)\)', '[[\g<href>|\g<name>]]'),
    # Just link
    (r'\(\((?P<href>[^)]*?)\)\)', '[[\g<href>]]'),
    (r'^!!!!!!\s*(?P<heading>.*?)$', '====== \g<heading> ======'),
    (r'^!!!!!\s*(?P<heading>.*?)$', '===== \g<heading> ====='),
    (r'^!!!!\s*(?P<heading>.*?)$', '==== \g<heading> ===='),
    (r'^!!!\s*(?P<heading>.*?)$', '=== \g<heading> ==='),
    (r'^!!\s*(?P<heading>.*?)$', '== \g<heading> =='),
    (r'^!\s*(?P<heading>.*?)$', '= \g<heading> ='),
    (r'^---(?P<separator>[ \n])', '----\g<separator>'),
    (r'\{CODE\(\)\}(?P<codetext>.*?)\{CODE\}', '<code>\g<codetext></code>'),
    (r'\{PATH\(\)\}(?P<txt>.*?)\{PATH\}', '{menu \g<txt>}'),
    (r'\{MENU\(\)\}(?P<txt>.*?)\{MENU\}', '{menu \g<txt>}'),
    (r'\{FILE\(\)\}(?P<txt>.*?)\{FILE\}', '{filepath \g<txt>}'),
    (r'\{PREF\(\)\}(?P<txt>.*?)\{PREF\}', '{pref \g<txt>}'),
    (r'~np~(?P<txt>.*?)~\/np~', '<nowiki>\g<txt></nowiki>'),
    (r'~(h|t)c~(?P<txt>.*?)~\/(h|t)c~', '<!--\g<txt>-->'),
    (r'\{SCREENCAST\s*\(\s*file=?\>?\s*(?P<file>.*?)\).*\}',
     '[[Video:\g<file>]]'),
    (r'\{\s*SCREENCAST\s*\}', ''),  # remaining are useless closing tags
    (r'\{img.*?'             # {img followed by anything
     r'src\s*=?"?\/?'        # stop at e.g. src ="/
     r'img\/wiki_up\/'       # follow it by img/wiki_up
     r'(?P<file>[^\}" ]*)[ "]*(?P<params>.*?)\}',   # capture the file
     _internal_img_regex),
    (r'\{img.*?'             # {img followed by anything
     r'src\s*=?"?\/?'        # stop at e.g. src ="/
     r'(?P<url>[^\}" ]*)[ "]*(?P<params>.*?)\}',   # capture the url
     _external_img_regex),
    (r'\{REDIRECT\s*\(\s*page\s*=\s*(?P<page>[^\)]*)\)\/?\}',
     REDIRECTOR_REGEX),
    (r'%{3,}', '<br/>'),
    (r'\^(?P<text>[^\^]*?)\^', '{note}\g<text>{/note}'),
    (r'(\s)*\{maketoc\}(\s)*', '\n\n'),
    (r'\{\s*DYNVARS\s*\(?[^\}\{\(\)]*?\s*\)?\s*\/?\s*\}', ' '),
    (r'\{\s*ANAME\s*\([^\}\{]*?\}.*?\{[^\(\)]*?ANAME[^\(\)]*?\}', ' '),
    (r'\{\s*content\s*(idlabel|label|id)\s*=\s*([^\}\{]*?)\s*\}',
     _content_templates),
    # After image and internal links were processed, it's possible they were
    # nested. Fix that.
    (r'\[\[(?P<href>[^\n):\]]+)\|\[\[Image:(?P<src>[^\n):\]]+)\]\]\]\]',
     '[[Image:\g<src>|page=\g<href>]]'),
    (r'\r', ''),
)


STACKS_PATTERNS = {
    'div': (
    ('entry', r'(\{DIV[^\{\}]*?\})'),  # this marks the entry/exit point
    ('class', r'\{DIV[^\{\}]*?'        # starts with {DIV*
              r'class=?>?(&gt;)?.*?'   # continues with class
              r'([a-zA-Z0-9\. ]+)'     # capture the class value, e.g. mac
              r'([^\{\}]*?)\}')),      # ends with *}
    'tag': (
    ('entry', r'(\{TAG[^\{\}]*?\})'),
    ('tag', r'\{TAG[^\{\}]*?'      # starts with {TAG*
            r'tag=?>?(&gt;)?.*?'   # continues with tag
            r'([a-zA-Z0-9\. ]+)'   # capture the tag value, e.g. kbd
            r'([^\{\}]*?)\}')),    # ends with *}
    'showfor': (
    ('entry', r'(\{SHOWFOR[^\{\}]*?\})'),
    ('browser', r'\{SHOWFOR[^\{\}]*?'     # starts with {SHOWFOR*
                r'browser=?>?(&gt;)?.*?'  # continues with browser
                r'([a-zA-Z0-9\.\+ ]+)'    # capture the browser value, e.g. fx3
                r'([^\{\}]*?)\}'),        # ends with *}
    ('os', r'\{SHOWFOR[^\{\}]*?'   # starts with {SHOWFOR*
           r'os=?>?(&gt;)?.*?'     # continues with os
           r'([a-zA-Z0-9\.\+ ]+)'  # capture the os value, e.g. fx3
           r'([^\{\}]*?)\}'),      # ends with *}
    ('spans', r'\{SHOWFOR[^\{\}]*?'  # starts with {SHOWFOR*
           r'spans.*?'               # continues with spans
           r'([^\{\}]*?)\}')),       # ends with *}
}

re_plugin_flags = re.MULTILINE | re.IGNORECASE | re.DOTALL

converter_patterns = [
    (re.compile(pattern[0], re.MULTILINE | re.DOTALL), pattern[1]) for
    pattern in CONVERTER_PATTERNS]


def stacks_patterns_entry_to_dict(entry):
    return dict([(k, re.compile(p, re_plugin_flags)) for k, p in entry])


stacks_patterns = dict([(k, stacks_patterns_entry_to_dict(e)) for
                        k, e in STACKS_PATTERNS.iteritems()])


class TikiMarkupConverter(object):
    """
    Converter for Tiki syntax to MediaWiki syntax.
    """
    openers = []  # stack element == (entry match, div class)
    warnings = []

    def convert(self, text):
        for p in converter_patterns:
            text = p[0].sub(p[1], text)
        return text

    def simulate_pda(self, text, plugin, get_metadata, get_openers,
                     get_closers, can_nest=True):
        """Simulates a push-down automaton, using the self.openers stack.

        * Set can_nest=False to return a warning if the plugin is nested
        Provides callbacks for:
        * getting metadata, e.g. for div: class, for showfor: browser, os
        * getting openers and closers for the syntax

        Important: this PDA outputs processed text as it goes through the
        original text.

        """
        new_text = ''
        last_match_pos = 0
        for m in stacks_patterns[plugin]['entry'].finditer(text):
            entry_text = m.group(1)
            metadata = get_metadata(entry_text, self)
            # If not in a {<plugin>()}..{<plugin>}, append anything that was
            # skipped between the last matched position, and the current one
            if not self.openers:
                new_text += text[last_match_pos:m.start()]
                # step forward
                last_match_pos = m.end()

            # Opening a {<plugin>()}, push it on the stack append passed text
            if metadata or metadata is False:
                if self.openers and not can_nest:
                    self.warnings.append("Can't nest %s." % plugin)
                self.openers.append((m, metadata))
                # if nested, also append anything that's been skipped
                new_text += text[last_match_pos:m.start()]
                # step forward
                last_match_pos = m.end()
                new_text += get_openers(metadata, self)
            # Closing a {<plugin>()}, pop things off the stack
            else:
                last_metadata = True
                if self.openers:
                    _, last_metadata = self.openers[-1]
                if last_metadata is not False:  # Skip contents of this plugin
                    new_text += text[last_match_pos:m.start()]
                # If anything is open, close it
                if self.openers:
                    # step forward
                    self.openers.pop()
                    new_text += get_closers(last_metadata, self)

                # Move last_match_pos after closing
                last_match_pos = m.end()
        # Clear out openers
        self.openers = []
        # Append what's left
        new_text += text[last_match_pos:]
        return new_text

    def parse_div(self, text):
        """Parses {DIV} plugin."""
        return self.simulate_pda(text, 'div', get_div_class, get_div_openers,
                                 get_div_closers)

    def parse_tag(self, text):
        """Parses {TAG} plugin."""
        # Tags are not nestable
        return self.simulate_pda(text, 'tag', get_tag_name, get_tag_openers,
                                 get_tag_closers, can_nest=False)

    def parse_showfor(self, text):
        """Parses {SHOWFOR} plugin."""
        # Showfor tags are nestable, but {SHOWFOR(spans=on)/} is self-closing
        # ... and meaningless for migration purposes, needs to be skipped.
        return self.simulate_pda(text, 'showfor', get_showfor_metadata,
                                 get_showfor_openers, get_showfor_closers)

    def parse(self, text):
        """Convert, then parse."""
        self.warnings = []
        text = self.convert(text)    # Convert all the regexes first
        for func in  (self.parse_div, self.parse_tag, self.parse_showfor):
            text = func(text)
        # We don't like surrounding whitespace
        text = text.strip()
        return (text, self.warnings)


def get_showfor_metadata(text, pda):
    showfor = stacks_patterns['showfor']['spans'].search(text)
    # {SHOWFOR(spans=on)/} must be skipped
    if showfor:
        return None

    showfor = {}
    for param in ('os', 'browser'):
        showfor[param] = stacks_patterns['showfor'][param].search(text)
        if showfor[param]:
            showfor[param] = showfor[param].group(2).strip().lower()
            # There may be multiple oses/browsers. Check and build a list.
            list_val = showfor[param].split('+')
            showfor[param] = []
            for cls in list_val:
                if cls in CLASSES_MAP:
                    showfor[param].append(CLASSES_MAP[cls])
                else:
                    showfor[param].append(cls)
            # Make this a set, no point in having {for fx3, fx3}
            showfor[param] = set(showfor[param])

    # Ignore/skip fx2
    discard_fx2 = False
    if showfor['browser'] and 'fx2' in showfor['browser']:
        discard_fx2 = True
        showfor['browser'].discard('fx2')

    if not (showfor['os'] or showfor['browser']):
        if discard_fx2:  # Special case for skipping content
            return False
        else:
            return None

    return showfor


def get_showfor_openers(showfor, pda):
    if not showfor:
        return ''

    open_text = ''
    for param in ('os', 'browser'):
        if showfor[param]:
            open_text += '{for %s}' % ','.join(showfor[param])

    return open_text


def get_showfor_closers(showfor, pda):
    if not showfor:
        return ''

    close_text = ''
    for param in ('os', 'browser'):
        if showfor[param]:
            close_text += '{/for}'

    return close_text


def get_tag_name(text, pda):
    tag = stacks_patterns['tag']['tag'].search(text)
    if tag:
        tag = tag.group(2).strip().lower()
    return tag


def get_tag_openers(tag, pda):
    if tag == 'sup':  # sup dawg?
        return '<sup>'
    elif tag == 'strike':
        return '<strike>'
    elif tag != 'kbd':
        pda.warnings.append('Unrecognized tag (%s).' % tag)
    return '{key '


def get_tag_closers(tag, pda):
    if tag == 'sup':
        return '</sup>'
    elif tag == 'strike':
        return '</strike>'
    return '}'


# These are classes that turn into self-closing markup, such as
# {menu}, {button}, etc
TO_SELFCLOSE_CLASSES = ('button', 'menu', 'filepath', 'key')
# These are classes that turn into showfor syntax
CLASSES_MAP = {
# Firefox versions
    'firefox4': 'fx4',
    'firefox4.0': 'fx4',
    'ff4': 'fx4',
    '4.0': 'fx4',
    'firefox3.1': 'fx35',
    'fx3.1': 'fx35',
    'ff3.1': 'fx35',
    '3.1': 'fx35',
    'ff3.5': 'fx35',
    '3.5': 'fx35',
    'firefox3.5': 'fx35',
    'firefox3.6': 'fx35',
    'firefox35': 'fx35',
    'firefox36': 'fx35',
    'fx3.6': 'fx35',
    '3.6': 'fx35',
    'ff3.6': 'fx35',
    'ff3': 'fx3',
    'firefox3.0': 'fx3',
    'firefox3': 'fx3',
    '3': 'fx3',
    '2': 'fx2',
    'firefox2': 'fx2',
    'firefox2.0': 'fx2',
    'ff2': 'fx2',
# Operating systems
    'windows': 'win',
    'nomac': 'win,linux',
    'nounix': 'win,mac',
    'nolinux': 'win,mac',
    'unix': 'linux',
    'nowin': 'mac,linux',
    'nowindows': 'mac,linux',
# Menu
    'menupath': 'menu',
# Keyboard
    'kbd': 'key',
}

# These trigger using the {for} markup
TO_SHOWFOR_FF = tuple([ver[2] for ver in FIREFOX_VERSIONS])
TO_SHOWFOR_OS = tuple([ver[2] for ver in OPERATING_SYSTEMS])
TO_SHOWFOR_CLASSES = TO_SHOWFOR_FF + TO_SHOWFOR_OS + (
                     'win,linux', 'win,mac', 'mac,linux')


def get_div_class(text, pda):
    """Returns a dict with the class keys of the div.

    Mapping is necessary for the showfor classes, such as noMac, unix, etc,
    since they are no longer supported.

    """
    div_class = stacks_patterns['div']['class'].search(text)
    if div_class:
        div_class = div_class.group(2).strip().lower()

    if not div_class:
        if '(' in text:  # check for e.g. {DIV()}
            return ['noclass']
        return div_class

    # There may be multiple classes. Check for that and build a list.
    div_class_tmp = div_class.split(' ')
    div_class = []
    for cls in div_class_tmp:
        if cls in CLASSES_MAP:
            div_class.append(CLASSES_MAP[cls])
        else:
            div_class.append(cls)

    # Any self-closing elements need to be last
    # E.g. {DIV(class=kbd mac,type=span)}...{DIV} should turn into
    # {for mac}{key ...}{/for}, NOT {key {for mac}...{/for}}
    # WARNING: Mixing multiple self-closing elements produces unexpected
    #          results!!! E.g. there's no such thing as a kbd button...
    found = 0
    for cls in TO_SELFCLOSE_CLASSES:
        if cls in div_class:
            found += 1
            div_class.append(div_class.pop(div_class.index(cls)))
    if found > 1:
        pda.warnings.append(
            'Found two or more self-closing classes in the same {DIV} (%s).' %
            ' '.join(div_class))

    if len(div_class) <= 1 and 'fx2' in div_class:
        return False

    return div_class


def get_div_opener(div_class, pda):
    """Handles a single class for the opener."""
    if div_class in TO_SELFCLOSE_CLASSES:
        return '{' + div_class + ' '

    if div_class in TO_SHOWFOR_CLASSES:
        return '{for %s}' % div_class

    if div_class == 'noclass':
        return '<div>'

    return '<span class=%s>' % quoteattr(div_class)


def get_div_openers(div_class, pda):
    """Returns openers for given {DIV} type and a list of classes."""
    if div_class is False:
        return ''
    text = ''
    for cls in div_class:
        text += get_div_opener(cls, pda)
    return text


def get_div_closer(div_class, pda):
    """Handles a single class for the closer."""
    if div_class in TO_SELFCLOSE_CLASSES:
        return '}'

    if div_class in TO_SHOWFOR_CLASSES:
        return '{/for}'

    if div_class == 'noclass':
        return '</div>'

    return '</span>'


def get_div_closers(div_class, pda):
    """Returns closers for given {DIV} type and a list of classes."""
    if div_class is False:
        return ''
    text = ''
    div_class.reverse()
    for cls in div_class:
        text += get_div_closer(cls, pda)
    return text
