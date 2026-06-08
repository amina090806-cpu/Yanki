import os
import psycopg2
from psycopg2.extras import DictCursor
import bcrypt

from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    flash,
    session
)

from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = 'super_secret_key_for_yanki_project'
MODERATOR_EMAIL = "amina090806@gmail.com"

# =========================================================
# FILES
# =========================================================

UPLOAD_FOLDER = os.path.join('static', 'uploads')

ALLOWED_EXTENSIONS = {
    'png',
    'jpg',
    'jpeg',
    'gif',
    'webp',
    'mp4',
    'mov',
    'avi',
    'mp3',
    'wav'
}

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

os.makedirs(UPLOAD_FOLDER, exist_ok=True)


def allowed_file(filename):

    return (
        '.' in filename
        and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS
    )


def save_uploaded_file(file):

    if not file:
        return None

    if file.filename == '':
        return None

    if not allowed_file(file.filename):
        return None

    filename = secure_filename(file.filename)

    filepath = os.path.join(
        app.config['UPLOAD_FOLDER'],
        filename
    )

    file.save(filepath)

    return '/' + filepath.replace('\\', '/')


# =========================================================
# DATABASE
# =========================================================

def get_db_connection():
    return psycopg2.connect(os.environ.get("DATABASE_URL"))
# =========================================================
# HOME
# =========================================================
# restart
@app.route('/')
def index():

    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=DictCursor)

    # ИСПРАВЛЕНО: добавлено условие AND status = 'published'
    cur.execute("""

        SELECT *
        FROM events
        WHERE event_date >= NOW() AND status = 'published'
        ORDER BY event_date ASC

    """)

    events = cur.fetchall()

    conn.close()

    return render_template(
        'index.html',
        events=events
    )


# =========================================================
# SEARCH
# =========================================================

@app.route('/search')
def search_users():

    query = request.args.get('q', '').strip()

    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=DictCursor)

    users = []

    if query:

        cur.execute("""

            SELECT *
            FROM users
            WHERE LOWER(nickname) LIKE LOWER(%s)
            LIMIT 20

        """, (f'%{query}%',))

        users = cur.fetchall()

    # ИСПРАВЛЕНО: добавлено условие AND status = 'published'
    cur.execute("""

        SELECT *
        FROM events
        WHERE event_date >= NOW() AND status = 'published'
        ORDER BY event_date ASC

    """)

    events = cur.fetchall()

    conn.close()

    return render_template(
        'index.html',
        users=users,
        events=events
    )


# =========================================================
# HELP
# =========================================================

@app.route('/help')
def help():
    return render_template('help.html')


# =========================================================
# PUBLIC PROFILE
# =========================================================

@app.route('/profile/<int:user_id>')
def public_profile(user_id):

    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=DictCursor)

    # USER

    cur.execute("""

        SELECT *
        FROM users
        WHERE id = %s

    """, (user_id,))

    user = cur.fetchone()

    if not user:
        conn.close()
        return redirect(url_for('index'))

    # GALLERY

    cur.execute("""

        SELECT *
        FROM user_gallery
        WHERE user_id = %s
        ORDER BY uploaded_at DESC

    """, (user_id,))

    gallery = cur.fetchall()

    # EVENTS
    # ИСПРАВЛЕНО: добавлено условие AND status = 'published', чтобы не показывать скрытые/отклоненные мероприятия
    cur.execute("""

        SELECT *
        FROM events
        WHERE organizer_id = %s AND status = 'published'
        ORDER BY created_at DESC

    """, (user_id,))

    events = cur.fetchall()

    # SERVICES

    cur.execute("""

        SELECT *
        FROM services
        WHERE user_id = %s
        ORDER BY id DESC

    """, (user_id,))

    portfolio = cur.fetchall()

    conn.close()

    return render_template(
        'public_profile.html',
        user=user,
        gallery=gallery,
        events=events,
        portfolio=portfolio
    )


# =========================================================
# REGISTER
# =========================================================

@app.route('/register', methods=['GET', 'POST'])
def register():

    if request.method == 'POST':

        nickname = request.form.get('nickname')
        email = request.form.get('email')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')

        phone = request.form.get('phone') or None
        city = request.form.get('city') or 'Смоленск'
        role = request.form.get('role')

        if password != confirm_password:

            flash('Пароли не совпадают!')
            return redirect(url_for('register'))

        hashed_password = bcrypt.hashpw(
            password.encode('utf-8'),
            bcrypt.gensalt()
        ).decode('utf-8')

        conn = None

        try:

            conn = get_db_connection()
            cur = conn.cursor(cursor_factory=DictCursor)

            cur.execute("""

                INSERT INTO users (
                    nickname,
                    email,
                    password_hash,
                    phone,
                    city
                )

                VALUES (%s, %s, %s, %s, %s)

                RETURNING id

            """, (

                nickname,
                email,
                hashed_password,
                phone,
                city

            ))

            user_id = cur.fetchone()['id']

            if role:

                cur.execute("""

                    SELECT id
                    FROM roles
                    WHERE name = %s

                """, (role,))

                role_row = cur.fetchone()

                if role_row:

                    cur.execute("""

                        INSERT INTO user_roles (
                            user_id,
                            role_id
                        )

                        VALUES (%s, %s)

                    """, (

                        user_id,
                        role_row['id']

                    ))

            conn.commit()

            flash('Регистрация успешна!')

            return redirect(url_for('login'))

        except Exception as e:

            if conn:
                conn.rollback()

            flash(f'Ошибка: {e}')

        finally:

            if conn:
                conn.close()

    return render_template('registration.html')


# =========================================================
# LOGIN
# =========================================================

@app.route('/login', methods=['GET', 'POST'])
def login():

    if request.method == 'POST':

        email = request.form.get('email')
        password = request.form.get('password')

        conn = None

        try:

            conn = get_db_connection()

            cur = conn.cursor(cursor_factory=DictCursor)

            cur.execute("""

                SELECT *
                FROM users
                WHERE email = %s

            """, (email,))

            user = cur.fetchone()

            if user and bcrypt.checkpw(

                password.encode('utf-8'),
                user['password_hash'].encode('utf-8')

            ):

                session['user_id'] = user['id']

                flash('Вы вошли в аккаунт')

                return redirect(url_for('cabinet'))

            flash('Неверный email или пароль')

        except Exception as e:

            flash(f'Ошибка: {e}')

        finally:

            if conn:
                conn.close()

    return render_template('login.html')


# =========================================================
# LOGOUT
# =========================================================

@app.route('/logout')
def logout():

    session.clear()

    flash('Вы вышли из аккаунта')

    return redirect(url_for('login'))


# =========================================================
# CABINET
# =========================================================

@app.route('/cabinet')
def cabinet():

    if 'user_id' not in session:
        return redirect(url_for('login'))

    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=DictCursor)

    # USER
    cur.execute("""
        SELECT *
        FROM users
        WHERE id = %s
    """, (session['user_id'],))

    user = cur.fetchone()
    is_moderator = (user['email'] == MODERATOR_EMAIL)
    # GALLERY
    cur.execute("""
        SELECT *
        FROM user_gallery
        WHERE user_id = %s
        ORDER BY uploaded_at DESC
    """, (session['user_id'],))

    gallery = cur.fetchall()

    # EVENTS
    cur.execute("""
        SELECT *
        FROM events
        WHERE organizer_id = %s
        ORDER BY created_at DESC
    """, (session['user_id'],))

    events = cur.fetchall()

    # MARKET ITEMS
    cur.execute("""
        SELECT *
        FROM market_items
        WHERE user_id = %s
        ORDER BY created_at DESC
    """, (session['user_id'],))

    market_items = cur.fetchall()

    # VOLUNTEER PROFILE
    cur.execute("""
        SELECT *
        FROM volunteer_profiles
        WHERE user_id = %s
    """, (session['user_id'],))

    volunteer_profile = cur.fetchone()
    
    cur.execute("""
        SELECT ea.*, e.title AS event_title
        FROM event_applications ea
        JOIN events e ON ea.event_id = e.id
        WHERE ea.user_id = %s
        ORDER BY ea.created_at DESC
    """, (session['user_id'],))

    my_applications = cur.fetchall()

    conn.close()

    return render_template(
    'cabinet.html',
    user=user,
    gallery=gallery,
    events=events,
    market_items=market_items,
    volunteer_profile=volunteer_profile,
    is_moderator=is_moderator,
    my_applications=my_applications
)

#МОДЕРАТОР ТЕМКА

@app.route('/moderator_panel')
def moderator_panel():

    if 'user_id' not in session:
        return redirect(url_for('login'))

    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=DictCursor)

    cur.execute("""
        SELECT 1
        FROM user_roles
        WHERE user_id = %s
        AND role_id = 6
    """, (session['user_id'],))

    is_moderator = cur.fetchone()

    if not is_moderator:
        flash('Нет доступа')
        return redirect(url_for('index'))

    cur.execute("""
        SELECT *
        FROM events
        WHERE status = 'moderation'
        ORDER BY created_at DESC
    """)
    events = cur.fetchall()

    cur.execute("""
        SELECT *
        FROM market_items
        WHERE status = 'pending'
        ORDER BY created_at DESC
    """)
    market_items = cur.fetchall()

    cur.execute("""
        SELECT *
        FROM volunteer_profiles
    """)
    volunteers = cur.fetchall()

    conn.close()

    return render_template(
        'moderator_panel.html',
        events=events,
        market_items=market_items,
        volunteers=volunteers
    )


@app.route('/moderator/event/<int:event_id>/approve')
def approve_event(event_id):

    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("""
        UPDATE events
        SET status = 'published'
        WHERE id = %s
    """, (event_id,))

    conn.commit()
    conn.close()

    return redirect(url_for('moderator_panel'))

@app.route('/moderator/event/<int:event_id>/reject')
def reject_event(event_id):

    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("""
        UPDATE events
        SET status = 'rejected'
        WHERE id = %s
    """, (event_id,))

    conn.commit()
    conn.close()

    return redirect(url_for('moderator_panel'))

@app.route('/moderator/market/<int:item_id>/approve')
def approve_market(item_id):

    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("""
        UPDATE market_items
        SET status = 'approved'
        WHERE id = %s
    """, (item_id,))

    conn.commit()
    conn.close()

    return redirect(url_for('moderator_panel'))

@app.route('/moderator/market/<int:item_id>/reject')
def reject_market(item_id):

    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("""
        UPDATE market_items
        SET status = 'rejected'
        WHERE id = %s
    """, (item_id,))

    conn.commit()
    conn.close()

    return redirect(url_for('moderator_panel'))

# =========================================================
# EDIT PROFILE
# =========================================================

@app.route('/edit_profile', methods=['POST'])
def edit_profile():

    if 'user_id' not in session:
        return redirect(url_for('login'))

    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("""

        UPDATE users
        SET
            nickname = %s,
            city = %s,
            phone = %s
        WHERE id = %s

    """, (

        request.form.get('nickname'),
        request.form.get('city'),
        request.form.get('phone'),
        session['user_id']

    ))

    conn.commit()
    conn.close()

    flash('Профиль обновлён')

    return redirect(url_for('cabinet'))


# =========================================================
# PRIVACY
# =========================================================

@app.route('/update_privacy', methods=['POST'])
def update_privacy():

    if 'user_id' not in session:
        return redirect(url_for('login'))

    hide_email = 'hide_email' in request.form
    hide_phone = 'hide_phone' in request.form

    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("""

        UPDATE users
        SET
            hide_email = %s,
            hide_phone = %s
        WHERE id = %s

    """, (

        hide_email,
        hide_phone,
        session['user_id']

    ))

    conn.commit()
    conn.close()

    flash('Настройки приватности обновлены')

    return redirect(url_for('cabinet'))


# =========================================================
# UPLOAD IMAGE
# =========================================================

@app.route('/upload_image/<image_type>', methods=['POST'])
def upload_image(image_type):

    if 'user_id' not in session:
        return redirect(url_for('login'))

    file = request.files.get('file')

    image_path = save_uploaded_file(file)

    if not image_path:

        flash('Ошибка загрузки файла')
        return redirect(url_for('cabinet'))

    conn = get_db_connection()
    cur = conn.cursor()

    if image_type == 'avatar':

        cur.execute("""

            UPDATE users
            SET avatar_url = %s
            WHERE id = %s

        """, (

            image_path,
            session['user_id']

        ))

    else:

        cur.execute("""

            UPDATE users
            SET cover_url = %s
            WHERE id = %s

        """, (

            image_path,
            session['user_id']

        ))

    conn.commit()
    conn.close()

    flash('Изображение загружено')

    return redirect(url_for('cabinet'))


# =========================================================
# UPLOAD GALLERY
# =========================================================

@app.route('/upload_gallery', methods=['POST'])
def upload_gallery():

    if 'user_id' not in session:
        return redirect(url_for('login'))

    file = request.files.get('file')

    image_path = save_uploaded_file(file)

    if not image_path:

        flash('Ошибка загрузки файла')
        return redirect(url_for('cabinet'))

    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("""

        INSERT INTO user_gallery (
            user_id,
            image_url
        )

        VALUES (%s, %s)

    """, (

        session['user_id'],
        image_path

    ))

    conn.commit()
    conn.close()

    flash('Фото добавлено')

    return redirect(url_for('cabinet'))


# =========================================================
# MASTER FLOW
# =========================================================

@app.route('/master/select')
def master_select():

    if 'user_id' not in session:
        return redirect(url_for('login'))

    return render_template('master_role_select.html')


@app.route('/master/setup/<role>')
def master_setup(role):

    if 'user_id' not in session:
        return redirect(url_for('login'))

    allowed_roles = [
        'crafter',
        'photographer',
        'makeup',
        'wigmaker'
    ]

    if role not in allowed_roles:
        return redirect(url_for('master_select'))

    return render_template(
        'master_setup.html',
        role=role
    )


@app.route('/master/save', methods=['POST'])
def save_master_profile():

    if 'user_id' not in session:
        return redirect(url_for('login'))

    conn = get_db_connection()
    cur = conn.cursor()

    role = request.form.get('role')

    cur.execute("""

        UPDATE users
        SET
            master_type = %s,
            master_verified = TRUE
        WHERE id = %s

    """, (

        role,
        session['user_id']

    ))

    cur.execute("""

        INSERT INTO services (
            user_id,
            title,
            description,
            price
        )

        VALUES (%s, %s, %s, %s)

    """, (

        session['user_id'],
        request.form.get('service_title'),
        request.form.get('service_desc'),
        request.form.get('service_price')

    ))

    conn.commit()
    conn.close()

    flash('Портфолио отправлено')

    return redirect(url_for('cabinet'))

#ВОЛОНТЕРЫ

@app.route('/save_volunteer_profile', methods=['POST'])
def save_volunteer_profile():

    if 'user_id' not in session:
        return redirect(url_for('login'))

    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("""

        DELETE FROM volunteer_profiles
        WHERE user_id = %s

    """, (session['user_id'],))

    cur.execute("""

        INSERT INTO volunteer_profiles (

            user_id,
            full_name,
            age,
            experience,
            skills,
            contacts

        )

        VALUES (

            %s,
            %s,
            %s,
            %s,
            %s,
            %s

        )

    """, (

        session['user_id'],

        request.form.get('full_name'),
        request.form.get('age'),
        request.form.get('experience'),
        request.form.get('skills'),
        request.form.get('contacts')

    ))

    cur.execute("""

        UPDATE users
        SET volunteer_verified = TRUE
        WHERE id = %s

    """, (session['user_id'],))

    conn.commit()
    conn.close()

    flash('Анкета волонтёра отправлена')

    return redirect(url_for('cabinet'))

# =========================================================
# CREATE EVENT
# =========================================================

@app.route('/create_event', methods=['POST'])
def create_event():

    if 'user_id' not in session:
        return redirect(url_for('login'))

    stage_photo = save_uploaded_file(
        request.files.get('stage_photo')
    )

    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("""

        INSERT INTO events (

            organizer_id,

            title,
            theme,
            description,
            rules,

            deadline,

            event_date,
            location,

            stage_width,
            stage_depth,
            stage_height,

            stage_photo,

            tables_count,
            chairs_count,

            backstage_available,
            backstage_description,

            basic_light,
            color_light,
            spot_light,

            custom_equipment,

            status

        )

        VALUES (

            %s,

            %s,
            %s,
            %s,
            %s,

            %s,

            %s,
            %s,

            %s,
            %s,
            %s,

            %s,

            %s,
            %s,

            %s,
            %s,

            %s,
            %s,
            %s,

            %s,

            'moderation'

        )

    """, (

        session['user_id'],

        request.form.get('event_title'),
        request.form.get('theme'),
        request.form.get('description'),
        request.form.get('rules'),

        request.form.get('deadline'),

        request.form.get('event_date'),
        request.form.get('location'),

        request.form.get('stage_width'),
        request.form.get('stage_depth'),
        request.form.get('stage_height'),

        stage_photo,

        request.form.get('tables_count'),
        request.form.get('chairs_count'),

        request.form.get('backstage_available') == 'yes',

        request.form.get('backstage_description'),

        'basic_light' in request.form,
        'color_light' in request.form,
        'spot_light' in request.form,

        'custom_equipment' in request.form

    ))

    cur.execute("""

        UPDATE users
        SET organizer_verified = TRUE
        WHERE id = %s

    """, (session['user_id'],))

    conn.commit()
    conn.close()

    flash('Мероприятие создано')

    return redirect(url_for('cabinet'))

#МАРКЕТ

@app.route('/create_market_item', methods=['POST'])
def create_market_item():

    if 'user_id' not in session:
        return redirect(url_for('login'))

    photo = save_uploaded_file(request.files.get('item_photo'))

    if not photo:
        flash('Фото товара обязательно')
        return redirect(url_for('cabinet'))

    conn = get_db_connection()
    cur = conn.cursor()

    # 1. создаём товар (ВСЕГДА pending)
    cur.execute("""
        INSERT INTO market_items (
            user_id,
            name,
            description,
            price,
            quantity,
            photo_url,
            status
        )
        VALUES (%s, %s, %s, %s, %s, %s, 'pending')
    """, (
        session['user_id'],
        request.form.get('item_name'),
        request.form.get('item_description'),
        request.form.get('item_price'),
        request.form.get('item_quantity'),
        photo
    ))

    # 2. ВАЖНО: НЕ делаем auto-verify!
    # (ярмарка = роль, а не факт добавления товара)

    conn.commit()
    conn.close()

    flash('Товар отправлен на модерацию')
    return redirect(url_for('cabinet'))
# =========================================================
# EVENT PAGE
# =========================================================

@app.route('/event/<int:event_id>')
def event_page(event_id):

    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=DictCursor)

    cur.execute("""

        SELECT *
        FROM events
        WHERE id = %s

    """, (event_id,))

    event = cur.fetchone()

    conn.close()

    if not event:
        return redirect(url_for('index'))

    return render_template(
        'event_page.html',
        event=event
    )


# =========================================================
# EVENT APPLICATIONS
# =========================================================

@app.route('/event/applications/<int:event_id>')
def event_applications(event_id):

    if 'user_id' not in session:
        return redirect(url_for('login'))

    conn = get_db_connection()

    cur = conn.cursor(cursor_factory=DictCursor)

    # EVENT

    cur.execute("""

        SELECT *
        FROM events
        WHERE id = %s
        AND organizer_id = %s

    """, (

        event_id,
        session['user_id']

    ))

    event = cur.fetchone()

    if not event:

        conn.close()

        return redirect(url_for('cabinet'))

    # APPLICATIONS

    cur.execute("""

        SELECT *
        FROM event_applications
        WHERE event_id = %s
        ORDER BY
            is_favorite DESC,
            created_at DESC

    """, (event_id,))

    applications = cur.fetchall()

    conn.close()

    return render_template(
        'event_applications.html',
        event=event,
        applications=applications
    )


# =========================================================
# APPLY EVENT
# =========================================================

@app.route('/event/apply/<int:event_id>', methods=['POST'])
def apply_event(event_id):

    if 'user_id' not in session:
        return redirect(url_for('login'))

    conn = get_db_connection()

    cur = conn.cursor(cursor_factory=DictCursor)

    # EVENT

    cur.execute("""

        SELECT *
        FROM events
        WHERE id = %s

    """, (event_id,))

    event = cur.fetchone()

    if not event:

        conn.close()

        return redirect(url_for('index'))
    

    # DEADLINE

    if event['deadline']:

        cur.execute("""

            SELECT NOW() > %s AS closed

        """, (event['deadline'],))

        closed = cur.fetchone()['closed']

        if closed:

            conn.close()

            flash('Подача заявок завершена')

            return redirect(
                url_for(
                    'event_page',
                    event_id=event_id
                )
            )

    # FILES

    rehearsal_video = save_uploaded_file(
        request.files.get('rehearsal_video')
    )

    music_track = save_uploaded_file(
        request.files.get('music_track')
    )

    video_background = save_uploaded_file(
        request.files.get('video_background')
    )

    costume_photo = save_uploaded_file(
        request.files.get('costume_photo')
    )

    # INSERT

    cur.execute("""

        INSERT INTO event_applications (

            event_id,
            user_id,

            application_type,

            full_name,
            nickname,
            phone,
            social_link,

            performance_name,
            comment,

            performance_type,
            performance_description,

            rehearsal_video,
            music_track,
            video_background,
            costume_photo,

            character_reference,

            light_wishes,
            program_wishes,

            assortment_description,
            placement_wishes,

            volunteer_role,

            status,
            is_favorite

        )

        VALUES (

            %s,
            %s,

            %s,

            %s,
            %s,
            %s,
            %s,

            %s,
            %s,

            %s,
            %s,

            %s,
            %s,
            %s,
            %s,

            %s,

            %s,
            %s,

            %s,
            %s,

            %s,

            'pending',
            FALSE

        )

    """, (

        event_id,
        session['user_id'],

        request.form.get('application_type'),

        request.form.get('full_name'),
        request.form.get('nickname'),
        request.form.get('phone'),
        request.form.get('social_link'),

        request.form.get('performance_name'),
        request.form.get('comment'),

        request.form.get('performance_type'),
        request.form.get('performance_description'),

        rehearsal_video,
        music_track,
        video_background,
        costume_photo,

        request.form.get('character_reference'),

        request.form.get('light_wishes'),
        request.form.get('program_wishes'),

        request.form.get('assortment_description'),
        request.form.get('placement_wishes'),

        request.form.get('volunteer_role')

    ))

    conn.commit()
    conn.close()

    flash('Заявка успешно отправлена')

    return redirect(
        url_for(
            'event_page',
            event_id=event_id
        )
    )


# =========================================================
# FAVORITE APPLICATION
# =========================================================

@app.route('/favorite_application/<int:application_id>')
def favorite_application(application_id):

    if 'user_id' not in session:
        return redirect(url_for('login'))

    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("""

        UPDATE event_applications
        SET is_favorite = NOT is_favorite
        WHERE id = %s

    """, (application_id,))

    conn.commit()
    conn.close()

    return redirect(request.referrer)


# =========================================================
# UPDATE APPLICATION STATUS
# =========================================================

@app.route('/update_application_status/<int:application_id>/<status>')
def update_application_status(application_id, status):

    if 'user_id' not in session:
        return redirect(url_for('login'))

    allowed_statuses = [
        'pending',
        'checking',
        'accepted',
        'rejected',
        'reserve'
    ]

    if status not in allowed_statuses:
        return redirect(request.referrer)

    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("""

        UPDATE event_applications
        SET status = %s
        WHERE id = %s

    """, (

        status,
        application_id

    ))

    conn.commit()
    conn.close()

    return redirect(request.referrer)

@app.route('/edit_application/<int:application_id>', methods=['GET', 'POST'])
def edit_application(application_id):

    if 'user_id' not in session:
        return redirect(url_for('login'))

    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=DictCursor)

    cur.execute("""

        SELECT *
        FROM event_applications
        WHERE id = %s
        AND user_id = %s

    """, (

        application_id,
        session['user_id']

    ))

    application = cur.fetchone()

    if not application:

        conn.close()

        return redirect(url_for('cabinet'))

    if request.method == 'POST':

        cur.execute("""

            UPDATE event_applications

            SET

                comment = %s,
                light_wishes = %s,
                program_wishes = %s

            WHERE id = %s

        """, (

            request.form.get('comment'),
            request.form.get('light_wishes'),
            request.form.get('program_wishes'),
            application_id

        ))

        conn.commit()
        conn.close()

        flash('Заявка обновлена')

        return redirect(url_for('cabinet'))

    conn.close()

    return render_template(
        'edit_application.html',
        application=application
    )

@app.route('/master/crafter')
def master_crafter():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    return render_template('master_crafter.html')
@app.route('/master/photographer')
def master_photographer():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    return render_template('master_photographer.html')
@app.route('/master/makeup')
def master_makeup():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    return render_template('master_makeup.html')
@app.route('/master/wigmaker')
def master_wigmaker():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    return render_template('master_wigmaker.html')

@app.route('/master/edit')
def master_edit():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    master_type = request.args.get('type')
    section = request.args.get('section', 'portfolio')

    allowed = ['crafter', 'photographer', 'makeup', 'wigmaker']

    if master_type not in allowed:
        return redirect(url_for('master_select'))

    return render_template(
        'master_edit.html',
        master_type=master_type,
        section=section
    )

@app.route('/master/save_portfolio', methods=['POST'])
def save_portfolio():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    image = save_uploaded_file(request.files.get('image'))

    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("""
        INSERT INTO master_portfolio (
            user_id,
            title,
            description,
            image_url
        )
        VALUES (%s, %s, %s, %s)
    """, (
        session['user_id'],
        request.form.get('title'),
        request.form.get('description'),
        image
    ))

    conn.commit()
    conn.close()

    return redirect(url_for('cabinet'))




# =========================================================
# START
# =========================================================

if __name__ == '__main__':
    app.run(debug=True)