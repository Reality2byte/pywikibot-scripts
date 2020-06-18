# -*- coding: utf-8 -*-
try:
    from collections.abc import MutableMapping
except ImportError:
    from collections import MutableMapping

import pywikibot

from pywikibot import Claim, html2unicode
from pywikibot.tools import first_lower
from pywikibot.tools.chars import invisible_regex


class DataWrapper(MutableMapping):

    def __init__(self, read, write):
        self.read = read
        self.write = write
        self.update(write)

    def __getitem__(self, key):
        return self.read[key]

    def __delitem__(self, key):
        del self.read[key]
        del self.write[key]

    def __setitem__(self, key, value):
        self.read[key] = value
        self.write[key] = value

    def __iter__(self):
        return iter(self.read)

    def __len__(self):
        return len(self.read)

    def __contains__(self, key):
        return key in self.read


class WikidataCleanupToolkit(object):

    lang_map = {
        'als': 'gsw',
        'bat-smg': 'sgs',
        'be-x-old': 'be-tarask',
        'bh': 'bho',
        'commons': None,
        'de-formal': 'de',
        'es-formal': 'es',
        'fiu-vro': 'vro',
        'hu-formal': 'hu',
        'incubator': None,
        'media': None,
        'meta': 'en',
        'nl-informal': 'nl',
        'no': 'nb',
        'roa-rup': 'rup',
        'simple': 'en',
        'species': 'en',
        'sources': None,
        'wikidata': 'en',
        'wikimania': 'en',
        'zh-classical': 'lzh',
        'zh-min-nan': 'nan',
        'zh-yue': 'yue',
    }

    def __init__(self, fixes=[]):
        self.fixes = set(fixes)

    def cleanup(self, item, data=None):
        # todo: unify
        if data is not None:
            return self.cleanup_data(item, data)
        else:
            return self.cleanup_entity(item)

    def exec_fix(self, fix, *args, **kwargs):
        ret = False
        if not self.fixes or fix in self.fixes:
            handler = getattr(self, fix)
            ret = handler(*args, **kwargs)
        return ret

    def _get_terms(self, item):
        return {'labels': item.labels,
                'descriptions': item.descriptions,
                'aliases': item.aliases}

    def get_sitelinks(self, item, data=dict()):
        sitelinks = {}
        for key, value in item._content.get('sitelinks', {}).items():
            sitelinks[key] = value['title']
        for key, value in data.items():
            sitelinks[key] = value['title']
        return sitelinks

    def cleanup_data(self, item, data):
        # fixme: entity type
        terms = {}
        keys = ('labels', 'descriptions', 'aliases')
        for key in keys:
            terms[key] = DataWrapper(
                getattr(item, key), data.setdefault(key, {}))
        ret = False
        ret = self.exec_fix('fix_languages', terms) or ret
        ret = self.exec_fix('deduplicate_aliases', terms) or ret
        #ret = self.exec_fix('move_alias_to_label', terms) or ret
        ret = self.exec_fix(
            'add_missing_labels',
            self.get_sitelinks(item, data.get('sitelinks', {})),
            terms['labels']
        ) or ret
        ret = self.exec_fix('cleanup_labels', terms) or ret
        ret = self.exec_fix(
            'fix_HTML',
            terms,
            item.claims,
            [], #data.setdefault('claims', [])
        ) or ret
        ret = self.exec_fix('replace_invisible', terms) or ret
        # fixme: buggy
##        ret = self.exec_fix(
##            'fix_quantities',
##            item.claims,
##            data.setdefault('claims', [])
##        ) or ret
##        ret = self.exec_fix(
##            'deduplicate_claims',
##            item.claims,
##            data.setdefault('claims', [])
##        ) or ret
        for key in keys + ('claims',):
            if not data[key]:
                data.pop(key)
        return ret

    def cleanup_entity(self, item):
        # fixme: entity type
        # fixme: sync order with cleanup_data
        terms = self._get_terms(item)
        ret = False
        ret = self.exec_fix('fix_languages', terms) or ret
        ret = self.exec_fix('fix_HTML', terms, item.claims, []) or ret
        ret = self.exec_fix('replace_invisible', terms) or ret
        ret = self.exec_fix('deduplicate_aliases', terms) or ret
        #ret = self.exec_fix('move_alias_to_label', terms) or ret
        ret = self.exec_fix(
            'add_missing_labels',
            self.get_sitelinks(item),
            terms['labels']
        ) or ret
        ret = self.exec_fix('cleanup_labels', terms) or ret
        ret = self.exec_fix('fix_quantities', item.claims, []) or ret
        ret = self.exec_fix('deduplicate_claims', item.claims, []) or ret
        return ret

    def move_alias_to_label(self, terms):  # todo: not always desired
        ret = False
        for lang, aliases in terms['aliases'].items():
            if len(aliases) == 1:
                terms['aliases'][lang] = []
                terms['labels'][lang] = aliases.pop()
                ret = True
        return ret

    def deduplicate_aliases(self, data):
        ret = False
        for lang, aliases in data['aliases'].items():
            already = set()
            label = data['labels'].get(lang)
            if label:
                already.add(label)
            for alias in aliases[:]:
                if alias in already:
                    aliases.remove(alias)
                    ret = True
                else:
                    already.add(alias)
            data['aliases'][lang] = aliases
        return ret

    @classmethod
    def normalize_lang(cls, lang):
        lang = lang.replace('_', '-')
        return cls.lang_map.get(lang, lang)

    def fix_languages(self, data):
        ret = False
        for lang, norm in self.lang_map.items():
            label = data['labels'].get(lang)
            if not label:
                continue
            if norm:
                if norm in data['labels']:
                    aliases = data['aliases'].get(norm, [])
                    if label not in map(first_lower, aliases):
                        aliases.append(label)
                        data['aliases'][norm] = aliases
                else:
                    data['labels'][norm] = label
            data['labels'][lang] = ''
            ret = True
        for lang, norm in self.lang_map.items():
            description = data['descriptions'].get(lang)
            if description:
                if norm and norm not in data['descriptions']:
                    data['descriptions'][norm] = description
                data['descriptions'][lang] = ''
                ret = True
        for lang, norm in self.lang_map.items():
            old_aliases = data['aliases'].get(lang)
            if old_aliases:
                if norm:
                    new_aliases = data['aliases'].get(norm, [])
                    already = set(map(first_lower, new_aliases))
                    if norm in data['labels']:
                        already.add(first_lower(data['labels'][norm]))
                    for alias in old_aliases:
                        if alias not in already:
                            new_aliases.append(alias)
                            already.add(alias)
                    # fixme: buggy, raises not-recognized-array
                    data['aliases'][norm] = new_aliases
                data['aliases'][lang] = []
                ret = True
        return ret

    def get_missing_labels(self, sitelinks, dont):
        labels = {}
        for dbname, title in sitelinks.items():
            if 'wikinews' in dbname:
                continue
            # [[d:Topic:Vedxkcb8ek6ss1pc]]
            if dbname.startswith('alswiki'):
                continue
            # [[d:Topic:Vhs5f72i5obvkr3t]]
            if title.startswith('Wikipedia:Artikelwerkstatt/'):
                continue
            # [[d:Topic:Vn16a76j30dblqo7]]
            if dbname == 'zh_yuewiki' and title.startswith('Portal:時人時事/'):
                continue
            if ':' not in title and '/' in title:
                continue
            # fixme: 'wikidata' -> ('', 'wiki', 'data')
            # fixme: 'mediawikiwiki' -> ('media', 'wiki', 'wiki')
            lang = self.normalize_lang(dbname.partition('wik')[0])
            if lang and lang not in dont:
                # [[d:Topic:Uhdjlv9aae6iijuc]]
                # todo: create a lib for this
                if lang == 'fr' and title.startswith(
                        ('Abbaye ', 'Cathédrale ', 'Chapelle ', 'Cloître ',
                         'Couvent ', 'Monastère ', 'Église ')):
                    title = first_lower(title)
                label = labels.get(lang)
                if label and first_lower(label) != first_lower(title):
                    labels.pop(lang)  # todo: better handling
                    dont.add(lang)
                    continue
                labels[lang] = title
        return labels

    def add_missing_labels(self, sitelinks, data):
        labels = self.get_missing_labels(sitelinks, set(data.keys()))
        data.update(labels)
        return bool(labels)

    @staticmethod
    def can_strip(part, description):
        words = {  # [[d:Topic:Uljziilm6l85hsp3]]
            'vrouwen', 'mannen', 'jongens', 'meisjes', 'enkel', 'dubbel',
            'mannenenkel', 'vrouwenenkel', 'jongensenkel', 'meisjesenkel',
            'mannendubbel', 'vrouwendubbel', 'jongensdubbel', 'meisjesdubbel',
        }
        if part[-1].isdigit() or part in words:
            return False
        if part not in description:  # todo: word to word, not just substring
            for sub in part.split(', '):
                if sub not in description:
                    return False
        return True

    def cleanup_labels(self, terms):
        ret = False
        for lang, label in terms['labels'].items():
            description = terms['descriptions'].get(lang)
            if not description:
                continue
            left, sep, right = label.rstrip(')').rpartition(' (')
            #if not sep:
            #    left, sep, right = label.partition(', ')
            if sep and not (set(left) & set('(:)')):
                if right and self.can_strip(right, description):
                    terms['labels'][lang] = left.strip()
                    ret = True
        return ret

    def fix_HTML(self, terms, claims, data):
        ret = False
        for key in ('labels', 'descriptions'):
            for lang, value in terms[key].items():
                while True:
                    new = html2unicode(value.replace('^|^', '&'))
                    if new == value:
                        break
                    terms[key][lang] = value = new
                    ret = True
        for lang, aliases in terms['aliases'].items():
            for i, value in enumerate(aliases):
                while True:
                    new = html2unicode(value.replace('^|^', '&'))
                    if new == value:
                        break
                    aliases[i] = value = new
                    ret = True
        for values in claims.values():
            for claim in values:
                if claim.type != 'monolingualtext':
                    continue
                value = claim.target.text if claim.target else None
                changed = False
                while value:
                    new = html2unicode(value.replace('^|^', '&'))
                    if value == new:
                        break
                    claim.target.text = value = new
                    changed = True
                if changed:
                    data.append(claim.toJSON())
                    ret = True
        return ret

    def replace_invisible(self, terms):
        ret = False
        double = ' ' * 2
        for key in ('labels', 'descriptions'):
            for lang, value in terms[key].items():
                new = value
                # fixme: really all of them?
                #new = invisible_regex.sub('', new)
                while double in new:
                    new = new.replace(double, ' ')
                if new != value:
                    terms[key][lang] = new
                    ret = True
        for lang, aliases in terms['aliases'].items():
            for i, value in enumerate(aliases):
                new = value
                # fixme: really all of them?
                #new = invisible_regex.sub('', new)
                while double in new:
                    new = new.replace(double, ' ')
                if new != value:
                    aliases[i] = new
                    ret = True
        return ret

    def fix_quantity(self, snak):
        if snak.type == 'quantity' and snak.snaktype == 'value':
            if snak.target.upperBound == snak.target.amount:
                snak.target.upperBound = None
                snak.target.lowerBound = None
                return True
        return False

    def iter_fixed_quantities(self, all_claims):
        for claims in all_claims.values():
            for claim in claims:
                ret = self.fix_quantity(claim)
                for snaks in claim.qualifiers.values():
                    for snak in snaks:
                        ret = self.fix_quantity(snak) or ret
                if ret:
                    yield claim

    def fix_quantities(self, claims, data):
        ret = False
        for claim in self.iter_fixed_quantities(claims):
            data.append(claim.toJSON())
            ret = True
        return ret

    def deduplicate_claims(self, claims, data):
        ret = False
        for claims_list in claims.values():
            ret = self.deduplicate_claims_list(claims_list, data) or ret
        return ret

    def deduplicate_claims_list(self, claims, data):
        stack = []
        changed = set()
        removed = set()
        for i, claim in enumerate(claims):
            remove = False
            for j, c in stack:
                if self.merge_claims(c, claim):
                    remove = True
                    changed.add(j)
                    break
            if remove:
                removed.add(i)
            else:
                stack.append((i, claim))
        for i in changed:
            data.append(claims[i].toJSON())
        for i in sorted(removed, reverse=True):
            json = claims[i].toJSON()
            json['remove'] = ''
            data.append(json)
            claims.pop(i)
        return bool(changed)

    def merge_claims(self, claim1, claim2):
        if claim1 == claim2:
            if claim1.rank != claim2.rank:
                if claim1.rank == 'normal':
                    claim1.rank = claim2.rank
                elif claim2.rank != 'normal':
                    return False
            hashes = {ref['hash'] for ref in claim1.toJSON().get(
                'references', [])}
            for ref in claim2.toJSON().get('references', []):
                if ref['hash'] not in hashes:
                    ref_copy = Claim.referenceFromJSON(claim2.repo, ref)
                    claim1.sources.append(ref_copy)
                    hashes.add(ref['hash'])
            return True
        else:
            return False
