# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import pywikibot

from pywikibot import pagegenerators, textlib
from pywikibot.bot import SingleSiteBot, SkipPageError

from .typoloader import TypoRule, TyposLoader


class TypoReportBot(SingleSiteBot):

    def __init__(self, **kwargs):
        self.availableOptions.update({
            'always': True,
            'anything': False,
            'outputpage': None,  # todo: mandatory
            'typospage': None,
            'whitelistpage': None,
        })
        super(TypoReportBot, self).__init__(**kwargs)

    def setup(self):
        loader = TyposLoader(
            self.site, allrules=True, typospage=self.getOption('typospage'),
            whitelistpage=self.getOption('whitelistpage'))
        self.typoRules = loader.loadTypos()
        self.fp_page = loader.getWhitelistPage()
        self.whitelist = loader.loadWhitelist()
        self.data = []

    @property
    def generator(self):
        return pagegenerators.PreloadingGenerator(self._generator())

    def _generator(self):
        for rule in self.typoRules:
            if not rule.canSearch():
                continue

            pywikibot.output('Query: "%s"' % rule.query)
            self.current_rule = rule
            for page in rule.querySearch():
                yield page

    def init_page(self, page):
        # fixme: this is deprecated
        if page.title() in self.whitelist:
            raise SkipPageError(page, 'Page is whitelisted')

        if self.current_rule.find.search(page.title()):
            raise SkipPageError(page, 'Rule matches title')

        super(TypoReportBot, self).init_page(page)

    def treat(self, page):
        text = textlib.removeDisabledParts(
            page.text, TypoRule.exceptions, site=self.site)
        match = self.current_rule.find.search(text)
        if match:
            text = '# {} - {}'.format(page.title(as_link=True), match.group(0))
            pywikibot.stdout(text)
            self.data.append(text)

    def teardown(self):
        if self._generator_completed or self.getOption('anything'):
            page = pywikibot.Page(self.site, self.getOption('outputpage'))
            page.put('\n'.join(self.data), minor=False, cc=False,
                     summary='aktualizace seznamu překlepů')
        super(TypoReportBot, self).teardown()


def main(*args):
    options = {}
    for arg in pywikibot.handle_args(args):
        if arg.startswith('-'):
            arg, sep, value = arg.partition(':')
            if value != '':
                options[arg[1:]] = int(value) if value.isdigit() else value
            else:
                options[arg[1:]] = True

    bot = TypoReportBot(**options)
    bot.run()


if __name__ == '__main__':
    main()
