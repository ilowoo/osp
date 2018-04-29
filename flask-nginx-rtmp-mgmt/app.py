from flask import Flask, redirect, request, abort, render_template, url_for, flash, sessionfrom flask_security import Security, SQLAlchemyUserDatastore, UserMixin, RoleMixin, login_required, url_for_security, current_userfrom flask_security.forms import RegisterForm, LoginForm, StringField, Requiredfrom flask_sqlalchemy import SQLAlchemyfrom flask_socketio import SocketIO, emit, send, join_room, leave_room, roomsimport uuidimport loggingimport datetimeimport configapp = Flask(__name__)app.config['SQLALCHEMY_DATABASE_URI'] = config.dbLocationapp.config['SECRET_KEY'] = config.secretKeyapp.config['SECURITY_PASSWORD_HASH'] = "pbkdf2_sha512"app.config['SECURITY_PASSWORD_SALT'] = config.passwordSaltapp.config['SECURITY_REGISTERABLE'] = Trueapp.config['SECURITY_RECOVERABLE'] = Trueapp.config['SECURITY_CHANGABLE'] = Trueapp.config['SECURITY_CONFIRMABLE'] = Falseapp.config['SECURITY_USER_IDENTITY_ATTRIBUTES'] = ['username']app.config['SECURITY_FLASH_MESSAGES'] = Truelogger = logging.getLogger('gunicorn.error').handlerssocketio = SocketIO(app,logger=True)db = SQLAlchemy(app)class ExtendedRegisterForm(RegisterForm):    username = StringField('username', [Required()])roles_users = db.Table('roles_users',        db.Column('user_id', db.Integer(), db.ForeignKey('user.id')),        db.Column('role_id', db.Integer(), db.ForeignKey('role.id')))class Role(db.Model, RoleMixin):    id = db.Column(db.Integer(), primary_key=True)    name = db.Column(db.String(80), unique=True)    description = db.Column(db.String(255))class User(db.Model, UserMixin):    id = db.Column(db.Integer, primary_key=True)    username = db.Column(db.String(255), unique=True)    email = db.Column(db.String(255), unique=True)    password = db.Column(db.String(255))    active = db.Column(db.Boolean())    confirmed_at = db.Column(db.DateTime())    roles = db.relationship('Role', secondary=roles_users,                            backref=db.backref('users', lazy='dynamic'))class Stream(db.Model):    __tablename__="Stream"    id = db.Column(db.Integer, primary_key=True)    linkedChannel = db.Column(db.Integer,db.ForeignKey('Channel.id'))    streamKey = db.Column(db.String)    streamName = db.Column(db.String)    currentViewers = db.Column(db.Integer)    totalViewers = db.Column(db.Integer)    def __init__(self, streamKey, streamName, linkedChannel):        self.streamKey = streamKey        self.streamName = streamName        self.linkedChannel = linkedChannel        self.currentViewers = 0        self.totalViewers = 0    def __repr__(self):        return '<id %r>' % self.id    def add_viewer(self):        self.currentViewers = self.currentViewers + 1        db.session.commit()    def remove_viewer(self):        self.currentViewers = self.currentViewers - 1        db.session.commit()class Channel(db.Model):    __tablename__="Channel"    id = db.Column(db.Integer, primary_key=True)    owningUser = db.Column(db.Integer, db.ForeignKey('user.id'))    streamKey = db.Column(db.String(255), unique=True)    channelName = db.Column(db.String(255))    channelLoc = db.Column(db.String(255), unique=True)    topic = db.Column(db.Integer)    views = db.Column(db.Integer)    record = db.Column(db.Boolean)    stream = db.relationship('Stream', backref='channel', lazy="joined")    recordedVideo = db.relationship('RecordedVideo', backref='channel', lazy="joined")    def __init__(self, owningUser, streamKey, channelName, topic, record):        self.owningUser = owningUser        self.streamKey = streamKey        self.channelName = channelName        self.topic = topic        self.channelLoc = str(uuid.uuid4())        self.record = record        self.views = 0    def __repr__(self):        return '<id %r>' % self.idclass RecordedVideo(db.Model):    __tablename__="RecordedVideo"    id = db.Column(db.Integer,primary_key=True)    videoDate = db.Column(db.DateTime)    owningUser = db.Column(db.Integer,db.ForeignKey('user.id'))    channelName = db.Column(db.String(255))    channelID = db.Column(db.Integer,db.ForeignKey('Channel.id'))    topic = db.Column(db.Integer)    views = db.Column(db.Integer)    videoLocation = db.Column(db.String(255))    thumbnailLocation = db.Column(db.String(255))    pending = db.Column(db.Boolean)    def __init__(self,owningUser,channelID,channelName,topic,views,videoLocation):        self.videoDate = datetime.datetime.now()        self.owningUser=owningUser        self.channelID=channelID        self.channelName=channelName        self.topic=topic        self.views=views        self.videoLocation=videoLocation        self.pending = True    def __repr__(self):        return '<id %r>' % self.idclass topics(db.Model):    __table__name="topics"    id = db.Column(db.Integer, primary_key=True)    name = db.Column(db.String(255))    iconClass = db.Column(db.String(255))    def __init__(self, name, iconClass):        self.name = name        self.iconClass = iconClass    def __repr__(self):        return '<id %r>' % self.id# Setup Flask-Securityuser_datastore = SQLAlchemyUserDatastore(db, User, Role)security = Security(app, user_datastore, register_form=ExtendedRegisterForm)db.create_all()def init_db_values():    topicList = [("Static Webcam","&#xf03d;"),                 ("Gaming","&#xf11b;"),                 ("Meeting","&#xf0c0;"),                 ("News","&#xf1ea;"),                 ("Other","&#xf292;")]    for topic in topicList:        existingTopic = topics.query.filter_by(name=topic[0]).first()        if existingTopic is None:            newTopic = topics(topic[0], topic[1])            db.session.add(newTopic)    db.session.commit()@app.context_processordef inject_user_info():    return dict(user=current_user)@app.template_filter('normalize_uuid')def normalize_uuid(uuidstr):    return uuidstr.replace("-", "")@app.template_filter('get_topicName')def get_topicName(topicID):    topicQuery = topics.query.filter_by(id=int(topicID)).first()    return topicQuery.name@app.template_filter('get_userName')def get_userName(userID):    userQuery = User.query.filter_by(id=int(userID)).first()    return userQuery.username@app.route('/')def main_page():    activeStreams = Stream.query.all()    return render_template('index.html',streamList=activeStreams)@app.route('/view/<loc>/')def view_page(loc):    requestedChannel = Channel.query.filter_by(channelLoc=loc).first()    streamData = Stream.query.filter_by(streamKey=requestedChannel.streamKey).first()    if streamData is not None:        streamURL = ""        if streamData.channel.record is True:            streamURL = 'http://' + config.ipAddress + '/live-rec/' + streamData.channel.channelLoc + '/index.m3u8'        elif streamData.channel.record is False:            streamURL = 'http://' + config.ipAddress + '/live/' + streamData.channel.channelLoc + '/index.m3u8'        streamData.channel.views = streamData.channel.views + 1        streamData.totalViewers = streamData.totalViewers + 1        db.session.commit()        return render_template('player.html', stream=streamData, streamURL=streamURL)    else:        redirect(url_for("main_page"))@app.route('/play/<videoID>')def view_vid_page(videoID):    recordedVid = RecordedVideo.query.filter_by(id=videoID).first()    recordedVid.views = recordedVid.views + 1    db.session.commit()    streamURL = 'http://' + config.ipAddress + '/videos/' + recordedVid.videoLocation    return render_template('vidplayer.html', video=recordedVid, streamURL=streamURL)@app.route('/settings/channels', methods=['POST','GET'])@login_requireddef settings_channels_page():    if request.method == 'GET':        if request.args.get("action") is not None:            action = request.args.get("action")            streamKey = request.args.get("streamkey")            requestedChannel = Channel.query.filter_by(streamKey=streamKey).first()            if action == "delete":                if current_user.id == requestedChannel.id:                    db.session.delete(requestedChannel)                    db.session.commit()                    flash("Channel Deleted")                else:                    flash("Invalid Deletion Attempt","Error")    elif request.method == 'POST':        type = request.form['type']        channelName = request.form['channelName']        streamKey = request.form['streamKey']        topic = request.form['channeltopic']        record = False        if 'recordSelect' in request.form:            record = True        if type == 'new':            newChannel = Channel(current_user.id, streamKey, channelName, topic, record)            db.session.add(newChannel)            db.session.commit()        elif type == 'change':            origStreamKey = request.form['origStreamKey']            requestedChannel = Channel.query.filter_by(streamKey=origStreamKey).first()            if current_user.id == requestedChannel.id:                requestedChannel.channelName = channelName                requestedChannel.streamKey = streamKey                requestedChannel.topic = topic                requestedChannel.record = record                db.session.commit()            else:                flash("Invalid Change Attempt","Error")    topicList = topics.query.all()    user_channels = Channel.query.filter_by(owningUser = current_user.id).all()    return render_template('user_channels.html', channels=user_channels, topics=topicList)@app.route('/auth-key', methods=['POST'])def streamkey_check():    key = request.form['name']    ipaddress = request.form['addr']    channelRequest = Channel.query.filter_by(streamKey=key).first()    if channelRequest is not None:        returnMessage = {'time': str(datetime.datetime.now()), 'status': 'Successful Key Auth', 'key':str(key), 'channelName': str(channelRequest.channelName), 'userName':str(channelRequest.owningUser), 'ipAddress': str(ipaddress)}        print(returnMessage)        newStream = Stream(key,str(channelRequest.channelName),int(channelRequest.id))        db.session.add(newStream)        db.session.commit()        if channelRequest.record is False:            return redirect('rtmp://' + config.ipAddress + '/stream-data/' + channelRequest.channelLoc, code=302)        elif channelRequest.record is True:            userCheck = User.query.filter_by(id=channelRequest.owningUser).first()            newRecording = RecordedVideo(userCheck.id,channelRequest.id,channelRequest.channelName,channelRequest.topic,0,"")            db.session.add(newRecording)            db.session.commit()            return redirect('rtmp://' + config.ipAddress + '/streamrec-data/' + channelRequest.channelLoc, code=302)    else:        returnMessage = {'time': str(datetime.datetime.now()), 'status': 'Failed Key Auth', 'key':str(key), 'ipAddress': str(ipaddress)}        print(returnMessage)        return abort(400)@app.route('/auth-user', methods=['POST'])def user_auth_check():    key = request.form['name']    ipaddress = request.form['addr']    requestedChannel = Channel.query.filter_by(channelLoc=key).first()    authedStream = Stream.query.filter_by(streamKey=requestedChannel.streamKey).first()    if authedStream is not None:        returnMessage = {'time': str(datetime.datetime.now()), 'status': 'Successful Channel Auth', 'key': str(requestedChannel.streamKey), 'channelName': str(requestedChannel.channelName), 'ipAddress': str(ipaddress)}        print(returnMessage)        return 'OK'    else:        returnMessage = {'time': str(datetime.datetime.now()), 'status': 'Failed Channel Auth. No Authorized Stream Key', 'channelName': str(key), 'ipAddress': str(ipaddress)}        print(returnMessage)        return abort(400)@app.route('/deauth-user', methods=['POST'])def user_deauth_check():    key = request.form['name']    ipaddress = request.form['addr']    authedStream = Stream.query.filter_by(streamKey=key).all()    channelRequest = Channel.query.filter_by(streamKey=key).first()    if authedStream is not []:        for stream in authedStream:            pendingVideo = RecordedVideo.query.filter_by(channelID=channelRequest.id, videoLocation="", pending=True).first()            pendingVideo.views = stream.totalViewers            db.session.delete(stream)            db.session.commit()            returnMessage = {'time': str(datetime.datetime.now()), 'status': 'Stream Closed', 'key': str(key), 'channelName': str(channelRequest.channelName), 'userName':str(channelRequest.owningUser), 'ipAddress': str(ipaddress)}            print(returnMessage)        return 'OK'    else:        returnMessage = {'time': str(datetime.datetime.now()), 'status': 'Stream Closure Failure - No Such Stream', 'key': str(key), 'ipAddress': str(ipaddress)}        print(returnMessage)        return abort(400)@app.route('/recComplete', methods=['POST'])def rec_Complete_handler():    key = request.form['name']    path = request.form['path']    requestedChannel = Channel.query.filter_by(channelLoc=key).first()    pendingVideo = RecordedVideo.query.filter_by(channelID=requestedChannel.id, videoLocation="", pending=True).first()    videoPath = path.replace('/tmp/',requestedChannel.channelLoc + '/')    imagePath = videoPath.replace('.flv','.png')    videoPath = videoPath.replace('.flv','.mp4')    pendingVideo.thumbnailLocation = imagePath    pendingVideo.videoLocation = videoPath    pendingVideo.pending = False    db.session.commit()    return 'OK'@socketio.on('newViewer')def handle_new_viewer(streamData):    channelLoc = str(streamData['data'])    requestedChannel = Channel.query.filter_by(channelLoc=channelLoc).first()    stream = Stream.query.filter_by(streamKey=requestedChannel.streamKey).first()    viewedStream = Stream.query.filter_by(streamName=stream.streamName).first()    viewedStream.currentViewers = viewedStream.currentViewers + 1    db.session.commit()    join_room(streamData['data'])    if current_user.is_authenticated:        emit('message', {'msg': current_user.username + ' has entered the room.'}, room=streamData['data'])    else:        emit('message', {'msg': 'Guest has entered the room.'}, room=streamData['data'])@socketio.on('removeViewer')def handle_leaving_viewer(streamData):    channelLoc = str(streamData['data'])    requestedChannel = Channel.query.filter_by(channelLoc=channelLoc).first()    stream = Stream.query.filter_by(streamKey=requestedChannel.streamKey).first()    viewedStream = Stream.query.filter_by(streamName=stream.streamName).first()    viewedStream.currentViewers = viewedStream.currentViewers - 1    if viewedStream.currentViewers < 0:        viewedStream.currentViewers = 0    db.session.commit()    leave_room(streamData['data'])    if current_user.is_authenticated:        emit('message', {'msg': current_user.username + ' has left the room.'}, room=streamData['data'])    else:        emit('message', {'msg': 'Guest has left the room.'}, room=streamData['data'])@socketio.on('getViewerTotal')def handle_viewer_total_request(streamData):    channelLoc = str(streamData['data'])    requestedChannel = Channel.query.filter_by(channelLoc=channelLoc).first()    stream = Stream.query.filter_by(streamKey=requestedChannel.streamKey).first()    requestedStream = Stream.query.filter_by(streamName=stream.streamName).first()    emit('viewerTotalResponse', {'data':str(requestedStream.currentViewers)})socketio.on('disconnect')def disconnect(message):    logger.error(message)    emit('message', {'msg': message['msg']})@socketio.on('text')def text(message):    """Sent by a client when the user entered a new message.    The message is sent to all people in the room."""    room = message['room']    emit('message', {'msg': current_user.username + ': ' + message['msg']}, room=room)init_db_values()if __name__ == '__main__':    app.jinja_env.auto_reload = True    app.config['TEMPLATES_AUTO_RELOAD'] = True    socketio.run(app)