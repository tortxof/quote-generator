import os

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

from models import (
    db,
    User,
    Quote,
    Collection,
    QuoteCollection,
    IntegrityError,
    fn,
)
from playhouse.shortcuts import model_to_dict
from forms import (
    SignupForm,
    LoginForm,
    QuoteAddForm,
    QuoteEditForm,
    CollectionAddForm,
    CollectionEditForm,
)

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
        collections = Collection.select().where(
            Collection.user == current_user.get_id(),
        )
        return render_template(
            'collections.html',
            form=form,
            collections=collections,
        )

@app.route('/collection/<collection_name>', methods=['GET', 'POST'])
@login_required
def collection(collection_name):
    try:
        collection = Collection.get(
            Collection.name == collection_name,
            Collection.user == current_user.get_id(),
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
            collection_name = collection_name,
        )

@app.route('/api/collection/<collection_name>')
def collection_json(collection_name):
    collection = Collection.get(Collection.name == collection_name)
    return jsonify({'quotes': list(
        Quote.select().join(QuoteCollection).where(
            QuoteCollection.collection == collection,
        ).dicts()
    )})

@app.route('/api/collection/<collection_name>/random')
def collection_random_json(collection_name):
    collection = Collection.get(Collection.name == collection_name)
    return jsonify(model_to_dict(
        Quote.select().join(QuoteCollection).where(
            QuoteCollection.collection == collection,
        ).order_by(fn.Random()).limit(1)[0],
        recurse = False,
    ))
