"""
Azure AD OAuth2 backend, docs at:
    http://psa.matiasaguirre.net/docs/backends/azuread.html
"""
import datetime
from calendar import timegm
from social.exceptions import AuthException, AuthFailed, AuthCanceled, \
                              AuthUnknownError, AuthMissingParameter, \
                              AuthTokenError

from social.backends.oauth import BaseOAuth2
from social.backends.open_id import OpenIdAuth, OpenIdConnectAuth
import urllib
from jwt import DecodeError, ExpiredSignature, decode as jwt_decode

class AzureADOAuth2(BaseOAuth2):
    name = 'azuread-oauth2'
    SCOPE_SEPARATOR = ' '
    AUTHORIZATION_URL = 'https://login.windows.net/common/oauth2/authorize'
    ACCESS_TOKEN_URL = 'https://login.windows.net/common/oauth2/token'
    ACCESS_TOKEN_METHOD = 'POST'
    REDIRECT_STATE = False
    DEFAULT_SCOPE = ['openid', 'profile', 'user_impersonation']
    EXTRA_DATA = [
        ('access_token', 'access_token'),
        ('id_token', 'id_token'),
        ('refresh_token', 'refresh_token'),
        ('expires_in', 'expires'),
        ('given_name', 'first_name'),
        ('family_name', 'last_name'),
        ('token_type', 'token_type')
    ]

    def auth_extra_arguments(self):
        """Return extra arguments needed on auth process. The defaults can be
        overriden by GET parameters."""
        extra_arguments = {
            'resource': self.setting('SHAREPOINT_SITE')
        }
        return extra_arguments

    def get_user_id(self, details, response):
        """Use upn as unique id"""
        print 'get_user_id'
        print response.get('upn')
        return response.get('upn')

    def get_user_details(self, response):
        print 'get_user_details'
        
        """Return user details from Azure AD account"""
        fullname, first_name, last_name = (
            response.get('name', ''),
            response.get('given_name', ''),
            response.get('family_name', '')
        )
        return {'username': fullname,
                'email': response.get('upn'),
                'fullname': fullname,
                'first_name': first_name,
                'last_name': last_name}

    def user_data(self, access_token, *args, **kwargs):
        print 'user_data'
        response = kwargs.get('response')
        id_token = response.get('id_token')
        
        try:
            decoded_id_token = jwt_decode(id_token, verify=False)
        except (DecodeError, ExpiredSignature) as de:
            raise AuthTokenError(self, de)
        
        return decoded_id_token

    def extra_data(self, user, uid, response, details=None):
        """Return access_token and extra defined names to store in
        extra_data field"""
        data = super(BaseOAuth2, self).extra_data(user, uid, response, details)
        data['sharepoint_site'] = self.setting('SHAREPOINT_SITE')
        return data

class AzureADOpenIDConnect(AzureADOAuth2, OpenIdConnectAuth):

    name = 'azuread-openidconnect'
    DEFAULT_SCOPE = ['openid']
    ID_TOKEN_ISSUER = 'https://sts.windows.net/ec02513e-fec1-4bac-af12-d76197b80939/'

    def user_data(self, access_token, *args, **kwargs):
        print 'user_data'
        response = kwargs.get('response')
        id_token = response.get('id_token')

        try:
            decoded_id_token = jwt_decode(id_token, verify=False)
        except (DecodeError, ExpiredSignature) as de:
            raise AuthTokenError(self, de)

        return decoded_id_token

    def validate_and_return_id_token(self, id_token):
        """
        Validates the id_token according to the steps at
        http://openid.net/specs/openid-connect-core-1_0.html#IDTokenValidation.
        """
        client_id, _client_secret = self.get_key_and_secret()
        try:
            # Decode the JWT and raise an error if the secret is invalid or
            # the response has expired.
            id_token = jwt_decode(id_token,  verify=False)
        except (DecodeError, ExpiredSignature) as de:
            raise AuthTokenError(self, de)

        # Verify the issuer of the id_token is correct
        if id_token['iss'] != self.ID_TOKEN_ISSUER:
            raise AuthTokenError(self, 'Incorrect id_token: iss')

        # Verify the token was issued in the last 10 minutes
        utc_timestamp = timegm(datetime.datetime.utcnow().utctimetuple())
        if id_token['iat'] < (utc_timestamp - 600):
            raise AuthTokenError(self, 'Incorrect id_token: iat')

        # Verify this client is the correct recipient of the id_token
        aud = id_token.get('aud')
        if aud != client_id:
            raise AuthTokenError(self, 'Incorrect id_token: aud')

        return id_token

