from web.app import app
print('safe_url_for exists:', 'safe_url_for' in app.jinja_env.globals)
print('sample:', app.jinja_env.globals['safe_url_for']('analytics_api.workforce_dashboard'))
