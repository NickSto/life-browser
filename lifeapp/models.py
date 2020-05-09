from datetime import datetime
import logging
import django.conf
import django.core.exceptions
try:
  django.conf.settings.DEBUG
  from django.db import models
except django.core.exceptions.ImproperlyConfigured as error:
  from shims import models
log = logging.getLogger(__name__)


class Event(models.Model):

  # The type of event ('sms', 'call', 'chat', 'location', 'photo', etc).
  stream = models.CharField(max_length=31, blank=False)
  # The format it originated from ('hangouts', 'voice', 'mytracks', 'geotracker', etc).
  format = models.CharField(max_length=63, blank=False)
  # Unix timestamp of the event start.
  #TODO: Make a DateTimeField.
  start = models.BigIntegerField(null=False)

  class Meta:
    abstract = True

  @classmethod
  def create(cls, stream, format, start, raw=None):
    event = cls(stream=stream, format=format, start=start)
    event.add_raw(raw)
    return event

  def add_raw(self, raw):
    if raw is None:
      self.raw = {}
    else:
      self.raw = raw


class MessageEvent(Event):
  """Messages like SMS, chats, etc."""

  #TODO: sender = models.ForeignKey(Contact, on_delete=models.SET_NULL)
  sender = models.CharField(max_length=127, blank=False)
  # A null-delimited string of recipient names. This is a very temporary kludge just to get this up
  # and running without defining a Contact table.
  #TODO: recipients = models.ManyToManyField(Contact, related_name='messages')
  _recipients = models.CharField(max_length=1023, blank=False)
  message = models.TextField()
  # If this is a message from myself to myself, it will show up twice.
  # `echo` should be True if this is the 2nd appearance of the message.
  echo = models.BooleanField(default=False)

  @classmethod
  def create(cls, stream, format, start, sender, recipients, message, echo=False, raw=None):
    event = cls(stream=stream, format=format, start=start, sender=sender, recipients=recipients,
                message=message, echo=echo)
    event.add_raw(raw)
    return event

  @property
  def recipients(self):
    return self._recipients.split('\x00')

  @recipients.setter
  def recipients(self, values):
    self._recipients = '\x00'.join([str(value) for value in values])
