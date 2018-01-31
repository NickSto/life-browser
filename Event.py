
OPTIONALS = ('lat', 'long', 'accuracy', 'sender', 'recipients', 'message', 'raw')

class Event(object):

  #TODO: Replace timestamp with "start" and "end".
  def __init__(self, stream, format, timestamp, **optionals):
    # stream: SMS, Calls, Chats, Location, etc
    # format: Hangouts, Voice, MyTracks, Geo Tracker, etc
    self.stream = stream
    self.format = format
    self.timestamp = timestamp
    for optional in OPTIONALS:
      setattr(self, optional, optionals.get(optional))


def make_events(driver, paths, **kwargs):
  for event in driver.get_events(paths, **kwargs):
    optionals = {}
    for optional in OPTIONALS:
      optionals[optional] = event.get(optional)
    yield Event(event['stream'], event['format'], event['timestamp'], **optionals)
