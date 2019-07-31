# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import pywikibot
import re
import time

from operator import methodcaller

from pywikibot import pagegenerators, textlib

from pywikibot.tools.formatter import color_format


class IncompleteTypoRuleException(Exception):

    '''Exception raised when constructing a typo rule from incomplete data'''

    def __init__(self, message):
        self.message = message


class InvalidExpressionException(Exception):

    '''Exception raised when an expression has invalid syntax'''

    def __init__(self, error, aspect='regular expression'):
        self.message = error.msg
        self.aspect = aspect


class TypoRule(object):

    '''Class representing one typo rule'''

    exceptions = ['category', 'comment', 'gallery', 'header', 'hyperlink',
                  'interwiki', 'invoke', 'pre', 'property', 'source',
                  'startspace', 'template'] # todo: remove 'template' or 'startspace'
    # tags
    exceptions += ['ce', 'chem', 'code', 'graph', 'imagemap', 'mapframe',
                   'maplink', 'math', 'nowiki', 'poem', 'score', 'section',
                   'timeline']

    # todo: linktrail?
    exceptions += [
        re.compile(r'\[\[([^][|]+)(\]\]|([^][|]+\|)+)'), # 'target-part' of a wikilink
        re.compile('<[a-z]+ [^>]+>'), # HTML tag
        re.compile('„[^"“]+["“]'), # quotation marks
        re.compile(r"((?<!\w)\"|(?<!')'')(?:(?!\1)[^\n])+\1", re.U), # italics
        re.compile(r'\b[A-Za-z]+\.[a-z]{2}'), # url fragment
    ]

    nowikiR = re.compile('</?nowiki>')

    def __init__(self, find, replacements, site, auto=False, query=None):
        self.find = find
        self.replacements = replacements
        self.site = site
        self.auto = auto
        self.query = query
        self.longest = 0

    def __eq__(self, other):
        if isinstance(other, self.__class__):
            return self.id == other.id
        else:
            return False

    def __ne__(self, other):
        return not self.__eq__(other)

## TODO
##    def __repr__(self):
##        pass

    def needs_decision(self):
        return not self.auto or len(self.replacements) > 1

    def canSearch(self):
        return self.query is not None

    def querySearch(self):
        # todo: remove
        return pagegenerators.SearchPageGenerator(
            self.query, namespaces=[0], site=self.site)

    @classmethod
    def newFromParameters(cls, parameters, site):
        if '1' not in parameters:
            raise IncompleteTypoRuleException('Missing find expression')

        find = cls.nowikiR.sub('', parameters['1'])
        try:
            find = re.compile(find, re.U | re.M)
        except re.error as exc:
            raise InvalidExpressionException(exc)

        replacements = []
        for key in '23456':
            if key in parameters:
                replacement = re.sub(r'\$([1-9])', r'\\\1', cls.nowikiR.sub(
                    '', parameters[key]))
                replacements.append(replacement)

        if len(replacements) == 0:
            raise IncompleteTypoRuleException('No replacements found')

        query = None
        if parameters.get('hledat'):
            part = parameters['hledat'].replace('{{!}}', '|')
            if parameters.get('insource') == 'ne':
                query = part
            else:
                try:
                    re.compile(part)
                    query = 'insource:/%s/i' % part
                except re.error as exc:
                    raise InvalidExpressionException(exc, 'query')

        auto = parameters.get('auto') == 'ano'

        return cls(find, replacements, site, auto, query)

    def summary_hook(self, match, replaced):
        def underscores(string):
            if string.startswith(' '):
                string = '_' + string[1:]
            if string.endswith(' '):
                string = string[:-1] + '_'
            return string

        new = old = match.group()
        if self.needs_decision():
            options = [('keep', 'k')]
            replacements = []
            for i, repl in enumerate(self.replacements, start=1):
                replacement = match.expand(repl)
                replacements.append(replacement)
                options.append(
                    ('%s %s' % (i, underscores(replacement)), str(i))
                )
            text = match.string
            pre = text[max(0, match.start() - 30):match.start()].rpartition('\n')[2]
            post = text[match.end():match.end() + 30].partition('\n')[0]
            pywikibot.output(color_format('{0}{lightred}{1}{default}{2}',
                                          pre, old, post))
            choice = pywikibot.input_choice('Choose the best replacement',
                                            options, automatic_quit=False,
                                            default='k')
            if choice != 'k':
                new = replacements[int(choice) - 1]
        else:
            new = match.expand(self.replacements[0])
            if old == new:
                pywikibot.warning('No replacement done in string "%s"' % old)

        if old != new:
            fragment = ' → '.join(underscores(re.sub('\n', r'\\n', i))
                                  for i in (old, new))
            if fragment.lower() not in map(methodcaller('lower'), replaced):
                replaced.append(fragment)
        return new

    def apply(self, text, replaced=[]):
        hook = lambda match: self.summary_hook(match, replaced)
        start = time.clock()
        text = textlib.replaceExcept(
            text, self.find, hook, self.exceptions, site=self.site)
        finish = time.clock()
        delta = finish - start
        self.longest = max(delta, self.longest)
        if delta > 5:
            pywikibot.warning('Slow typo rule "%s" (%f)' % (
                self.find.pattern, delta))
        return text


class TyposLoader(object):

    top_id = 0

    '''Class loading and holding typo rules'''

    def __init__(self, site, allrules=False, typospage=None, whitelistpage=None):
        self.site = site
        self.load_all = allrules
        self.typos_page_name = typospage
        self.whitelist_page_name = whitelistpage

    def getWhitelistPage(self):
        if self.whitelist_page_name is None:
            self.whitelist_page_name = 'Wikipedie:WPCleaner/Typo/False'

        return pywikibot.Page(self.site, self.whitelist_page_name)

    def loadTypos(self):
        pywikibot.output('Loading typo rules')
        self.typoRules = []

        if self.typos_page_name is None:
            self.typos_page_name = 'Wikipedie:WPCleaner/Typo'
        typos_page = pywikibot.Page(self.site, self.typos_page_name)
        if not typos_page.exists():
            # todo: feedback
            return

        text = textlib.removeDisabledParts(
            typos_page.text, include=['nowiki'], site=self.site)
        load_all = self.load_all is True
        for template, fielddict in textlib.extract_templates_and_params(
                text, remove_disabled_parts=False, strip=False):
            if template.lower() == 'typo':
                try:
                    rule = TypoRule.newFromParameters(fielddict, self.site)
                except IncompleteTypoRuleException as exc:
                    pywikibot.warning(exc.message)  # pwb.exception?
                except InvalidExpressionException as exc:
                    if 'fixed-width' not in exc.message:
                        pywikibot.warning('Invalid %s %s: %s' % (
                            exc.aspect, fielddict['1'], exc.message))
                else:
                    rule.id = self.top_id
                    self.top_id += 1
                    if load_all or not rule.needs_decision():
                        self.typoRules.append(rule)

        pywikibot.output('%d typo rules loaded' % len(self.typoRules))
        return self.typoRules

    def loadWhitelist(self):
        self.whitelist = []
        self.fp_page = self.getWhitelistPage()
        if self.fp_page.exists():
            content = self.fp_page.get()
            for match in re.finditer(r'\[\[([^]|]+)\]\]', content):
                self.whitelist.append(match.group(1).strip())
        return self.whitelist
