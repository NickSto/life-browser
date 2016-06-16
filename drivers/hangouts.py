#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
The article included in this repository is licensed under a Attribution-NonCommercial-ShareAlike 3.0
license, meaning that you are free to copy, distribute, transmit and adapt this work for non-
commercial use, but that you must credit Fabian Mueller as the original author of the piece, and
provide a link to the source: https://bitbucket.org/dotcs/hangouts-log-reader/

You can read the full license here:
http://creativecommons.org/licenses/by-nc-sa/3.0/us/
"""

import sys
import os
import argparse
import json

from datetime import datetime

VERSION = "0.1"

class Participant(object):
    """
    Participant class.
    """
    def __init__(self, gaia_id, chat_id, name, phone):
        """
        Constructor
        """
        self.name = name 
        self.phone = phone
        self.gaia_id = gaia_id 
        self.chat_id = chat_id

    def get_id(self):
        """
        Getter for the internal Google ID of the participant.

        @return internal Google participant id
        """
        return self.gaia_id
    
    def get_phone(self):
        """
        Getter for the phone of a participant.

        @return phone of the participant (may be None)
        """
        return self.phone
    def get_name(self):
        """
        Getter for the name of a participant.

        @return name of the participant (may be None)
        """
        return self.name

    def __unicode__(self):
        """
        @return name of the participant or its id if name is None
        """
        if self.get_name() is None:
            if self.get_phone() is None:
                return self.get_id()
            else:
                return self.get_phone()
        else:
            #return "%s <%s>" % (self.get_name(), self.get_id())
            return self.get_name()

class ParticipantList(object):
    """
    List class for participants.
    """
    def __init__(self):
        """
        Constructor
        """
        self.p_list = {}
        self.current_iter = 0
        self.max_iter = 0

    def add(self, p):
        """
        Adds a participant to the list.

        @return the participant list
        """
        self.p_list[p.get_id()] = p
        return self.p_list

    def get_by_id(self, id):
        """
        Queries a participant by its id.

        @return the participant or None if id is not listed
        """
        try:
            return self.p_list[id]
        except:
            return None

    def __iter__(self):
        self.current_iter = 0
        self.max_iter = len(self.p_list)-1
        return self

    def next(self):
        if self.current_iter > self.max_iter:
            raise StopIteration
        else:
            self.current_iter += 1
            return self.p_list.values()[self.current_iter-1]

    def __unicode__(self):
        """
        @return names of the participants seperated by a comma
        """
        string = ""
        for p in self.p_list.values():
            string += unicode(p) + ", "
        return string[:-2]

class Event(object):
    """
    Event class.
    """
    def __init__(self, event_id, sender_id, timestamp, message):
        """
        Constructor
        """
        self.event_id = event_id
        self.sender_id = sender_id
        self.timestamp = timestamp
        self.message = message

    def get_id(self):
        """
        Getter method for the id.

        @return event id
        """
        return self.event_id

    def get_sender_id(self):
        """
        Getter method for the sender id.

        @return sender id of the event
        """
        return self.sender_id

    def get_timestamp(self):
        """
        Getter method for the timestamp.

        @return timestamp of the event
        """
        return self.timestamp

    def get_message(self):
        """
        Getter method for the message.

        @return message (list)
        """
        return self.message
    
    def get_picture(self):
        """
        Getter method for the picture.

        @return picture (url)
        """
        return self.message

    def get_formatted_message(self):
        """
        Getter method for a formatted message (the messages are joined by a space).

        @return message (string)
        """
        string = ""
        for m in self.message:
            string += m + " "
        return string[:-1]

class EventList(object):
    """
    Event list class
    """
    def __init__(self):
        """
        Constructor
        """
        self.event_list = {}
        self.current_iter = 0
        self.max_iter = 0

    def add(self, e):
        """
        Adds an event to the event list

        @return event list
        """
        self.event_list[e.get_id()] = e
        return self.event_list

    def get_by_id(self, id):
        """
        Getter method for an event by its id.

        @returns event
        """
        try:
            return self.event_list[id]
        except:
            return None

    def __iter__(self):
        self.current_iter = 0
        self.max_iter = len(self.event_list)-1
        return self

    def next(self):
        if self.current_iter > self.max_iter:
            raise StopIteration
        else:
            self.current_iter += 1
            return self.event_list.values()[self.current_iter-1]

class Conversation(object):
    """
    Conversation class
    """
    def __init__(self, conversation_id, timestamp, participants, events):
        """
        Constructor
        """
        self.conversation_id = conversation_id
        self.timestamp = timestamp
        self.participants = participants
        self.events = events
    
    def __str__(self):
        """
        Prints to string
        """
        return self.conversation_id 

    def get_id(self):
        """
        Getter method for the conversation id

        @return conversation id
        """
        return self.conversation_id

    def get_timestamp(self):
        """
        Getter method for the timestamp

        @return timestamp
        """
        return self.timestamp
        
    def get_participants(self):
        """
        Getter method for the participants.

        @return participants of the conversation
        """
        return self.participants

    def get_events(self):
        """
        Getter method for the sorted events.

        @return events of the conversation (sorted)
        """
        return sorted(self.events, key=lambda event: event.get_timestamp())

    def get_events_unsorted(self):
        """
        Getter method for the unsorted events.

        @return events of the conversation (unsorted)
        """
        return self.events

    def print_conversation(self):
        """
        Prints conversations in human readable format.

        @return None
        """
        participants = self.get_participants()
        for event in self.get_events():
            author = "<UNKNOWN>"
            author_id = participants.get_by_id(event.get_sender_id())
            if author_id:
                author = author_id.get_name()
            print "%(timestamp)s: <%(author)s> %(message)s" % \
                    {
                        "timestamp": datetime.fromtimestamp(long(long(event.get_timestamp())/10**6.)),
                        "author": author,
                        "message": event.get_formatted_message(),
                    }


#TODO: Finish converting from stdout-printing class to generator yielding data structures.
def read_hangouts(logfile, verbose_mode=False, conversation_id=None):
    """Parses the json file.
    Yields the conversation list or a complete conversation depending on the users choice."""
    validate_file(logfile)
    with open(logfile) as json_data:
        if verbose_mode:
            print "Analyzing json file ..."
        data = json.load(json_data)
        for conversation in data["conversation_state"]:
            convo = _extract_conversation_data(conversation)
            if conversation_id is None or convo.get_id() == conversation_id:
                yield convo

def _extract_conversation_data(conversation):
    """
    Extracts the data that belongs to a single conversation.

    @return Conversation object
    """
    try:
        # note the initial timestamp of this conversation
        initial_timestamp = conversation["response_header"]["current_server_time"]
        conversation_id = conversation["conversation_id"]["id"]

        # find out the participants
        participant_list = ParticipantList()
        for participant in conversation["conversation_state"]["conversation"]["participant_data"]:
            gaia_id = participant["id"]["gaia_id"]
            chat_id = participant["id"]["chat_id"]
            try:
                name = participant["fallback_name"]
            except KeyError:
                name = None
            try:
                phone = participant["phone_number"]["e164"]
            except KeyError:
                phone = None
            p = Participant(gaia_id,chat_id,name,phone)
            participant_list.add(p)

        event_list = EventList()

        for event in conversation["conversation_state"]["event"]:
            event_id = event["event_id"]
            sender_id = event["sender_id"] # has dict values "gaia_id" and "chat_id"
            timestamp = event["timestamp"]
            text = list()
            try:
                message_content = event["chat_message"]["message_content"]
                try:
                    for segment in message_content["segment"]:
                        if segment["type"].lower() in ("TEXT".lower(), "LINK".lower()):
                            text.append(segment["text"])
                except KeyError:
                    pass # may happen when there is no (compatible) attachment
                try:
                    for attachment in message_content["attachment"]:
                        # if there is a Google+ photo attachment we append the URL
                        if attachment["embed_item"]["type"][0].lower() == "PLUS_PHOTO".lower():
                            text.append(attachment["embed_item"]["embeds.PlusPhoto.plus_photo"]["url"])
                except KeyError:
                    pass # may happen when there is no (compatible) attachment
            except KeyError:
                continue # that's okay
            # finally add the event to the event list
            event_list.add(Event(event_id, sender_id["gaia_id"], timestamp, text))
    except KeyError:
        raise RuntimeError("The conversation data could not be extracted.")
    return Conversation(conversation_id, initial_timestamp, participant_list, event_list)

def validate_file(filename):
    """
    Checks if a file is valid or not.
    Raises a ValueError if the file could not be found.

    @return filename if everything is fine
    """
    if not os.path.isfile(filename):
        raise ValueError("The given file is not valid.")
    return filename

def _write(message, file):
    """
    Writes the message to file with suffix in front of the message.

    @return None
    """
    file.write( "[%s] %s" % (os.path.basename(__file__), unicode(message).encode('utf8')))


def main(argv):
    parser = argparse.ArgumentParser(description='Commandline python script that allows reading Google Hangouts logfiles. Version: %s' % VERSION)

    parser.add_argument('logfile', type=str, help='filename of the logfile')
    parser.add_argument('--conversation-id', '-c', type=str, help='shows the conversation with given id')
    parser.add_argument('--verbose', '-v', action="store_true", help='activates the verbose mode')

    args = parser.parse_args()

    for convo in read_hangouts(args.logfile, verbose_mode=args.verbose, conversation_id=args.conversation_id):
        if args.conversation_id and args.conversation_id == convo.get_id():
            convo.print_conversation()
        else:
            print "conversation id: %s, participants: %s" % (convo.get_id(), unicode(convo.get_participants()))


if __name__ == "__main__":
    main(sys.argv)
