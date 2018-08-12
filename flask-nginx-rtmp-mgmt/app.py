from flask import Flask, redirect, request, abort, render_template, url_for, flash, sessionfrom flask_security import Security, SQLAlchemyUserDatastore, UserMixin, RoleMixin, login_required, url_for_security, current_user, roles_requiredfrom flask_security.utils import hash_passwordfrom flask_security.forms import RegisterForm, LoginForm, StringField, Requiredfrom flask_security.signals import user_registeredfrom flask_security import utilsfrom flask_sqlalchemy import SQLAlchemyfrom flask_socketio import SocketIO, emit, send, join_room, leave_room, roomsfrom flask_uploads import UploadSet, configure_uploads, IMAGES, UploadNotAllowed, patch_request_classimport uuidimport psutilimport shutilimport osimport subprocessimport timeimport sys#Import Pathscwp = sys.path[0]sys.path.append(cwp)sys.path.append('./classes')from HTMLParser import HTMLParserimport loggingfrom requests import getimport datetimeimport configapp = Flask(__name__)app.config['SQLALCHEMY_DATABASE_URI'] = config.dbLocationapp.config['SECRET_KEY'] = config.secretKeyapp.config['SECURITY_PASSWORD_HASH'] = "pbkdf2_sha512"app.config['SECURITY_PASSWORD_SALT'] = config.passwordSaltapp.config['SECURITY_REGISTERABLE'] = Trueapp.config['SECURITY_RECOVERABLE'] = Trueapp.config['SECURITY_CHANGABLE'] = Trueapp.config['SECURITY_CONFIRMABLE'] = Falseapp.config['SECURITY_USER_IDENTITY_ATTRIBUTES'] = ['username']app.config['SECURITY_FLASH_MESSAGES'] = Trueapp.config['UPLOADED_PHOTOS_DEST'] = '/var/www/images'app.config['UPLOADED_DEFAULT_DEST'] = '/var/www/images'logger = logging.getLogger('gunicorn.error').handlerssocketio = SocketIO(app,logger=True)appDBVersion = 0.1db = SQLAlchemy(app)from classes import Streamfrom classes import Channelfrom classes import dbVersionfrom classes import RecordedVideofrom classes import topicsfrom classes import settingsfrom classes import banListfrom classes import SecsysSettings = None# Setup Flask-Securityuser_datastore = SQLAlchemyUserDatastore(db, Sec.User, Sec.Role)security = Security(app, user_datastore, register_form=Sec.ExtendedRegisterForm)# Setup Flask-Uploadsphotos = UploadSet('photos', (IMAGES))configure_uploads(app, photos)patch_request_class(app)def init_db_values():    db.create_all()    dbVersionQuery = dbVersion.dbVersion.query.first()    if dbVersionQuery == None:        newDBVersion = dbVersion.dbVersion(appDBVersion)        db.session.add(newDBVersion)        db.session.commit()    elif dbVersionQuery.version != appDBVersion:        pass    user_datastore.find_or_create_role(name='Admin', description='Administrator')    user_datastore.find_or_create_role(name='User', description='User')    topicList = [("Other","None")]    for topic in topicList:        existingTopic = topics.topics.query.filter_by(name=topic[0]).first()        if existingTopic is None:            newTopic = topics.topics(topic[0], topic[1])            db.session.add(newTopic)    db.session.commit()    sysSettings = settings.settings.query.first()    if sysSettings != None:        app.config['SECURITY_EMAIL_SENDER'] = sysSettings.smtpSendAs        app.config['MAIL_SERVER'] = sysSettings.smtpAddress        app.config['MAIL_PORT'] = sysSettings.smtpPort        app.config['MAIL_USE_SSL'] = sysSettings.smtpTLS        app.config['MAIL_USERNAME'] = sysSettings.smtpUsername        app.config['MAIL_PASSWORD'] = sysSettings.smtpPassword        app.config.update(SECURITY_REGISTERABLE=sysSettings.allowRegistration)def check_existing_users():    existingUserQuery = Sec.User.query.all()    if existingUserQuery == []:        return False    else:        return Trueclass MLStripper(HTMLParser):    def __init__(self):        self.reset()        self.fed = []    def handle_data(self, d):        self.fed.append(d)    def get_data(self):        return ''.join(self.fed)def strip_html(text):    s = MLStripper()    s.feed(text)    return s.get_data()def getVidLength(input_video):    result = subprocess.check_output(['ffprobe', '-i', input_video, '-show_entries', 'format=duration', '-v', 'quiet', '-of', 'csv=%s' % ("p=0")])    return float(result)@app.context_processordef inject_user_info():    return dict(user=current_user)@app.context_processordef inject_sysSettings():    sysSettings = settings.settings.query.first()    return dict(sysSettings=sysSettings)@app.template_filter('normalize_uuid')def normalize_uuid(uuidstr):    return uuidstr.replace("-", "")@app.template_filter('normalize_date')def normalize_date(dateStr):    return str(dateStr)[:19]@app.template_filter('hms_format')def hms_format(seconds):    val = "Unknown"    if seconds != None:        val = time.strftime("%H:%M:%S", time.gmtime(seconds))    return val@app.template_filter('get_topicName')def get_topicName(topicID):    topicQuery = topics.topics.query.filter_by(id=int(topicID)).first()    if topicQuery == None:        return "None"    return topicQuery.name@app.template_filter('get_userName')def get_userName(userID):    userQuery = Sec.User.query.filter_by(id=int(userID)).first()    return userQuery.username@app.template_filter('get_diskUsage')def get_diskUsage(channelLocation):    channelLocation = '/var/www/videos/' + channelLocation    total_size = 0    for dirpath, dirnames, filenames in os.walk(channelLocation):        for f in filenames:            fp = os.path.join(dirpath, f)            total_size += os.path.getsize(fp)    return "{:,}".format(total_size)@user_registered.connect_via(app)def user_registered_sighandler(app, user, confirm_token):    default_role = user_datastore.find_role("User")    user_datastore.add_role_to_user(user, default_role)    db.session.commit()@app.route('/')def main_page():    firstRunCheck = check_existing_users()    if firstRunCheck is False:        return render_template('firstrun.html')    else:        activeStreams = Stream.Stream.query.order_by(Stream.Stream.currentViewers).all()        return render_template('index.html', streamList=activeStreams)@app.route('/channels')def channels_page():    channelList = Channel.Channel.query.all()    return render_template('channels.html', channelList=channelList)@app.route('/channel/<chanID>/')def channel_view_page(chanID):    chanID = int(chanID)    channelData = Channel.Channel.query.filter_by(id=chanID).first()    openStreams = Stream.Stream.query.filter_by(linkedChannel=chanID).all()    recordedVids = RecordedVideo.RecordedVideo.query.filter_by(channelID=chanID, pending=False).all()    return render_template('channelView.html', channelData=channelData, openStreams=openStreams, recordedVids=recordedVids)@app.route('/topics')def topic_page():    topicIDList = []    for streamInstance in db.session.query(Stream.Stream.topic).distinct():        topicIDList.append(streamInstance.topic)    for recordedVidInstance in db.session.query(RecordedVideo.RecordedVideo.topic).distinct():        if recordedVidInstance.topic not in topicIDList:            topicIDList.append(recordedVidInstance.topic)    topicsList = []    for item in topicIDList:        topicQuery = topics.topics.topics.query.filter_by(id=item).first()        if topicQuery != None:            topicsList.append(topicQuery)    return render_template('topics.html', topicsList=topicsList)@app.route('/topic/<topicID>/')def topic_view_page(topicID):    topicID = int(topicID)    streamsQuery = Stream.Stream.query.filter_by(topic=topicID).all()    recordedVideoQuery = RecordedVideo.RecordedVideo.query.filter_by(topic=topicID, pending=False).all()    return render_template('topicView.html', streamsList=streamsQuery, recordedVideoList=recordedVideoQuery)@app.route('/view/<loc>/')def view_page(loc):    sysSettings = settings.settings.query.first()    requestedChannel = Channel.Channel.query.filter_by(channelLoc=loc).first()    streamData = Stream.Stream.query.filter_by(streamKey=requestedChannel.streamKey).first()    if streamData is not None:        streamURL = ""        if streamData.channel.record is True:            streamURL = '/live-rec/' + streamData.channel.channelLoc + '/index.m3u8'        elif streamData.channel.record is False:            streamURL = '/live/' + streamData.channel.channelLoc + '/index.m3u8'        streamData.channel.views = streamData.channel.views + 1        streamData.totalViewers = streamData.totalViewers + 1        db.session.commit()        topicList = topics.topics.topics.query.all()        return render_template('player.html', stream=streamData, streamURL=streamURL, topics=topicList)    else:        return redirect(url_for("main_page"))@app.route('/view/<loc>/change', methods=['POST'])@login_requireddef view_change_page(loc):    requestedChannel = Channel.Channel.query.filter_by(channelLoc=loc, owningUser=current_user.id).first()    streamData = Stream.Stream.query.filter_by(streamKey=requestedChannel.streamKey).first()    newStreamName = strip_html(request.form['newStreamName'])    newStreamTopic = request.form['newStreamTopic']    if streamData is not None:        streamData.streamName = newStreamName        streamData.topic = newStreamTopic        db.session.commit()    return redirect(url_for('view_page', loc=loc))@app.route('/play/<videoID>')def view_vid_page(videoID):    sysSettings = settings.settings.query.first()    recordedVid = RecordedVideo.RecordedVideo.query.filter_by(id=videoID).first()    recordedVid.views = recordedVid.views + 1    if recordedVid.length == None:        fullVidPath = '/var/www/videos/' + recordedVid.videoLocation        duration = getVidLength(fullVidPath)        recordedVid.length = duration    db.session.commit()    topicList = topics.topics.topics.query.all()    streamURL = '/videos/' + recordedVid.videoLocation    return render_template('vidplayer.html', video=recordedVid, streamURL=streamURL, topics=topicList)@app.route('/play/<loc>/change', methods=['POST'])@login_requireddef vid_change_page(loc):    recordedVidQuery = RecordedVideo.RecordedVideo.query.filter_by(id=loc, owningUser=current_user.id).first()    newStreamName = strip_html(request.form['newStreamName'])    newStreamTopic = request.form['newStreamTopic']    if recordedVidQuery is not None:        recordedVidQuery.channelName = newStreamName        recordedVidQuery.topic = newStreamTopic        db.session.commit()    return redirect(url_for('view_vid_page', videoID=loc))@app.route('/play/<videoID>/delete')@login_requireddef delete_vid_page(videoID):    recordedVid = RecordedVideo.RecordedVideo.query.filter_by(id=videoID).first()    if current_user.id == recordedVid.owningUser and recordedVid.videoLocation != None:        filePath = '/var/www/videos/' + recordedVid.videoLocation        if os.path.exists(filePath) and (recordedVid.videoLocation != None or recordedVid.videoLocation != ""):            shutil.rmtree(filePath, ignore_errors=True)        db.session.delete(recordedVid)        db.session.commit()        return redirect(url_for('main_page'))    flash("Error Deleting Video")    return redirect(url_for('view_vid_page', videoID=videoID))@app.route('/settings/user', methods=['POST','GET'])@login_requireddef user_page():    if request.method == 'GET':        return render_template('userSettings.html')    elif request.method == 'POST':        emailAddress = request.form['emailAddress']        password1 = request.form['password1']        password2 = request.form['password2']        if password1 != "":            if password1 == password2:                newPassword = hash_password(password1)                current_user.password = newPassword                flash("Password Changed")            else:                flash("Passwords Don't Match!")        if 'photo' in request.files:            oldImage = None            if current_user.pictureLocation != None:                oldImage = current_user.pictureLocation            filename = photos.save(request.files['photo'], name=str(uuid.uuid4()) + '.')            current_user.pictureLocation = filename            if oldImage != None:                try:                    os.remove(oldImage)                except OSError:                    pass        current_user.emailAddress = emailAddress        db.session.commit()    return redirect(url_for('user_page'))@app.route('/settings/admin', methods=['POST','GET'])@login_required@roles_required('Admin')def admin_page():    if request.method == 'GET':        if request.args.get("action") is not None:            action = request.args.get("action")            setting = request.args.get("setting")            if action == "delete":                if setting == "topics":                    topicID = int(request.args.get("topicID"))                    topicQuery = topics.topics.query.filter_by(id=topicID).first()                    db.session.delete(topicQuery)                    db.session.commit()                    flash("Topic Deleted")                    return redirect(url_for('admin_page'))        appDBVer = dbVersion.dbVersion.query.first().version        userList = Sec.User.query.all()        roleList = Sec.Role.query.all()        channelList = Channel.Channel.query.all()        streamList = Stream.Stream.query.all()        topicsList = topics.topics.query.all()        return render_template('admin.html', appDBVer=appDBVer, userList=userList, roleList=roleList, channelList=channelList, streamList=streamList, topicsList=topicsList)    elif request.method == 'POST':        sysSettings = settings.settings.query.first()        settingType = request.form['settingType']        if settingType == "system":            serverName = request.form['serverName']            serverAddress = request.form['serverAddress']            smtpSendAs = request.form['smtpSendAs']            smtpAddress = request.form['smtpAddress']            smtpPort = request.form['smtpPort']            smtpUser = request.form['smtpUser']            smtpPassword = request.form['smtpPassword']            background = request.form['background']            recordSelect = False            registerSelect = False            smtpTLS = False            if 'recordSelect' in request.form:                recordSelect = True            if 'registerSelect' in request.form:                registerSelect = True            if 'smtpTLS' in request.form:                smtpTLS = True            sysSettings.siteName = serverName            sysSettings.siteAddress = serverAddress            sysSettings.smtpSendAs = smtpSendAs            sysSettings.smtpAddress = smtpAddress            sysSettings.smtpPort = smtpPort            sysSettings.smtpUsername = smtpUser            sysSettings.smtpPassword = smtpPassword            sysSettings.smtpTLS = smtpTLS            sysSettings.allowRecording = recordSelect            sysSettings.allowRegistration = registerSelect            sysSettings.background = background            db.session.commit()            sysSettings = settings.settings.query.first()            app.config.update(SECURITY_EMAIL_SENDER=sysSettings.smtpSendAs)            app.config.update(MAIL_SERVER=sysSettings.smtpAddress)            app.config.update(MAIL_PORT=sysSettings.smtpPort)            app.config.update(MAIL_USE_SSL=sysSettings.smtpTLS)            app.config.update(MAIL_USERNAME=sysSettings.smtpUsername)            app.config.update(MAIL_PASSWORD=sysSettings.smtpPassword)            app.config.update(SECURITY_REGISTERABLE=sysSettings.allowRegistration)        elif settingType == "topics":            if 'topicID' in request.form:                topicID = int(request.form['topicID'])                topicName = request.form['name']                topicQuery = topics.topics.query.filter_by(id=topicID).first()                if topicQuery != None:                    topicQuery.name = topicName                    if 'photo' in request.files:                        oldImage = None                        if topicQuery.iconClass != None:                            oldImage = topicQuery.iconClass                        filename = photos.save(request.files['photo'], name=str(uuid.uuid4()) + '.')                        topicQuery.iconClass = filename                        if oldImage != None:                            try:                                os.remove(oldImage)                            except OSError:                                pass            else:                topicName = request.form['name']                topicImage = None                if 'photo' in request.files:                    filename = photos.save(request.files['photo'], name=str(uuid.uuid4()) + '.')                    topicImage = filename                newTopic = topics.topics(topicName,topicImage)                db.session.add(newTopic)            db.session.commit()        return redirect(url_for('admin_page'))@app.route('/settings/channels', methods=['POST','GET'])@login_requireddef settings_channels_page():    sysSettings = settings.settings.query.first()    if request.method == 'GET':        if request.args.get("action") is not None:            action = request.args.get("action")            streamKey = request.args.get("streamkey")            requestedChannel = Channel.Channel.query.filter_by(streamKey=streamKey).first()            if action == "delete":                if current_user.id == requestedChannel.owningUser:                    filePath = '/var/www/videos/' + requestedChannel.channelLoc                    shutil.rmtree(filePath, ignore_errors=True)                    db.session.delete(requestedChannel)                    db.session.commit()                    flash("Channel Deleted")                else:                    flash("Invalid Deletion Attempt","Error")    elif request.method == 'POST':        type = request.form['type']        channelName = strip_html(request.form['channelName'])        topic = request.form['channeltopic']        record = False        if 'recordSelect' in request.form and sysSettings.allowRecording is True:            record = True        chatEnabled = False        if 'chatSelect' in request.form:            chatEnabled = True        if type == 'new':            newUUID = str(uuid.uuid4())            newChannel = Channel.Channel(current_user.id, newUUID, channelName, topic, record, chatEnabled)            db.session.add(newChannel)            db.session.commit()        elif type == 'change':            streamKey = request.form['streamKey']            origStreamKey = request.form['origStreamKey']            requestedChannel = Channel.Channel.query.filter_by(streamKey=origStreamKey).first()            if current_user.id == requestedChannel.owningUser:                requestedChannel.channelName = channelName                requestedChannel.streamKey = streamKey                requestedChannel.topic = topic                requestedChannel.record = record                requestedChannel.chatEnabled = chatEnabled                if 'photo' in request.files:                    oldImage = None                    if requestedChannel.imageLocation != None:                        oldImage = requestedChannel.imageLocation                    filename = photos.save(request.files['photo'], name=str(uuid.uuid4()) + '.')                    requestedChannel.imageLocation = filename                    if oldImage != None:                        try:                            os.remove(oldImage)                        except OSError:                            pass                flash("Channel Edited")                db.session.commit()            else:                flash("Invalid Change Attempt","Error")            redirect(url_for('settings_channels_page'))    topicList = topics.topics.query.all()    user_channels = Channel.Channel.query.filter_by(owningUser = current_user.id).all()    return render_template('user_channels.html', channels=user_channels, topics=topicList)@app.route('/settings/initialSetup', methods=['POST'])def initialSetup():    firstRunCheck = check_existing_users()    if firstRunCheck is False:        username = request.form['username']        email = request.form['email']        password1 = request.form['password1']        password2 = request.form['password2']        serverName = request.form['serverName']        serverAddress = request.form['serverAddress']        smtpSendAs = request.form['smtpSendAs']        smtpAddress = request.form['smtpAddress']        smtpPort = request.form['smtpPort']        smtpUser = request.form['smtpUser']        smtpPassword = request.form['smtpPassword']        recordSelect = False        registerSelect = False        smtpTLS = False        if 'recordSelect' in request.form:            recordSelect = True        if 'registerSelect' in request.form:            registerSelect = True        if 'smtpTLS' in request.form:            smtpTLS = True        if password1 == password2:            passwordhash = utils.hash_password(password1)            user_datastore.create_user(email=email, username=username, password=passwordhash)            db.session.commit()            user = Sec.User.query.filter_by(username=username).first()            user_datastore.add_role_to_user(user,'Admin')            serverSettings = settings.settings(serverName, serverAddress, smtpAddress, smtpPort, smtpTLS, smtpUser, smtpPassword, smtpSendAs, registerSelect, recordSelect)            db.session.add(serverSettings)            db.session.commit()            sysSettings = settings.settings.query.first()            if settings != None:                app.config.update(SECURITY_EMAIL_SENDER=sysSettings.smtpSendAs)                app.config.update(MAIL_SERVER=sysSettings.smtpAddress)                app.config.update(MAIL_PORT=sysSettings.smtpPort)                app.config.update(MAIL_USE_SSL=sysSettings.smtpTLS)                app.config.update(MAIL_USERNAME=sysSettings.smtpUsername)                app.config.update(MAIL_PASSWORD=sysSettings.smtpPassword)                app.config.update(SECURITY_REGISTERABLE=sysSettings.allowRegistration)        else:            flash('Passwords do not match')            return redirect(url_for('main_page'))    return redirect(url_for('main_page'))@app.route('/auth-key', methods=['POST'])def streamkey_check():    sysSettings = settings.settings.query.first()    key = request.form['name']    ipaddress = request.form['addr']    channelRequest = Channel.Channel.query.filter_by(streamKey=key).first()    if channelRequest is not None:        returnMessage = {'time': str(datetime.datetime.now()), 'status': 'Successful Key Auth', 'key':str(key), 'channelName': str(channelRequest.channelName), 'userName':str(channelRequest.owningUser), 'ipAddress': str(ipaddress)}        print(returnMessage)        externalIP = get('https://api.ipify.org').text        newStream = Stream.Stream(key, str(channelRequest.channelName), int(channelRequest.id), channelRequest.topic)        db.session.add(newStream)        db.session.commit()        if channelRequest.record is False:            return redirect('rtmp://' + externalIP + '/stream-data/' + channelRequest.channelLoc, code=302)        elif channelRequest.record is True:            userCheck = Sec.User.query.filter_by(id=channelRequest.owningUser).first()            newRecording = RecordedVideo.RecordedVideo(userCheck.id,channelRequest.id,channelRequest.channelName,channelRequest.topic,0,"")            db.session.add(newRecording)            db.session.commit()            return redirect('rtmp://' + externalIP + '/streamrec-data/' + channelRequest.channelLoc, code=302)    else:        returnMessage = {'time': str(datetime.datetime.now()), 'status': 'Failed Key Auth', 'key':str(key), 'ipAddress': str(ipaddress)}        print(returnMessage)        return abort(400)@app.route('/auth-user', methods=['POST'])def user_auth_check():    key = request.form['name']    ipaddress = request.form['addr']    requestedChannel = Channel.Channel.query.filter_by(channelLoc=key).first()    authedStream = Stream.Stream.query.filter_by(streamKey=requestedChannel.streamKey).first()    if authedStream is not None:        returnMessage = {'time': str(datetime.datetime.now()), 'status': 'Successful Channel Auth', 'key': str(requestedChannel.streamKey), 'channelName': str(requestedChannel.channelName), 'ipAddress': str(ipaddress)}        print(returnMessage)        return 'OK'    else:        returnMessage = {'time': str(datetime.datetime.now()), 'status': 'Failed Channel Auth. No Authorized Stream Key', 'channelName': str(key), 'ipAddress': str(ipaddress)}        print(returnMessage)        return abort(400)@app.route('/deauth-user', methods=['POST'])def user_deauth_check():    key = request.form['name']    ipaddress = request.form['addr']    authedStream = Stream.Stream.query.filter_by(streamKey=key).all()    channelRequest = Channel.Channel.query.filter_by(streamKey=key).first()    if authedStream is not []:        for stream in authedStream:            pendingVideo = RecordedVideo.RecordedVideo.query.filter_by(channelID=channelRequest.id, videoLocation="", pending=True).first()            if pendingVideo is not None:                pendingVideo.channelName = stream.streamName                pendingVideo.views = stream.totalViewers                pendingVideo.topic = stream.topic            db.session.delete(stream)            db.session.commit()            returnMessage = {'time': str(datetime.datetime.now()), 'status': 'Stream Closed', 'key': str(key), 'channelName': str(channelRequest.channelName), 'userName':str(channelRequest.owningUser), 'ipAddress': str(ipaddress)}            print(returnMessage)        return 'OK'    else:        returnMessage = {'time': str(datetime.datetime.now()), 'status': 'Stream Closure Failure - No Such Stream', 'key': str(key), 'ipAddress': str(ipaddress)}        print(returnMessage)        return abort(400)@app.route('/recComplete', methods=['POST'])def rec_Complete_handler():    key = request.form['name']    path = request.form['path']    requestedChannel = Channel.Channel.query.filter_by(channelLoc=key).first()    pendingVideo = RecordedVideo.RecordedVideo.query.filter_by(channelID=requestedChannel.id, videoLocation="", pending=True).first()    videoPath = path.replace('/tmp/',requestedChannel.channelLoc + '/')    imagePath = videoPath.replace('.flv','.png')    videoPath = videoPath.replace('.flv','.mp4')    pendingVideo.thumbnailLocation = imagePath    pendingVideo.videoLocation = videoPath    fullVidPath = '/var/www/videos/' + videoPath    pendingVideo.pending = False    db.session.commit()    while not os.path.exists(fullVidPath):        time.sleep(1)    if os.path.isfile(fullVidPath):        pendingVideo.length = getVidLength(fullVidPath)        db.session.commit()    return 'OK'@socketio.on('newViewer')def handle_new_viewer(streamData):    channelLoc = str(streamData['data'])    requestedChannel = Channel.Channel.query.filter_by(channelLoc=channelLoc).first()    stream = Stream.Stream.query.filter_by(streamKey=requestedChannel.streamKey).first()    viewedStream = Stream.Stream.query.filter_by(streamName=stream.streamName).first()    viewedStream.currentViewers = viewedStream.currentViewers + 1    db.session.commit()    join_room(streamData['data'])    if current_user.is_authenticated:        pictureLocation = current_user.pictureLocation        if current_user.pictureLocation == None:            pictureLocation = '/static/img/user2.png'        else:            pictureLocation = '/images/' + pictureLocation        emit('message', {'user':'Server','msg': current_user.username + ' has entered the room.', 'image': pictureLocation}, room=streamData['data'])    else:        emit('message', {'user':'Server','msg': 'Guest has entered the room.', 'image': '/static/img/user2.png'}, room=streamData['data'])@socketio.on('removeViewer')def handle_leaving_viewer(streamData):    channelLoc = str(streamData['data'])    requestedChannel = Channel.Channel.query.filter_by(channelLoc=channelLoc).first()    stream = Stream.Stream.query.filter_by(streamKey=requestedChannel.streamKey).first()    viewedStream = Stream.Stream.query.filter_by(streamName=stream.streamName).first()    viewedStream.currentViewers = viewedStream.currentViewers - 1    if viewedStream.currentViewers < 0:        viewedStream.currentViewers = 0    db.session.commit()    leave_room(streamData['data'])    if current_user.is_authenticated:        pictureLocation = current_user.pictureLocation        if current_user.pictureLocation == None:            pictureLocation = '/static/img/user2.png'        else:            pictureLocation = '/images/' + pictureLocation        emit('message', {'user':'Server', 'msg': current_user.username + ' has left the room.', 'image': pictureLocation}, room=streamData['data'])    else:        emit('message', {'user':'Server', 'msg': 'Guest has left the room.', 'image': '/static/img/user2.png'}, room=streamData['data'])@socketio.on('getViewerTotal')def handle_viewer_total_request(streamData):    channelLoc = str(streamData['data'])    requestedChannel = Channel.Channel.query.filter_by(channelLoc=channelLoc).first()    stream = Stream.Stream.query.filter_by(streamKey=requestedChannel.streamKey).first()    requestedStream = Stream.Stream.query.filter_by(streamName=stream.streamName).first()    emit('viewerTotalResponse', {'data':str(requestedStream.currentViewers)})socketio.on('disconnect')def disconnect(message):    logger.error(message)    emit('message', {'msg': message['msg']})@socketio.on('text')def text(message):    """Sent by a client when the user entered a new message.    The message is sent to all people in the room."""    room = message['room']    msg = strip_html(message['msg'])    pictureLocation = current_user.pictureLocation    if current_user.pictureLocation == None:        pictureLocation = '/static/img/user2.png'    else:        pictureLocation = '/images/' + pictureLocation    if msg.startswith('/'):        if msg.startswith('/test '):            commandArray = msg.split(' ',1)            if len(commandArray) >= 2:                command = commandArray[0]                target = commandArray[1]                msg = 'Test Received - Success: ' + command + ":" + target        elif msg == '/bok':            msg = '<i class="em em-chicken"></i><i class="em em-chicken"></i> BOK BOK BOK <i class="em em-chicken"></i><i class="em em-chicken"></i>'        elif msg.startswith('/ban '):            if current_user.has_role('Admin'):                commandArray = msg.split(' ', 1)                if len(commandArray) >= 2:                    command = commandArray[0]                    target = commandArray[1]                    userQuery = Sec.User.query.filter_by(username=target).first()                    if userQuery != None:                        newBan = banList.banList(room,userQuery.id)                        db.session.add(newBan)                        db.session.commit()                        msg = '<b>*** ' + target + ' has been banned ***</b>'        elif msg.startswith('/unban '):            if current_user.has_role('Admin'):                commandArray = msg.split(' ', 1)                if len(commandArray) >= 2:                    command = commandArray[0]                    target = commandArray[1]                    userQuery = Sec.User.query.filter_by(username=target).first()                    if userQuery != None:                        banQuery = banList.banList.query.filter_by(userID=userQuery.id, channelLoc=room).first()                        if banQuery != None:                            db.session.delete(banQuery)                            db.session.commit()                            msg = '<b>*** ' + target + ' has been unbanned ***</b>'    banQuery = banList.banList.query.filter_by(userID=current_user.id, channelLoc=room).first()    if banQuery == None:        emit('message', {'user': current_user.username, 'image': pictureLocation, 'msg':msg}, room=room)    elif banQuery:        msg = '<b>*** You have been banned and can not send messages ***</b>'        emit('message', {'user': current_user.username, 'image': pictureLocation, 'msg': msg}, broadcast=False)@socketio.on('getServerResources')def get_resource_usage(message):    cpuUsage = psutil.cpu_percent(interval=1)    memoryUsage = psutil.virtual_memory()[2]    diskUsage = psutil.disk_usage('/')[3]    emit('serverResources', {'cpuUsage':cpuUsage,'memoryUsage':memoryUsage, 'diskUsage':diskUsage})init_db_values()if __name__ == '__main__':    app.jinja_env.auto_reload = True    app.config['TEMPLATES_AUTO_RELOAD'] = True    socketio.run(app)