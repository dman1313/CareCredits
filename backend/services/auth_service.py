import secrets
import time
from sqlalchemy.orm import Session

from models.account import Account
from models.session import LoginSession
from security import digest, password_hash
from backend.services.oauth_service import OAuthError


class AuthService:
    def __init__(self, db: Session):
        self.db = db

    def upsert_google_account(self, identity: dict, allow_create: bool) -> Account:
        """Links Google identity to existing account or creates new one."""
        issuer = 'https://accounts.google.com'
        subject = (identity.get('subject') or '').strip() or None
        
        account = None
        if subject:
            account = self.db.query(Account).filter_by(
                identity_issuer=issuer, identity_subject=subject
            ).first()
            
        if not account:
            account = self.db.query(Account).filter_by(email=identity['email']).first()
            
        if account:
            # Security: prevent subject hijacking on existing email
            if subject and account.identity_subject and account.identity_subject != subject:
                raise OAuthError('Google account does not match linked identity.', 401)
                
            # Link subject if previously unlinked
            if subject and not account.identity_subject:
                account.identity_issuer = issuer
                account.identity_subject = subject
            return account
            
        # Create new account
        if not allow_create:
            raise OAuthError('Registration is disabled.', 403)
            
        account = Account(
            email=identity['email'],
            name=identity['name'] or 'Doctor',
            password_hash=password_hash(secrets.token_urlsafe(32)),
            identity_issuer=issuer if subject else None,
            identity_subject=subject,
        )
        self.db.add(account)
        self.db.flush()
        return account

    def issue_session(self, account: Account, prior_token: str | None = None) -> str:
        """Creates new session and invalidates prior session for security."""
        if prior_token:
            self.db.query(LoginSession).filter_by(
                token_hash=digest(prior_token)
            ).delete()
            
        token = secrets.token_urlsafe(32)
        self.db.add(LoginSession(
            token_hash=digest(token),
            account_id=account.id,
            expires_at=time.time() + 28800
        ))
        self.db.commit()
        return token