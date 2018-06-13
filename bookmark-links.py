#!/usr/bin/env python3
import argparse
import logging
import re
import sys
from utillib import pinboard
assert sys.version_info.major >= 3, 'Python 3 required'

DESCRIPTION = """"""


def make_argparser():
  parser = argparse.ArgumentParser(description=DESCRIPTION)
  parser.add_argument('links', type=argparse.FileType('r'), default=sys.stdin, nargs='?',
    help='The file containing the urls to bookmark. Will read from stdin by default.')
  parser.add_argument('-m', '--metadata', metavar='meta.tsv', type=argparse.FileType('r'),
    help='The metadata file output by dl-media.py. If provided, this script will not bookmark '
         'links already saved as image files.')
  parser.add_argument('-a', '--auth-token',
    help='Your Pinboard API authentication token. Required if not using --simulate. If simulating, '
         'providing it will allow simulating every step except saving the bookmark. Available from '
         'https://pinboard.in/settings/password')
  parser.add_argument('-t', '--tags', default='automated,messaged',
    help='The tags to save the bookmark(s) with. Use a comma-delimited list. Default: "%(default)s"')
  parser.add_argument('-d', '--save-dead-links', dest='skip_dead_links', action='store_false',
    default=True,
    help="Don't bookmark urls which return an error HTTP status.")
  parser.add_argument('-A', '--user-agent',
    default='Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:60.0) Gecko/20100101 Firefox/60.0',
    help='User agent to give when making requests to the urls. Default: "%(default)s"')
  parser.add_argument('-n', '--simulate', action='store_true',
    help='Only simulate the process, printing the tabs which will be archived but without actually '
         'doing it.')
  parser.add_argument('-l', '--log', type=argparse.FileType('w'), default=sys.stderr,
    help='Print log messages to this file instead of to stderr. Warning: Will overwrite the file.')
  volume = parser.add_mutually_exclusive_group()
  volume.add_argument('-q', '--quiet', dest='volume', action='store_const', const=logging.CRITICAL,
    default=logging.WARNING)
  volume.add_argument('-v', '--verbose', dest='volume', action='store_const', const=logging.INFO)
  volume.add_argument('-D', '--debug', dest='volume', action='store_const', const=logging.DEBUG)
  return parser


def main(argv):

  parser = make_argparser()
  args = parser.parse_args(argv[1:])

  logging.basicConfig(stream=args.log, level=args.volume, format='%(message)s')

  if args.metadata:
    image_urls = get_image_urls(args.metadata)
  else:
    image_urls = set()

  if not (args.auth_token or args.simulate):
    fail('Error: --auth-token is required if not simulating (-n).')

  filtered_urls = filter_urls(args.links, image_urls)

  pinboard.save_bookmarks(filtered_urls, args.auth_token, tags=args.tags.split(','),
                          simulate=args.simulate, skip_dead_links=args.skip_dead_links,
                          user_agent=args.user_agent)


def filter_urls(raw_urls, image_urls):
  for line in raw_urls:
    url = line.rstrip('\r\n')
    url = fix_url(url)
    if url is None:
      continue
    if url in image_urls:
      logging.info('url already saved as image: {}'.format(url))
      continue
    yield url


def fix_url(url):
  # Does it look like an email address?
  if url.startswith('mailto:'):
    return None
  if re.search(r'[^:/]+@[a-zA-Z0-9.-]+', url):
    return None
  # Does it omit the scheme?
  if url.startswith('http://') or url.startswith('https://'):
    return url
  else:
    return 'http://'+url


def get_image_urls(metafile):
  image_urls = set()
  for line in metafile:
    fields = line.rstrip('\r\n').split('\t')
    if len(fields) != 4:
      continue
    timestamp_str, content_type, filename, url = fields
    if filename and filename != '.':
      image_urls.add(url)
  return image_urls


def fail(message):
  logging.critical(message)
  if __name__ == '__main__':
    sys.exit(1)
  else:
    raise Exception('Unrecoverable error')


if __name__ == '__main__':
  try:
    sys.exit(main(sys.argv))
  except BrokenPipeError:
    pass
