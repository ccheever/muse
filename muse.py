__doc__ = """
Muse (= Mu - Server Edition)

Muse is a Facebook Connect API client written in Python.  It is lightweight, 
small, and pretty transparent.  It leaves it up to you to manage your own
sessions, and it doesn't ever try to touch cookiesor anything like that.
It support asynchronous API calls, and its interface is pretty raw--you
explicitly specify the method name and all the parameters which means it
should support any future method added to the API seamlessly.

Muse isn't a great solution for making in-canvas Facebook apps since it 
doesn't provide much besides a server-side API.

Muse is a server-side complement and loose port of the Mu Facebook Connect 
client in JavaScript by Naitik Shah
    http://mu.daaku.org/
    http://github.com/nshah/mu

Example Usage:

    # Without a session
    In [1]: import muse
    In [2]: fb = muse.Muse("4fce3d843afa190fb41c60e8d2b41469", "70b33830655b8f1e7dadf9e43e67d3b6")
    In [3]: fb.api("fql.query", {"query": "SELECT name FROM user WHERE uid = 1160"})
    Out[3]: [{'name': 'Charlie Cheever'}]

    # With a session key and an app secret
    In [4]: fb = muse.Muse(api_key="4fce3d843afa190fb41c60e8d2b41469", app_secret="70b33830655b8f1e7dadf9e43e67d3b6", session_key="360d81e8f278c89328c86084-219770") 
    In [5]: fb.api("fql.query", {"query": "SELECT name FROM user WHERE uid = 1160"}) 
    Out[5]: [{'name': 'Charlie Cheever'}]

    # With a session key and a session secret
    In [2]: fb = muse.Muse(api_key="4fce3d843afa190fb41c60e8d2b41469", session_key="360d81e8f278c89328c86084-219770", session_secret="93d6e352a907feb53461d711312491d3")
    In [3]: fb.api("fql.query", {"query": "SELECT name FROM user WHERE uid = 1160"}) 
    Out[3]: [{'name': 'Charlie Cheever'}]

    # Extra keyword arguments will be treated as part of the params
    In [3]: fb.api("fql.query", query="SELECT name FROM user WHERE uid = 1160")
    Out[3]: [{'name': 'Charlie Cheever'}]


"""

__author__ = "ccheever" # Charlie Cheever
__date__ = "Sun Sep 27 18:40:03 PDT 2009"

import urllib
import urllib2
import time
import hashlib
import threading

# We don't want to use cjson since it has a bug where it doesn't handle
# '\/' correctly.  
#
# See: http://www.quora.com/q/Why_does_the_cjson_Python_module_not_correctly_unescape_reverse_solidus_solidus_
#
try:
    import simplejson as json
except ImportError:
    import json
json_encode = json.dumps
json_decode = json.loads
json_error = ValueError

MAX_CONCURRENT_API_CALLS = 4

_pool = threading.BoundedSemaphore(MAX_CONCURRENT_API_CALLS)

# urllib.quote_plus barfs on some Unicode chars so we encode in UTF-8
_urlencode = lambda x: urllib.quote_plus(("%s" % x).encode("utf-8"))

class MuseError(Exception):
    pass

class URLTooLongError(MuseError):
    pass

class FacebookAPIError(MuseError):
    pass

class NetworkError(MuseError):
    pass

class NoSecretError(MuseError):
    pass

class JSONError(MuseError):
    pass

class Muse(object):

    _scheme = "http"
    _domain = "api.facebook.com"
    _restserver  = "restserver.php"

    def __init__(self, api_key=None, app_secret=None, session_key=None, session_secret=None):
        self._api_key = api_key
        self._app_secret = app_secret
        self._session_key = session_key
        self._session_secret = session_secret

        # Use test account credentials if no API key is provided
        # This should make it easier to learn what's going on
        if api_key is None:
            import warnings
            warnings.warn("No API Key supplied.  Defaulting to test app API key and app secret.  You can use this to play around with the API but you *must* get your own API key to use with your app.  You can do this at: http://www.facebook.com/developers/createapp.php", stacklevel=2)
            self._api_key = "4fce3d843afa190fb41c60e8d2b41469"
            self._app_secret = "70b33830655b8f1e7dadf9e43e67d3b6"

        if not self._app_secret and not self._session_secret:
            raise NoSecretError("A client needs either either an app secret or a session secret to make API calls.")

    def session(self):
        """This returns a dict representing the session associated with this 
            client

            If you have information like expiration time and uid available,
            then you may want to override this method and include that
            information in the returned dict.
            
        """

        return {
            "api_key": self._api_key,
            "app_secret": self._app_secret,
            "session_key": self._session_key,
            "session_secret": self._session_secret,
        }


    def _sign(self, params):
        """Sign the given params and prepare them for an API call, either using
            an explicit secret or using the current session.  It updates the 
            given params dict *in place* with the necessary parameters

        """

        if self._session_secret:
            _secret = self._session_secret
            params["ss"] = 1

        elif self._app_secret:
            _secret = self._app_secret

        else:
            assert False, "There should always be either an app secret or a session secret associated with the client"

        if self._session_key:
            params["session_key"] = self._session_key

        params.update({
            "api_key": self._api_key,
            "call_id": str(int(time.time() * 1000000)),
            "format": "json",
            "v": "1.0",
        })

        params["sig"] = hashlib.md5(_sig_encode(params) + _secret).hexdigest()

        return params

    def api(self, method=None, params=None, callback=None, failure_callback=None, other_data=None, async=False, **kwargs):
        """Call an API method"""

        if params is None:
            params = {}
        else:
            # Clone params so callers don't have things they pass get mutated
            params = dict(params)

        # So we enable calling like fb.api("fql.query", query="SELECT ...)
        if kwargs:
            params.update(kwargs)

        if method is not None:
            params["method"] = method

        if callback or failure_callback:
            async = True

        url = self._json_url(params)

        if async:
            # TODO(ccheever): Fix this so we actually use the semaphore
            # properly
            t = APICallThread(url, self.session(), callback, other_data, failure_callback, _pool)
            t.start()
            return t
        else:
            return _fetch_json(url)


    def _json_url(self, params):
        """Returns the URL for making an API request that will return JSON"""

        params = self._sign(params)
        
        url = self._scheme + "://" + self._domain + "/" + self._restserver + "?" + _qs_encode(params)


        if len(url) > 2000:
            raise URLTooLongError("GET requests onl support a maximum of 2000 bytes of input")

        # TODO(ccheever): At some point, make this use POST for API
        # calls that are long.  We don't need this for now though.

        return url


def _qs_encode(params, sep="&"):
    """Encode parameters to a query string"""

    pairs = []
    for (k, v) in params.items():
        pairs.append(_urlencode(k) + "=" + _urlencode(v))
    pairs.sort()
    return sep.join(pairs)

def _sig_encode(params):
    """Encodes a set of params for computing the sig

        See description here:
        http://wiki.developers.facebook.com/index.php/Verifying_The_Signature
    
    """

    pairs = []
    for p in params.items():
        pairs.append("%s=%s" % p)
    pairs.sort()
    return "".join(pairs)

def _fetch_json(url):
    """Makes an HTTP GET request and returns the JSON decoded response body"""

    # We'll wrap all the networking errors here so that you can
    # catch MuseErrors and not worry about what is used to implement
    # the actual data fetching
    try:
        result = json_decode(urllib2.urlopen(url).read())
    except urllib2.URLError, e:
        raise NetworkError(e)
    except json_error, e:
        raise JSONError(e)

    # Since we're only using this to make FB API calls, we'll check for 
    # errors coming from there and raise an Error if appropriate
    if type(result) is dict and result.has_key("error_code"):
        raise FacebookAPIError(result["error_code"], result["error_msg"], result)
    return result


class APICallThread(threading.Thread):
    """A Thread that makes an API call and calls a callback with the results

    The callback that you pass in will be called like this:
        callback(result, session, other_data)

    If the call fails, the failure_callback will be called like this:
        failure_callback(error, session, other_data)

    callback, other_data, and failure_callback are all optional
    
    """
    
    def __init__(self, url, session, callback=None, other_data=None, failure_callback=None, pool=None):
        threading.Thread.__init__(self)
        self._session = session
        self._url = url
        self._callback = callback
        self._other_data = other_data
        self._failure_callback = failure_callback

        # The easiest way to handle the case where the caller doesn't want
        # to draw from any pool is just to create our own on the fly
        if pool is None:
            self._pool = threading.Semaphore()
        else:
            self._pool = pool

    def run(self):
        with self._pool:
            try:
                result = _fetch_json(self._url)
                if self._callback:
                    self._callback(result, self._session, self._other_data)
            except MuseError, e:
                if self._failure_callback:
                    self._failure_callback(e, self._session, self._other_data)
                else:
                    raise e

