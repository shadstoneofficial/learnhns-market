from flask import Blueprint, render_template, request
from app.models import Listing

main_bp = Blueprint('main', __name__)

@main_bp.route('/')
def index():
    query = request.args.get('q', '')
    min_price = request.args.get('min_price')
    # Basic active listings query
    listings = Listing.query.filter_by(status='active').order_by(Listing.created_at.desc()).all()
    return render_template('index.html', listings=listings)

@main_bp.route('/listing/<name>')
def listing_detail(name):
    listing = Listing.query.filter_by(name=name, status='active').first_or_404()
    return render_template('listing.html', listing=listing)
