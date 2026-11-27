"""Cross-cutting building blocks (config, database session, security, errors, message contracts).

Any layer may import app.core; app.core never imports app.api, app.services,
app.repositories or app.integration (checked by .importlinter).
"""
