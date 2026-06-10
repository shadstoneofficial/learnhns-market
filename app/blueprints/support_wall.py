import secrets
from datetime import datetime
from functools import wraps
from urllib.parse import urlparse

from flask import Blueprint, current_app, jsonify, redirect, render_template, request, url_for

from app.auth import current_account, login_required
from app.models import Account, SupportWallPost, db

support_wall_bp = Blueprint('support_wall', __name__)

POST_STATUSES = {'pending', 'pending_review', 'needs_consent', 'approved', 'rejected', 'hidden'}
CONSENT_STATUSES = {'self_submitted', 'explicit_consent', 'needs_consent', 'unknown'}
SOURCE_CHANNELS = {'self', 'telegram', 'x', 'email', 'discord', 'in-person', 'other'}
VERIFICATION_STATUSES = {'unverified', 'gfavip_logged_in', 'verified_hns_name', 'admin_attested', 'pending_hns_txt'}
SUPPORT_WALL_ROLES = {'none', 'reviewer', 'admin'}


def _support_wall_admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        account = current_account()
        if not _is_support_wall_admin(account):
            return render_template(
                'account_error.html',
                message='This page is limited to support-wall admins.',
            ), 403
        return view(*args, **kwargs)
    return wrapped


def _is_support_wall_admin(account):
    if not account:
        return False

    ids = current_app.config.get('SUPPORT_WALL_ADMIN_GFAVIP_IDS') or set()
    emails = current_app.config.get('SUPPORT_WALL_ADMIN_EMAILS') or set()
    usernames = current_app.config.get('SUPPORT_WALL_ADMIN_USERNAMES') or set()

    return (
        account.support_wall_role == 'admin'
        or account.gfavip_user_id in ids
        or (account.email and account.email.lower() in emails)
        or (account.username and account.username.lower() in usernames)
    )


@support_wall_bp.route('/support-wall/submit', methods=['GET', 'POST'])
def submit():
    account = current_account()
    if request.method == 'POST':
        mode = request.form.get('submit_mode') or 'gfavip'
        if mode == 'gfavip' and not account:
            return redirect(url_for('account.login_page', next=url_for('support_wall.submit')))

        post, errors = _post_from_form(account=account, submitted_by=account, txt_mode=(mode == 'hns_txt'))
        if errors:
            return render_template(
                'support_wall_submit.html',
                account=account,
                errors=errors,
                form=request.form,
                post=None,
            ), 400

        db.session.add(post)
        db.session.commit()
        return render_template('support_wall_submitted.html', post=post)

    return render_template('support_wall_submit.html', account=account, errors=[], form={}, post=None)


@support_wall_bp.route('/account/support-wall')
@login_required
def my_posts():
    account = current_account()
    posts = (
        SupportWallPost.query
        .filter_by(account_id=account.id)
        .order_by(SupportWallPost.created_at.desc())
        .all()
    )
    return render_template('support_wall_my_posts.html', posts=posts)


@support_wall_bp.route('/admin/support-wall')
@login_required
@_support_wall_admin_required
def admin_index():
    status = request.args.get('status') or 'pending'
    query = SupportWallPost.query
    if status != 'all':
        query = query.filter_by(status=status)
    posts = query.order_by(SupportWallPost.created_at.desc()).all()
    counts = {
        item: SupportWallPost.query.filter_by(status=item).count()
        for item in ['pending', 'pending_review', 'needs_consent', 'approved', 'rejected', 'hidden']
    }
    return render_template('support_wall_admin.html', posts=posts, status=status, counts=counts)


@support_wall_bp.route('/admin/support-wall/admins', methods=['GET', 'POST'])
@login_required
@_support_wall_admin_required
def admin_roles():
    message = None
    error = None
    if request.method == 'POST':
        lookup = str(request.form.get('account_lookup') or '').strip()
        role = str(request.form.get('support_wall_role') or 'none').strip()
        if role not in SUPPORT_WALL_ROLES:
            error = 'Unsupported support-wall role.'
        elif not lookup:
            error = 'Enter a GFAVIP user id, email, or username.'
        else:
            account = _find_account(lookup)
            if not account:
                error = 'No account matched that GFAVIP id, email, or username. The user may need to log in once first.'
            else:
                account.support_wall_role = role
                db.session.commit()
                message = f'Updated {account.username or account.email or account.gfavip_user_id} to {role}.'

    accounts = (
        Account.query
        .filter(Account.support_wall_role != 'none')
        .order_by(Account.support_wall_role.desc(), Account.username.asc(), Account.email.asc())
        .all()
    )
    return render_template('support_wall_admin_roles.html', accounts=accounts, message=message, error=error)


@support_wall_bp.route('/admin/support-wall/new', methods=['GET', 'POST'])
@login_required
@_support_wall_admin_required
def admin_new():
    admin = current_account()
    if request.method == 'POST':
        post, errors = _post_from_form(
            account=None,
            submitted_by=admin,
            on_behalf=True,
            admin_mode=True,
        )
        if errors:
            return render_template('support_wall_admin_form.html', errors=errors, form=request.form, post=None), 400
        db.session.add(post)
        db.session.commit()
        return redirect(url_for('support_wall.admin_edit', post_id=post.id))
    return render_template('support_wall_admin_form.html', errors=[], form={}, post=None)


@support_wall_bp.route('/admin/support-wall/<int:post_id>', methods=['GET', 'POST'])
@login_required
@_support_wall_admin_required
def admin_edit(post_id):
    post = SupportWallPost.query.get_or_404(post_id)
    admin = current_account()
    if request.method == 'POST':
        errors = _update_post_from_admin_form(post, admin)
        if errors:
            return render_template('support_wall_admin_form.html', errors=errors, form=request.form, post=post), 400
        db.session.commit()
        return redirect(url_for('support_wall.admin_edit', post_id=post.id))
    return render_template('support_wall_admin_form.html', errors=[], form={}, post=post)


@support_wall_bp.route('/admin/support-wall/<int:post_id>/<action>', methods=['POST'])
@login_required
@_support_wall_admin_required
def admin_action(post_id, action):
    post = SupportWallPost.query.get_or_404(post_id)
    admin = current_account()
    if action == 'approve':
        post.status = 'approved'
        post.approved_at = datetime.utcnow()
        post.approved_by_account_id = admin.id
        if post.verification_status == 'pending_hns_txt':
            post.verification_status = 'admin_attested'
    elif action in {'reject', 'hide', 'pending'}:
        post.status = {'reject': 'rejected', 'hide': 'hidden', 'pending': 'pending'}[action]
        if action != 'approve':
            post.approved_at = None if action in {'reject', 'pending'} else post.approved_at
    else:
        return render_template('account_error.html', message='Unsupported support-wall action.'), 400
    db.session.commit()
    return redirect(request.referrer or url_for('support_wall.admin_index'))


@support_wall_bp.route('/api/support-wall')
@support_wall_bp.route('/api/v2/support-wall')
def api_support_wall():
    posts = (
        SupportWallPost.query
        .filter_by(status='approved')
        .order_by(SupportWallPost.approved_at.desc(), SupportWallPost.created_at.desc())
        .all()
    )
    response = jsonify({
        'entries': [_public_payload(post) for post in posts],
        'count': len(posts),
        'generatedAt': datetime.utcnow().isoformat() + 'Z',
    })
    response.headers['Cache-Control'] = f"public, max-age={current_app.config.get('SUPPORT_WALL_API_CACHE_SECONDS', 60)}"
    return response


def _post_from_form(account=None, submitted_by=None, on_behalf=False, admin_mode=False, txt_mode=False):
    errors = []
    public_name = _clean_text(request.form.get('public_name'), 120)
    role = _clean_text(request.form.get('role'), 80)
    location = _clean_text(request.form.get('location'), 120, required=False)
    message = _clean_text(request.form.get('message'), 700)
    link = _clean_url(request.form.get('link'), errors)
    hns_name = _clean_hns_name(request.form.get('hns_name'), errors, required=txt_mode)

    if not public_name:
        errors.append('Name or handle is required.')
    if not role:
        errors.append('Role is required.')
    if not message:
        errors.append('Message is required.')
    if not admin_mode and request.form.get('consent') != 'yes':
        errors.append('Please confirm the message may be published publicly.')

    if errors:
        return None, errors

    status = request.form.get('status') if admin_mode else 'pending'
    if status not in POST_STATUSES:
        status = 'pending'

    consent_status = request.form.get('consent_status') if admin_mode else 'self_submitted'
    if consent_status not in CONSENT_STATUSES:
        consent_status = 'unknown'

    source_channel = request.form.get('source_channel') if admin_mode else ('self' if not txt_mode else 'other')
    if source_channel not in SOURCE_CHANNELS:
        source_channel = 'other'

    verification_status = 'gfavip_logged_in' if account else 'unverified'
    verification_method = 'gfavip' if account else None
    verification_nonce = None
    verification_payload = None
    if txt_mode:
        verification_status = 'pending_hns_txt'
        verification_method = 'hns_txt'
        verification_nonce = f"hnswall={datetime.utcnow().strftime('%Y%m%d')}:{secrets.token_urlsafe(18)}"
        verification_payload = f"Add TXT record to {hns_name}: {verification_nonce}"

    if admin_mode and request.form.get('verification_status') in VERIFICATION_STATUSES:
        verification_status = request.form.get('verification_status')
        verification_method = request.form.get('verification_method') or verification_method

    post = SupportWallPost(
        account_id=account.id if account else None,
        submitted_by_account_id=submitted_by.id if submitted_by else None,
        submitted_on_behalf_of=on_behalf,
        public_name=public_name,
        role=role,
        location=location,
        message=message,
        link=link,
        hns_name=hns_name,
        status=status,
        verification_status=verification_status,
        verification_method=verification_method,
        verification_payload_private=verification_payload,
        verification_nonce=verification_nonce,
        source_channel=source_channel,
        source_note_private=_clean_text(request.form.get('source_note_private'), 1000, required=False) if admin_mode else None,
        consent_status=consent_status,
        admin_note_private=_clean_text(request.form.get('admin_note_private'), 1000, required=False) if admin_mode else None,
        badges_json=_clean_badges(request.form.get('badges')),
    )
    if status == 'approved':
        post.approved_at = datetime.utcnow()
        post.approved_by_account_id = submitted_by.id if submitted_by else None
    return post, []


def _update_post_from_admin_form(post, admin):
    errors = []
    public_name = _clean_text(request.form.get('public_name'), 120)
    role = _clean_text(request.form.get('role'), 80)
    message = _clean_text(request.form.get('message'), 700)
    link = _clean_url(request.form.get('link'), errors)
    hns_name = _clean_hns_name(request.form.get('hns_name'), errors, required=False)
    if not public_name:
        errors.append('Name or handle is required.')
    if not role:
        errors.append('Role is required.')
    if not message:
        errors.append('Message is required.')
    if errors:
        return errors

    old_status = post.status
    post.public_name = public_name
    post.role = role
    post.location = _clean_text(request.form.get('location'), 120, required=False)
    post.message = message
    post.link = link
    post.hns_name = hns_name
    post.status = request.form.get('status') if request.form.get('status') in POST_STATUSES else post.status
    post.verification_status = (
        request.form.get('verification_status')
        if request.form.get('verification_status') in VERIFICATION_STATUSES
        else post.verification_status
    )
    post.verification_method = _clean_text(request.form.get('verification_method'), 40, required=False)
    post.source_channel = (
        request.form.get('source_channel')
        if request.form.get('source_channel') in SOURCE_CHANNELS
        else post.source_channel
    )
    post.source_note_private = _clean_text(request.form.get('source_note_private'), 1000, required=False)
    post.consent_status = (
        request.form.get('consent_status')
        if request.form.get('consent_status') in CONSENT_STATUSES
        else post.consent_status
    )
    post.admin_note_private = _clean_text(request.form.get('admin_note_private'), 1000, required=False)
    post.badges_json = _clean_badges(request.form.get('badges'))
    if post.status == 'approved' and old_status != 'approved':
        post.approved_at = datetime.utcnow()
        post.approved_by_account_id = admin.id
    if post.status != 'approved' and old_status == 'approved':
        post.approved_at = None
        post.approved_by_account_id = None
    return []


def _public_payload(post):
    badges = list(post.badges_json or [])
    if post.verification_status == 'verified_hns_name' and 'Verified HNS name' not in badges:
        badges.append('Verified HNS name')
    elif post.verification_status == 'gfavip_logged_in' and 'GFAVIP account' not in badges:
        badges.append('GFAVIP account')
    elif post.verification_status == 'admin_attested' and post.submitted_on_behalf_of and 'Admin attested' not in badges:
        badges.append('Admin attested')

    return {
        'id': f'post_{post.id}',
        'name': post.public_name,
        'role': post.role,
        'location': post.location,
        'message': post.message,
        'link': post.link,
        'hnsName': post.hns_name,
        'badges': badges,
        'approvedAt': post.approved_at.isoformat() if post.approved_at else None,
    }


def _clean_text(value, max_length, required=True):
    text = ' '.join(str(value or '').strip().split())
    if not text and not required:
        return None
    return text[:max_length]


def _clean_url(value, errors):
    link = str(value or '').strip()
    if not link:
        return None
    parsed = urlparse(link)
    if parsed.scheme not in {'http', 'https'} or not parsed.netloc:
        errors.append('Link must be a valid http or https URL.')
        return None
    return link[:500]


def _clean_hns_name(value, errors, required=False):
    name = str(value or '').strip().lower().rstrip('/.')
    if not name:
        if required:
            errors.append('HNS name is required for TXT verification.')
        return None
    if len(name) > 255 or any(char.isspace() for char in name):
        errors.append('HNS name must be a single root name without spaces.')
        return None
    return name


def _clean_badges(value):
    raw_badges = str(value or '').split(',')
    badges = []
    for raw in raw_badges:
        badge = _clean_text(raw, 40, required=False)
        if badge and badge not in badges:
            badges.append(badge)
    return badges[:6]


def _find_account(lookup):
    normalized = lookup.strip()
    lowered = normalized.lower()
    return (
        Account.query.filter_by(gfavip_user_id=normalized).first()
        or Account.query.filter(db.func.lower(Account.email) == lowered).first()
        or Account.query.filter(db.func.lower(Account.username) == lowered).first()
    )
