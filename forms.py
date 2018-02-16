from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, TextAreaField
from wtforms.validators import InputRequired, Email, Length

class SignupForm(FlaskForm):
    email = StringField(
        'Email',
        [InputRequired(), Length(max=255), Email()],
    )
    password = PasswordField(
        'Password',
        [InputRequired(), Length(min=8, max=1024)],
    )

class LoginForm(FlaskForm):
    email = StringField(
        'Email',
        [InputRequired(), Length(max=255), Email()],
    )
    password = PasswordField(
        'Password',
        [InputRequired(), Length(min=8, max=1024)],
    )

class QuoteAddForm(FlaskForm):
    content = TextAreaField('Quote', [InputRequired(), Length(max=4096)])
    author = StringField('Author', [Length(max=255)])

class CollectionAddForm(FlaskForm):
    name = StringField('Name', [InputRequired(), Length(max=255)])
