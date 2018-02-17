import os

from flask import (
    Flask,
    render_template,
    redirect,
    url_for,
    request,
    flash,
)
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import (
    LoginManager,
    current_user,
    login_user,
    logout_user,
    login_required,
)

from models import db, User, Quote, Collection, QuoteCollection, IntegrityError
from forms import SignupForm, LoginForm, QuoteAddForm, CollectionAddForm

app = Flask(__name__)

app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY') or 'DEBUGSECRETKEY'

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

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))

@app.route('/quotes', methods=['GET', 'POST'])
@login_required
def quotes():
    form = QuoteAddForm()
    if form.validate_on_submit():
        with db.atomic() as txn:
            Quote.create(
                content = form.content.data,
                author = form.author.data,
                user = current_user.get_id(),
            )
        return redirect(url_for('quotes'))
    else:
        quotes = Quote.select().where(Quote.user == current_user.get_id())
        return render_template('quotes.html', form=form, quotes=quotes)

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
        collections = Collection.select().where(
            Collection.user == current_user.get_id(),
        )
        return render_template(
            'collections.html',
            form=form,
            collections=collections,
        )
