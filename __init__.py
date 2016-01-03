from flask import Flask, flash, session, redirect, url_for, render_template, request
from flask.ext.socketio import SocketIO, emit, join_room, leave_room
from functools import wraps
from passlib.hash import sha256_crypt
from forms import RegistrationForm
from MySQLdb import escape_string
from dbconnection import connection
from random import randrange
import gc

def create_app(debug=False):
	app = Flask(__name__)
	app.debug = debug
	app.config['SECRET_KEY'] = "@s!t2)&b$&bwmhbey_i^=dle7pb%bve50hv@9*v5i!^pu+!6kv"
	socketio.init_app(app)
	return app

socketio = SocketIO()
app = create_app(debug=True)
active_users = {}
active_users['lobby'] = set()


def login_required(f):
	'''decorator for login required pages'''
	@wraps(f)
	def wrap(*args, **kwargs):
		if 'logged_in' in session:
			return f(*args, **kwargs)
		else:
			flash("You can't do this if you're not logged in")
			return redirect(url_for('index'))

	return wrap	

def logout_required(f):
	'''logout required decorator, similar to the above one.
	In fact, there's no link in the header for logout required pages on the user is logged in 
	but if someone types into the address bar directly, they may go to the registration page
	while they're already logged in.'''
	@wraps(f)
	def wrap(*args, **kwargs):
		if 'logged_in' in session:
			flash("You can't do this if you're already logged in")
			return redirect(url_for('index'))
		else:
			return f(*args, **kwargs)
	return wrap	


	
@socketio.on('joined', namespace='/chat')
def joined(message):
	'''A new user has entered the room, status message sent to everybody in the room.
	Also, the list of active users is updated and setn to everybody in the room'''
	room = session.get('room')
	join_room(room)
	emit('status', {'msg': session.get('name') + ' has entered the room.'}, room=room)
	emit('active', {'msg': 	'\n'.join(list(active_users[room])) }, room=room)

@socketio.on('text', namespace='/chat')
def sent(message):
	'''New chat message gets sent to everybody in the room. Also if there are more than 
	one logged in user in the room, log the message'''
	room = session.get('room')
	emit('message', {'msg': session.get('name') + ':' + message['msg']}, room=room)

	#log the message only if the user is not the only logged in user in the room
	if len(active_users[session['room']]) > 1:
		# is it too costly to open/close a connection every time?
		ChatCursor,ChatConn = connection()
		ChatCursor.execute("INSERT INTO chatlog (sender,receiver,room,message) VALUES (%s, %s, %s, %s)", 
							[session['name'], 
							 str(list( active_users[session['room']] - set([session['name']]) )), 
							 room, 
							 message['msg'] 
							])
		ChatConn.commit()
		ChatCursor.close()
		ChatConn.close()
		gc.collect()
		
@socketio.on('left', namespace='/chat')
def left(message):
	'''A user has left the room. Broadcast the status message to everybody in the room
	and update&broadcast the list of active logged-in users to the room'''	
	room = session.get('room')
	leave_room(room)
	active_users[room].remove(session['name'])
	emit('status', {'msg': session.get('name') + ' has left the room.'}, room=room)
	emit('active', {'msg': 	'\n'.join(list(active_users[room])) }, room=room)
	



@app.route('/', methods=['GET', 'POST'])
def index():
	'''The main page. Description of the project etc in the html file'''
	try: 
		return render_template('index.html')
	except Exception as e:
		return render_template("500.html", error = e)

@app.route('/chat/')
def chat():
	'''The chat room. if the user is not logged in, give a random guest name. If the user
	is logged in, append to the logged-in users list -- this gets to be displayed on the left
	hand side of the chat room page. '''
	try:
		if 'logged_in' not in session or  ('logged_in' in session and session['logged_in'] == False):
			guest_username = "Guest_" + str(randrange(10000))
			session['name'] = guest_username
		else:
			active_users['lobby'].add(session['name'])

		if 'room' not in session: session['room'] = 'lobby'
		
		# could this happen?
		if session['name'] == '' or session['room'] == '':
			return redirect(url_for('index'))
		
		return render_template('chat.html', name=session['name'], room=session['room'])
	except Exception as e:
		return render_template("500.html", error = e)
	
@app.route('/logout/')
@login_required
def logout():
	'''Logging out the user and send them to the main page. Clear the information 
	stored in the session object. Not much logic is needed here, except the 
	login_required decorator.'''
	session.clear()
	flash("You have been logged out")
	gc.collect()
	return redirect(url_for('index'))
	
@app.route('/profile/')
@login_required
def profile_page():
	'''Connect to the users database to get the registered time.
	Connect to the chat logs database to get the recent chat logs of the user'''
	try:
		cursor,conn = connection()
		cursor.execute("SELECT * FROM users WHERE username = (%s)", [session['name']])
		user = dict(zip(map(lambda x:x[0], cursor.description), cursor.fetchone()))
		user["registered_time_displayform"] = user["registered_time"].strftime('%Y-%m-%d')
		cursor.execute("SELECT * FROM chatlog WHERE (receiver LIKE %s OR sender = %s) ORDER BY messageid DESC LIMIT 20;", 							["%"+session['name']+"%", 
						 session['name']
						])
		namespace = map(lambda x:x[0], cursor.description)
		user['chatlog'] = cursor.fetchall()
		return render_template('profile.html',user = user)
	except Exception as e:
		return render_template("500.html", error = e)	

@app.route('/login/', methods=["GET","POST"])
@logout_required
def login_page():
	'''The login page. If the user inputs a login&password, first check if the 
	username exists, if so check the password and send the user to the chat room
	after updating the session and active_users. Else, display "invalid credentials" 
	and render the template again. It's easy to flash different error messages for
	invalid username and invalid password, but that feels hacker-friendly. Easy to
	change anyway.'''
	try:
		if request.method == "POST":
			cursor,conn = connection()
			user_exists = cursor.execute("SELECT * FROM users WHERE username = (%s)", [request.form["username"]])
			# first see if the username exists
			if int(user_exists) > 0:
				# puts together the namespace and the values from the db... safer than doing things like row[2] assuming order etc.
				user = dict(zip(map(lambda x:x[0], cursor.description), cursor.fetchone()))
				# see if the password also checks out
				if sha256_crypt.verify(request.form['password'], user['password']):	
					session['logged_in'] = True
					session['name'] = user['username']
					active_users['lobby'].add(session['name'])
					flash("You are now logged in")
					return redirect(url_for("chat"))
				
			else:
				flash('Invalid credentials, please try again.')
				return render_template("login.html") 
				
		return render_template("login.html") 		
	except Exception as e:
		return render_template("500.html", error = e)

	
@app.route('/register/',methods=['GET','POST'])
@logout_required
def registration_page():
	'''With validated username and password fields from the form, check if 
	the username already exists. After registering update session and active_users
	and send the user to the chat page.'''
	try:
		form = RegistrationForm(request.form)
		# form.validate checks for the length of the username and password, and two password fields 
		# being equal to each other.
		if request.method == "POST" and form.validate():
			username = str(form.username.data)
			passwd =  sha256_crypt.encrypt((str(form.password.data)))
			cursor,conn = connection()
			#check if the user exists
			user_exists = cursor.execute("SELECT * FROM users WHERE username = (%s)", [username])
			if int(user_exists) > 0:
				flash("Username is already taken, please pick another one.")
				return render_template('register.html',form = form)
			
			else:
				if username.startswith('Guest_'):
					flash("Guest_* usernames are for guests, you deserve better.")				
					return render_template('register.html',form = form)
				
				cursor.execute("INSERT INTO users (username,password) VALUES (%s, %s)", [username, passwd])
				conn.commit()			
				cursor.close()
				conn.close()
				gc.collect()
				
				session['logged_in'] = True
				session['name'] = username
				flash("Thanks for registering!")
				active_users['lobby'].add(session['name'])
				return redirect(url_for('chat'))
		else:
			return render_template('register.html', form = form)
		
	except Exception as e:
		return render_template("500.html", error = e)	
	
	
@app.errorhandler(404)
def page_not_found(e):
	return render_template("404.html")

if __name__ == '__main__':
	socketio.run(app,host='0.0.0.0')

