import requests
from flask import current_app


def mailgun_api_url(path):
    region = current_app.config.get('MAILGUN_REGION', 'us')
    host = 'api.eu.mailgun.net' if region == 'eu' else 'api.mailgun.net'
    domain = current_app.config['MAILGUN_DOMAIN']
    return f'https://{host}/v3/{domain}/{path.lstrip("/")}'


def send_mailgun_email(to_email, subject, text, html=None, variables=None):
    api_key = current_app.config.get('MAILGUN_API_KEY')
    domain = current_app.config.get('MAILGUN_DOMAIN')
    if not api_key or not domain:
        raise RuntimeError('Mailgun is not configured')

    data = {
        'from': current_app.config['MAILGUN_FROM'],
        'to': to_email,
        'subject': subject,
        'text': text,
    }
    if html:
        data['html'] = html
    if variables:
        for key, value in variables.items():
            data[f'v:{key}'] = str(value)

    response = requests.post(
        mailgun_api_url('/messages'),
        auth=('api', api_key),
        data=data,
        timeout=15,
    )
    response.raise_for_status()
    return response.json()
