from nose.tools import eq_
from nose import SkipTest

from sumo.converter import TikiMarkupConverter
from sumo.tests import TestCase
from wiki.models import REDIRECT_CONTENT

converter = TikiMarkupConverter()


class TestConverter(TestCase):

    def test_bold(self):
        content = '__bold__'
        eq_("'''bold'''", converter.convert(content))

    def test_italics(self):
        content = "''italics''"
        eq_("''italics''", converter.convert(content))

    def test_bold_and_italics(self):
        content = "''__bold and italics__''"
        eq_("'''''bold and italics'''''", converter.convert(content))

    def test_internal_link(self):
        content = '((Internal link))'
        eq_('[[Internal link]]', converter.convert(content))

    def test_internal_link_named(self):
        content = '((Internal link|link name))'
        eq_('[[Internal link|link name]]', converter.convert(content))

    def test_internal_link_name_anchro(self):
        content = '((Internal link|#anchor here|link name))'
        eq_('[[Internal link#anchor here|link name]]',
            converter.convert(content))

    def test_internal_link_multiple(self):
        content = '((Internal link)) and ((Internal again|named))'
        eq_('[[Internal link]] and [[Internal again|named]]',
            converter.convert(content))
        content = '((Internal link|named)) and ((Internal again))'
        eq_('[[Internal link|named]] and [[Internal again]]',
            converter.convert(content))

    def test_convert_same_page_link(self):
        content = '((|#anchor))'
        eq_('[[#anchor]]', converter.convert(content))

    def test_convert_same_page_link_named(self):
        content = ('((Internal 1|{img src="img/wiki_up/file.png" }))')
        eq_('[[Image:file.png|page=Internal 1]]', converter.convert(content))

    def test_external_link(self):
        content = '[http://external.link]'
        eq_('[http://external.link]', converter.convert(content))
        content = '[http://external.link|named]'
        eq_('[http://external.link named]', converter.convert(content))

    def test_internal_link_for(self):
        content = ('((Page|{DIV(class=win,type=span)}Options{DIV}'
                   '{DIV(class=noWin,type=span)}Preferences{DIV} window))')
        expected = ('[[Page|{for win}Options{/for}{for mac,linux}Preferences'
                    '{/for} window]]')
        eq_(expected, converter.parse(content)[0])

    def test_heading(self):
        content = """!heading 1
                     \n!! heading 2
                     \n!!! heading 3
                     \n!!!!heading 4
                     \n!!!!! heading 5
                     \n!!!!!! heading 6"""
        expected = """= heading 1 =
                     \n== heading 2 ==
                     \n=== heading 3 ===
                     \n==== heading 4 ====
                     \n===== heading 5 =====
                     \n====== heading 6 ======"""
        eq_(expected, converter.convert(content))

    def test_underline(self):
        content = '===underlined text==='
        eq_('<u>underlined text</u>', converter.convert(content))

    def test_horizontal_line_3(self):
        # 4 dashes stays the same
        content = 'Some text\n----\nmore text'
        eq_('Some text\n----\nmore text', converter.convert(content))
        # 3 dashes are turned into 4
        content = 'Some text\n---\nmore text'
        eq_('Some text\n----\nmore text', converter.convert(content))

    def test_code(self):
        content = '{CODE()}\nthis is code\n{CODE}'
        eq_('<code>\nthis is code\n</code>', converter.convert(content))

    def test_remove_percents(self):
        content = '# lala  %%% line break'
        eq_('# lala  <br/> line break', converter.convert(content))

    def test_unicode(self):
        # French
        content = u'((Vous parl\u00e9 Fran\u00e7ais)). \n* Tr\u00e9s bien.'
        eq_(u'[[Vous parl\u00e9 Fran\u00e7ais]]. \n* Tr\u00e9s bien.',
            converter.convert(content))
        # Japanese
        content = u'!! \u6709\u52b9'
        eq_(u'== \u6709\u52b9 ==', converter.convert(content))

    def test_basic(self):
        """Basic functionality works."""
        content = """In [http://article.com|this article] he mentioned that
                     he found that certain proxy settings can cause a
                     ((Firefox never finishes loading certain websites))
                     condition.

                    Here's what we have now:
                    * ((Server not found)): %%% Just links to ((Firefox))
                    * ((Cannot connect after upgrading)) %%% Blah"""

        expected = """In [http://article.com this article] he mentioned that
                     he found that certain proxy settings can cause a
                     [[Firefox never finishes loading certain websites]]
                     condition.

                    Here's what we have now:
                    * [[Server not found]]: <br/> Just links to [[Firefox]]
                    * [[Cannot connect after upgrading]] <br/> Blah"""

        eq_(expected, converter.convert(content))

    def test_button_div(self):
        """Button syntax."""
        content = 'Here is a {DIV(class=button,type=span)}button text{DIV}.'
        expected = 'Here is a {button button text}.'
        eq_(expected, converter.parse(content)[0])

        content = ('Multiple {DIV(class=button,type=span)}button{DIV}. '
                   'Buttons {DIV(class=button,type=span)}!{DIV}. ')
        expected = 'Multiple {button button}. Buttons {button !}.'
        eq_(expected, converter.parse(content)[0])

    def test_showfor(self):
        """Showfor syntax."""
        content = 'Show me {DIV(class=mac,type=span)}for mac{DIV}.'
        expected = 'Show me {for mac}for mac{/for}.'
        eq_(expected, converter.parse(content)[0])

    def test_showfor_aliases(self):
        """Showfor aliases for noMac, noWin, etc"""
        content = 'My {DIV (class=noMac,type=span)}some text{DIV}.'
        expected = 'My {for win,linux}some text{/for}.'
        eq_(expected, converter.parse(content)[0])
        content = '{DIV (class= noWindows , type= span)}some text{DIV}.'
        expected = '{for mac,linux}some text{/for}.'
        eq_(expected, converter.parse(content)[0])
        content = ('Click on the {DIV(class=button,type=>span)}text{DIV}'
                   '{DIV(class=noUnix,type=span)}Views{DIV} button')
        expected = 'Click on the {button text}{for win,mac}Views{/for} button'
        eq_(expected, converter.parse(content)[0])

    def test_div_nesting_crazy(self):
        """Test with some real nested {DIV}s. Real data, can you believe it?"""
        content = (
            u'Les {DIV(class=>win,type=>span)}options{DIV} '               # 1
            u'{DIV(class=>noWin,type=>span)}pr\xc3f\xc3rences{DIV} '       # 2
            u'de blocage des fenetres popup sont situ\xc3es dans le '      # 3
            u'((Fenetre des options|#content_options|panneau ''Contenu'')) '
            u'dans {DIV(class=>win,type=>span)} '                          # 5
            u'{DIV(class=>menuPath,type=>span)}Outils > Options{DIV}'      # 6
            u'{DIV}{DIV(class=>unix,type=>span)} '                         # 7
            u'{DIV(class=>menuPath,type=>span)}Edition > Pr\xc3ferences'   # 8
            u'{DIV}{DIV}{DIV(class=>mac,type=>span)} '                     # 9
            u'{DIV(class=>menuPath,type=>span)} Firefox > '                # 10
            u'Preferences{DIV}{DIV}.')                                     # 11
        expected = (
            u'Les {for win}options{/for} '                                 # 1
            u'{for mac,linux}pr\xc3f\xc3rences{/for} '                     # 2
            u'de blocage des fenetres popup sont situ\xc3es dans le '      # 3
            u'[[Fenetre des options#content_options|panneau Contenu]] '    # 4
            u'dans {for win} '                                             # 5
            u'{menu Outils > Options}'                                     # 6
            u'{/for}{for linux} '                                          # 7
            u'{menu Edition > Pr\xc3ferences}'                             # 8
            u'{/for}{for mac} '                                            # 9
            u'{menu  Firefox > Preferences}'                               # 10
            u'{/for}.')                                                    # 11

        eq_(expected, converter.parse(content)[0])

    def test_div_triple_nesting(self):
        """OMG, it's a triple rainbow!!!"""
        content = (
            u'Les {DIV(class=>win,type=>span)}options '                    # 1
            u'{DIV(class= firefox3,type=>span)}pr\xc3f\xc3rences '         # 2
            u'{DIV(type=&span,class=&button)}de blocage{DIV} woot!'        # 3
            u'{DIV}{DIV}.')                                                # 4
        expected = (
            u'Les {for win}options '                                       # 1
            u'{for fx3}pr\xc3f\xc3rences '                                 # 2
            u'{button de blocage} woot!'                                  # 3
            u'{/for}{/for}.')                                              # 4

        eq_(expected, converter.parse(content)[0])

    def test_key_multi_class(self):
        """Multiple classes on a div."""
        content = '{DIV(type=span,class=kbd noMac)}Ctrl{DIV}'
        expected = '{for win,linux}{key Ctrl}{/for}'

        eq_(expected, converter.parse(content)[0])

    def test_tag_kbd(self):
        """kbd tag works."""
        content = '{TAG(tag=kbd)}Ctrl{TAG}'
        expected = '{key Ctrl}'
        eq_(expected, converter.parse(content)[0])

    def test_tag_strike(self):
        """strike tag works."""
        content = 'And {TAG(tag=strike)}one, two three... out{TAG}!'
        expected = 'And <s>one, two three... out</s>!'
        eq_(expected, converter.parse(content)[0])

    def test_div_tag_mixed(self):
        """{TAG} and {DIV} mixed."""
        content = ('Some {DIV(type=span,class=noMac)} text'
                   ' {TAG(tag=kbd)}here{TAG} goes{DIV}.')
        expected = 'Some {for win,linux} text {key here} goes{/for}.'
        eq_(expected, converter.parse(content)[0])

    def test_div_no_class_or_type(self):
        """{DIV()}...{DIV}."""
        content = '{DIV()}a div{DIV}'
        expected = '<div>a div</div>'
        eq_(expected, converter.parse(content)[0])
        content = '{DIV()}a {DIV()}nested{DIV} div{DIV}'
        expected = '<div>a <div>nested</div> div</div>'
        eq_(expected, converter.parse(content)[0])

    def test_showfor_spans(self):
        """{SHOWFOR(spans=on)/} is skipped."""
        content = '{SHOWFOR(spans=on)/}'
        expected = ''

        eq_(expected, converter.parse(content)[0])

    def test_showfor_browser(self):
        """{SHOWFOR(browser=...)}."""
        content = ('So {SHOWFOR(browser=firefox3)}3.0 me{SHOWFOR}'
                   ' and then {SHOWFOR(browser=ff4}4.0 me{SHOWFOR}!')
        expected = ('So \n{for fx3}\n3.0 me\n{/for}\n and then \n{for fx4}\n'
                    '4.0 me\n{/for}\n!')

        eq_(expected, converter.parse(content)[0])

    def test_showfor_browser_nested(self):
        """Unrealistic showfor browser test."""
        content = ('So {SHOWFOR(browser=firefox3+ff4)}3.0 me'
                   ' and {SHOWFOR(browser=ff4}4.0 me{SHOWFOR}!{SHOWFOR}!')
        expected = ('So \n{for fx4,fx3}\n3.0 me and \n{for fx4}\n4.0 me'
                    '\n{/for}\n!\n{/for}\n!')

        eq_(expected, converter.parse(content)[0])

    def test_showfor_os(self):
        """{SHOWFOR(os=...)}."""
        content = ('So \n{SHOWFOR(os=unix)}\nunixify\n{SHOWFOR}\n'
                   ' ! and {SHOWFOR(os=windows}win{SHOWFOR}!')
        expected = ('So \n{for linux}\nunixify\n{/for}\n ! and '
                    '\n{for win}\nwin\n{/for}\n!')

        eq_(expected, converter.parse(content)[0])

    def test_showfor_mixed(self):
        """Mix showfors desperately."""
        content = ('So {SHOWFOR(os=unix+mac)}unixify '
                   'on {SHOWFOR(browser=firefox4}4.0 '
                   '{SHOWFOR(os=mac)}mac only{SHOWFOR} or '
                   '{SHOWFOR(os=linux)}linux only{SHOWFOR}...{SHOWFOR}'
                   ',,,{SHOWFOR}!')
        expected = ('So \n{for mac,linux}\nunixify on \n{for fx4}\n4.0 '
                    '\n{for mac}\nmac only\n{/for}\n or \n{for linux}'
                    '\nlinux only\n{/for}\n...\n{/for}\n,,,\n{/for}\n!')

        eq_(expected, converter.parse(content)[0])

    def test_showfor_fx2(self):
        """Firefox 2 is removed from showfor."""
        content = ('So {SHOWFOR(browser=firefox3+ff2)}not removed'
                   '{SHOWFOR(browser=ff2)}removed{SHOWFOR}!{SHOWFOR}!')
        expected = 'So \n{for fx3}\nnot removed!\n{/for}\n!'
        eq_(expected, converter.parse(content)[0])
        content = ('So {SHOWFOR(browser=firefox2)}removed{SHOWFOR}'
                   '{SHOWFOR(browser=ff3)}not removed!{SHOWFOR}!')
        expected = 'So \n{for fx3}\nnot removed!\n{/for}\n!'
        eq_(expected, converter.parse(content)[0])

    def test_div_fx2(self):
        content = 'Show me {DIV(class=fx2,type=span)}for mac{DIV}.'
        expected = 'Show me .'
        eq_(expected, converter.parse(content)[0])

    def test_menu(self):
        """{MENU()}...{MENU}."""
        content = '{MENU()}File > new{MENU}'
        expected = '{menu File > new}'
        eq_(expected, converter.parse(content)[0])

    def test_path(self):
        """{PATH()}...{PATH}."""
        content = '{PATH()}File > new{PATH}'
        expected = '{menu File > new}'
        eq_(expected, converter.parse(content)[0])

    def test_pref(self):
        """{PREF()}...{PREF}."""
        content = '{PREF()}general.useragent.security{PREF}'
        expected = '{pref general.useragent.security}'
        eq_(expected, converter.parse(content)[0])

    def test_file(self):
        """{FILE)}...{FILE}."""
        content = '{FILE()}File > new{FILE}'
        expected = '{filepath File > new}'
        eq_(expected, converter.parse(content)[0])

    def test_hs(self):
        """~hs~."""
        content = '~hs~Some tex~hs~t here'
        expected = '&nbsp;Some tex&nbsp;t here'
        eq_(expected, converter.parse(content)[0])

    def test_span_color(self):
        """__~~#123456:Good~~__."""
        content = '__~~#123456:Good~~__'
        expected = """'''<span style="color:#123456">Good</span>'''"""
        eq_(expected, converter.parse(content)[0])

    def test_unicode_grrr(self):
        """~123~"""
        content_expected = ((u'~123~', u'{'),
                            (u'~5229~', u'\u146d'),
                            (u'~99999999~', u'~99999999~'))
        for content, expected in content_expected:
            eq_(expected, converter.parse(content)[0])

    def test_np(self):
        """~np~...~/np~."""
        # Note: this is, strictly speaking, incorrect.
        content = "~np~__Don't process this__~/np~"
        expected = "<nowiki>'''Don't process this'''</nowiki>"
        eq_(expected, converter.parse(content)[0])

    def test_hc(self):
        """~hc~...~/hc~."""
        content = "~hc~__This is a comment__~/hc~"
        expected = "<!--'''This is a comment'''-->"
        eq_(expected, converter.parse(content)[0])

    def test_tc(self):
        """~tc~...~/tc~."""
        content = "~tc~__This is a comment__~/tc~"
        expected = "<!--'''This is a comment'''-->"
        eq_(expected, converter.parse(content)[0])

    def test_img_simple(self):
        """Simple {img src=".."}"""
        content = '{img src="img/wiki_up/Fx3exeBlocked.png"}'
        expected = '[[Image:Fx3exeBlocked.png]]'
        eq_(expected, converter.parse(content)[0])

    def test_img_imalign(self):
        """Image with alignment."""
        # TODO: check tikiwiki image syntax for other values and params
        content = '{img src="img/wiki_up/vista.jpg" vertical-imalign=middle}'
        expected = '[[Image:vista.jpg|valign=middle]]'
        eq_(expected, converter.parse(content)[0])

    def test_img_external(self):
        """Image linking to external site."""
        content = ('{img src="http://test.com/vista.jpg" '
                   'vertical-imalign=middle}')
        expected = ('<img src="http://test.com/vista.jpg" '
                    'style="vertical-align: middle">')
        eq_(expected, converter.parse(content)[0])

    def test_img_various(self):
        """Various ways of messing with the syntax for {img ...}"""
        content = '{img &quot;src /img/wiki_up/Fx3exeBlocked.png"}'
        expected = '[[Image:Fx3exeBlocked.png]]'
        eq_(expected, converter.parse(content)[0])

        content = '{img src=/img/wiki_up/Fx3exeBlocked.png}'
        expected = '[[Image:Fx3exeBlocked.png]]'
        eq_(expected, converter.parse(content)[0])

        content = '{img src=img/wiki_up/Fx3exeBlocked.png}'
        expected = '[[Image:Fx3exeBlocked.png]]'
        eq_(expected, converter.parse(content)[0])

    def test_redirect(self):
        """Redirect {REDIRECT(page=Some page)/}"""
        content = '{REDIRECT(page=Remembering passwords)/}'
        expected = REDIRECT_CONTENT % 'Remembering passwords'
        eq_(expected, converter.parse(content)[0])

    def test_remove_aname(self):
        """ANAME and contents are replaced with whitespace."""
        content = '{ANAME ( )}remove{ ANAME } this not {ANAME ( )}again{ANAME}'
        expected = 'this not'
        eq_(expected, converter.parse(content)[0])

    def test_warning_nest(self):
        """Warning system when parsing."""
        content = '{TAG(tag=zzz)}{TAG(tag=zzz)}haha{TAG}{TAG}'
        expected = '{key {key haha}}'
        received = converter.parse(content)
        eq_(expected, received[0])
        assert 'Unrecognized tag (zzz).' in received[1], (
               'Received: %s' % received[1])
        assert "Can't nest tag." in received[1], (
               'Received: %s' % received[1])

    def test_warning_selfclosing(self):
        content = '{DIV(class=button menu,type=>span)}some text{DIV}'
        expected = '{button {menu some text}}'
        received = converter.parse(content)
        eq_(expected, received[0])
        found = ('Found two or more self-closing classes in the same {DIV} '
                 '(button menu).')
        assert found in received[1], '"%s" not in "%s"' % (found, received[1])

    def test_maketoc_to_toc(self):
        """{maketoc} is converted and surrounding whitespace is stripped."""
        content = 'some text\n\n {maketoc} \n more text'
        expected = 'some text\n__TOC__\n more text'
        eq_(expected, converter.convert(content))

    def test_dynvars_remove(self):
        """{DYNVARS()/} goes away."""
        content = ('{DYNVARS()/}', '{DYNVARS}', '{DYNVARS()}', '{DYNVARS/}',
                   '{DYNVARS(}')
        expected = ' '
        for c in content:
            eq_(expected, converter.convert(c))
        content = '{DYNVARS()}text{DYNVARS}'
        eq_(' text ', converter.convert(content))

    def test_note_hat(self):
        """The hat (^) turns into {note}."""
        content = '^__bold__^'
        expected = "{note}'''bold'''{/note}"
        eq_(expected, converter.parse(content)[0])

    def test_note_hat_multiple(self):
        """Multiple hats (^) turns into multiple {note}s properly."""
        content = '^__bold__\n some^ and \n^ a \n{TAG(tag=kbd)}key{TAG}\n^'
        expected = ("{note}'''bold'''\n some{/note} and \n{note} a \n"
                    '{key key}\n{/note}')
        eq_(expected, converter.parse(content)[0])

        content = '\n^ \n __bold__ \n ^ and a lonely hat ^'
        expected = "{note} \n '''bold''' \n {/note} and a lonely hat ^"
        eq_(expected, converter.parse(content)[0])

    def test_module_remove(self):
        """{MODULE()/} goes away."""
        raise SkipTest

    def test_listprogress_remove(self):
        """{LISTPROGRESS()/} goes away."""
        raise SkipTest

    def test_pagelist_remove(self):
        """{PAGELIST()/} goes away."""
        raise SkipTest

    def test_tag_sup(self):
        """{TAG(tag=>sup)}what's up?{TAG}."""
        content = '{TAG(tag=sup)}yo dawg{TAG}'
        expected = '<sup>yo dawg</sup>'
        eq_(expected, converter.parse(content)[0])

    def test_content_template_label(self):
        """{content label=b}."""
        content = '{content label=optionspreferences}'
        expected = '[[T:optionspreferences]]'
        eq_(expected, converter.parse(content)[0])

    def test_content_template_id(self):
        """{content id=1}."""
        content = '{content id=467}'
        expected = '[[T:closeFirefox]]'
        eq_(expected, converter.parse(content)[0])

    def test_content_template_idlabel(self):
        """{content idlabel=1b}."""
        content = '{content idlabel=2optionspreferences}'
        expected = '[[T:optionspreferences]]'
        eq_(expected, converter.parse(content)[0])

    def test_screencast(self):
        """{SCREENCAST (file=>some-file-hash)}{SCREENCAST}"""
        content = '{SCREENCAST (file=>file-1234-123) }{SCREENCAST}'
        expected = '[[Video:file-1234-123]]'
        eq_(expected, converter.parse(content)[0])

    def test_special_nbsping(self):
        """NBSP left-double-arrow, right-double-arrow, and ?"""
        content = u'Some\u00ab text \u00bb ?'
        expected = u'Some\u00ab&nbsp;text&nbsp;\u00bb&nbsp;?'
        eq_(expected, converter.convert(content))

    def test_screencast_grabs(self):
        """SCREENCAST should work inline with other closing tags, etc."""
        content = ('{DIV(class=win,type=span)}'
                   '{SCREENCAST(file=>123)}{SCREENCAST}{DIV}'
                   '{DIV(class=button,type=>span)}Yes{DIV} go!')
        expected = u'{for win}[[Video:123]]{/for}{button Yes} go!'
        eq_(expected, converter.parse(content)[0])
