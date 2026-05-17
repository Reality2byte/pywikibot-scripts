#!/usr/bin/python
import re

import pywikibot

from pywikibot import pagegenerators
from pywikibot.exceptions import NoPageError

from error_reporting import ErrorReportingBot
from query_store import QueryStore
from wikidata import WikidataEntityBot


class DisambigsCheckingBot(WikidataEntityBot, ErrorReportingBot):

    disambig_items = {'Q4167410', 'Q22808320', 'Q61996773'}
    file_name = 'log_disambigs.txt'
    page_pattern = 'User:%s/Disambig_errors'
    skip = {
        'brwiki',
        'enwiki',
        'hakwiki',
        'igwiki',
        'mkwiki',
        'mznwiki',
        'specieswiki',
        'towiki',
    }
    _skip_patterns = [
        ('bswiki', '%s (čvor)'),
        ('cawiki', '%s (desambiguació)'),
        ('cswiki', '%s (rozcestník)'),
        ('dewiki', '%s (Begriffsklärung)'),
        ('enwiki', '%s (disambiguation)'),
        ('eowiki', '%s (apartigilo)'),
        ('eswiki', '%s (desambiguación)'),
        ('euwiki', '%s (argipena)'),
        ('fawiki', '%s (ابهام‌زدایی)'),
        ('fiwiki', '%s (täsmennyssivu)'),
        ('frwiki', '%s (homonymie)'),
        ('hrwiki', '%s (razdvojba)'),
        ('huwiki', '%s (egyértelműsítő lap)'),
        ('iawiki', '%s (disambiguation)'),
        ('idwiki', '%s (disambiguasi)'),
        ('itwiki', '%s (disambigua)'),
        ('jvwiki', '%s (disambiguasi)'),
        ('kkwiki', '%s (айрық)'),
        ('kowiki', '%s (동음이의)'),
        ('ltwiki', '%s (reikšmės)'),
        ('nlwiki', '%s (doorverwijspagina)'),
        ('nowiki', '%s (andre betydninger)'),
        ('nowiki', '%s (peker)'),
        ('plwiki', '%s (ujednoznacznienie)'),
        ('ptwiki', '%s (desambiguação)'),
        ('rowiki', '%s (dezambiguizare)'),
        ('ruwiki', '%s (значения)'),
        ('shwiki', '%s (razvrstavanje)'),
        ('skwiki', '%s (rozlišovacia stránka)'),
        ('slwiki', '%s (razločitev)'),
        ('srwiki', '%s (вишезначна одредница)'),
        ('svwiki', '%s (olika betydelser)'),
        ('ukwiki', '%s (значення)'),
    ]
    use_from_page = False

    def __init__(self, generator=None, **kwargs):
        self.available_options.update({
            'limit': 1000,
            'min_sitelinks': 1,
            'offset': 0,
            #'only': None, todo
        })
        super().__init__(**kwargs)
        self.store = QueryStore()
        self.generator = pagegenerators.PreloadingEntityGenerator(
            generator or self.custom_generator()
        )
        self.skip_patterns = {
            dbname: re.escape(pattern).replace('%s', '.+', 1)
            for key, pattern in cls._skip_patterns
        }

    def custom_generator(self):
        query = self.store.build_query(
            'disambiguations',
            classes=' '.join(f'wd:{item}' for item in self.disambig_items),
            **self.opt
        )
        return pagegenerators.WikidataSPARQLPageGenerator(
            query, site=self.repo, result_type=list)

    def skip_page(self, item):
        if super().skip_page(item):
            return True

        title = item.title(as_link=True, insite=self.repo)
        return f'* [[{title}]]' in self.log_page.text \
               or not self.is_disambig(item)

    def is_disambig(self, item):
        for claim in item.claims.get('P31', []):
            if any(claim.target_equals(cls) for cls in self.disambig_items):
                return True
        return False

    @classmethod
    def is_disambig_title(cls, link):
        dbname = link.site.dbName()
        title = link.canonical_title()
        return any(
            dbname == key and pattern.fullmatch(title)
            for key, pattern in cls.skip_patterns
        )

    def treat_page_and_item(self, page, item):
        the_badge = pywikibot.ItemPage(item.repo, 'Q70894304')

        append_text = ''
        count = len(item.sitelinks)
        if count == 0:
            append_text += '\n** no sitelinks'
        for dbname in item.sitelinks:
            if dbname in self.skip:
                continue

            sitelink = item.sitelinks[dbname]
            page = pywikibot.Page(sitelink)
            args = (dbname, page.title(as_link=True, insite=self.repo))

            if not page.exists():
                append_text += "\n** {} – {} – doesn't exist".format(*args)
                continue

            if page.isRedirectPage() and the_badge not in sitelink.badges:
                target = page.getRedirectTarget()
                try:
                    target_item = target.data_item()
                except NoPageError:
                    link = "''no item''"
                else:
                    link = target_item.title(as_link=True, insite=self.repo)
                if not target.isDisambig():
                    link += ', not a disambiguation'
                append_text += '\n** {} – {} – redirects to {} ({})'.format(
                    *args, target.title(as_link=True, insite=self.repo), link)
                continue

            if the_badge in sitelink.badges and not page.isRedirectPage():
                append_text += '\n** {} – {} - is not redirect despite badge'.format(*args)
                continue

            if not page.isDisambig() and not self.is_disambig_title(sitelink):
                append_text += '\n** {} – {} – not a disambiguation'.format(*args)

        if append_text:
            prep = '\n* {}'.format(item.title(as_link=True, insite=self.repo))
            if count > 0:
                prep += f' ({count} sitelink' + ('s' if count > 1 else '') + ')'
            append_text = prep + append_text
            self.append(append_text)


def main(*args):
    options = {}
    local_args = pywikibot.handle_args(args)
    site = pywikibot.Site()
    genFactory = pagegenerators.GeneratorFactory(site=site)
    for arg in genFactory.handle_args(local_args):
        if arg.startswith('-'):
            arg, sep, value = arg.partition(':')
            if value != '':
                options[arg[1:]] = value if not value.isdigit() else int(value)
            else:
                options[arg[1:]] = True

    generator = genFactory.getCombinedGenerator()

    bot = DisambigsCheckingBot(site=site, generator=generator, **options)
    bot.run()


if __name__ == '__main__':
    main()
