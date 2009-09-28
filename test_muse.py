import muse

test_app_api_key = "4fce3d843afa190fb41c60e8d2b41469"
test_app_secret = "70b33830655b8f1e7dadf9e43e67d3b6"

test_account_session_key = "360d81e8f278c89328c86084-219770"
test_account_session_secret = "93d6e352a907feb53461d711312491d3"

my_name = [{'name': 'Charlie Cheever'}]

def test_session_secret():
    fb = muse.Muse(test_app_api_key, None, test_account_session_key, test_account_session_secret)
    assert fb.api("fql.query", {"query": "SELECT name FROM user WHERE uid = 1160"}) == my_name

def test_session():
    fb = muse.Muse(test_app_api_key, test_app_secret, test_account_session_key)
    assert fb.api("fql.query", {"query": "SELECT name FROM user WHERE uid = 1160"}) == my_name

def test_no_session():
    fb = muse.Muse(test_app_api_key, test_app_secret)
    assert fb.api("fql.query", {"query": "SELECT name FROM user WHERE uid = 1160"}) == my_name
    
def test_bad_query():
    fb = muse.Muse(test_app_api_key, test_app_secret)
    try:
        fb.api("fql.query", {"query": "A BAD QUERY"})
        assert False
    except muse.FacebookAPIError:
        pass

def test_bad_network():
    fb = muse.Muse(test_app_api_key, test_app_secret)
    fb._domain = "0.0.0.0"
    try:
        fb.api("fql.query", {"query": "SELECT name FROM user WHERE uid = 1160"})
        assert False
    except muse.NetworkError:
        pass
        

def test_async():

    val = {}

    def cb(result, session, other_data):
        val["result"] = result
        val["session"] = session
        val["other_data"] = other_data

    fb = muse.Muse(test_app_api_key, test_app_secret)
    t = fb.api("fql.query", {"query": "SELECT name FROM user WHERE uid = 1160"}, callback=cb, other_data=47)
    t.join()

    assert val == {
        "result": my_name,
        "session": {
            "api_key": test_app_api_key,
            "app_secret": test_app_secret,
            "session_key": None,
            "session_secret": None,
        },
        "other_data": 47,
    }

def test_async_fail():
    failed = {}
    def fcb(error, session, other_data):
        failed["done"] = True

    fb = muse.Muse(test_app_api_key, test_app_secret)
    t = fb.api("fql.queryiorierer", {"query": "SELECT name FROM Luser WHERE uid = 1160"}, failure_callback=fcb)
    t.join()
    
    assert failed["done"]

def test_kwargs_call():
    fb = muse.Muse(test_app_api_key, test_app_secret)
    assert fb.api("fql.query", query="SELECT name FROM user WHERE uid = 1160") == my_name
