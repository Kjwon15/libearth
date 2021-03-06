""":mod:`libearth.parser.rss2` --- RSS 2.0 parser
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Parsing RSS 2.0 feed.

"""
import re

try:
    import urlparse
except ImportError:
    from urllib import parse as urlparse

from ..compat.etree import fromstring
from ..feed import Category, Entry, Feed, Generator, Link
from .atom import ATOM_XMLNS_SET
from .base import ParserBase
from .rss_base import (CONTENT_XMLNS, RSSSession, content_parser,
                       datetime_parser, guess_default_tzinfo, link_parser,
                       make_legal_as_atom, person_parser, subtitle_parser,
                       text_parser)
from .util import normalize_xml_encoding


GUID_PATTERN = re.compile('^(\{{0,1}([0-9a-fA-F]){8}-([0-9a-fA-F]){4}-([0-9'
                          'a-fA-F]){4}-([0-9a-fA-F]){4}-([0-9a-fA-F]){12}\}'
                          '{0,1})$')


rss2_parser = ParserBase()


@rss2_parser.path('channel')
def parse_channel(element, session):
    return Feed(), session


@rss2_parser.path('item')
def parse_item(element, session):
    return Entry(), session


@parse_channel.path('pubDate', attr_name='updated_at')
@parse_item.path('pubDate', attr_name='published_at')
def parse_datetime(element, session):
    return datetime_parser(element, session)


@parse_channel.path('managingEditor', attr_name='contributors')
@parse_channel.path('webMaster', attr_name='contributors')
@parse_item.path('author', attr_name='authors')
def parse_person(element, session):
    return person_parser(element, session)


@parse_channel.path('category', attr_name='categories')
@parse_item.path('category', attr_name='categories')
def parse_category(element, session):
    return Category(
        term=element.text,
        scheme_uri=element.attrib.get('domain')
    ), session


@parse_channel.path('title')
@parse_channel.path('copyright', attr_name='rights')
@parse_item.path('title')
def parse_text(element, session):
    return text_parser(element, session)


@parse_channel.path('description', attr_name='subtitle')
def parse_subtitle(element, session):
    return subtitle_parser(element, session)


@parse_channel.path('link', ATOM_XMLNS_SET, attr_name='links')
def parse_atom_link(element, session):
    link = Link(uri=element.get('href'),
                relation=element.get('rel', 'alternate'),
                mimetype=element.get('type'))
    return link, session


@parse_channel.path('link', attr_name='links')
@parse_item.path('link', attr_name='links')
def parse_link(element, session):
    return link_parser(element, session)


@parse_channel.path('generator')
def parse_generator(element, session):
    generator = None
    try:
        if urlparse.urlparse(element.text).scheme in ('http', 'https'):
            generator = Generator(uri=element.text)
    except ValueError:
        pass
    return generator or Generator(value=element.text), session


@parse_item.path('enclosure', attr_name='links')
def parse_enclosure(element, session):
    return Link(
        relation='enclosure',
        mimetype=element.get('type'),
        uri=element.get('url')
    ), session


@parse_item.path('source')
def parse_source(element, session):
    from ..crawler import open_url
    from .autodiscovery import get_format
    url = element.get('url')
    f = open_url(url)  # FIXME: propagate timeout option
    xml = f.read()
    parser = get_format(xml)
    source, _ = parser(xml, url, parse_entry=False)
    return source, session


@parse_item.path('comments', attr_name='links')
def parse_comments(element, session):
    return Link(uri=element.text, relation='discussion'), session


@parse_item.path('description', attr_name='content')
@parse_item.path('encoded', [CONTENT_XMLNS], 'content')
def parse_content(element, session):
    return content_parser(element, session)


@parse_item.path('guid', attr_name='id')
def parse_guid(element, session):
    isPermalink = element.get('isPermalink')
    if element.text.startswith('http://') and isPermalink != 'False':
        return element.text, session
    elif GUID_PATTERN.match(element.text):
        return 'urn:uuid:' + element.text, session
    return None, session


def parse_rss2(xml, feed_url=None, parse_entry=True):
    """Parse RSS 2.0 XML and translate it into Atom.

    To make the feed data valid in Atom format, ``id`` and ``link[rel=self]``
    fields would become the url of the feed.

    If ``pubDate`` is not present, ``updated`` field will be from
    the latest entry's ``updated`` time, or the time it's crawled instead.

    :param xml: rss 2.0 xml string to parse
    :type xml: :class:`str`
    :param parse_item: whether to parse items (entries) as well.
                       it's useful when to ignore items when retrieve
                       ``<source>``.  :const:`True` by default
    :type parse_item: :class:`bool`
    :returns: a pair of (:class:`~libearth.feed.Feed`, crawler hint)
    :rtype: :class:`tuple`

    """
    root = fromstring(normalize_xml_encoding(xml))
    channel = root.find('channel')
    default_tzinfo = guess_default_tzinfo(root, feed_url)
    session = RSSSession(feed_url, default_tzinfo)
    feed_data = parse_channel(channel, session)
    if parse_entry:
        items = channel.findall('item')
        entry_list = []
        for item in items:
            entry_list.append(parse_item(item, session))
        feed_data.entries = entry_list
    make_legal_as_atom(feed_data, session)
    return feed_data, None
