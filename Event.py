
OPTIONALS = ('lat', 'long', 'accuracy', 'subtype', 'sender', 'recipients', 'message', 'raw')

class Event(object):

  def __init__(self, type, timestamp, **optionals):
    self.type = type
    self.timestamp = timestamp
    for optional in OPTIONALS:
      setattr(self, optional, optionals.get(optional))


def make_events(driver, paths, **kwargs):
  for event in driver.get_events(paths, **kwargs):
    optionals = {}
    for optional in OPTIONALS:
      optionals[optional] = event.get(optional)
    yield Event(event['type'], event['timestamp'], **optionals)
