from flask_wtf import FlaskForm
from wtforms import (
    StringField,
    PasswordField,
    TextAreaField,
    HiddenField,
    BooleanField,
    SelectMultipleField,
)
from wtforms.validators import InputRequired, Email, Length, Regexp

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
    collections = SelectMultipleField('Collections', coerce=str)

class QuoteEditForm(QuoteAddForm):
    id = HiddenField()
    form_delete = BooleanField('Delete', default=False)

class CollectionAddForm(FlaskForm):
    name = StringField(
        'Name',
        [
            InputRequired(),
            Length(min=1, max=255),
            Regexp(
                '^[a-zA-Z0-9_-]*$',
                message = 'Allowed characters: A-Z a-z 0-9 _ -',
            ),
        ],
    )

class CollectionEditForm(CollectionAddForm):
    form_delete = BooleanField('Delete', default=False)
