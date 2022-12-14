from .shared import db
from .settings import settings
from uuid import uuid4

from functions import cachedDbCalls

import datetime


class Stream(db.Model):
    __tablename__ = "Stream"
    id = db.Column(db.Integer, primary_key=True)
    uuid = db.Column(db.String(255))
    startTimestamp = db.Column(db.DateTime)
    endTimeStamp = db.Column(db.DateTime)
    linkedChannel = db.Column(db.Integer, db.ForeignKey("Channel.id"))
    streamKey = db.Column(db.String(255))
    streamName = db.Column(db.String(255))
    topic = db.Column(db.Integer)
    currentViewers = db.Column(db.Integer)
    totalViewers = db.Column(db.Integer)
    active = db.Column(db.Boolean)
    pending = db.Column(db.Boolean)
    complete = db.Column(db.Boolean)
    recordedVideoId = db.Column(db.Integer)
    rtmpServer = db.Column(db.Integer, db.ForeignKey("rtmpServer.id"))
    upvotes = db.relationship(
        "streamUpvotes", backref="stream", cascade="all, delete-orphan", lazy="joined"
    )

    def __init__(self, streamKey, streamName, linkedChannel, topic):
        self.uuid = str(uuid4())
        self.startTimestamp = datetime.datetime.utcnow()
        self.streamKey = streamKey
        self.streamName = streamName
        self.linkedChannel = linkedChannel
        self.currentViewers = 0
        self.totalViewers = 0
        self.topic = topic
        self.active = False
        self.pending = True
        self.complete = False

    def __repr__(self):
        return "<id %r>" % self.id

    def get_upvotes(self):
        return len(self.upvotes)

    def add_viewer(self):
        self.currentViewers = self.currentViewers + 1
        db.session.commit()

    def remove_viewer(self):
        self.currentViewers = self.currentViewers - 1
        db.session.commit()

    def serialize(self):
        sysSettings = cachedDbCalls.getSystemSettings()
        streamURL = ""
        if sysSettings.adaptiveStreaming is True:
            streamURL = "/live-adapt/" + self.channel.channelLoc + ".m3u8"
        else:
            streamURL = "/live/" + self.channel.channelLoc + "/index.m3u8"
        return {
            "id": self.id,
            "uuid": self.uuid,
            "startTimestamp": str(self.startTimestamp),
            "channelID": self.linkedChannel,
            "channelEndpointID": self.channel.channelLoc,
            "owningUser": self.channel.owningUser,
            "streamPage": "/view/" + self.channel.channelLoc + "/",
            "streamURL": streamURL,
            "streamName": self.streamName,
            "thumbnail": "/stream-thumb/" + self.channel.channelLoc + ".png",
            "gifLocation": "/stream-thumb/" + self.channel.channelLoc + ".gif",
            "topic": self.topic,
            "rtmpServer": self.server.address,
            "currentViewers": self.currentViewers,
            "totalViewers": self.currentViewers,
            "active": self.active,
            "upvotes": self.get_upvotes(),
        }
