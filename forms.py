from wtforms import Form, TextField, StringField, PasswordField, validators, SubmitField

class RegistrationForm(Form):
	username = TextField('Username', [validators.Length(min=4, max=20)])
	password = PasswordField('Password', [validators.Length(min=4, max=20),
										  validators.EqualTo('confirm', message='Passwords must match')
										 ])
	confirm = PasswordField('Re-enter Password')


