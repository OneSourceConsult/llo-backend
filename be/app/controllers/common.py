from datetime import datetime
import time


def timeit(f):
    def timed(*args, **kw):
        ts = time.time()
        result = f(*args, **kw)
        te = time.time()
        print('func:%r args:[%r, %r] took: %.4f sec' % (f.__name__, args, kw, te-ts))
        return result
    return timed
    
    
def elapsedTime(date):
    start = datetime.strptime(date, "%Y-%m-%dT%H:%M:%SZ")
    t = int((datetime.now() - start).total_seconds())
    if (t < 60):
        return "%ss" % (t)
    elif (t // 3600 < 24):
        return "%sh" % (t // 3600)
    else:
        days = (t // 3600 // 24)
        return "%sd%sh" % (days, (t - days * 24 * 3600) // 3600)
