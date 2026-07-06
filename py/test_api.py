import urllib.request, urllib.error, json
try:
    r = urllib.request.urlopen('http://127.0.0.1:18520/api/attendance/month', timeout=30)
    d = json.loads(r.read())
    print('OK:', d.get('month_label','?'), 'days:', len(d.get('days',{})))
except urllib.error.HTTPError as e:
    body = e.read().decode()
    print('HTTP', e.code, ':', body[:500])
except Exception as e:
    print('Error:', e)
