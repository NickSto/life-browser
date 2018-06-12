#!/usr/bin/env python3
import argparse
import logging
import re
import sys
import urllib.parse
import html5lib
from drivers.hangouts import hangouts
from drivers.voice import voice
from drivers.voice.gvoiceParser import gvParserLib
assert sys.version_info.major >= 3, 'Python 3 required'

KNOWN_TLDS = ('com', 'org', 'net', 'edu', 'gov', 'uk', 'co')
DESCRIPTION = """Extract all links from Hangouts conversations.
This finds all urls sent in Hangouts messages that Google recognized, and prints them
(one per line)."""


def make_argparser():
  parser = argparse.ArgumentParser(description=DESCRIPTION)
  parser.add_argument('archive',
    help='The Hangouts Takeout file.')
  parser.add_argument('-v', '--voice', dest='format', action='store_const', const='voice',
    default='hangouts',
    help='The archive file is from Google Voice.')
  parser.add_argument('-a', '--attachments', action='store_true',
    help='Extract urls of images sent in Hangouts messages instead of links in the text.')
  parser.add_argument('-t', '--thumbs', action='store_true',
    help='For videos, print the url to the thumbnail image instead of to the video, since the '
         'video url requires a login and can\'t easily be automatically retrieved.')
  parser.add_argument('-b', '--both', action='store_true',
    help='For videos, print both the url to the video and the url to the thumbnail.')
  parser.add_argument('-l', '--log', type=argparse.FileType('w'), default=sys.stderr,
    help='Print log messages to this file instead of to stderr. Warning: Will overwrite the file.')
  volume = parser.add_mutually_exclusive_group()
  volume.add_argument('-q', '--quiet', dest='volume', action='store_const', const=logging.CRITICAL,
    default=logging.WARNING)
  volume.add_argument('-V', '--verbose', dest='volume', action='store_const', const=logging.INFO)
  volume.add_argument('-D', '--debug', dest='volume', action='store_const', const=logging.DEBUG)
  return parser


def main(argv):

  parser = make_argparser()
  args = parser.parse_args(argv[1:])

  logging.basicConfig(stream=args.log, level=args.volume, format='%(message)s')

  if args.both:
    incl_vid_urls = True
    incl_thumb_urls = True
  elif args.thumbs:
    incl_vid_urls = False
    incl_thumb_urls = True
  else:
    incl_vid_urls = True
    incl_thumb_urls = False

  if args.format == 'voice' and args.attachments:
    fail('Error: Cannot use both --voice and --attachments.')

  for link in parse_archive(args.archive, args.format, attachments=args.attachments,
                            incl_video=incl_vid_urls, incl_thumbs=incl_thumb_urls):
    print(link)


def parse_archive(archive_path, format, **kwargs):
  if format == 'hangouts':
    return parse_hangouts(archive_path, **kwargs)
  elif format == 'voice':
    return parse_voice(archive_path, **kwargs)


def parse_hangouts(archive_path, attachments=False, incl_video=True, incl_thumbs=False, **kwargs):
  data = hangouts.extract_data(archive_path)
  if data is None:
    fail('No Hangouts data found!')
  convos = hangouts.read_hangouts(data)
  for convo in convos:
    for event in convo.events:
      if attachments:
        for attachment in event.attachments:
          if attachment.type == 'video':
            if incl_video:
              yield attachment.video
            if incl_thumbs:
              yield attachment.image
          elif attachment.type == 'image':
            yield attachment.image
      else:
        for link in event.links:
          yield link


def parse_voice(archive_path, **kwargs):
  archive = voice.Archive(archive_path)
  for raw_record in archive:
    tree = html5lib.parse(raw_record.contents)
    convo = gvParserLib.Parser.process_tree(tree, raw_record.filename, ())
    try:
      for message in convo:
        text = message.text
        if is_url(text):
          yield text
    except TypeError:
      pass


def is_url(possible_url):
  if not (possible_url.startswith('http://') or possible_url.startswith('https://')):
    possible_url = 'http://'+possible_url
  urlparts = urllib.parse(possible_url)
  domain = urlparts.netloc
  # Are there invalid characters in the "domain" name?
  valid_domain = re.sub(r'[^0-9a-zA-Z.-]', '', domain)
  if len(domain) > len(valid_domain):
    return False
  # If it's a valid domain name and has a path, too, it's probably a url.
  if urlparts.path:
    return True
  else:
    tld = domain.split('.')[-1]
    if tld in KNOWN_TLDS:
      return True
  return False


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
