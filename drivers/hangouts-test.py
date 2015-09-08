#!/usr/bin/env python
from __future__ import division
import os
import sys
import json
import argparse

OPT_DEFAULTS = {}
USAGE = "%(prog)s [options]"
DESCRIPTION = """"""

def main(argv):

  parser = argparse.ArgumentParser(description=DESCRIPTION)
  parser.set_defaults(**OPT_DEFAULTS)

  parser.add_argument('input',
    help='')
  parser.add_argument('-s', '--str',
    help='default: %(default)s')

  args = parser.parse_args(argv[1:])

  with open(args.input) as infile:
    data = json.load(infile)
    check_structure(data)


def check_structure(data):
  """Check assumptions about the structure of the JSON."""
  assert type(data) is dict
  assert sorted(data.keys()) == [u'continuation_end_timestamp', u'conversation_state']
  conversation_states = data['conversation_state']
  assert type(conversation_states) is list
  for conversation_state1 in conversation_states:
    assert sorted(conversation_state1.keys()) == [u'conversation_id', u'conversation_state',
                                                 u'response_header']
    conv_id = conversation_state1['conversation_id']['id']
    conv_state = conversation_state1['conversation_state']
    assert type(conv_state) is dict
    assert sorted(conv_state.keys()) == [u'conversation', u'conversation_id', u'event']
    assert conv_state['conversation_id']['id'] == conv_id
    assert type(conv_state['conversation']) is dict
    events = conv_state['event']
    assert type(events) is list
    for event in events:
      assert type(event) is dict
      assert sorted(event.keys()) == [u'advances_sort_timestamp', u'chat_message',
                                      u'conversation_id', u'delivery_medium', u'event_id',
                                      u'event_otr', u'event_type', u'self_event_state',
                                      u'sender_id', u'timestamp']
      assert event['conversation_id']['id'] == conv_id
      # sender_id
      sender_id = event['sender_id']
      assert type(sender_id) is dict
      assert sorted(sender_id.keys()) == [u'chat_id', u'gaia_id']
      # Might have to relax this expectation, in the case that I find out what a gaia_id is.
      assert sender_id['chat_id'] == sender_id['gaia_id']
      # timestamp
      assert isinstance(event['timestamp'], basestring)
      try:
        int(event['timestamp'])
      except ValueError as ve:
        sys.stderr.write('timestamp: |{}|\n'.format(event['timestamp']))
        raise AssertionError(str(ve))
      # self_event_state
      assert type(event['self_event_state']) is dict
      keys = sorted(event['self_event_state'].keys())
      if len(keys) == 2:
        assert keys == [u'notification_level', u'user_id']
      else:
        assert keys == [u'client_generated_id', u'notification_level', u'user_id']
      # event_id
      assert isinstance(event['event_id'], basestring)
      # advances_sort_timestamp
      assert type(event['advances_sort_timestamp']) is bool
      # event_otr
      assert isinstance(event['event_otr'], basestring)
      if event['event_otr'] != 'ON_THE_RECORD':
        pass#print "event['event_otr']: "+event['event_otr']
      # delivery_medium
      delivery_medium = event['delivery_medium']
      assert type(delivery_medium) is dict
      assert sorted(delivery_medium.keys()) == [u'medium_type', u'self_phone']
      assert isinstance(delivery_medium['medium_type'], basestring)
      if delivery_medium['medium_type'] != 'GOOGLE_VOICE_MEDIUM':
        pass#print "delivery_medium['medium_type']: "+delivery_medium['medium_type']
      assert type(delivery_medium['self_phone']) is dict
      assert sorted(delivery_medium['self_phone'].keys()) == [u'e164']
      assert isinstance(delivery_medium['self_phone']['e164'], basestring)
      # chat_message
      chat_message = event['chat_message']
      assert type(chat_message) is dict
      assert sorted(chat_message.keys()) == [u'message_content']
      message_content = chat_message['message_content']
      assert type(message_content) is dict
      keys = sorted(message_content.keys())
      if len(keys) == 1:
        assert keys == [u'segment']
      else:
        assert keys == [u'attachment', u'segment']
      segments = message_content['segment']
      assert type(segments) is list
      for segment in segments:
        assert type(segment) is dict
        keys = sorted(segment.keys())
        if len(keys) == 2:
          assert keys == [u'text', u'type']
        else:
          assert keys == [u'formatting', u'text', u'type']
          # formatting
          formatting = segment['formatting']
          assert type(formatting) is dict
          assert sorted(formatting.keys()) == [u'bold', u'italics', u'strikethrough', u'underline']
          for key in ('bold', 'italics', 'strikethrough', 'underline'):
            assert type(formatting[key]) is bool
        # type
        assert isinstance(segment['type'], basestring)
        if segment['type'] != 'TEXT':
          pass#print "segment['type']: "+segment['type']
        # text
        assert isinstance(segment['text'], basestring)


def fail(message):
  sys.stderr.write(message+"\n")
  sys.exit(1)

if __name__ == '__main__':
  sys.exit(main(sys.argv))
