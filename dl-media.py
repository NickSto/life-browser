#!/usr/bin/env python3
import argparse
import logging
import os
import re
import requests
import sys
import time
import urllib.parse
assert sys.version_info.major >= 3, 'Python 3 required'

IMAGE_TYPES = {'image/jpeg':'jpg', 'image/gif':'gif', 'image/png':'png', 'image/pjpeg':'jpg',
               'video/webm':'webm', 'audio/mpeg':'m4a', 'video/mp4':'mp4'}
DESCRIPTION = """Save the media referred to by a list of urls."""
EPILOG = """An HTTP request will be made to the url, and the result will be saved only if the
content-type header is one of the recognized media types: """+', '.join(IMAGE_TYPES.keys())


def make_argparser():
  parser = argparse.ArgumentParser(description=DESCRIPTION)
  parser.add_argument('links', type=argparse.FileType('r'), default=sys.stdin, nargs='?',
    help='File with the link urls, one per line. Omit to read from stdin.')
  parser.add_argument('metadata',
    help='A file storing info on which files correspond to which urls, as well as other info like '
         'the timestamp it was downloaded and the content-type returned with it. If it already '
         'exists, this will append to, not overwrite it. Images already recorded in this file will '
         'be skipped. The file is tab-delimited, with 4 columns: unix timestamp (of download), '
         'content-type header, output filename, and url. If no file was saved because the content-'
         'type indicated it wasn\'t a media file, the filename field will be empty. Also, the url '
         'field may not be exactly the same as the input url, since missing "http://" prefixes '
         'will be added.')
  parser.add_argument('outdir',
    help='Directory in which to store the image files.')
  parser.add_argument('-t', '--timeout', type=int, default=6,
    help='Timeout to wait for an HTTP response. Default: %(default)s')
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

  metadata = read_metadata(args.metadata)

  with open(args.metadata, 'a') as metafile:
    for line in args.links:
      url = fix_url(line.rstrip('\r\n'))
      if not url:
        continue
      if url in metadata:
        continue
      timestamp = int(time.time())
      image, content_type = fetch_image(url, args.timeout)
      if content_type is None:
        continue
      if image is None:
        metafile.write('{}\t{}\t{}\t{}\n'.format(timestamp, content_type, '', url))
        continue
      base, ext = make_filename_parts(url, content_type, timestamp)
      filename = make_new_filename(base, ext, args.outdir)
      path = os.path.join(args.outdir, filename)
      with open(path, 'wb') as image_file:
        image_file.write(image)
      metafile.write('{}\t{}\t{}\t{}\n'.format(timestamp, content_type, filename, url))
      metadata[url] = {'timestamp':timestamp, 'content_type':content_type, 'filename':filename}


def read_metadata(metapath):
  metadata = {}
  if not os.path.exists(metapath):
    return metadata
  with open(metapath) as metafile:
    for line in metafile:
      fields = line.rstrip('\r\n').split('\t')
      if len(fields) != 4:
        continue
      timestamp_str, content_type, filename, url = fields
      timestamp = int(timestamp_str)
      metadata[url] = {'timestamp':timestamp, 'content_type':content_type, 'filename':filename}
  return metadata


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


def fetch_image(url, timeout):
  # Note: requests handles redirects transparently (you can access them in response.history).
  try:
    response = requests.get(url, timeout=timeout, verify=False)
  except requests.exceptions.RequestException as error:
    logging.error('{}'.format(error))
    return None, None
  content_type = response.headers.get('content-type')
  if content_type in IMAGE_TYPES:
    return response.content, content_type
  else:
    logging.info('Not an image: {}..'.format(url[:60]))
    return None, content_type


def make_filename_parts(url, content_type, timestamp):
  # Take the last part of the path as the filename base.
  path = urllib.parse.urlparse(url).path
  basename = ''
  while not basename and path != '/' and path != '':
    basename = os.path.basename(path)
    path = os.path.dirname(path)
  # Remove weird characters.
  basename = re.sub(r'[^a-zA-Z0-9_.-]', '', basename)
  # Figure out the extension.
  base, ext = os.path.splitext(basename)
  if not 4 <= len(ext) <= 5:
    base = basename
    if content_type in IMAGE_TYPES:
      ext = '.'+IMAGE_TYPES[content_type]
    else:
      ext = ''
  # Truncate to 60 characters.
  base = base[:60]
  # If it's too short, add the timestamp.
  if not base:
    return str(timestamp), ext
  elif len(base) < 3:
    return base+'-'+str(timestamp), ext
  else:
    return base, ext


def make_new_filename(base, ext, outdir):
  filenames = os.listdir(outdir)
  i = 1
  filename = base+ext
  while filename in filenames:
    i += 1
    filename = '{}-{}{}'.format(base, i, ext)
  return filename


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
