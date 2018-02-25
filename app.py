import os
import time

import requests
from itsdangerous import URLSafeSerializer, BadSignature
from flask import (
    Flask,
    render_template,
    redirect,
    url_for,
    request,
    flash,
    jsonify,
)
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import (
    LoginManager,
    current_user,
    login_user,
    logout_user,
    login_required,
)
from flask_s3 import FlaskS3
from flask_assets import Environment, Bundle
from playhouse.shortcuts import model_to_dict
from zappa.async import task

from models import (
    db,
    User,
    Quote,
    Collection,
    QuoteCollection,
    IntegrityError,
    fn,
    JOIN,
)
from forms import (
    SignupForm,
    LoginForm,
    ForgotPasswordForm,
    ChangePasswordForm,
    QuoteAddForm,
    QuoteEditForm,
    CollectionAddForm,
    CollectionEditForm,
)

app = Flask(__name__)

app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY') or 'DEBUGSECRETKEY'
app.config['APP_URL'] = os.environ.get('APP_URL')
app.config['MAILGUN_DOMAIN'] = os.environ.get('MAILGUN_DOMAIN')
app.config['MAILGUN_KEY'] = os.environ.get('MAILGUN_KEY')
app.config['FLASKS3_CDN_DOMAIN'] = os.environ.get('FLASKS3_CDN_DOMAIN')
app.config['FLASKS3_BUCKET_NAME'] = os.environ.get('FLASKS3_BUCKET_NAME')
app.config['FLASKS3_HEADERS'] = {'Cache-Control': 'max-age=31536000'}
app.config['FLASKS3_GZIP'] = True
app.config['FLASK_ASSETS_USE_S3'] = True

if os.environ.get('FLASK_DEBUG'):
    app.config['ASSETS_DEBUG'] = True
    app.config['FLASK_ASSETS_USE_S3'] = False

s3 = FlaskS3(app)
assets = Environment(app)
assets.register(
    'css_all',
    Bundle('main.css', output='main.%(version)s.css'),
)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

@login_manager.user_loader
def load_user(user_id):
    try:
        user = User.get(User.id == user_id)
    except User.DoesNotExist:
        return None
    return user

@app.before_request
def _db_connect():
    db.connect(reuse_if_open=True)

@app.teardown_request
def _db_close(exc):
    if not db.is_closed():
        db.close()

cors_header = {'Access-Control-Allow-Origin': '*'}

@task
def send_email(domain, key, data):
    requests.post(
        f"https://api.mailgun.net/v3/{domain}/messages",
        auth = ('api', key),
        data = data,
    )

def send_recovery_email(email):
    s = URLSafeSerializer(app.config['SECRET_KEY'])
    token = s.dumps({
        'time': int(time.time()),
        'email': email,
    })
    email_data = {
        'from': f"Quote Generator <noreply@{app.config['MAILGUN_DOMAIN']}>",
        'to': email,
        'subject': 'Quote Generator Password Recovery',
        'html': render_template('forgot_email.html', token=token),
    }
    send_email(
        domain = app.config['MAILGUN_DOMAIN'],
        key = app.config['MAILGUN_KEY'],
        data = email_data,
    )

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    form = SignupForm()
    if form.validate_on_submit():
        with db.atomic() as txn:
            try:
                User.create(
                    email = form.email.data,
                    password = generate_password_hash(form.password.data),
                )
            except IntegrityError:
                flash('An account with that email already exists.')
                return redirect(url_for('signup'))
        flash('Account created.')
        return redirect(url_for('login'))
    else:
        return render_template('signup.html', form=form)

@app.route('/login', methods=['GET', 'POST'])
def login():
    form = LoginForm()
    if form.validate_on_submit():
        try:
            user = User.get(User.email == form.email.data)
        except User.DoesNotExist:
            flash('Incorrect email or password.')
            return redirect(url_for('login'))
        if check_password_hash(user.password, form.password.data):
            login_user(user)
            return redirect(url_for('index'))
        else:
            flash('Incorrect email or password.')
            return redirect(url_for('login'))
    else:
        return render_template('login.html', form=form)

@app.route('/forgot', methods=['GET', 'POST'])
def forgot():
    form = ForgotPasswordForm()
    if form.validate_on_submit():
        try:
            user = User.get(User.email == form.email.data)
        except User.DoesNotExist:
            flash('No account with that email was found.')
            return redirect(url_for('forgot'))
        send_recovery_email(form.email.data)
        flash('A recovery link will be sent to your email.')
        return redirect(url_for('index'))
    else:
        return render_template('forgot.html', form=form)

@app.route('/recover-password/<token>', methods=['GET', 'POST'])
def recover_password(token):
    s = URLSafeSerializer(app.config['SECRET_KEY'])
    try:
        token_data = s.loads(token)
    except BadSignature:
        flash('Failed to validate token.')
        return redirect(url_for('index'))
    if token_data['time'] + 600 < int(time.time()):
        flash('That link has expired')
        return redirect(url_for('forgot'))
    form = ChangePasswordForm()
    if form.validate_on_submit():
        try:
            user = User.get(User.email == token_data['email'])
        except User.DoesNotExist:
            flash('That user does not exist.')
            return redirect(url_for('index'))
        user.password = generate_password_hash(form.password.data)
        user.save()
        flash('Your password has been updated.')
        return redirect(url_for('login'))
    else:
        return render_template(
            'recover_password.html',
            form = form,
            token_data = token_data,
            token = token,
        )

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))

@app.route('/quotes', methods=['GET', 'POST'])
@login_required
def quotes():
    form = QuoteAddForm()
    form.collections.choices = [
        (collection.name, collection.name)
        for collection in Collection.select().where(
            Collection.user == current_user.get_id()
        )
    ]
    if form.validate_on_submit():
        with db.atomic() as txn:
            quote = Quote.create(
                content = form.content.data,
                author = form.author.data,
                user = current_user.get_id(),
            )
            for collection_name in form.collections.data:
                collection = Collection.get(
                    Collection.name == collection_name,
                    Collection.user == current_user.get_id(),
                )
                QuoteCollection.create(
                    quote = quote,
                    collection = collection,
                )
        return redirect(url_for('quotes'))
    else:
        quotes = Quote.select().where(Quote.user == current_user.get_id())
        return render_template('quotes.html', form=form, quotes=quotes)

@app.route('/quotes/<quote_id>', methods=['GET', 'POST'])
@login_required
def quote(quote_id):
    try:
        quote = Quote.get(
            Quote.id == quote_id,
            Quote.user == current_user.get_id(),
        )
    except Quote.DoesNotExist:
        flash('Quote not found')
        return redirect(url_for('quotes'))
    quote_collections = [
        collection.name
        for collection in Collection.select().join(QuoteCollection).where(
            QuoteCollection.quote == quote,
        )
    ]
    quote.collections = quote_collections
    form = QuoteEditForm(obj=quote)
    form.collections.choices = [
        (collection.name, collection.name)
        for collection in Collection.select().where(
            Collection.user == current_user.get_id()
        )
    ]
    if form.validate_on_submit():
        if form.id.data != quote_id:
            flash('Quote ID mismatch!')
            return redirect(url_for('quotes'))
        if form.form_delete.data:
            quote.delete_instance(recursive=True)
            flash('Quote deleted.')
            return redirect(url_for('quotes'))
        quote.content = form.content.data
        quote.author = form.author.data
        quote.save()
        if set(quote_collections) != set(form.collections.data):
            flash('Collections updated.')
            QuoteCollection.delete().where(
                QuoteCollection.quote == quote,
            ).execute()
            with db.atomic() as txn:
                for collection_name in form.collections.data:
                    QuoteCollection.create(
                        quote = quote,
                        collection = Collection.get(
                            Collection.name == collection_name,
                        ),
                    )
        flash('Quote updated.')
        return redirect(url_for('quotes'))
    else:
        return render_template('quote.html', form=form)

@app.route('/collections', methods=['GET', 'POST'])
@login_required
def collections():
    form = CollectionAddForm()
    if form.validate_on_submit():
        with db.atomic() as txn:
            try:
                Collection.create(
                    name = form.name.data,
                    user = current_user.get_id(),
                )
            except IntegrityError:
                flash('A collection with that name already exists.')
        return redirect(url_for('collections'))
    else:
        collections = (
            Collection.select(
                Collection,
                fn.COUNT(QuoteCollection.id).alias('quote_count'),
            )
            .join(QuoteCollection, JOIN.LEFT_OUTER)
            .group_by(Collection)
            .where(
                Collection.user == current_user.get_id(),
            )
        )
        return render_template(
            'collections.html',
            form = form,
            collections = collections,
        )

@app.route('/collection/<collection_name>', methods=['GET', 'POST'])
@login_required
def collection(collection_name):
    try:
        collection = (
            Collection.select(Collection, Quote)
            .join(QuoteCollection, JOIN.LEFT_OUTER)
            .join(Quote, JOIN.LEFT_OUTER)
            .where(
                Collection.name == collection_name,
                Collection.user == current_user.get_id(),
            )
            .get()
        )
    except Collection.DoesNotExist:
        flash('Collection not found')
        return redirect(url_for('collections'))
    form = CollectionEditForm(obj=collection)
    if form.validate_on_submit():
        if form.form_delete.data:
            collection.delete_instance(recursive=True)
            flash('Collection deleted.')
            return redirect(url_for('collections'))
        collection.name = form.name.data
        try:
            collection.save()
        except IntegrityError:
            flash('A collection with that name already exists.')
            return redirect(url_for('collections'))
        flash('Collection updated.')
        return redirect(url_for('collections'))
    else:
        return render_template(
            'collection.html',
            form = form,
            collection = collection,
        )

@app.route('/api/collection/<collection_name>')
def collection_json(collection_name):
    try:
        collection = Collection.get(Collection.name == collection_name)
    except Collection.DoesNotExist:
        return jsonify({'message': 'Collection not found.'}), 404, cors_header
    quotes = (
        Quote.select(
            Quote.content,
            Quote.author,
            Quote.id,
        )
        .join(QuoteCollection)
        .where(
            QuoteCollection.collection == collection,
        )
    )
    return jsonify({'quotes': list(quotes.dicts())}), cors_header

@app.route('/api/collection/<collection_name>/random')
def collection_random_json(collection_name):
    try:
        quote = (
            Quote.select()
            .join(QuoteCollection)
            .join(Collection)
            .where(
                Collection.name == collection_name,
            )
            .order_by(fn.Random())
            .get()
        )
    except Quote.DoesNotExist:
        return jsonify(
            {'message': 'There are no quotes in that collection.'}
        ), 404, cors_header
    return jsonify(model_to_dict(
        quote,
        recurse = False,
        exclude = [Quote.user],
    )), cors_header

@app.route('/api/quote/<quote_id>')
def quote_json(quote_id):
    try:
        quote = Quote.get(Quote.id == quote_id)
    except Quote.DoesNotExist:
        return jsonify({'message': 'Quote not found.'}), 404, cors_header
    return jsonify(model_to_dict(
        quote,
        recurse=False,
        exclude=[Quote.user],
    )), cors_header
